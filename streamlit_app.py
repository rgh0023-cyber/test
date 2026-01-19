import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面基本配置
st.set_page_config(page_title="关卡体验审计 V1.4 (动态截断统计版)", layout="wide")
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.4")

# --- 核心统计函数：支持动态百分比截断 ---
def calculate_trimmed_stats(series, trim_percentage):
    if len(series) < 10:  # 样本量过小时不截断，确保统计有效性
        return series.mean(), series.var()
    
    sorted_series = np.sort(series)
    n = len(sorted_series)
    # 计算剔除数量（前后各剔除百分比）
    trim_count = int(n * (trim_percentage / 100))
    
    if trim_count == 0:
        return series.mean(), series.var()
        
    trimmed_data = sorted_series[trim_count : n - trim_count]
    return np.mean(trimmed_data), np.var(trimmed_data)

# --- 核心审计逻辑：基于 V1.4 区间递进定义 ---
def audit_layered_v1_4(row, init_score):
    try:
        seq_str = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_str.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']
        difficulty = row['难度']
        actual_result = str(row['实际结果'])
    except:
        return 0, "拒绝", "解析失败", "格式错误", 0, 0, 0

    score = init_score
    score_reasons = []

    # A. 正向加分 (保持文档标准)
    if sum(seq[:3]) >= 4:
        score += 5
        score_reasons.append("开局破冰(+5)")
    if any(x >= 3 for x in seq[-5:]):
        score += 5
        score_reasons.append("尾部收割(+5)")
    if len(seq) >= 7 and max(seq) in seq[6:]:
        score += 5
        score_reasons.append("逆风翻盘(+5)")

    # B. 心流抑制项：全量区间递进判定 (V1.4 新逻辑)
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    boundaries = [-1] + eff_idx + [len(seq)]
    c1, c2, c3 = 0, 0, 0
    
    for j in range(len(boundaries) - 1):
        start = boundaries[j] + 1
        end = boundaries[j+1]
        inter = seq[start:end]
        
        if len(inter) > 0:
            L = len(inter)
            Z = inter.count(0)
            
            # 3级枯竭：L>=6 或 (L>=4 且 Z>=3)
            if L >= 6 or (L >= 4 and Z >= 3):
                c3 += 1
                penalty = -25 if start <= 2 else -20
                score += penalty
                label = "3级枯竭(开局)" if start <= 2 else "3级枯竭"
                score_reasons.append(f"{label}({penalty})")
            
            # 2级阻塞：L=5 或 (L in [3,4] 且 Z=2)
            elif L == 5 or (3 <= L <= 4 and Z == 2):
                c2 += 1
                score -= 9
                score_reasons.append("2级阻塞(-9)")
            
            # 1级平庸：L>=3 且不满足二三级
            elif L >= 3:
                c1 += 1
                score -= 5
                score_reasons.append("1级平庸(-5)")

    # C. 投喂项判定 (程度互斥)
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

    # D. 红线判定
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if max_con >= 7: red_tags.append("自动化局(L3)")
    if max(seq) < 3: red_tags.append("全局枯竭")
    
    if difficulty in [10, 20, 30] and "失败" in actual_result:
        red_tags.append("应胜实败")
    elif difficulty in [40, 50, 60] and "胜利" in actual_result:
        red_tags.append("应败实胜")
    
    red_label = ",".join(red_tags) if red_tags else "无"

    # E. 综合结果
    final_status = "通过" if not red_tags and score >= 50 else "拒绝"
    reason = f"触发红线: {red_label}" if red_tags else ("得分低" if score < 50 else "符合准入")

    return score, final_status, red_label, " | ".join(score_reasons), reason, c1, c2, c3

# 3. 界面布局
with st.sidebar:
    st.header("⚙️ 审计与统计参数")
    init_val = st.slider("初始基准分", 0, 100, 60)
    # 新增：截断百分比调整
    trim_val = st.slider("极值截断比例 (%)", 0, 25, 10, help="剔除每组数据中得分最高和最低的比例")
    st.divider()
    uploaded_file = st.file_uploader("📂 上传跑关数据 (Excel/CSV)", type=["xlsx", "csv"])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
        
        with st.spinner('执行 V1.4 深度审计中...'):
            res = df.apply(lambda r: pd.Series(audit_layered_v1_4(r, init_val)), axis=1)
            cols = ['逻辑得分', '结果', '红线详情', '得分构成', '理由', '1级数', '2级数', '3级数']
            df[cols] = res

        # A. 准入排行榜
        st.subheader(f"📊 解集准入排行榜 (截断比例: {trim_val}%)")
        summary_list = []
        for (jid, diff), group in df.groupby(['解集ID', '难度']):
            t_mean, t_var = calculate_trimmed_stats(group['逻辑得分'], trim_val)
            red_rate = (group['红线详情'] != "无").mean()
            
            summary_list.append({
                "解集ID": jid, "难度": diff,
                "μ_截断均值": round(t_mean, 2),
                "σ2_截断方差": round(t_var, 2),
                "红线率": f"{red_rate:.1%}",
                "1级均数": round(group['1级数'].mean(), 1),
                "2级均数": round(group['2级数'].mean(), 1),
                "3级均数": round(group['3级数'].mean(), 1),
                "准入判定": "✅ 准入" if t_mean >= 50 and t_var <= 15 and red_rate < 0.15 else "❌ 拒绝"
            })
        
        summary_df = pd.DataFrame(summary_list)
        st.dataframe(summary_df.style.background_gradient(cmap='RdYlGn', subset=['μ_截断均值']), use_container_width=True)

        # B. 详细明细
        st.divider()
        st.subheader("🔍 详细审计流水")
        st.dataframe(df[['解集ID', '难度', '实际结果', '逻辑得分', '1级数', '2级数', '3级数', '红线详情', '理由', '得分构成']], use_container_width=True)

        # C. 导出
        csv = df.to_csv(index=False).encode('utf_8_sig')
        st.download_button(f"📥 下载 V1.4 审计报告", csv, "Audit_V1.4_Report.csv")

    except Exception as e:
        st.error(f"处理失败: {e}")
else:
    st.info("💡 请上传文件。当前逻辑：全量区间累计 + 动态截断统计。")
