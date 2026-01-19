import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面基本配置
st.set_page_config(page_title="Tripeaks 审计系统 V1.6.2", layout="wide")
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.6.2")

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

    # A. 基础加分项
    if sum(seq[:3]) >= 4: score += 5; reasons.append("开局破冰(+5)")
    if any(x >= 3 for x in seq[-5:]): score += 5; reasons.append("尾部收割(+5)")
    if len(seq) >= 7 and max(seq) in seq[6:]: score += 5; reasons.append("逆风翻盘(+5)")

    # B. 连击接力 (方案 A)
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    relay_count = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx) - 1):
            if (eff_idx[i+1] - eff_idx[i] - 1) <= 1: relay_count += 1
    if relay_count >= 3: score += 10; reasons.append(f"接力x{relay_count}(+10)")
    elif relay_count == 2: score += 7; reasons.append(f"接力x{relay_count}(+7)")
    elif relay_count == 1: score += 5; reasons.append("接力x1(+5)")

    # C. 贫瘠区分析
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

    # D. 投喂项分析
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

    # E. 红线判定
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (difficulty <= 30 and "失败" in actual_result) or (difficulty >= 40 and "胜利" in actual_result):
        red_tags.append("逻辑违逆")
    
    red_label = ",".join(red_tags) if red_tags else "无"
    status = "通过" if not red_tags and score >= 50 else "拒绝"
    return score, status, red_label, " | ".join(reasons), c1, c2, c3, relay_count, f1, f2

# --- 2. 页面顶层：红线说明与全局筛选 ---
st.markdown("""
### 🚩 红线规则说明
- **数值崩坏**：单次连击数超过初始桌面牌总数的 40% (即单次收牌过多)。
- **自动化局**：出现连续 7 张及以上的手牌均产生连击 (玩家无需思考)。
- **逻辑违逆**：低难度(≤30)出现失败，或高难度(≥40)出现胜利 (结果偏离难度设计目标)。
- **基础拒绝**：除上述红线外，审计逻辑得分低于 **50分** 也会被判定为拒绝。
""")

st.divider()

# --- 3. 侧边栏配置 ---
with st.sidebar:
    st.header("⚙️ 核心参数")
    init_val = st.slider("基础及格分", 0, 100, 50)
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大变异系数 (CV)", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差保护值", 10, 50, 25)
    uploaded_file = st.file_uploader("📂 上传跑关数据", type=["xlsx", "csv"])

# --- 4. 数据展示逻辑 ---
if uploaded_file:
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    
    with st.spinner('执行标准审计...'):
        res = df.apply(lambda r: pd.Series(audit_engine(r, init_val)), axis=1)
        df[['得分', '审计结果', '红线详情', '构成', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = res

    # === 全局第一部分筛选器 ===
    st.subheader("🎯 审计准入筛选")
    status_filter = st.radio("选择显示结果：", ["全部", "通过", "拒绝"], horizontal=True)

    # A. 聚合排行计算
    summary = []
    for (jid, diff), gp in df.groupby(['解集ID', '难度']):
        mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
        red_rate = (gp['红线详情'] != "无").mean()
        is_pass = mu >= init_val and (cv <= cv_limit or var <= var_limit) and red_rate < 0.15
        pass_status = "通过" if is_pass else "拒绝"
        
        # 应用顶层筛选
        if status_filter == "全部" or status_filter == pass_status:
            summary.append({
                "解集ID": jid, "难度": diff, "μ_均值": mu, "CV_变异系数": cv, "σ2_方差": var, 
                "红线率": red_rate, "3级均": gp['c3'].mean(), "2级均": gp['c2'].mean(), 
                "L2均": gp['f2'].mean(), "接力均": gp['接力'].mean(),
                "准入判定": "✅ 通过" if is_pass else "❌ 拒绝"
            })
    
    if summary:
        sum_df = pd.DataFrame(summary)
        st.write(f"已筛选出的解集数量: **{len(sum_df)}**")
        st.dataframe(sum_df.style.background_gradient(cmap='RdYlGn', subset=['μ_均值', 'CV_变异系数']).format({
            "红线率":"{:.1%}", "μ_均值":"{:.2f}", "σ2_方差":"{:.2f}", "CV_变异系数":"{:.3f}"
        }), use_container_width=True)
    else:
        st.warning("没有符合当前筛选条件的解集。")

    # B. 明细流水筛选
    st.divider()
