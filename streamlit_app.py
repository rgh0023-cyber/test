import streamlit as st
import pandas as pd
import numpy as np

# 页面配置
st.set_page_config(page_title="Tripeaks 审计系统 V1.6.0", layout="wide")
st.title("🎴 Tripeaks 关卡审计 V1.6.0 (CV 稳定性版)")

# --- 核心统计函数：计算截断均值、方差及CV ---
def calculate_advanced_stats(series, trim_percentage):
    if len(series) < 5: 
        m = series.mean()
        v = series.var()
        return m, v, (np.sqrt(v)/m if m > 0 else 0)
    
    sorted_series = np.sort(series)
    n = len(sorted_series)
    trim_count = int(n * (trim_percentage / 100))
    # 执行截断
    trimmed_data = sorted_series[trim_count : n - trim_count] if trim_count > 0 else sorted_series
    
    mu = np.mean(trimmed_data)
    var = np.var(trimmed_data)
    cv = (np.sqrt(var) / mu) if mu > 0 else 0
    return mu, var, cv

# --- 审计引擎 (保留 V1.5.4 核心扣分逻辑) ---
def audit_engine(row, init_score):
    try:
        seq_raw = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']
        difficulty = row['难度']
        actual_result = str(row['实际结果'])
    except: return 0, "拒绝", "解析失败", "", 0, 0, 0, 0, 0, 0

    score = init_score
    reasons = []

    # 1. 连击接力 (方案 A)
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    relay_count = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx) - 1):
            if (eff_idx[i+1] - eff_idx[i] - 1) <= 1: relay_count += 1
    
    if relay_count >= 3: score += 10; reasons.append(f"接力x{relay_count}(+10)")
    elif relay_count == 2: score += 7; reasons.append(f"接力x2(+7)")
    elif relay_count == 1: score += 5; reasons.append(f"接力x1(+5)")

    # 2. 贫瘠区 (全量累计)
    boundaries = [-1] + eff_idx + [len(seq)]
    c1, c2, c3 = 0, 0, 0
    for j in range(len(boundaries) - 1):
        start, end = boundaries[j] + 1, boundaries[j+1]
        inter = seq[start:end]
        if len(inter) > 0:
            L, Z = len(inter), inter.count(0)
            if L >= 6 or (L >= 4 and Z >= 3):
                c3 += 1; p = -25 if start <= 2 else -20
                score += p; reasons.append(f"3级枯竭({p})")
            elif L == 5 or (3 <= L <= 4 and Z == 2):
                c2 += 1; score -= 9; reasons.append("2级阻塞(-9)")
            elif L >= 3:
                c1 += 1; score -= 5; reasons.append("1级平庸(-5)")

    # 3. 投喂项 & 红线
    f1, f2, red_auto = 0, 0, False
    con_list = []
    cur = 0
    for x in seq:
        if x > 0: cur += 1
        else:
            if cur > 0: con_list.append(cur)
            cur = 0
    if cur > 0: con_list.append(cur)
    for fl in con_list:
        if fl >= 7: red_auto = True
        elif 5 <= fl <= 6: f2 += 1; score -= 9; reasons.append(f"L2投喂({fl}连)")
        elif fl == 4: f1 += 1; score -= 3; reasons.append("L1投喂(4连)")

    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (difficulty <= 30 and "失败" in actual_result) or (difficulty >= 40 and "胜利" in actual_result):
        red_tags.append("逻辑违逆")
    
    red_label = ",".join(red_tags) if red_tags else "无"
    status = "通过" if not red_tags and score >= 50 else "拒绝"
    return score, status, red_label, " | ".join(reasons), c1, c2, c3, relay_count, f1, f2

# --- UI 面板 ---
with st.sidebar:
    st.header("⚙️ 准入阈值设置")
    init_val = st.slider("基础分", 0, 100, 50)
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大变异系数 (CV)", 0.05, 0.50, 0.20, step=0.01)
    var_limit = st.slider("最大方差保护值", 10, 50, 25)
    uploaded_file = st.file_uploader("📂 上传跑关数据", type=["xlsx", "csv"])

if uploaded_file:
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    with st.spinner('正在进行 CV 稳定性审计...'):
        results = df.apply(lambda r: pd.Series(audit_engine(r, init_val)), axis=1)
        df[['得分', '审计结果', '红线详情', '构成', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = results

    # 排行榜计算
    st.subheader("📊 解集稳定性排行榜")
    summary = []
    for (jid, diff), gp in df.groupby(['解集ID', '难度']):
        mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
        red_rate = (gp['红线详情'] != "无").mean()
        
        # 准入条件：均值达标 & (CV达标 或 方差极小) & 红线率低
        is_pass = mu >= init_val and (cv <= cv_limit or var <= var_limit) and red_rate < 0.15
        
        summary.append({
            "牌集ID": jid, "难度": diff, "μ_截断均值": mu, "CV_变异系数": cv, "σ2_方差": var, 
            "红线率": red_rate, "准入判定": "✅ 准入" if is_pass else "❌ 拒绝"
        })
    
    sum_df = pd.DataFrame(summary)
    st.dataframe(sum_df.style.background_gradient(cmap='RdYlGn', subset=['μ_截断均值', 'CV_变异系数']).format({
        "红线率":"{:.1%}", "μ_截断均值":"{:.2f}", "σ2_方差":"{:.2f}", "CV_变异系数":"{:.3f}"
    }), use_container_width=True)

    # 详细筛选与流水 (省略重复UI代码...)
    st.divider()
    st.write("### 🔍 明细流水")
    st.dataframe(df[['解集ID', '难度', '得分', '审计结果', '红线详情', '全部连击（每张手牌的连击数）', '构成']], use_container_width=True)
