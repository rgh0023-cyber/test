import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面基本配置
st.set_page_config(page_title="Tripeaks 审计系统 V1.5.2", layout="wide")
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.5.2")

# --- 核心统计函数 ---
def calculate_trimmed_stats(series, trim_percentage):
    if len(series) < 5: return series.mean(), series.var()
    sorted_series = np.sort(series)
    n = len(sorted_series)
    trim_count = int(n * (trim_percentage / 100))
    if trim_count == 0: return series.mean(), series.var()
    trimmed_data = sorted_series[trim_count : n - trim_count]
    return np.mean(trimmed_data), np.var(trimmed_data)

# --- 核心审计引擎 ---
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

    # A. 加分
    if sum(seq[:3]) >= 4: score += 5; reasons.append("开局破冰(+5)")
    if any(x >= 3 for x in seq[-5:]): score += 5; reasons.append("尾部收割(+5)")
    if len(seq) >= 7 and max(seq) in seq[6:]: score += 5; reasons.append("逆风翻盘(+5)")

    # B. 贫瘠区与接力
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    boundaries = [-1] + eff_idx + [len(seq)]
    c1, c2, c3, relay = 0, 0, 0, 0
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
            if 0 < j < len(boundaries) - 1 and L <= 1: relay += 1

    if relay >= 3: score += 10; reasons.append(f"接力x{relay}(+10)")
    elif relay == 2: score += 7; reasons.append("接力x2(+7)")
    elif relay == 1: score += 5; reasons.append("接力x1(+5)")

    # C. 投喂项 (互斥分级)
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
        elif fl == 4: f1 += 1; score -= 3; reasons.append("L1投喂(4连/-3)")

    # D. 红线判定
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if max(seq) < 3: red_tags.append("全局枯竭")
    if (difficulty <= 30 and "失败" in actual_result) or (difficulty >= 40 and "胜利" in actual_result):
        red_tags.append("逻辑违逆")
    
    red_label = ",".join(red_tags) if red_tags else "无"
    status = "通过" if not red_tags and score >= 50 else "拒绝"
    return score, status, red_label, " | ".join(reasons), c1, c2, c3, relay, f1, f2

# --- 2. 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 全局配置")
    init_val = st.slider("初始基准分", 0, 100, 60)
    trim_val = st.slider("截断比例 (%)", 0, 25, 10)
    uploaded_file = st.file_uploader("📂 上传跑关数据", type=["xlsx", "csv"])

# --- 3. 主逻辑区域 ---
if uploaded_file:
    # A. 数据加载与审计
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    with st.spinner('审计计算中...'):
        results = df.apply(lambda r: pd.Series(audit_engine(r, init_val)), axis=1)
        df[['得分', '审计结果', '红线详情', '构成', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = results

    # B. 聚合排行榜
    st.subheader(f"📊 解集排行榜 (截断比例: {trim_val}%)")
    summary = []
    for (jid, diff), gp in df.groupby(['解集ID', '难度']):
        t_mean, t_var = calculate_trimmed_stats(gp['得分'], trim_val)
        red_rate = (gp['红线详情'] != "无").mean()
        summary.append({
            "解集ID": jid, "难度": diff, "μ_截断均值": t_mean, "σ2_截断方差": t_var, "红线率": red_rate,
            "3级均": gp['c3'].mean(), "2级均": gp['c2'].mean(), "1级均": gp['c1'].mean(),
            "L2投喂均": gp['f2'].mean(), "接力均": gp['接力'].mean(),
            "准入": "✅ 准入" if t_mean >= 50 and t_var <= 15 and red_rate < 0.15 else "❌ 拒绝"
        })
    sum_df = pd.DataFrame(summary)
    st.dataframe(sum_df.style.background_gradient(cmap='RdYlGn', subset=['μ_截断均值']).format({"红线率":"{:.1%}", "μ_截断均值":"{:.2f}", "σ2_截断方差":"{:.2f}"}), use_container_width=True)

    # C. 增强型筛选器交互区
    st.divider()
    st.subheader("🔍 高级结果筛选器")
    
    # 第一排筛选：状态、难度、红线
    r1_c1, r1_c2, r1_c3 = st.columns([2, 2, 1])
    with r1_c1:
        f_status = st.multiselect("审计状态", options=df['审计结果'].unique(), default=df['审计结果'].unique())
    with r1_c2:
        f_diff = st.multiselect("难度选择", options=sorted(df['难度'].unique()), default=sorted(df['难度'].unique()))
    with r1_c3:
        show_red_only = st.checkbox("仅看红线轮次")

    # 第二排筛选：解集ID (牌集ID)
    all_jids = sorted(df['解集ID'].unique())
    f_jids = st.multiselect("牌集 ID 筛选", options=all_jids, default=all_jids, help="支持多选或搜索特定ID")

    # 执行综合筛选逻辑
    mask = (df['审计结果'].isin(f_status)) & (df['难度'].isin(f_diff)) & (df['解集ID'].isin(f_jids))
    filtered_df = df[mask]
    if show_red_only:
        filtered_df = filtered_df[filtered_df['红线详情'] != "无"]

    # D. 明细展示 (包含原始序列字段)
    st.write(f"当前筛选条件下共有 **{len(filtered_df)}** 条记录：")
    
    # 调整列顺序，将原始序列放到显眼位置
    display_cols = [
        '解集ID', '难度', '实际结果', '得分', '审计结果', '红线详情', 
        '全部连击（每张手牌的连击数）', '构成'
    ]
    
    st.dataframe(filtered_df[display_cols], use_container_width=True)

    # E. 导出
    st.download_button("📥 导出筛选后的审计结果", filtered_df.to_csv(index=False).encode('utf_8_sig'), "Audit_Filtered_Detail.csv")
else:
    st.info("💡 请上传数据以激活审计面板。")
