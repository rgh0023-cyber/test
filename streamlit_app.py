import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面配置
st.set_page_config(page_title="关卡审计 V1.1", layout="wide")
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.1")

# 2. 核心逻辑函数定义
def audit_logic_v1_1(row, init_score):
    try:
        # 将序列字符串转为数字列表
        seq = [int(x) for x in str(row['全部连击（每张手牌的连击数）']).split(',')]
    except:
        return 0, "拒绝", "序列格式解析失败"
    
    desk_init = row['初始桌面牌']
    score = init_score
    reasons = []

    # --- 红线判定 (一票否决) ---
    max_c = max(seq)
    if max_c >= desk_init * 0.4:
        return 0, "拒绝", f"红线：数值崩坏(Max:{max_c})"
    
    # 连续性计算 (用于投喂等级判定)
    con_list = []
    cur = 0
    for x in seq:
        if x > 0: cur += 1
        else:
            if cur > 0: con_list.append(cur)
            cur = 0
    if cur > 0: con_list.append(cur)
    max_con = max(con_list) if con_list else 0

    if max_con >= 7: return 0, "拒绝", "红线：自动化局(L3)"
    if max_c < 3: return 0, "拒绝", "红线：全局枯竭"

    # --- 投喂项判定 (L2 > L1 互斥) ---
    if 5 <= max_con <= 6:
        score -= 20
        reasons.append("L2过度投喂")
    elif con_list.count(4) >= 3:
        score -= 10
        reasons.append("L1高频投喂")

    # --- 心流抑制项判定 (3级 > 2级 > 1级 互斥) ---
    found_suppression = False
    for i in range(len(seq) - 3):
        window = seq[i:i+4]
        if len(window) >= 4 and window.count(0) >= 2:
            p = -25 if i <= 2 else -20
            score += p
            reasons.append(f"3级枯竭" + ("(开局)" if i <= 2 else ""))
            found_suppression = True
            break 
            
    if not found_suppression:
        for i in range(len(seq) - 2):
            w3 = seq[i:i+3]
            if len(w3) >= 3:
                unconn3 = w3.count(0)
                if 1 <= unconn3 <= 2:
                    score -= 12
                    reasons.append("2级阻塞")
                    break
                elif all(0 < x <= 2 for x in w3):
                    score -= 5
                    reasons.append("1级平庸")
                    break

    # --- 正向加分项 ---
    if sum(seq[:3]) >= 4: score += 5
    if any(x >= 3 for x in seq[-5:]): score += 5
    if max_c in seq[6:]: score += 5

    return score, "通过", "|".join(reasons) if reasons else "正常"

# 3. 侧边栏配置
with st.sidebar:
    st.header("⚙️ 参数配置")
    init_val = st.slider("初始基准分", 0, 100, 60)
    st.divider()
    uploaded_file = st.file_uploader("📂 上传跑关文件 (Excel/CSV)", type=["xlsx", "csv"])

# 4. 运行逻辑
if uploaded_file:
    # 读取文件
    if "xlsx" in uploaded_file.name:
        df = pd.read_excel(uploaded_file)
    else:
        df = pd.read_csv(uploaded_file)
    
    st.success(f"文件上传成功！共识别 {len(df)} 条数据。")

    # 执行审计逻辑并生成新列
    with st.spinner('审计算法运行中...'):
        results = df.apply(lambda r: pd.Series(audit_logic_v1_1(r, init_val)), axis=1)
        df[['审计得分', '审计结果', '详细理由']] = results

    # 5. 聚合汇总表 (修正了变量名不匹配问题)
    st.subheader("📊 解集准入概览")
    
    summary_df = df.groupby(['解集ID', '难度']).agg(
        得分均值=('审计得分', 'mean'),
        得分方差=('审计得分', 'var'),
        红线率=('审计结果', lambda x: (x == "拒绝").mean())
    ).reset_index()
    
    # 准入规则判定
    summary_df['最终结论'] = summary_df.apply(
        lambda r: "✅ 准入" if r['得分均值'] >= 50 and r['得分方差'] <= 15 and r['红线率'] < 0.15 else "❌ 拒绝", 
        axis=1
    )

    # 显示汇总表并高亮最高分
    st.dataframe(summary_df.style.highlight_max(axis=0, subset=['得分均值']), use_container_width=True)

    # 6. 详细明细展示
    st.divider()
    st.subheader("📝 详细审计流水")
    st.write("点击列头可进行排序筛选：")
    st.dataframe(df[['解集ID', '测试轮次', '难度', '审计得分', '审计结果', '详细理由']], use_container_width=True)

    # 7. 下载报告
    csv = df.to_csv(index=False).encode('utf_8_sig')
    st.download_button("📥 下载完整审计报告 (CSV)", csv, "audit_report.csv", "text/csv")

else:
    st.info("👋 欢迎！请在左侧侧边栏上传您的数据文件开始审计。")
