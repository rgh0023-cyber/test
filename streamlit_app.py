import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面基本配置
st.set_page_config(page_title="关卡体验审计 V1.2 (全量区间累计版)", layout="wide")
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.2")

# 2. 核心逻辑：基于全量区间统计的审计函数
def audit_layered_v1_2(row, init_score):
    try:
        # 基础数据解析
        seq_str = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_str.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']
        difficulty = row['难度']
        actual_result = str(row['实际结果'])
    except:
        return 0, "拒绝", "解析失败", "数据格式异常", 0, 0, 0

    # --- 第一层：逻辑得分层 (Experience Scoring) ---
    score = init_score
    score_reasons = []

    # A. 正向加分项 (保持 V1.1 标准)
    if sum(seq[:3]) >= 4:
        score += 5
        score_reasons.append("开局破冰(+5)")
    if any(x >= 3 for x in seq[-5:]):
        score += 5
        score_reasons.append("尾部收割(+5)")
    if len(seq) >= 7 and max(seq) in seq[6:]:
        score += 5
        score_reasons.append("逆风翻盘(+5)")

    # B. 抑制项判定：全量区间累计算法 (修正点)
    # 1. 定义高效手牌索引并切割区间
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    boundaries = [-1] + eff_idx + [len(seq)]
    
    # 2. 初始化区间统计数据
    count_l1, count_l2, count_l3 = 0, 0, 0
    
    # 3. 遍历所有贫瘠区间并分类判定
    for j in range(len(boundaries) - 1):
        start = boundaries[j] + 1
        end = boundaries[j+1]
        inter_seq = seq[start:end]
        
        if len(inter_seq) > 0:
            inter_len = len(inter_seq)
            zeros = inter_seq.count(0)
            
            # 3.1 3级枯竭区判定 (长度>=4 且 0>=2)
            if inter_len >= 4 and zeros >= 2:
                count_l3 += 1
                penalty = -25 if start <= 2 else -20
                score += penalty
                label = "3级枯竭(开局)" if start <= 2 else "3级枯竭"
                score_reasons.append(f"{label}({penalty})")
            
            # 3.2 2级阻塞区判定 (长度>=3 且 0在1-2个)
            elif inter_len >= 3 and 1 <= zeros <= 2:
                count_l2 += 1
                score -= 9
                score_reasons.append("2级阻塞(-9)")
            
            # 3.3 1级平庸区判定 (长度>=3 且 全部为低效牌)
            elif inter_len >= 3 and zeros == 0:
                count_l1 += 1
                score -= 5
                score_reasons.append("1级平庸(-5)")

    # C. 投喂项判定 (保持互斥逻辑：L2 > L1)
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

    # --- 第二层：红线判定层 (保持不变) ---
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if max_con >= 7: red_tags.append("自动化局(L3)")
    if max(seq) < 3: red_tags.append("全局枯竭")
    
    # 双向逻辑违逆判定
    if difficulty in [10, 20, 30] and "失败" in actual_result:
        red_tags.append("应胜实败")
    elif difficulty in [40, 50, 60] and "胜利" in actual_result:
        red_tags.append("应败实胜")
    
    red_label = ",".join(red_tags) if red_tags else "无"

    # --- 第三层：综合判定层 ---
    final_status = "通过"
    if red_tags:
        final_status = "拒绝"
        final_reason = f"触发红线: {red_label}"
    elif score < 50:
        final_status = "拒绝"
        final_reason = "累计体验分过低"
    else:
        final_reason = "符合准入标准"

    return score, final_status, red_label, " | ".join(score_reasons), final_reason, count_l1, count_l2, count_l3

# 3. Streamlit 侧边栏
with st.sidebar:
    st.header("⚙️ 审计参数设置")
    init_val = st.slider("初始基准分", 0, 100, 60)
    st.divider()
    uploaded_file = st.file_uploader("📂 上传跑关数据 (Excel/CSV)", type=["xlsx", "csv"])

# 4. 主页面逻辑
if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
        
        with st.spinner('正在执行全量区间统计审计...'):
            # 应用审计函数
            audit_res = df.apply(lambda r: pd.Series(audit_layered_v1_2(r, init_val)), axis=1)
            # 映射结果列
            cols = ['逻辑得分', '审计结果', '红线详情', '得分构成', '最终结论理由', '1级数量', '2级数量', '3级数量']
            df[cols] = audit_res

        # A. 聚合排行榜
        st.subheader("📊 解集准入排行榜 (基于100轮均值)")
        summary = df.groupby(['解集ID', '难度']).agg(
            μ_得分均值=('逻辑得分', 'mean'),
            σ2_得分方差=('逻辑得分', 'var'),
            红线率=('红线详情', lambda x: (x != "无").mean()),
            avg_L1=('1级数量', 'mean'),
            avg_L2=('2级数量', 'mean'),
            avg_L3=('3级数量', 'mean')
        ).reset_index()

        summary['准入判定'] = summary.apply(
            lambda r: "✅ 准入" if r['μ_得分均值'] >= 50 and r['σ2_得分方差'] <= 15 and r['红线率'] < 0.15 else "❌ 拒绝", axis=1
        )
        st.dataframe(summary.style.highlight_max(axis=0, subset=['μ_得分均值']), use_container_width=True)

        # B. 详细审计流水
        st.divider()
        st.subheader("🔍 详细审计明细 (包含贫瘠区计数)")
        display_cols = ['解集ID', '测试轮次', '难度', '实际结果', '逻辑得分', '1级数量', '2级数量', '3级数量', '红线详情', '最终结论理由', '得分构成']
        st.dataframe(df[display_cols], use_container_width=True)

        # C. 导出
        csv_data = df.to_csv(index=False).encode('utf_8_sig')
        st.download_button("📥 下载完整 V1.2 审计报告", csv_data, "Audit_Report_V1.2.csv", "text/csv")

    except Exception as e:
        st.error(f"处理文件时发生错误: {e}")
else:
    st.info("💡 请上传数据。V1.2 版本支持全量贫瘠区间累计扣分与数量统计。")
