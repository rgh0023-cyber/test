import streamlit as st
import pandas as pd
import numpy as np

# 1. 页面配置
st.set_page_config(page_title="Tripeaks 审计系统 V1.6.3", layout="wide")
st.title("🎴 Tripeaks 关卡审计系统 V1.6.3")

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
    return mu, var, (np.sqrt(var) / mu) if mu > 0 else 0

# --- 审计引擎 ---
def audit_engine(row, init_score):
    try:
        seq_raw = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']; diff = row['难度']; actual = str(row['实际结果'])
    except: return 0, "拒绝", "解析失败", "", 0, 0, 0, 0, 0, 0

    score = init_score
    reasons = []
    # A. 基础加分
    if sum(seq[:3]) >= 4: score += 5; reasons.append("破冰")
    if any(x >= 3 for x in seq[-5:]): score += 5; reasons.append("收割")
    if len(seq) >= 7 and max(seq) in seq[6:]: score += 5; reasons.append("翻盘")
    # B. 接力
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    relay = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx)-1):
            if (eff_idx[i+1]-eff_idx[i]-1) <= 1: relay += 1
    if relay >= 3: score += 10; reasons.append(f"接力x{relay}")
    elif relay == 2: score += 7; reasons.append(f"接力x2")
    elif relay == 1: score += 5; reasons.append("接力x1")
    # C. 贫瘠区
    boundaries = [-1] + eff_idx + [len(seq)]
    c1, c2, c3 = 0, 0, 0
    for j in range(len(boundaries)-1):
        start, end = boundaries[j]+1, boundaries[j+1]
        inter = seq[start:end]
        if inter:
            L, Z = len(inter), inter.count(0)
            if L >= 6 or (L >= 4 and Z >= 3): c3 += 1; score -= 20; reasons.append("3级")
            elif L == 5 or (3 <= L <= 4 and Z == 2): c2 += 1; score -= 9; reasons.append("2级")
            elif L >= 3: c1 += 1; score -= 5; reasons.append("1级")
    # D. 投喂 & 红线
    f1, f2, red_auto = 0, 0, False
    con_list = []
    cur = 0
    for x in seq:
        if x > 0: cur += 1
        else:
            if cur > 0: con_list.append(cur); 
            cur = 0
    if cur > 0: con_list.append(cur)
    for fl in con_list:
        if fl >= 7: red_auto = True
        elif 5 <= fl <= 6: f2 += 1; score -= 9; reasons.append("L2投喂")
        elif fl == 4: f1 += 1; score -= 3; reasons.append("L1投喂")
    
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (diff
