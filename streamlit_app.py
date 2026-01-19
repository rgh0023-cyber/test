import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面配置
st.set_page_config(page_title="Tripeaks 审计系统 V1.6.5", layout="wide")
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.6.5")

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

# --- 核心审计引擎 (保留全部基础标准) ---
def audit_engine(row, init_score):
    try:
        seq_raw = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']; diff = row['难度']; actual = str(row['实际结果'])
    except: return 0, "拒绝", "解析失败", "", 0, 0, 0, 0, 0, 0

    score = init_score
    reasons = []

    # A. 基础加分 (破冰/收割/翻盘)
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

    # C. 贫瘠区分析 (全量分级)
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

    # D. 投喂项与红线判定
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
    if (diff <= 30 and "失败" in actual) or (diff >= 40 and "胜利" in actual):
        red_tags.append("逻辑违逆")
    
    red_label = ",".join(red_tags) if red_tags else "无"
    status = "通过" if not red_tags and score >= 50 else "拒绝"
    return score, status, red_label, " | ".join(reasons), c1, c2, c3, relay, f1, f2

# --- 2. 页面说明与全局配置 ---
st.markdown("### 🚩 红线规则说明")
st.caption("数值崩坏: 单次连击>40%桌面牌 | 自动化: 连续7+连击 | 逻辑违逆: 难度与胜负预期不符 | 分值低: 无红线但得分<50")

with st.sidebar:
    st.header("⚙️ 核心参数")
    init_val = st.slider("准入及格分 (μ)", 0, 100, 50, help="控制解集平均分的门槛")
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大变异系数 (CV)", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差保护值", 10, 50, 25)
    uploaded_file = st.file_uploader("📂 上传跑关数据", type=["xlsx", "csv"])

# --- 3. 核心逻辑处理 ---
if uploaded_file:
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    with st.spinner('执行标准审计...'):
        res = df.apply(lambda r: pd.Series(audit_engine(r, init_val)), axis=1)
        df[['得分', '审计结果', '红线详情', '构成', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = res

    # === 第一部分：全局筛选器 ===
    st.subheader("🎯 审计准入筛选")
    status_filter = st.radio("选择显示最终判定结果：", ["全部", "通过", "拒绝"], horizontal=True)

    # 预计算解集汇总表
    summary = []
    FIXED_BASE = 50 # 固定单局判定基准，解耦滑块
    for (jid, diff), gp in df.groupby(['解集ID', '难度']):
        mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
        red_mask = gp['红线详情'] != "无"
        red_rate = red_mask.mean()
        
        # 准入判定逻辑：只看均值是否过线、稳定性、红线率
        is_pass = mu >= init_val and (cv <= cv_limit or var <= var_limit) and red_rate < 0.15
        pass_status = "通过" if is_pass else "拒绝"
        
        if status_filter == "全部" or status_filter == pass_status:
            all_reds = ",".join(gp['红线详情']).split(",")
            summary.append({
                "解集ID": jid, "难度": diff, "μ_均值": mu, "Min_最低分": gp['得分'].min(), "CV": cv,
                "准入判定": "✅ 通过" if is_pass else "❌ 拒绝",
                "红线率": red_rate,
                "分值过低%": ((gp['得分'] < FIXED_BASE) & (~red_mask)).mean(),
                "数值崩坏%": all_reds.count("数值崩坏") / len(gp),
                "自动化%": all_reds.count("自动化局") / len(gp),
                "逻辑违逆%": all_reds.count("逻辑违逆") / len(gp)
            })
    
    if summary:
        sum_df = pd.DataFrame(summary)
        # 显示汇总表
        st.dataframe(sum_df.style.background_gradient(cmap='RdYlGn', subset=['μ_均值'])
                     .background_gradient(cmap='YlOrRd', subset=['红线率', 'CV', '分值过低%'])
                     .format({"红线率":"{:.1%}", "分值过低%":"{:.1%}", "数值崩坏%":"{:.1%}", "自动化%":"{:.1%}", "逻辑违逆%":"{:.1%}", "μ_均值":"{:.2f}", "CV":"{:.3f}"}), 
                     use_container_width=True)
    else:
        st.warning("无匹配数据")

    # === 第二部分：明细流水 (包含原始序列) ===
    st.divider()
    st.subheader("🔍 跑关详细流水")
    
    # 联动上方单选筛选
    f_df = df if status_filter == "全部" else df[df['审计结果'] == status_filter]
    
    # 增加细分筛选
    c1, c2 = st.columns(2)
    with c1: detail_jid = st.multiselect("牌集 ID", sorted(df['解集ID'].unique()), default=sorted(df['解集ID'].unique()))
    with c2: detail_diff = st.multiselect("难度", sorted(df['难度'].unique()), default=sorted(df['难度'].unique()))
    
    final_df = f_df[(f_df['解集ID'].isin(detail_jid)) & (f_df['难度'].isin(detail_diff))]
    
    st.dataframe(final_df[['解集ID', '难度', '得分', '审计结果', '红线详情', '全部连击（每张手牌的连击数）', '构成']], use_container_width=True)

    # 导出按钮
    st.download_button("📥 导出筛选后的结果", final_df.to_csv(index=False).encode('utf_8_sig'), "Tripeaks_Audit_Detail.csv")
