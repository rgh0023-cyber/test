import streamlit as st
import pandas as pd
import numpy as np
import chardet
import io

# 1. 页面配置
st.set_page_config(page_title="Tripeaks 算法对比平台 V1.9.4", layout="wide")
st.title("🎴 Tripeaks 算法对比与深度审计平台 V1.9.4")

# --- 核心：列名自动纠错识别引擎 ---
def get_col_safe(df, target_keywords):
    """防止编码乱码或空格导致的 KeyError"""
    for col in df.columns:
        c_str = str(col).replace(" ", "").replace("\n", "")
        for key in target_keywords:
            if key in c_str:
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
        seq_raw = str(row[col_map['seq']])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row[col_map['desk']]
        diff = row[col_map['diff']]
        actual = str(row[col_map['act']])
    except: return 0, "解析失败", 0, 0, 0, 0, 0, 0

    score = base_init_score
    # A. 正向加分
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

    # C. 贫瘠区扣分 (c1, c2, c3)
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

    # D. 投喂项
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

# --- 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 审计全局参数")
    base_score = st.slider("审计初始分 (Base)", 0, 100, 60)
    mu_limit = st.slider("及格门槛 (μ)", 0, 100, 70)
    st.divider()
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大 CV (稳定性)", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差保护", 10, 100, 25)
    uploaded_files = st.file_uploader("📂 上传多个数据 (xlsx/csv)", type=["xlsx", "csv"], accept_multiple_files=True)

# --- 主计算流 ---
if uploaded_files:
    dfs = []
    for f in uploaded_files:
        try:
            if f.name.endswith('.xlsx'): curr_df = pd.read_excel(f)
            else:
                raw = f.read(); enc = chardet.detect(raw)['encoding'] or 'utf-8'
                curr_df = pd.read_csv(io.BytesIO(raw), encoding=enc)
            curr_df['源文件'] = f.name
            dfs.append(curr_df)
        except Exception as e: st.error(f"加载 {f.name} 失败: {e}")

    if dfs:
        df = pd.concat(dfs, ignore_index=True)
        # 建立列名映射图 (解决 KeyError 核心)
        col_map = {
            'seq': get_col_safe(df, ['全部连击', 'ComboSequence']),
            'desk': get_col_safe(df, ['初始桌面牌', 'InitialDesk']),
            'diff': get_col_safe(df, ['难度', 'Difficulty']),
            'act': get_col_safe(df, ['实际结果', 'Result']),
            'hand': get_col_safe(df, ['初始手牌', 'HandCards']),
            'jid': get_col_safe(df, ['解集ID', 'SetID'])
        }

        if None in col_map.values():
            st.error(f"检测到关键列缺失，请检查文件。当前映射结果：{col_map}")
        else:
            with st.spinner('算法对比审计计算中...'):
                res = df.apply(lambda r: pd.Series(audit_engine(r, col_map, base_score)), axis=1)
                df[['得分', '红线判定', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = res

            # === 1. 总体统计看板 (需求2.1) ===
            st.header("📊 算法策略看板")
            strat_list = []
            h_col, j_col = col_map['hand'], col_map['jid']
            for h_val, gp_h in df.groupby(h_col):
                total_jids = gp_h[j_col].nunique()
                pass_jids = 0
                for jid, gp in gp_h.groupby(j_col):
                    mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
                    red_rate = (gp['红线判定'] != "通过").mean()
                    if mu >= mu_limit and (cv <= cv_limit or var <= var_limit) and red_rate < 0.15:
                        pass_jids += 1
                strat_list.append({
                    "初始手牌数": h_val, "牌集总数": total_jids, "✅ 通过牌集": pass_jids,
                    "通过率": pass_jids/total_jids if total_jids>0 else 0,
                    "审计均分": gp_h['得分'].mean(), "红线率": (gp_h['红线判定'] != "通过").mean()
                })
            st.dataframe(pd.DataFrame(strat_list).style.format({"通过率":"{:.1%}", "红线率":"{:.1%}", "审计均分":"{:.2f}"}).background_gradient(cmap='RdYlGn', subset=['通过率']), use_container_width=True)

            # === 2. 详情排行与层级结论 ===
            st.divider()
            st.subheader("🎯 牌集明细排行")
            
            # 筛选器复活 (需求2.2)
            c1, c2 = st.columns([1, 2])
            with c1: f_hands = st.multiselect("手牌数维度筛选", sorted(df[h_col].unique()), default=sorted(df[h_col].unique()))
            with c2: f_status = st.radio("判定过滤", ["全部", "通过", "拒绝"], horizontal=True)

            detailed_sum = []
            for (h_v, jid, diff), gp in df.groupby([h_col, j_col, col_map['diff']]):
                if h_v not in f_hands: continue
                mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
                red_mask = gp['红线判定'] != "通过"
                red_rate = red_mask.mean()
                
                # 层级拒绝理由 (需求核心)
                reason = "✅ 通过"
                if red_rate >= 0.15: reason = f"❌ 红线拒绝 ({gp[red_mask]['红线判定'].mode()[0]})"
                elif mu < mu_limit: reason = "❌ 分值拒绝"
                elif cv > cv_limit: reason = "❌ 稳定性拒绝"
                
                tag = "通过" if "✅" in reason else "拒绝"
                if f_status == "全部" or f_status == tag:
                    detailed_sum.append({
                        "手牌数": h_v, "解集ID": jid, "难度": diff, "μ_均值": mu, "CV": cv, 
                        "判定结论": reason, "3级枯竭均": gp['c3'].mean(), "红线率": red_rate
                    })
            
            if detailed_sum:
                st.dataframe(pd.DataFrame(detailed_sum).style.applymap(lambda x: 'color: #ff4b4b' if '❌' in str(x) else 'color: #008000', subset=['判定结论'])
                             .format({"μ_均值":"{:.2f}", "CV":"{:.3f}", "红线率":"{:.1%}", "3级枯竭均":"{:.1f}"}), use_container_width=True)

            # === 3. 跑关流水追踪 ===
            st.divider()
            st.subheader("🔍 跑关详细流水")
            st.dataframe(df[df[h_col].isin(f_hands)][['源文件', h_col, j_col, '得分', '红线判定', 'c3', '接力', col_map['seq']]], use_container_width=True)
