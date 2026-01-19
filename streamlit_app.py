import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面配置
st.set_page_config(page_title="Tripeaks 审计系统 V1.7.5", layout="wide")
st.title("🎴 Tripeaks 关卡审计系统 V1.7.5 (纯净统计版)")

# --- 核心统计函数 ---
def calculate_advanced_stats(series, trim_percentage):
    if len(series) < 5: 
        m = series.mean(); v = series.var()
        return m, v, (np.sqrt(v)/m if m > 0 else 0)
    sorted_s = np.sort(series)
    n = len(sorted_s)
    trim = int(n * (trim_percentage / 100))
    # 截断两端
    trimmed = sorted_s[trim : n - trim] if trim > 0 else sorted_s
    mu, var = np.mean(trimmed), np.var(trimmed)
    cv = (np.sqrt(var) / mu) if mu > 0 else 0
    return mu, var, cv

# --- 核心审计引擎 ---
def audit_engine(row, base_init_score):
    try:
        seq_raw = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']; diff = row['难度']; actual = str(row['实际结果'])
    except: return 0, "无", "解析失败", "", 0, 0, 0, 0

    # 1. 计算得分：基准分 + 正向 - 负向
    score = base_init_score
    reasons = []

    # A. 正向体验项
    if sum(seq[:3]) >= 4: score += 5; reasons.append("破冰(+5)")
    if any(x >= 3 for x in seq[-5:]): score += 5; reasons.append("收割(+5)")
    if len(seq) >= 7 and max(seq) in seq[6:]: score += 5; reasons.append("翻盘(+5)")

    # B. 连击接力 (方案 A)
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    relay = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx)-1):
            if (eff_idx[i+1]-eff_idx[i]-1) <= 1: relay += 1
    if relay >= 3: score += 10; reasons.append(f"接力x{relay}(+10)")
    elif relay == 2: score += 7; reasons.append(f"接力x2(+7)")
    elif relay == 1: score += 5; reasons.append("接力x1(+5)")

    # C. 负向体验项 (贫瘠区全量扣分)
    boundaries = [-1] + eff_idx + [len(seq)]
    c1, c2, c3 = 0, 0, 0
    for j in range(len(boundaries)-1):
        start, end = boundaries[j]+1, boundaries[j+1]
        inter = seq[start:end]
        if inter:
            L, Z = len(inter), inter.count(0)
            if L >= 6 or (L >= 4 and Z >= 3):
                c3 += 1; p = -25 if start <= 2 else -20
                score += p; reasons.append(f"3级枯竭({p})")
            elif L == 5 or (3 <= L <= 4 and Z == 2):
                c2 += 1; score -= 9; reasons.append("2级阻塞(-9)")
            elif L >= 3:
                c1 += 1; score -= 5; reasons.append("1级平庸(-5)")

    # D. 投喂项扣分与自动化判定
    red_auto = False
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
        elif 5 <= fl <= 6: score -= 9; reasons.append(f"L2投喂(-9)")
        elif fl == 4: score -= 3; reasons.append(f"L1投喂(-3)")

    # E. 红线判定
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (diff <= 30 and "失败" in actual) or (diff >= 40 and "胜利" in actual): red_tags.append("逻辑违逆")
    
    red_label = ",".join(red_tags) if red_tags else "无"
    return score, "通过", red_label, " | ".join(reasons), c1, c2, c3, relay

# --- 2. 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 审计参数")
    base_init_score = st.slider("审计初始分 (Base)", 0, 100, 60)
    mu_threshold = st.slider("准入及格分 (μ门槛)", 0, 100, 70)
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    
    st.divider()
    st.header("⚖️ 稳定性控制")
    cv_limit = st.slider("最大变异系数 (CV)", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差保护值", 10, 100, 25)
    
    uploaded_file = st.file_uploader("📂 上传跑关数据", type=["xlsx", "csv"])

# --- 3. 核心计算与结果展示 ---
if uploaded_file:
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    with st.spinner('审计统计中...'):
        res = df.apply(lambda r: pd.Series(audit_engine(r, base_init_score)), axis=1)
        df[['得分', '状态', '红线详情', '构成', 'c1', 'c2', 'c3', '接力']] = res

    # === 第一部分：解集排行榜 (核心判定区) ===
    st.subheader("📊 解集审计排行榜 (基于截断统计)")
    
    # 统计筛选
    status_filter = st.radio("准入结果过滤：", ["全部", "通过", "拒绝"], horizontal=True)

    summary = []
    for (jid, diff), gp in df.groupby(['解集ID', '难度']):
        mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
        red_rate = (gp['红线详情'] != "无").mean()
        
        # 判定准入：均值、稳定性、红线率
        is_pass = mu >= mu_threshold and (cv <= cv_limit or var <= var_limit) and red_rate < 0.15
        pass_status = "通过" if is_pass else "拒绝"
        
        if status_filter == "全部" or status_filter == pass_status:
            all_reds = ",".join(gp['红线详情']).split(",")
            summary.append({
                "解集ID": jid, "难度": diff, "μ_截断均值": mu, "Min_最低": gp['得分'].min(), 
                "CV_变异系数": cv, "σ2_方差": var, "红线率": red_rate,
                "准入判定": "✅ 通过" if is_pass else "❌ 拒绝",
                "数值崩坏%": all_reds.count("数值崩坏") / len(gp),
                "自动化%": all_reds.count("自动化局") / len(gp),
                "逻辑违逆%": all_reds.count("逻辑违逆") / len(gp)
            })
    
    if summary:
        sum_df = pd.DataFrame(summary)
        st.dataframe(sum_df.style.background_gradient(cmap='RdYlGn', subset=['μ_截断均值'])
                     .background_gradient(cmap='YlOrRd', subset=['CV_变异系数', '红线率'])
                     .format({
                         "红线率":"{:.1%}", "数值崩坏%":"{:.1%}", "自动化%":"{:.1%}", 
                         "逻辑违逆%":"{:.1%}", "μ_截断均值":"{:.2f}", "CV_变异系数":"{:.3f}", "σ2_方差":"{:.2f}"
                     }), use_container_width=True)
    else:
        st.warning("暂无匹配数据")

    # === 第二部分：明细流水 ===
    st.divider()
    st.subheader("🔍 详细单局得分流水")
    st.dataframe(df[['解集ID', '难度', '得分', '红线详情', '构成', '全部连击（每张手牌的连击数）']], use_container_width=True)
