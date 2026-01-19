import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面基本配置
st.set_page_config(page_title="关卡体验审计 V1.3 (截断方差优化版)", layout="wide")
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.3")

# 核心逻辑：计算截断后的统计指标
def calculate_trimmed_stats(series):
    if len(series) < 5:  # 数据样本过少时不做截断
        return series.mean(), series.var()
    
    # 排序并去除前后 10%
    sorted_series = np.sort(series)
    n = len(sorted_series)
    low = int(n * 0.1)
    high = n - low
    trimmed_data = sorted_series[low:high]
    
    return np.mean(trimmed_data), np.var(trimmed_data)

# 2. 核心审计函数 (保持 V1.2 的区间累计判定逻辑)
def audit_layered_v1_3(row, init_score):
    try:
        seq_str = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_str.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']
        difficulty = row['难度']
        actual_result = str(row['实际结果'])
    except:
        return 0, "拒绝", "解析失败", "数据格式异常", 0, 0, 0

    score = init_score
    score_reasons = []

    # A. 正向加分
    if sum(seq[:3]) >= 4:
        score += 5
        score_reasons.append("开局破冰(+5)")
    if any(x >= 3 for x in seq[-5:]):
        score += 5
        score_reasons.append("尾部收割(+5)")
    if len(seq) >= 7 and max(seq) in seq[6:]:
        score += 5
        score_reasons.append("逆风翻盘(+5)")

    # B. 抑制项判定：全量区间累计
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    boundaries = [-1] + eff_idx + [len(seq)]
    count_l1, count_l2, count_l3 = 0, 0, 0
    
    for j in range(len(boundaries) - 1):
        start = boundaries[j] + 1
        end = boundaries[j+1]
        inter_seq = seq[start:end]
        if len(inter_seq) > 0:
            inter_len = len(inter_seq)
            zeros = inter_seq.count(0)
            if inter_len >= 4 and zeros >= 2:
                count_l3 += 1
                p = -25 if start <= 2 else -20
                score += p
                score_reasons.append(f"3级枯竭" + ("(开局)" if start <= 2 else "") + f"({p})")
            elif inter_len >= 3 and 1 <= zeros <= 2:
                count_l2 += 1
                score -= 9
                score_reasons.append("2级阻塞(-9)")
            elif inter_len >= 3 and zeros == 0:
                count_l1 += 1
                score -= 5
                score_reasons.append("1级平庸(-5)")

    # C. 投喂项判定 (互斥)
    con_list = []
    cur = 0
    for x in seq:
        if x > 0: cur += 1
        else:
            if cur > 0: con_list.append(cur)
            cur = 0
    if cur > 0: con_list.append(cur)
    max_con = max(con_list) if con_list else 0

    if 5 <= max_con <= 6:
        score -= 20
        score_reasons.append("L2过度投喂(-20)")
    elif con_list.count(4) >= 3:
        score -= 10
        score_reasons.append("L1高频投喂(-10)")

    # --- 第二层：红线判定层 ---
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if max_con >= 7: red_tags.append("自动化局(L3)")
    if max(seq) < 3: red_tags.append("全局枯竭")
    
    if difficulty in [10, 20, 30] and "失败" in actual_result:
        red_tags.append("应胜实败")
    elif difficulty in [40, 50, 60] and "胜利" in actual_result:
        red_tags.append("应败实胜")
    
    red_label = ",".join(red_tags) if red_tags else "无"

    # --- 第三层：综合判定 ---
    final_status = "通过" if not red_tags and score >= 50 else "拒绝"
    final_reason = f"触发红线: {red_label}" if red_tags else ("体验得分低" if score < 50 else "符合准入标准")

    return score, final_status, red_label, " | ".join(score_reasons), final_reason, count_l1, count_l2, count_l3

# 3. Streamlit 侧边栏及主页面
with st.sidebar:
    st.header("⚙️ 审计参数")
    init_val = st.slider("初始基准分", 0, 100, 60)
    st.info("💡 方差计算已启用 10% 截断算法，剔除极端极值。")
    uploaded_file = st.file_uploader("📂 上传数据", type=["xlsx", "csv"])

if uploaded_file:
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    
    # 核心计算
    res = df.apply(lambda r: pd.Series(audit_layered_v1_3(r, init_val)), axis=1)
    df[['逻辑得分', '审计结果', '红线详情', '得分构成', '理由', 'L1数', 'L2数', 'L3数']] = res

    # A. 聚合报表 (应用截断方差逻辑)
    st.subheader("📊 解集准入排行榜 (中间 80% 抽样统计)")
    
    summary_list = []
    for (jid, diff), group in df.groupby(['解集ID', '难度']):
        t_mean, t_var = calculate_trimmed_stats(group['逻辑得分'])
        red_rate = (group['红线详情'] != "无").mean()
        
        summary_list.append({
            "解集ID": jid,
            "难度": diff,
            "μ_截断均值": round(t_mean, 2),
            "σ2_截断方差": round(t_var, 2),
            "红线率": f"{red_rate:.1%}",
            "L1均值": round(group['L1数'].mean(), 1),
            "L2均值": round(group['L2数'].mean(), 1),
            "L3均值": round(group['L3数'].mean(), 1),
            "准入判定": "✅ 准入" if t_mean >= 50 and t_var <= 15 and red_rate < 0.15 else "❌ 拒绝"
        })
    
    st.dataframe(pd.DataFrame(summary_list), use_container_width=True)

    # B. 流水展示
    st.divider()
    st.subheader("🔍 详细审计流水")
    st.dataframe(df[['解集ID', '测试轮次', '难度', '实际结果', '逻辑得分', 'L1数', 'L2数', 'L3数', '红线详情', '理由']], use_container_width=True)

    csv = df.to_csv(index=False).encode('utf_8_sig')
    st.download_button("📥 下载审计报告", csv, "Audit_V1.3.csv")
