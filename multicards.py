import streamlit as st
import pandas as pd
import numpy as np
import chardet
import io

# 1. 页面配置
st.set_page_config(page_title="Tripeaks 算法对比平台 V1.9.3", layout="wide")
st.title("🎴 Tripeaks 审计与对比平台 (KeyError 修复版)")

# --- 辅助函数：模糊匹配列名 ---
def get_col(df, target_names):
    """
    在 DataFrame 中寻找可能的列名，解决中英文括号、空格、编码带来的 KeyError
    """
    for col in df.columns:
        clean_col = str(col).strip()
        for target in target_names:
            if target in clean_col:
                return col
    return None

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

# --- 核心审计引擎 ---
def audit_engine(row, col_map, base_init_score):
    try:
        # 使用模糊匹配后的列名提取数据
        seq_raw = str(row[col_map['seq']])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row[col_map['desk']]
        diff = row[col_map['diff']]
        actual = str(row[col_map['act']])
    except Exception as e:
        return 0, f"数据行解析失败", 0, 0, 0, 0, 0, 0

    score = base_init_score
    # --- 逻辑运算 (保持之前版本) ---
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    if sum(seq[:3]) >= 4: score += 5
    if any(x >= 3 for x in seq[-5:]): score += 5
    if len(seq) >= 7 and max(seq) in seq[6:]: score += 5
    
    relay = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx)-1):
            if (eff_idx[i+1]-eff_idx[i]-1) <= 1: relay += 1
    score += (10 if relay >= 3 else 7 if relay == 2 else 5 if relay == 1 else 0)

    c1, c2, c3 = 0, 0, 0
    boundaries = [-1] + eff_idx + [len(seq)]
    for j in range(len(boundaries)-1):
        start, end = boundaries[j]+1, boundaries[j+1]
        inter = seq[start:end]
        if inter:
            L, Z = len(inter), inter.count(0)
            if L >= 6 or (L >= 4 and Z >= 3): c3 += 1; score -= (25 if start <= 2 else 20)
            elif L == 5 or (3 <= L <= 4 and Z == 2): c2 += 1; score -= 9
            elif L >= 3: c1 += 1; score -= 5

    f1, f2, red_auto = 0, 0, False
    con_list = []
    cur = 0
    for x in seq:
        if x > 0: cur += 1
        else:
            if cur > 0: con_list.append(cur); cur = 0
    if cur > 0: con_list.append(cur)
    for fl in con_list:
        if fl >= 7: red_auto = True
        elif 5 <= fl <= 6: f2 += 1; score -= 9
        elif fl == 4: f1 += 1; score -= 3

    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (diff <= 30 and "失败" in actual) or (diff >= 40 and "胜利" in actual): red_tags.append("逻辑违逆")
    
    return score, ",".join(red_tags) if red_tags else "通过", c1, c2, c3, relay, f1, f2

# --- 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 参数配置")
    base_init_score = st.slider("审计初始分", 0, 100, 60)
    mu_threshold = st.slider("及格门槛 (μ)", 0, 100, 70)
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大 CV", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差", 10, 100, 25)
    uploaded_files = st.file_uploader("📂 上传数据", type=["xlsx", "csv"], accept_multiple_files=True)

# --- 主逻辑 ---
if uploaded_files:
    dfs = []
    for f in uploaded_files:
        try:
            if f.name.endswith('.xlsx'):
                curr_df = pd.read_excel(f)
            else:
                raw = f.read(); enc = chardet.detect(raw)['encoding'] or 'utf-8'
                curr_df = pd.read_csv(io.BytesIO(raw), encoding=enc)
            curr_df['源文件'] = f.name
            dfs.append(curr_df)
        except Exception as e: st.error(f"读取 {f.name} 失败: {e}")

    if dfs:
        df = pd.concat(dfs, ignore_index=True)
        
        # === 核心：动态列名映射，防止 KeyError ===
        col_map = {
            'seq': get_col(df, ['全部连击', '全部连击数', 'Combo Sequence']),
            'desk': get_col(df, ['初始桌面牌', 'Initial Desk']),
            'diff': get_col(df, ['难度', 'Difficulty']),
            'act': get_col(df, ['实际结果', 'Result']),
            'hand': get_col(df, ['初始手牌', 'Hand Cards', '手牌数'])
        }

        # 检查关键列是否缺失
        missing = [k for k, v in col_map.items() if v is None]
        if missing:
            st.error(f"文件中缺少关键列: {missing}。请检查列名是否包含：全部连击、初始桌面牌、难度、实际结果、初始手牌。")
            st.write("当前检测到的列名:", list(df.columns))
        else:
            with st.spinner('审计计算中...'):
                # 传入 col_map 进行安全取值
                res = df.apply(lambda r: pd.Series(audit_engine(r, col_map, base_init_score)), axis=1)
                df[['得分', '红线判定', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = res

            # --- 展示看板与详情 (逻辑复用 V1.9.2) ---
            st.header("📊 策略看板")
            # 使用映射后的列名聚合
            h_col = col_map['hand']
            summary = []
            for h_val, gp in df.groupby(h_col):
                jids = gp.groupby('解集ID').apply(lambda x: calculate_advanced_stats(x['得分'], trim_val)[0] >= mu_threshold).sum()
                summary.append({"初始手牌": h_val, "牌集总数": gp['解集ID'].nunique(), "通过率": jids/gp['解集ID'].nunique()})
            st.table(pd.DataFrame(summary))
            
            st.divider()
            st.subheader("🔍 详细流水")
            st.dataframe(df[[h_col, '解集ID', '得分', '红线判定']])
