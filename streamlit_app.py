import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面基本配置
st.set_page_config(page_title="关卡体验审计 V1.1 (分层判定版)", layout="wide")
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.1")

# 2. 核心逻辑：分层审计函数
def audit_layered_v1_1(row, init_score):
    try:
        # 获取序列
        seq_str = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x) for x in seq_str.split(',')]
        desk_init = row['初始桌面牌']
    except:
        return 0, "拒绝", "解析失败", "数据格式异常"

    # --- 第一层：逻辑得分层 (Score Calculation) ---
    score = init_score
    score_reasons = []

    # A. 正向加分
    if sum(seq[:3]) >= 4:
        score += 5
        score_reasons.append("开局破冰(+5)")
    if any(x >= 3 for x in seq[-5:]):
        score += 5
        score_reasons.append("尾部收割(+5)")
    if max(seq) in seq[6:]:
        score += 5
        score_reasons.append("逆风翻盘(+5)")

    # B. 抑制项判定 (L2 > L1 互斥)
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

    # C. 抑制项判定 (3级 > 2级 > 1级 互斥)
    found_suppression = False
    # 优先检测3级
    for i in range(len(seq) - 3):
        window = seq[i:i+4]
        if len(window) >= 4 and window.count(0) >= 2:
            p = -25 if i <= 2 else -20
            score += p
            score_reasons.append(f"3级枯竭" + ("(开局)" if i <= 2 else "") + f"({p})")
            found_suppression = True
            break 
    # 若无3级，检测2级和1级
    if not found_suppression:
        for i in range(len(seq) - 2):
            window3 = seq[i:i+3]
            if len(window3) >= 3:
                unconn3 = window3.count(0)
                if 1 <= unconn3 <= 2:
                    score -= 12
                    score_reasons.append("2级阻塞(-12)")
                    break
                elif all(0 < x <= 2 for x in window3):
                    score -= 5
                    score_reasons.append("1级平庸(-5)")
                    break

    # --- 第二层：红线判定层 (Red Line Tagging) ---
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if max_con >= 7: red_tags.append("自动化局(L3)")
    if max(seq) < 3: red_tags.append("全局枯竭")
    
    red_label = ",".join(red_tags) if red_tags else "无"

    # --- 第三层：综合判定层 (Final Decision) ---
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

# 3. Streamlit 侧边栏
with st.sidebar:
    st.header("⚙️ 审计参数")
    init_val = st.slider("初始基准分", 0, 100, 60)
    st.divider()
    uploaded_file = st.file_uploader("上传 Excel 或 CSV 文件", type=["xlsx", "csv"])

# 4. 主页面逻辑
if uploaded_file:
    # 读取文件
    if uploaded_file.name.endswith('.xlsx'):
        df = pd.read_excel(uploaded_file)
    else:
        df = pd.read_csv(uploaded_file)
    
    st.success(f"成功读取 {len(df)} 条数据")

    # 执行审计 (分层返回结果)
    with st.spinner('分层判定计算中...'):
        audit_res = df.apply(lambda r: pd.Series(audit_layered_v1_1(r, init_val)), axis=1)
        df[['逻辑得分', '审计结果', '红线详情', '得分构成', '最终结论理由']] = audit_res

    # A. 准入排行榜
    st.subheader("📊 解集准入排行榜")
    summary = df.groupby(['解集ID', '难度']).agg(
        μ_逻辑得分=('逻辑得分', 'mean'),
        σ2_得分方差=('逻辑得分', 'var'),
        红线率=('红线详情', lambda x: (x != "无").mean())
    ).reset_index()

    summary['准入判定'] = summary.apply(
        lambda r: "✅ 准入" if r['μ_逻辑得分'] >= 45 and r['σ2_得分方差'] <= 20 and r['红线率'] < 0.15 else "❌ 拒绝", axis=1
    )
    st.dataframe(summary.style.highlight_max(axis=0, subset=['μ_逻辑得分']), use_container_width=True)

    # B. 详细审计明细 (展示得分与红线的分层)
    st.divider()
    st.subheader("🔍 详细审计明细 (前100条)")
    display_cols = ['解集ID', '测试轮次', '难度', '逻辑得分', '红线详情', '审计结果', '得分构成', '最终结论理由']
    st.dataframe(df[display_cols].head(100), use_container_width=True)

    # C. 数据导出
    csv = df.to_csv(index=False).encode('utf_8_sig')
    st.download_button("📥 下载完整审计报告", csv, "Audit_Report.csv", "text/csv")

else:
    st.info("请在左侧上传数据文件。系统将根据 初始分60 进行逻辑打分，并独立扫描红线。")

