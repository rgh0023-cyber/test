import streamlit as st
import pandas as pd
import numpy as np
import chardet
import io

# 1. 页面配置
st.set_page_config(page_title="Tripeaks 算法对比平台 V1.9.15", layout="wide")
st.title("🎴 Tripeaks 算法对比与深度审计平台 V1.9.15")

# --- 【底层工具函数】 ---
def get_col_safe(df, target_keywords):
    """确保模糊匹配列名，防止 NameError"""
    for col in df.columns:
        c_str = str(col).replace(" ", "").replace("\n", "")
        for key in target_keywords:
            if key in c_str: return col
    return None

def calculate_advanced_stats(series, trim_percentage):
    """核心统计引擎：15% 截断统计法"""
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

def audit_engine(row, col_map, base_init_score, burst_window, burst_threshold):
    """核心审计引擎：计算得分与各项红线"""
    try:
        seq_raw = str(row[col_map['seq']])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row[col_map['desk']]
        diff = row[col_map['diff']]
        actual = str(row[col_map['act']])
    except: return 0, "解析失败", 0, 0, 0, 0, 0, 0, 0

    score = base_init_score
    # A. 基础加分/扣分 (锁定逻辑)
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

    # E. 红线判定
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (diff <= 30 and "失败" in actual) or (diff >= 40 and "胜利" in actual): red_tags.append("逻辑违逆")
    
    # 消除集中度 (滑动窗口包含0)
    total_eliminated = sum(seq)
    max_burst_rate = 0.0
    if total_eliminated > 0 and len(seq) >= burst_window:
        for i in range(len(seq) - burst_window + 1):
            window_sum = sum(seq[i : i + burst_window])
            rate = window_sum / total_eliminated
            if rate > max_burst_rate: max_burst_rate = rate
        if max_burst_rate >= (burst_threshold / 100):
            red_tags.append("消除高度集中")
    
    return score, ",".join(red_tags) if red_tags else "通过", c1, c2, c3, relay, f1, f2, max_burst_rate

# --- 2. 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 审计全局参数")
    base_score = st.slider("审计初始分", 0, 100, 60)
    mu_limit = st.slider("及格门槛 (μ)", 0, 100, 70)
    st.divider()
    st.subheader("⚠️ 节奏风控红线")
    burst_win = st.number_input("连续手牌数 (窗口)", 1, 10, 3)
    burst_thr = st.slider("消除占比阈值 (%)", 0, 100, 80)
    st.divider()
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大 CV (稳定性)", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差保护", 10, 100, 25)
    uploaded_files = st.file_uploader("📂 上传测试数据", type=["xlsx", "csv"], accept_multiple_files=True)

# --- 3. 计算与对齐流程 ---
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
            'seq': get_col_safe(df, ['全部连击']), 'desk': get_col_safe(df, ['初始桌面牌']),
            'diff': get_col_safe(df, ['难度']), 'act': get_col_safe(df, ['实际结果']),
            'hand': get_col_safe(df, ['初始手牌']), 'jid': get_col_safe(df, ['解集ID'])
        }

        with st.spinner('执行多维风险概率审计...'):
            # 基础局审计
            audit_res = df.apply(lambda r: pd.Series(audit_engine(r, col_map, base_score, burst_win, burst_thr)), axis=1)
            df[['得分', '红线判定', 'c1', 'c2', 'c3', '接力', 'f1', 'f2', 'mbr']] = audit_res

            fact_list = []
            h_col, j_col, d_col = col_map['hand'], col_map['jid'], col_map['diff']
            for (f_name, h_val, j_id, d_val), gp in df.groupby(['__ORIGIN__', h_col, j_col, d_col]):
                mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
                total_runs = len(gp)
                is_red = gp['红线判定'] != "通过"
                
                # 计算各红线触发概率
                prob_break = (gp['红线判定'].str.contains("数值崩坏")).sum() / total_runs
                prob_auto = (gp['红线判定'].str.contains("自动化局")).sum() / total_runs
                prob_logic = (gp['红线判定'].str.contains("逻辑违逆")).sum() / total_runs
                prob_burst = (gp['红线判定'].str.contains("消除高度集中")).sum() / total_runs
                total_red_rate = is_red.mean()
                
                # 判定结论
                reason = "✅ 通过"
                if total_red_rate >= 0.15: 
                    reason = f"❌ 红线拒绝 ({gp[is_red]['红线判定'].mode()[0]})"
                elif mu < mu_limit: reason = "❌ 分值拒绝"
                elif cv > cv_limit: reason = "❌ 稳定性拒绝"
                elif var > var_limit: reason = "❌ 波动拒绝"
                
                fact_list.append({
                    "源文件": f_name, "初始手牌": h_val, "解集ID": j_id, "难度": d_val,
                    "μ_均值": mu, "σ²_方差": var, "CV": cv, "判定结论": reason,
                    "总红线率": total_red_rate, "数值崩坏率": prob_break,
                    "自动化率": prob_auto, "逻辑违逆率": prob_logic, "爆发集中率": prob_burst,
                    "is_pass": 1 if "✅" in reason else 0
                })
            df_fact = pd.DataFrame(fact_list)

        # === 4.1 总体算法策略看板 ===
        st.header("📊 算法策略看板")
        summary_rows = []
        for h_v, gp_h in df_fact.groupby('初始手牌'):
            # 严格基于 df_fact 统计行数，确保看板与明细对齐
            diff_pass = gp_h[gp_h['is_pass'] == 1].groupby('难度').size().to_dict()
            total_pass_jid = gp_h[gp_h['is_pass'] == 1].drop_duplicates(subset=['源文件', '解集ID']).shape[0]
            total_unique_jid = gp_h.drop_duplicates(subset=['源文件', '解集ID']).shape[0]

            row = {"初始手牌数": h_v, "牌集总数": total_unique_jid, "✅ 总通过数(去重)": total_pass_jid, 
                   "资源覆盖率": total_pass_jid / total_unique_jid if total_unique_jid > 0 else 0}
            for d in sorted(df_fact['难度'].unique()):
                row[f"难度{d}通过"] = diff_pass.get(d,
