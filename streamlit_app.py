import streamlit as st
import pandas as pd

# 1. 设置网页标题
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.1")

# 2. 侧边栏配置参数
with st.sidebar:
    st.header("审计参数设置")
    init_score = st.slider("初始分", 0, 100, 60)
    pass_score = st.number_input("合格分数线", value=50)
    redline_ratio = st.slider("最大容忍红线率 (%)", 0, 100, 15) / 100

# 3. 文件上传器
uploaded_file = st.file_uploader("请上传跑关数据文件 (Excel 或 CSV)", type=["xlsx", "csv"])

if uploaded_file:
    df = pd.read_excel(uploaded_file) if "xlsx" in uploaded_file.name else pd.read_csv(uploaded_file)
    
    # 这里运行我们之前写好的 V1.1 审计逻辑函数
    # result_df, summary_df = run_audit_system(df, init_score)
    
    # 4. 浏览器实时展示结论
    st.subheader("📊 审计准入排行榜")
    st.dataframe(summary_df.style.highlight_max(axis=0, subset=['得分均值'])) 

    # 5. 可视化图表：展示分值分布
    st.line_chart(summary_df['得分均值'])
    
    # 6. 一键导出
    st.download_button("下载完整审计报告", data=result_df.to_csv(), file_name="audit_report.csv")