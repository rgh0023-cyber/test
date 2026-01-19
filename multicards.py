import streamlit as st
import pandas as pd
import numpy as np
import chardet  # 用于自动识别文件编码
import io

# 1. 页面配置
st.set_page_config(page_title="Tripeaks 算法对比平台 V1.9.2", layout="wide")
st.title("🎴 Tripeaks 关卡审计与算法策略对比平台")

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
def audit_engine(row, base_init_score):
    try:
        # 兼容处理字段名中可能存在的不可见字符
        seq_raw = str(row['全部连击（每张手牌的连击数）'])
        seq = [int(x.strip()) for x in seq_raw.split(',') if x.strip() != ""]
        desk_init = row['初始桌面牌']
        diff = row['难度']
        actual = str(row['实际结果'])
    except Exception as e:
        return 0, f"解析失败: {str(e)}", 0, 0, 0, 0, 0, 0

    score = base_init_score
    # --- A. 正向体验项 ---
    if sum(seq[:3]) >= 4: score += 5
    if any(x >= 3 for x in seq[-5:]): score += 5
    if len(seq) >= 7 and max(seq) in seq[6:]: score += 5

    # --- B. 连击接力 ---
    eff_idx = [i for i, x in enumerate(seq) if x >= 3]
    relay = 0
    if len(eff_idx) >= 2:
        for i in range(len(eff_idx)-1):
            if (eff_idx[i+1]-eff_idx[i]-1) <= 1: relay += 1
    score += (10 if relay >= 3 else 7 if relay == 2 else 5 if relay == 1 else 0)

    # --- C. 贫瘠区扣分 (c1, c2, c3) ---
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

    # --- D. 投喂项判定 (f1, f2, f3-红线) ---
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

    # --- E. 红线判定 ---
    red_tags = []
    if max(seq) >= desk_init * 0.4: red_tags.append("数值崩坏")
    if red_auto: red_tags.append("自动化局")
    if (diff <= 30 and "失败" in actual) or (diff >= 40 and "胜利" in actual): red_tags.append("逻辑违逆")
    
    return score, ",".join(red_tags) if red_tags else "通过", c1, c2, c3, relay, f1, f2

# --- 2. 侧边栏配置 ---
with st.sidebar:
    st.header("⚙️ 审计全局参数")
    base_init_score = st.slider("审计初始分 (Base)", 0, 100, 60)
    mu_threshold = st.slider("及格门槛 (μ)", 0, 100, 70)
    st.divider()
    trim_val = st.slider("截断比例 (%)", 0, 30, 15)
    cv_limit = st.slider("最大 CV (稳定性)", 0.05, 0.50, 0.20)
    var_limit = st.slider("最大方差保护", 10, 100, 25)
    st.divider()
    uploaded_files = st.file_uploader("📂 上传多个牌集数据 (xlsx/csv)", type=["xlsx", "csv"], accept_multiple_files=True)

