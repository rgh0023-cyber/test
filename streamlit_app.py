import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面配置
st.set_page_config(page_title="Tripeaks 审计系统 V1.6.3", layout="wide")
st.title("🎴 Tripeaks 关卡审计系统 V1.6.3")

# --- 核心统计函数 ---
def calculate_advanced_stats(series, trim_percentage):
    if len(series) < 5: 
        m = series.mean(); v = series.var()
        return m, v, (np.sqrt(v)/m if m > 0 else 0)
    sorted_s = np.sort(series)
    n = len(sorted_s)
    trim = int(n * (trim_percentage / 100))
    trimmed = sorted_s[trim : n - trim] if trim > 0 else sorted_s
    mu, var = np.mean(trimmed), np.var(trimmed)
    return mu, var, (np.sqrt(var) / mu) if mu > 0 else 0

# --- 审计引擎 ---
def audit_engine(row, init_score):
    try:
        seq_raw = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']; diff = row['难度']; actual = str(row['实际结果'])
    except: return 0, "拒绝", "解析失败", "", 0, 0, 0, 0, 0, 0

    score = init_score
    reasons = []
    # A. 基础加分
    if sum(seq[:3]) >= 4: score += 5; reasons.append("破冰")
    if any(x >= 3 for x in seq[-5:]): score += 5; reasons.append("收割")
    if len(seq) >= 7 and max(seq) in seq[6:]: score += 5; reasons.append("翻盘")
    # B. 接力
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    relay = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx)-1):
            if (eff_idx[i+1]-eff_idx[i]-1) <= 1: relay += 1
    if relay >= 3: score += 10; reasons.append(f"接力x{relay}")
    elif relay == 2: score += 7; reasons.append(f"接力x2")
    elif relay == 1: score += 5; reasons.append("接力x1")
    # C. 贫瘠区
    boundaries = [-1] + eff_idx + [len(seq)]
    c1, c2, c3 = 0, 0, 0
    for j in range(len(boundaries)-1):
        start, end = boundaries[j]+1, boundaries[j+1]
        inter = seq[start:end]
        if inter:
            L, Z = len(inter), inter.count(0)
            if L >= 6 or (L >= 4 and Z >= 3): c3 += 1; score -= 20; reasons.append("3级")
            elif L == 5 or (3 <= L <= 4 and Z == 2): c2 += 1; score -= 9; reasons.append("2级")
            elif L >= 3: c1 += 1; score -= 5; reasons.append("1级")
    # D. 投喂 & 红线
    f1, f2, red_auto = 0, 0, False
    con_list = []
    cur = 0
    for x in seq:
        if x > 0: cur += 1
        else:
            if cur > 0: con_list.append(cur); 
            cur = 0
    if cur > 0: con_list.append(cur)
    for fl in con_list:
        if fl >= 7: red_auto = True
        elif 5 <= fl <= 6: f2 += 1; score -= 9; reasons.append("L2投喂")
        elif fl == 4: f1 += 1; score -= 3; reasons.append("L1投喂")
    
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (diff <= 30 and "失败" in actual) or (diff >= 40 and "胜利" in actual): red_tags.append("逻辑违逆")
    
    red_label = ",".join(red_tags) if red_tags else "无"
    status = "通过" if not red_tags and score >= 50 else "拒绝"
    return score, status, red_label, " | ".join(reasons), c1, c2, c3, relay, f1, f2

# --- 2. 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 核心参数")
    init_val = st.slider("及格分", 0, 100, 50)
    trim_val = st.slider("截断比例", 0, 30, 15)
    cv_limit = st.slider("CV 阈值", 0.05, 0.50, 0.20)
    var_limit = st.slider("方差保护", 10, 50, 25)
    uploaded_file = st.file_uploader("📂 上传数据", type=["xlsx", "csv"])

# --- 3. 主页面 ---
if uploaded_file:
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    with st.spinner('审计中...'):
        res = df.apply(lambda r: pd.Series(audit_engine(r, init_val)), axis=1)
        df[['得分', '审计结果', '红线详情', '构成', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = res

    # === 第一部分：全局筛选与红线分布统计 ===
    st.subheader("🎯 审计准入与红线分布分析")
    status_filter = st.radio("全局状态筛选：", ["全部", "通过", "拒绝"], horizontal=True)

    # 预计算所有解集的排行榜数据
    summary = []
    for (jid, diff), gp in df.groupby(['解集ID', '难度']):
        mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
        red_rate = (gp['红线详情'] != "无").mean()
        is_pass = mu >= init_val and (cv <= cv_limit or var <= var_limit) and red_rate < 0.15
        
        # 统计各类红线在该解集内部出现的比例
        all_reds = ",".join(gp['红线详情']).split(",")
        summary.append({
            "解集ID": jid, "难度": diff, "μ_均值": mu, "CV": cv, "σ2": var, 
            "红线率": red_rate, "审计判定": "通过" if is_pass else "拒绝",
            "数值崩坏%": all_reds.count("数值崩坏") / len(gp),
            "自动化%": all_reds.count("自动化局") / len(gp),
            "逻辑违逆%": all_reds.count("逻辑违逆") / len(gp),
            "分值过低%": (gp['得分'] < init_val).mean()
        })
    
    sum_df = pd.DataFrame(summary)
    
    # 执行筛选显示
    if status_filter != "全部":
        disp_df = sum_df[sum_df['审计判定'] == status_filter]
    else:
        disp_df = sum_df

    # --- 显示红线详细比例表 ---
    st.write(f"当前筛选条件下共有 **{len(disp_df)}** 个解集：")
    
    # 定义列展示与格式
    cols_to_show = ["解集ID", "难度", "μ_均值", "CV", "σ2", "审计判定", "红线率", "数值崩坏%", "自动化%", "逻辑违逆%", "分值过低%"]
    
    st.dataframe(disp_df[cols_to_show].style.background_gradient(cmap='YlOrRd', subset=["红线率", "数值崩坏%", "自动化%", "逻辑违逆%", "分值过低%"])
                 .format({
                     "红线率": "{:.1%}", "数值崩坏%": "{:.1%}", "自动化%": "{:.1%}", 
                     "逻辑违逆%": "{:.1%}", "分值过低%": "{:.1%}", "μ_均值": "{:.2f}", "CV": "{:.3f}"
                 }), use_container_width=True)

    # --- 红线比例说明 ---
    with st.expander("📝 拒绝原因数据列说明 (针对被拒绝的解集)"):
        st.markdown("""
        | 列名 | 业务含义 | 优化建议 |
        | :--- | :--- | :--- |
        | **数值崩坏%** | 该解集下有多少比例的关卡产生了单次过长的连击。 | 检查牌面花色/数值分布是否过于集中。 |
        | **自动化%** | 该解集下有多少比例的关卡无需玩家思考即可连消。 | 减少连续可连接牌的排布。 |
        | **逻辑违逆%** | 玩家表现与难度目标不符 (如高难必胜)。 | 调整系统对玩家补牌或初始手牌的控制。 |
        | **分值过低%** | 虽未触碰红线，但贫瘠区过多或体验项加分太少。 | 优化关卡节奏，减少长距离的 0 连击区间。 |
        """)

    # === 第二部分：明细流水 (跟随第一部分筛选) ===
    st.divider()
    st.subheader("🔍 详细跑关流水")
    f_df = df if status_filter == "全部" else df[df['审计结果'] == status_filter]
    st.dataframe(f_df[['解集ID', '难度', '得分', '审计结果', '红线详情', '构成']], use_container_width=True)
