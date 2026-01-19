import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Tripeaks 审计系统 V1.8.0", layout="wide")
st.title("🎴 Tripeaks 关卡审计系统 V1.8.0")

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

# --- 审计引擎 ---
def audit_engine(row, base_init_score):
    try:
        seq_raw = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']; diff = row['难度']; actual = str(row['实际结果'])
    except: return 0, "解析失败", "无"

    score = base_init_score
    # A. 正向体验项
    if sum(seq[:3]) >= 4: score += 5
    if any(x >= 3 for x in seq[-5:]): score += 5
    if len(seq) >= 7 and max(seq) in seq[6:]: score += 5
    # B. 连击接力
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    relay = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx)-1):
            if (eff_idx[i+1]-eff_idx[i]-1) <= 1: relay += 1
    if relay >= 3: score += 10
    elif relay == 2: score += 7
    elif relay == 1: score += 5
    # C. 负向体验项
    boundaries = [-1] + eff_idx + [len(seq)]
    for j in range(len(boundaries)-1):
        start, end = boundaries[j]+1, boundaries[j+1]
        inter = seq[start:end]
        if inter:
            L, Z = len(inter), inter.count(0)
            if L >= 6 or (L >= 4 and Z >= 3): score -= 20
            elif L == 5 or (3 <= L <= 4 and Z == 2): score -= 9
            elif L >= 3: score -= 5
    # D. 投喂项判定
    red_auto = False
    con_list = []
    cur = 0
    for x in seq:
        if x > 0: cur += 1
        else:
            if cur > 0: con_list.append(cur); cur = 0
    if cur > 0: con_list.append(cur)
    for fl in con_list:
        if fl >= 7: red_auto = True
        elif 5 <= fl <= 6: score -= 9
        elif fl == 4: score -= 3

    # E. 红线判定
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (diff <= 30 and "失败" in actual) or (diff >= 40 and "胜利" in actual): red_tags.append("逻辑违逆")
    
    return score, ",".join(red_tags) if red_tags else "通过", " | ".join(red_tags) if red_tags else "无"

# --- 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 准入判定标准")
    base_init_score = st.slider("审计初始分", 0, 100, 60)
    mu_threshold = st.slider("准入及格分 (μ)", 0, 100, 70)
    st.divider()
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大 CV (稳定性)", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差保护", 10, 100, 25)
    uploaded_file = st.file_uploader("📂 上传数据", type=["xlsx", "csv"])

# --- 核心处理与逻辑展示 ---
if uploaded_file:
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    with st.spinner('审计中...'):
        res = df.apply(lambda r: pd.Series(audit_engine(r, base_init_score)), axis=1)
        df[['得分', '红线判定', '红线详情']] = res

    summary = []
    for (jid, diff), gp in df.groupby(['解集ID', '难度']):
        mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
        
        # 依次判定拒绝理由 (Only one reason)
        red_mask = gp['红线判定'] != "通过"
        red_rate = red_mask.mean()
        
        # 层级判定逻辑
        reason = "✅ 通过"
        if red_rate >= 0.15:
            # 找出该解集最主要的红线类型
            top_red = gp[red_mask]['红线判定'].mode()[0]
            reason = f"❌ 红线拒绝 ({top_red})"
        elif mu < mu_threshold:
            reason = "❌ 分值拒绝 (均值不达标)"
        elif cv > cv_limit:
            reason = "❌ 稳定性拒绝 (CV过高)"
        elif var > var_limit:
            reason = "❌ 波动拒绝 (方差过大)"

        summary.append({
            "解集ID": jid, "难度": diff, "μ_截断均值": mu, "CV": cv, "σ2": var,
            "判定结论": reason, "红线率": red_rate
        })
    
    st.subheader("📊 解集最终准入判定排行")
    sum_df = pd.DataFrame(summary)
    st.dataframe(sum_df.style.applymap(lambda x: 'color: red' if '❌' in str(x) else 'color: green', subset=['判定结论'])
                 .format({"红线率":"{:.1%}",
