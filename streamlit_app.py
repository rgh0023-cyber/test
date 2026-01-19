import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面基本配置
st.set_page_config(page_title="Tripeaks 关卡审计 V1.5.1", layout="wide")
st.title("🎴 Tripeaks 关卡体验自动化审计系统 V1.5.1")
st.markdown("---")

# --- 核心统计函数：支持动态百分比截断 ---
def calculate_trimmed_stats(series, trim_percentage):
    if len(series) < 5:  # 样本量极小时不做截断
        return series.mean(), series.var()
    
    sorted_series = np.sort(series)
    n = len(sorted_series)
    # 计算两侧剔除的数量
    trim_count = int(n * (trim_percentage / 100))
    
    if trim_count == 0:
        return series.mean(), series.var()
        
    trimmed_data = sorted_series[trim_count : n - trim_count]
    return np.mean(trimmed_data), np.var(trimmed_data)

# --- 核心审计逻辑：全量分级累计版 ---
def audit_engine_v1_5_1(row, init_score):
    try:
        seq_str = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_str.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']
        difficulty = row['难度']
        actual_result = str(row['实际结果'])
    except:
        return 0, "拒绝", "解析失败", "格式错误", 0, 0, 0, 0, 0, 0

    score = init_score
    score_reasons = []

    # A. 正向加分项
    if sum(seq[:3]) >= 4:
        score += 5
        score_reasons.append("开局破冰(+5)")
    if any(x >= 3 for x in seq[-5:]):
        score += 5
        score_reasons.append("尾部收割(+5)")
    if len(seq) >= 7 and max(seq) in seq[6:]:
        score += 5
        score_reasons.append("逆风翻盘(+5)")

    # B. 贫瘠区分析：全量统计 (抑制项 & 接力)
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    boundaries = [-1] + eff_idx + [len(seq)]
    c1, c2, c3, relay_count = 0, 0, 0, 0
    
    for j in range(len(boundaries) - 1):
        start, end = boundaries[j] + 1, boundaries[j+1]
        inter = seq[start:end]
        if len(inter) > 0:
            L, Z = len(inter), inter.count(0)
            
            # 抑制项分级 (3 > 2 > 1 互斥)
            if L >= 6 or (L >= 4 and Z >= 3):
                c3 += 1
                p = -25 if start <= 2 else -20
                score
