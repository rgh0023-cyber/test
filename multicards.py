import streamlit as st
import pandas as pd
import numpy as np
import chardet
import io

# 1. 页面配置
st.set_page_config(page_title="Tripeaks 算法对比平台 V1.9.11", layout="wide")
st.title("🎴 Tripeaks 算法对比与深度审计平台 V1.9.11")

# --- 【工具函数：确保无 NameError】 ---
def get_col_safe(df, target_keywords):
    """防止编码乱码或空格导致的 KeyError/NameError"""
    for col in df.columns:
        c_str = str(col).replace(" ", "").replace("\n", "")
        for key in target_keywords:
            if key in c_str:
                return col
    return None

def calculate_advanced_stats(series, trim_percentage):
    """底层统计引擎：15% 截断统计"""
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

def audit_engine(row, col_map, base_init_score):
    """底层审计评分引擎：计算单局得分与红线判定"""
    try:
        seq_raw = str(row[col_map['seq']])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row[col_map['desk']]
        diff = row[col_map['diff']]
        actual = str(row[col_map['act']])
    except: return 0, "解析失败", 0, 0, 0, 0, 0, 0

    score = base_init_score
    # A. 正向体验项
    if sum(seq[:3]) >= 4: score += 5
    if any(x >= 3 for x in seq[-5:]): score += 5
    if len(seq) >= 7 and max(seq) in seq[6:]: score += 5
    
    # B. 连击接力
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    relay = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx)-1):
            if (eff_idx[i+1]-eff_idx[i]-1) <= 1: relay += 1
    score += (10 if relay >= 3 else 7 if relay == 2 else 5 if relay == 1 else 0)

    # C. 贫瘠区扣分
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

    # D. 投喂项与自动化
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

    # E. 红线判定
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (diff <= 30 and "失败" in actual) or (diff >= 40 and "胜利" in actual): red_tags.append("逻辑违逆")
    
    return score, ",".join(red_tags) if red_tags else "通过", c1, c2, c3, relay, f1, f2

# --- 2. 侧边栏配置 ---
with st.sidebar:
    st.header("⚙️ 审计全局参数")
    base_score = st.slider("审计初始分 (Base)", 0, 100, 60)
    mu_limit = st.slider("及格门槛 (μ)", 0, 100, 70)
    st.divider()
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大 CV (稳定性)", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差保护", 10, 100, 25)
    uploaded_files = st.file_uploader("📂 上传多个数据 (xlsx/csv)", type=["xlsx", "csv"], accept_multiple_files=True)

# --- 3. 主计算与对齐逻辑 ---
if uploaded_files:
    all_raw_dfs = []
    for f in uploaded_files:
        try:
            if f.name.endswith('.xlsx'): t_df = pd.read_excel(f)
            else:
                raw_b = f.read(); enc = chardet.detect(raw_b)['encoding'] or 'utf-8'
                t_df = pd.read_csv(io.BytesIO(raw_b), encoding=enc)
            t_df['__ORIGIN__'] = f.name 
            all_raw_dfs.append(t_df)
        except: st.error(f"读取 {f.name} 失败")

    if all_raw_dfs:
        df = pd.concat(all_raw_dfs, ignore_index=True)
        col_map = {
            'seq': get_col_safe(df, ['全部连击']),
            'desk': get_col_safe(df, ['初始桌面牌']),
            'diff': get_col_safe(df, ['难度']),
            'act': get_col_safe(df, ['实际结果']),
            'hand': get_col_safe(df, ['初始手牌']),
            'jid': get_col_safe(df, ['解集ID'])
        }

        # 构建统一事实表
        with st.spinner('审计引擎计算中...'):
            res = df.apply(lambda r: pd.Series(audit_engine(r, col_map, base_score)), axis=1)
            df[['得分', '红线判定', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = res

            fact_records = []
            h_col, j_col, d_col = col_map['hand'], col_map['jid'], col_map['diff']
            for (f_name, h_val, j_id, d_val), gp in df.groupby(['__ORIGIN__', h_col, j_col, d_col]):
                mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
                red_m = gp['红线判定'] != "通过"
                
                reason = "✅ 通过"
                if red_m.mean() >= 0.15: reason = f"❌ 红线拒绝 ({gp[red_m]['红线判定'].mode()[0]})"
                elif mu < mu_limit: reason = "❌ 分值拒绝"
                elif cv > cv_limit: reason = "❌ 稳定性拒绝"
                elif var > var_limit: reason = "❌ 波动拒绝 (方差超标)"
                
                fact_records.append({
                    "源文件": f_name, "初始手牌": h_val, "解集ID": j_id, "难度": d_val,
                    "μ_均值": mu, "σ²_方差": var, "CV": cv, "判定结论": reason,
                    "is_pass": 1 if "✅" in reason else 0
                })
            df_fact = pd.DataFrame(fact_records)

        # === 4.1 总体算法策略看板 ===
        st.header("📊 算法策略看板")
        summary_rows = []
        for h_v, gp_h in df_fact.groupby('初始手牌'):
            diff_counts = gp_h[gp_h['is_pass'] == 1].groupby('难度').size().to_dict()
            total_pass_jid = gp_h[gp_h['is_pass'] == 1].drop_duplicates(subset=['源文件', '解集ID']).shape[0]
            total_unique_jid = gp_h.drop_duplicates(subset=['源文件', '解集ID']).shape[0]

            row = {"初始手牌数": h_v, "牌集总数": total_unique_jid, "✅ 总去重通过数": total_pass_jid, 
                   "资源覆盖率": total_pass_jid / total_unique_jid if total_unique_jid > 0 else 0}
            for d in sorted(df_fact['难度'].unique()):
                row[f"难度{d}通过"] = diff_counts.get(d, 0)
            summary_rows.append(row)
        
        st.dataframe(pd.DataFrame(summary_rows).style.format({"资源覆盖率":"{:.1%}"}), use_container_width=True)

        # === 4.2 牌集明细排行 ===
        st.divider()
        st.subheader("🎯 牌集明细排行")
        f_h = st.multiselect("手牌维度", sorted(df_fact['初始手牌'].unique()), default=sorted(df_fact['初始手牌'].unique()))
        f_s = st.radio("判定过滤", ["全部", "通过", "拒绝"], horizontal=True)

        view_df = df_fact[df_fact['初始手牌'].isin(f_h)].copy()
        if f_s == "通过": view_df = view_df[view_df['is_pass'] == 1]
        elif f_s == "拒绝": view_df = view_df[view_df['is_pass'] == 0]

        st.dataframe(view_df.drop(columns=['is_pass']).style.applymap(
            lambda x: 'color: #ff4b4b' if '❌' in str(x) else 'color: #008000', subset=['判定结论']
        ).format({"μ_均值":"{:.2f}", "σ²_方差":"{:.2f}", "CV":"{:.3f}"}), use_container_width=True)

        st.info(f"📊 数据核对：当前明细表共有 {view_df[view_df['is_pass']==1].shape[0]} 行通过记录。")
