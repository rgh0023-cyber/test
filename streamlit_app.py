import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面基本配置
st.set_page_config(page_title="关卡体验审计 V1.1 (区间修正版)", layout="wide")
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.1")

# 2. 核心逻辑：基于说明书定义的区间审计函数
def audit_layered_v1_1(row, init_score):
    try:
        # 基础数据解析
        seq_str = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_str.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']
        difficulty = row['难度']
        actual_result = str(row['实际结果'])
    except:
        return 0, "拒绝", "解析失败", "数据格式异常", "解析失败"

    # --- 第一层：逻辑得分层 (Experience Scoring) ---
    score = init_score
    score_reasons = []

    # A. 正向加分项 (保持不变)
    if sum(seq[:3]) >= 4:
        score += 5
        score_reasons.append("开局破冰(+5)")
    if any(x >= 3 for x in seq[-5:]):
        score += 5
        score_reasons.append("尾部收割(+5)")
    if len(seq) >= 7 and max(seq) in seq[6:]:
        score += 5
        score_reasons.append("逆风翻盘(+5)")

    # B. 抑制项判定：基于区间切割算法 (修正点)
    # 1. 定义高效手牌索引
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    # 2. 切割贫瘠区间 (由高效手牌或端点分割)
    boundaries = [-1] + eff_idx + [len(seq)]
    intervals = []
    for j in range(len(boundaries) - 1):
        start = boundaries[j] + 1
        end = boundaries[j+1]
        inter_seq = seq[start:end]
        if len(inter_seq) > 0:
            intervals.append({
                "seq": inter_seq,
                "start": start,
                "len": len(inter_seq),
                "zeros": inter_seq.count(0)
            })

    # 3. 按照优先级(3>2>1)进行区间打分 (互斥)
    found_flow_issue = False
    # 优先查3级枯竭
    for inter in intervals:
        if inter["len"] >= 4 and inter["zeros"] >= 2:
            penalty = -25 if inter["start"] <= 2 else -20
            score += penalty
            score_reasons.append(f"3级枯竭" + ("(开局)" if inter["start"] <= 2 else "") + f"({penalty})")
            found_flow_issue = True
            break
    
    # 若无3级，查2级和1级
    if not found_flow_issue:
        for inter in intervals:
            if inter["len"] >= 3:
                if 1 <= inter["zeros"] <= 2:
                    score -= 12
                    score_reasons.append("2级阻塞(-12)")
                    found_flow_issue = True
                    break
                elif inter["zeros"] == 0: # 全部由低效手牌(1,2)组成
                    score -= 5
                    score_reasons.append("1级平庸(-5)")
                    found_flow_issue = True
                    break

    # C. 投喂项判定 (程度互斥：L2 > L1)
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
    
    # 双向逻辑违逆
    if difficulty in [10, 20, 30] and "失败" in actual_result:
        red_tags.append("逻辑违逆(应胜实败)")
    elif difficulty in [40, 50, 60] and "胜利" in actual_result:
        red_tags.append("逻辑违逆(应败实胜)")
    
    red_label = ",".join(red_tags) if red_tags else "无"

    # --- 第三层：综合判定层 ---
    final_status = "通过"
    if red_tags:
        final_status = "拒绝"
        final_reason = f"触发红线: {red_label}"
    elif score < 50:
        final_status = "拒绝"
        final_reason = "体验得分低于50分"
    else:
        final_reason = "符合准入标准"

    return score, final_status, red_label, " | ".join(score_reasons), final_reason

# 3. 侧边栏
with st.sidebar:
    st.header("⚙️ 审计参数设置")
    init_val = st.slider("初始基准分", 0, 100, 60)
    st.divider()
    uploaded_file = st.file_uploader("📂 上传跑关数据 (Excel/CSV)", type=["xlsx", "csv"])

# 4. 主页面
if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
        
        with st.spinner('严格执行区间切割审计中...'):
            audit_res = df.apply(lambda r: pd.Series(audit_layered_v1_1(r, init_val)), axis=1)
            df[['逻辑得分', '审计结果', '红线详情', '得分构成', '最终结论理由']] = audit_res

        # A. 聚合报表
        st.subheader("📊 解集准入排行榜")
        summary = df.groupby(['解集ID', '难度']).agg(
            μ_得分均值=('逻辑得分', 'mean'),
            σ2_得分方差=('逻辑得分', 'var'),
            红线率=('红线详情', lambda x: (x != "无").mean())
        ).reset_index()

        summary['准入判定'] = summary.apply(
            lambda r: "✅ 准入" if r['μ_得分均值'] >= 50 and r['σ2_得分方差'] <= 15 and r['红线率'] < 0.15 else "❌ 拒绝", axis=1
        )
        st.dataframe(summary.style.highlight_max(axis=0, subset=['μ_得分均值']), use_container_width=True)

        # B. 流水展示
        st.divider()
        st.subheader("🔍 审计流水明细")
        st.dataframe(df[['解集ID', '测试轮次', '难度', '实际结果', '逻辑得分', '红线详情', '最终结论理由', '得分构成']], use_container_width=True)

    except Exception as e:
        st.error(f"处理出错: {e}")
else:
    st.info("请上传数据。当前版本已修正贫瘠区间定义，采用高效牌分割逻辑。")
