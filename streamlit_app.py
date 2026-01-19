import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面基本配置
st.set_page_config(page_title="Tripeaks 审计系统 V1.6.1", layout="wide")
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.6.1")
st.info("已恢复全部基础审计标准：含开局破冰、尾部收割、逆风翻盘及全量贫瘠区统计。")

# --- 核心统计函数 ---
def calculate_advanced_stats(series, trim_percentage):
    if len(series) < 5: 
        m = series.mean()
        v = series.var()
        return m, v, (np.sqrt(v)/m if m > 0 else 0)
    sorted_series = np.sort(series)
    n = len(sorted_series)
    trim_count = int(n * (trim_percentage / 100))
    trimmed_data = sorted_series[trim_count : n - trim_count] if trim_count > 0 else sorted_series
    mu = np.mean(trimmed_data)
    var = np.var(trimmed_data)
    cv = (np.sqrt(var) / mu) if mu > 0 else 0
    return mu, var, cv

# --- 核心审计引擎 (严格保留基础标准) ---
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

    # === A. 基础加分项 (严禁修改) ===
    # 1. 开局破冰：前3张手牌累积连击>=4
    if sum(seq[:3]) >= 4: 
        score += 5
        reasons.append("开局破冰(+5)")
    # 2. 尾部收割：最后5张手牌中有连击>=3
    if any(x >= 3 for x in seq[-5:]): 
        score += 5
        reasons.append("尾部收割(+5)")
    # 3. 逆风翻盘：第7张手牌后出现全局最高连击
    if len(seq) >= 7 and max(seq) in seq[6:]: 
        score += 5
        reasons.append("逆风翻盘(+5)")

    # === B. 连击接力 (方案 A: 关系链接) ===
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    relay_count = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx) - 1):
            if (eff_idx[i+1] - eff_idx[i] - 1) <= 1: 
                relay_count += 1
    if relay_count >= 3: score += 10; reasons.append(f"接力x{relay_count}(+10)")
    elif relay_count == 2: score += 7; reasons.append(f"接力x{relay_count}(+7)")
    elif relay_count == 1: score += 5; reasons.append("接力x1(+5)")

    # === C. 贫瘠区分析 (全量分级累计) ===
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

    # === D. 投喂项分析 (分级累计 & 红线) ===
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
        elif 5 <= fl <= 6: f2 += 1; score -= 9; reasons.append(f"L2投喂({fl}连/-9)")
        elif fl == 4: f1 += 1; score -= 3; reasons.append(f"L1投喂(4连/-3)")

    # === E. 红线判定 ===
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (difficulty <= 30 and "失败" in actual_result) or (difficulty >= 40 and "胜利" in actual_result):
        red_tags.append("逻辑违逆")
    
    red_label = ",".join(red_tags) if red_tags else "无"
    status = "通过" if not red_tags and score >= 50 else "拒绝"
    return score, status, red_label, " | ".join(reasons), c1, c2, c3, relay_count, f1, f2

# --- 2. 侧边栏及上传 ---
with st.sidebar:
    st.header("⚙️ 准入阈值设置")
    init_val = st.slider("基础及格分", 0, 100, 50)
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大变异系数 (CV)", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差保护值", 10, 50, 25)
    uploaded_file = st.file_uploader("📂 上传跑关数据", type=["xlsx", "csv"])

# --- 3. 数据处理与排行展示 ---
if uploaded_file:
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    with st.spinner('执行全量标准审计...'):
        res = df.apply(lambda r: pd.Series(audit_engine(r, init_val)), axis=1)
        df[['得分', '审计结果', '红线详情', '构成', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = res

    # 聚合排行 (使用 CV 稳定性判定)
    st.subheader("📊 解集稳定性排行榜 (基于 CV 及 1.6.1 标准)")
    summary = []
    for (jid, diff), gp in df.groupby(['解集ID', '难度']):
        mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
        red_rate = (gp['红线详情'] != "无").mean()
        is_pass = mu >= init_val and (cv <= cv_limit or var <= var_limit) and red_rate < 0.15
        
        summary.append({
            "解集ID": jid, "难度": diff, "μ_均值": mu, "CV_变异系数": cv, "σ2_方差": var, 
            "红线率": red_rate, "3级均": gp['c3'].mean(), "2级均": gp['c2'].mean(), 
            "L2均": gp['f2'].mean(), "接力均": gp['接力'].mean(),
            "准入判定": "✅ 准入" if is_pass else "❌ 拒绝"
        })
    
    sum_df = pd.DataFrame(summary)
    st.dataframe(sum_df.style.background_gradient(cmap='RdYlGn', subset=['μ_均值', 'CV_变异系数']).format({
        "红线率":"{:.1%}", "μ_均值":"{:.2f}", "σ2_方差":"{:.2f}", "CV_变异系数":"{:.3f}"
    }), use_container_width=True)

    # 筛选器
    st.divider()
    st.subheader("🔍 结果明细筛选器")
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1: f_status = st.multiselect("审计状态", options=df['审计结果'].unique(), default=df['审计结果'].unique())
    with c2: f_diff = st.multiselect("难度筛选", options=sorted(df['难度'].unique()), default=sorted(df['难度'].unique()))
    with c3: show_red = st.checkbox("仅看红线")
    f_jids = st.multiselect("解集 ID 筛选", options=sorted(df['解集ID'].unique()), default=sorted(df['解集ID'].unique()))

    mask = (df['审计结果'].isin(f_status)) & (df['难度'].isin(f_diff)) & (df['解集ID'].isin(f_jids))
    f_df = df[mask]
    if show_red: f_df = f_df[f_df['红线详情'] != "无"]

    st.dataframe(f_df[['解集ID', '难度', '得分', '审计结果', '红线详情', '全部连击（每张手牌的连击数）', '构成']], use_container_width=True)
