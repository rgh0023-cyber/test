import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面配置
st.set_page_config(page_title="Tripeaks 审计系统 V1.8.1", layout="wide")
st.title("🎴 Tripeaks 审计系统 V1.8.1 (全功能复活版)")

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

# --- 核心审计引擎 ---
def audit_engine(row, base_init_score):
    try:
        seq_raw = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']; diff = row['难度']; actual = str(row['实际结果'])
    except: return 0, "解析失败", "无", 0, 0, 0, 0, 0, 0

    score = base_init_score
    reasons = []

    # A. 正向体验项
    if sum(seq[:3]) >= 4: score += 5; reasons.append("破冰")
    if any(x >= 3 for x in seq[-5:]): score += 5; reasons.append("收割")
    if len(seq) >= 7 and max(seq) in seq[6:]: score += 5; reasons.append("翻盘")

    # B. 连击接力
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    relay = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx)-1):
            if (eff_idx[i+1]-eff_idx[i]-1) <= 1: relay += 1
    if relay >= 3: score += 10
    elif relay == 2: score += 7
    elif relay == 1: score += 5

    # C. 负向体验项 (贫瘠区)
    boundaries = [-1] + eff_idx + [len(seq)]
    c1, c2, c3 = 0, 0, 0
    for j in range(len(boundaries)-1):
        start, end = boundaries[j]+1, boundaries[j+1]
        inter = seq[start:end]
        if inter:
            L, Z = len(inter), inter.count(0)
            if L >= 6 or (L >= 4 and Z >= 3):
                c3 += 1; p = -25 if start <= 2 else -20
                score += p
            elif L == 5 or (3 <= L <= 4 and Z == 2):
                c2 += 1; score -= 9
            elif L >= 3:
                c1 += 1; score -= 5

    # D. 投喂项判定
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
        elif 5 <= fl <= 6: f2 += 1; score -= 9
        elif fl == 4: f1 += 1; score -= 3

    # E. 红线判定
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (diff <= 30 and "失败" in actual) or (diff >= 40 and "胜利" in actual):
        red_tags.append("逻辑违逆")
    
    return score, ",".join(red_tags) if red_tags else "通过", " | ".join(reasons), c1, c2, c3, relay, f1, f2

# --- 2. 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 审计标准配置")
    base_init_score = st.slider("审计初始分 (Base)", 0, 100, 60)
    mu_threshold = st.slider("及格门槛 (μ)", 0, 100, 70)
    st.divider()
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大 CV (稳定性)", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差保护", 10, 100, 25)
    uploaded_file = st.file_uploader("📂 上传跑关数据", type=["xlsx", "csv"])

# --- 3. 核心计算 ---
if uploaded_file:
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    with st.spinner('执行标准审计...'):
        res = df.apply(lambda r: pd.Series(audit_engine(r, base_init_score)), axis=1)
        df[['得分', '红线判定', '构成', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = res

    # === 第一部分：解集排行榜 (层级判定) ===
    st.subheader("📊 解集最终判定排行")
    status_filter = st.radio("准入结果过滤：", ["全部", "通过", "拒绝"], horizontal=True)

    summary = []
    for (jid, diff), gp in df.groupby(['解集ID', '难度']):
        mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
        red_mask = gp['红线判定'] != "通过"
        red_rate = red_mask.mean()
        
        # --- 唯一理由判定层级 ---
        reason = "✅ 通过"
        if red_rate >= 0.15:
            top_red = gp[red_mask]['红线判定'].mode()[0]
            reason = f"❌ 红线拒绝 ({top_red})"
        elif mu < mu_threshold:
            reason = "❌ 分值拒绝 (均值未达标)"
        elif cv > cv_limit:
            reason = "❌ 稳定性拒绝 (CV过高)"
        elif var > var_limit:
            reason = "❌ 波动拒绝 (方差过大)"
        
        # 结果过滤逻辑
        pass_tag = "通过" if "✅" in reason else "拒绝"
        if status_filter == "全部" or status_filter == pass_tag:
            summary.append({
                "解集ID": jid, "难度": diff, "μ_均值": mu, "CV": cv, "判定结论": reason,
                "红线率": red_rate, "3级均": gp['c3'].mean(), "2级均": gp['c2'].mean(),
                "L2投喂均": gp['f2'].mean(), "平均接力": gp['接力'].mean()
            })
    
    if summary:
        sum_df = pd.DataFrame(summary)
        st.dataframe(sum_df.style.applymap(lambda x: 'color: #ff4b4b' if '❌' in str(x) else 'color: #008000', subset=['判定结论'])
                     .background_gradient(cmap='YlGnBu', subset=['μ_均值'])
                     .format({"红线率":"{:.1%}", "μ_均值":"{:.2f}", "CV":"{:.3f}", "3级均":"{:.1f}", "2级均":"{:.1f}", "L2投喂均":"{:.1f}", "平均接力":"{:.1f}"}), 
                     use_container_width=True)
    else:
        st.warning("暂无匹配数据")

    # === 第二部分：明细流水筛选 ===
    st.divider()
    st.subheader("🔍 跑关详细流水筛选")
    
    # 筛选 UI
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1: f_jid = st.multiselect("解集 ID", sorted(df['解集ID'].unique()), default=sorted(df['解集ID'].unique()))
    with c2: f_diff = st.multiselect("难度等级", sorted(df['难度'].unique()), default=sorted(df['难度'].unique()))
    with c3: f_red = st.checkbox("仅显示触发红线的轮次")
    
    # 应用过滤
    mask = (df['解集ID'].isin(f_jid)) & (df['难度'].isin(f_diff))
    if status_filter != "全部":
        # 转换单选过滤到明细行 (这里逻辑需稍作调整以匹配解集结论)
        passed_jids = [s['解集ID'] for s in summary if "✅" in s['判定结论']]
        if status_filter == "通过":
            mask = mask & (df['解集ID'].isin(passed_jids))
        else:
            mask = mask & (~df['解集ID'].isin(passed_jids))
    
    display_df = df[mask]
    if f_red:
        display_df = display_df[display_df['红线判定'] != "通过"]

    st.write(f"当前显示行数: {len(display_df)}")
    st.dataframe(display_df[['解集ID', '难度', '得分', '红线判定', '全部连击（每张手牌的连击数）', '构成', 'c3', 'c2', '接力']], use_container_width=True)

    # 导出
    csv = display_df.to_csv(index=False).encode('utf_8_sig')
    st.download_button("📥 导出明细数据", csv, "audit_detail.csv", "text/csv")