# --- 3. 稳健文件读取逻辑 ---
if uploaded_files:
    all_data_list = []
    for uploaded_file in uploaded_files:
        try:
            if uploaded_file.name.endswith('.xlsx'):
                temp_df = pd.read_excel(uploaded_file)
            else:
                # 三重读取保险
                content = uploaded_file.read()
                # 1. 尝试检测编码
                detected = chardet.detect(content)
                enc = detected['encoding'] if detected['encoding'] else 'utf-8'
                try:
                    temp_df = pd.read_csv(io.BytesIO(content), encoding=enc)
                except:
                    try:
                        # 2. 尝试常用中文编码 GBK
                        temp_df = pd.read_csv(io.BytesIO(content), encoding='gbk')
                    except:
                        # 3. 尝试带有 BOM 的 UTF-8
                        temp_df = pd.read_csv(io.BytesIO(content), encoding='utf-8-sig')
            
            temp_df['源文件'] = uploaded_file.name
            all_data_list.append(temp_df)
        except Exception as e:
            st.error(f"无法读取文件 {uploaded_file.name}: {e}")

    if all_data_list:
        df = pd.concat(all_data_list, ignore_index=True)
        # 字段自动映射（适配'初始手牌'和'初始手牌数'）
        if '初始手牌' not in df.columns and '初始手牌数' in df.columns:
            df = df.rename(columns={'初始手牌数': '初始手牌'})

        with st.spinner('执行算法策略并行审计...'):
            res = df.apply(lambda r: pd.Series(audit_engine(r, base_init_score)), axis=1)
            df[['得分', '红线判定', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = res

        # === 4.1 算法策略看板 ===
        st.header("📊 算法策略看板")
        strategy_summary = []
        for (hand_count), gp_hand in df.groupby('初始手牌'):
            total_jids = gp_hand['解集ID'].nunique()
            jid_pass_results = []
            for jid, gp in gp_hand.groupby('解集ID'):
                mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
                red_rate = (gp['红线判定'] != "通过").mean()
                # 准入核心逻辑
                is_pass = mu >= mu_threshold and (cv <= cv_limit or var <= var_limit) and red_rate < 0.15
                jid_pass_results.append(1 if is_pass else 0)
            
            p_rate = sum(jid_pass_results) / total_jids if total_jids > 0 else 0
            strategy_summary.append({
                "初始手牌数": hand_count,
                "牌集总数": total_jids,
                "✅ 通过数": sum(jid_pass_results),
                "❌ 拒绝数": total_jids - sum(jid_pass_results),
                "通过率": p_rate,
                "审计均分": gp_hand['得分'].mean(),
                "平均红线率": (gp_hand['红线判定'] != "通过").mean()
            })
        
        st.dataframe(pd.DataFrame(strategy_summary).style.background_gradient(cmap='RdYlGn', subset=['通过率'])
                     .format({"通过率": "{:.1%}", "平均红线率": "{:.1%}", "审计均分": "{:.2f}"}), use_container_width=True)

        # === 4.2 筛选与明细排行 ===
        st.divider()
        st.subheader("🎯 牌集详情排行")
        
        col_f1, col_f2 = st.columns([1, 2])
        with col_f1:
            hand_options = sorted(df['初始手牌'].unique())
            selected_hands = st.multiselect("筛选初始手牌维度：", hand_options, default=hand_options)
        with col_f2:
            status_filter = st.radio("准入判定过滤：", ["全部", "通过", "拒绝"], horizontal=True)

        summary_details = []
        for (h_val, jid, diff), gp in df.groupby(['初始手牌', '解集ID', '难度']):
            if h_val not in selected_hands: continue
            mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
            red_mask = gp['红线判定'] != "通过"
            red_rate = red_mask.mean()
            
            # 唯一拒绝理由判定
            reason = "✅ 通过"
            if red_rate >= 0.15:
                reason = f"❌ 红线拒绝 ({gp[red_mask]['红线判定'].mode()[0]})"
            elif mu < mu_threshold:
                reason = "❌ 分值拒绝"
            elif cv > cv_limit:
                reason = "❌ 稳定性拒绝"
            
            if status_filter == "全部" or (status_filter == "通过" and "✅" in reason) or (status_filter == "拒绝" and "❌" in reason):
                summary_details.append({
                    "手牌数": h_val, "解集ID": jid, "难度": diff, "μ_截断均值": mu, "CV": cv, 
                    "最终结论": reason, "3级枯竭均值": gp['c3'].mean(), "红线率": red_rate
                })
        
        if summary_details:
            st.dataframe(pd.DataFrame(summary_details).style.applymap(lambda x: 'color: #ff4b4b' if '❌' in str(x) else 'color: #008000', subset=['最终结论'])
                         .format({"红线率":"{:.1%}", "μ_截断均值":"{:.2f}", "CV":"{:.3f}"}), use_container_width=True)

        # === 4.3 跑关流水追踪 ===
        st.divider()
        st.subheader("🔍 跑关原始流水 (已联动上方筛选)")
        track_mask = (df['初始手牌'].isin(selected_hands))
        st.dataframe(df[track_mask][['源文件', '初始手牌', '解集ID', '难度', '得分', '红线判定', '构成']], use_container_width=True)

else:
    st.info("👋 请在左侧上传文件。支持同时上传多个不同算法参数（手牌数）的数据进行对比。")
