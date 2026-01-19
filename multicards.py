import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面配置
st.set_page_config(page_title="Tripeaks 算法对比平台 V1.9.0", layout="wide")
st.title("🎴 Tripeaks 关卡审计与算法策略对比平台")

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
    cv = (np.sqrt(var) / mu) if mu > 0 else 0
    return mu, var, cv

# --- 核心审计引擎 (V1.8.1 逻辑) ---
def audit_engine(row, base_init_score):
    try:
        seq_raw = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']; diff = row['难度']; actual = str(row['实际结果'])
    except: return 0, "解析失败", "无", 0, 0, 0, 0, 0, 0

    score = base_init_score
    reasons = []

    # 正向加分
    if sum(seq[:3]) >= 4: score += 5
    if any(x >= 3 for x in seq[-5:]): score += 5
    if len(seq) >= 7 and max(seq) in seq[6:]: score += 5
    
    # 连击接力
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    relay = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx)-1):
            if (eff_idx[i+1]-eff_idx[i]-1) <= 1: relay += 1
    score += (10 if relay >= 3 else 7 if relay == 2 else 5 if relay == 1 else 0)

    # 负向体验 (贫瘠区)
    boundaries = [-1] + eff_idx + [len(seq)]
    c1, c2, c3 = 0, 0, 0
    for j in range(len(boundaries)-1):
        start, end = boundaries[j]+1, boundaries[j+1]
        inter = seq[start:end]
        if inter:
            L, Z = len(inter), inter.count(0)
            if L >= 6 or (L >= 4 and Z >= 3): c3 += 1; score -= (25 if start <= 2 else 20)
            elif L == 5 or (3 <= L <= 4 and Z == 2): c2 += 1; score -= 9
            elif L >= 3: c1 += 1; score -= 5

    # 投喂判定
    f1, f2, red_auto = 0, 0, False
    con_list = []
    cur = 0
    for x in seq:
        if x > 0: cur += 1
        else:
            if cur > 0: con_list.append(cur); cur = 0
    if cur > 0: con_list.append(cur)
    for fl in con_list:
        if fl >= 7: red_auto = True
        elif 5 <= fl <= 6: f2 += 1; score -= 9
        elif fl == 4: f1 += 1; score -= 3

    # 红线判定
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (diff <= 30 and "失败" in actual) or (diff >= 40 and "胜利" in actual): red_tags.append("逻辑违逆")
    
    return score, ",".join(red_tags) if red_tags else "通过", c1, c2, c3, relay, f1, f2

# --- 2. 侧边栏配置 ---
with st.sidebar:
    st.header("⚙️ 审计全局参数")
    base_init_score = st.slider("审计初始分 (Base)", 0, 100, 60)
    mu_threshold = st.slider("及格门槛 (μ)", 0, 100, 70)
    st.divider()
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大 CV (稳定性)", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差保护", 10, 100, 25)
    st.divider()
    # 支持多文件上传
    uploaded_files = st.file_uploader("📂 上传多个牌集数据 (xlsx/csv)", type=["xlsx", "csv"], accept_multiple_files=True)

# --- 3. 核心计算 ---
if uploaded_files:
    all_data_list = []
    for file in uploaded_files:
        temp_df = pd.read_excel(file) if file.name.endswith('.xlsx') else pd.read_csv(file)
        # 记录文件名作为区分标识
        temp_df['源文件'] = file.name
        all_data_list.append(temp_df)
    
    df = pd.concat(all_data_list, ignore_index=True)

    with st.spinner('算法策略对比计算中...'):
        res = df.apply(lambda r: pd.Series(audit_engine(r, base_init_score)), axis=1)
        df[['得分', '红线判定', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = res

    # === 2.1 算法策略看板 (总体统计表) ===
    st.header("📊 算法策略看板 (横向对比)")
    
    # 按照 初始手牌数 聚合计算
    strategy_summary = []
    # 这里我们认为不同的初始手牌数代表了不同的算法策略
    for hand_count, gp_hand in df.groupby('初始手牌'):
        total_jids = gp_hand['解集ID'].nunique()
        jid_stats = []
        for jid, gp in gp_hand.groupby('解集ID'):
            mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
            red_rate = (gp['红线判定'] != "通过").mean()
            is_pass = mu >= mu_threshold and (cv <= cv_limit or var <= var_limit) and red_rate < 0.15
            jid_stats.append(1 if is_pass else 0)
        
        pass_count = sum(jid_stats)
        strategy_summary.append({
            "初始手牌数": hand_count,
            "测试解集数": total_jids,
            "通过牌集数": pass_count,
            "拒绝牌集数": total_jids - pass_count,
            "通过率": pass_count / total_jids if total_jids > 0 else 0,
            "平均截断得分": gp_hand['得分'].mean(),
            "平均红线率": (gp_hand['红线判定'] != "通过").mean()
        })
    
    st.table(pd.DataFrame(strategy_summary).style.format({"通过率": "{:.1%}", "平均红线率": "{:.1%}", "平均截断得分": "{:.2f}"}))

    # === 2.2 详细审计排行与筛选 ===
    st.divider()
    st.subheader("🎯 牌集详情审计")
    
    # 侧边栏增加手牌数筛选 (2.2需求)
    hand_options = sorted(df['初始手牌'].unique())
    selected_hands = st.multiselect("筛选初始手牌数：", hand_options, default=hand_options)
    
    status_filter = st.radio("准入结果过滤：", ["全部", "通过", "拒绝"], horizontal=True)

    summary = []
    # 增加手牌数作为分组键
    for (hand_count, jid, diff), gp in df.groupby(['初始手牌', '解集ID', '难度']):
        if hand_count not in selected_hands: continue
        
        mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
        red_mask = gp['红线判定'] != "通过"
        red_rate = red_mask.mean()
        
        # 理由判定层级
        reason = "✅ 通过"
        if red_rate >= 0.15:
            top_red = gp[red_mask]['红线判定'].mode()[0]
            reason = f"❌ 红线拒绝 ({top_red})"
        elif mu < mu_threshold:
            reason = "❌ 分值拒绝"
        elif cv > cv_limit:
            reason = "❌ 稳定性拒绝"
        
        pass_tag = "通过" if "✅" in reason else "拒绝"
        if status_filter == "全部" or status_filter == pass_tag:
            summary.append({
                "初始手牌": hand_count, "解集ID": jid, "难度": diff, "μ_均值": mu, "CV": cv, 
                "判定结论": reason, "红线率": red_rate, "3级均": gp['c3'].mean(), "2级均": gp['c2'].mean()
            })
    
    if summary:
        sum_df = pd.DataFrame(summary)
        st.dataframe(sum_df.style.applymap(lambda x: 'color: #ff4b4b' if '❌' in str(x) else 'color: #008000', subset=['判定结论'])
                     .format({"红线率":"{:.1%}", "μ_均值":"{:.2f}", "CV":"{:.3f}"}), use_container_width=True)
    
    # === 明细流水筛选 ===
    st.divider()
    st.subheader("🔍 单局流水追踪")
    mask = (df['初始手牌'].isin(selected_hands))
    st.dataframe(df[mask][['初始手牌', '解集ID', '难度', '得分', '红线判定', '全部连击（每张手牌的连击数）']].sort_values('得分'), use_container_width=True)

else:
    st.info("💡 请在左侧上传一个或多个牌集文件进行算法对比。")
