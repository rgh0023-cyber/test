import streamlit as st
import pandas as pd
import numpy as np
import chardet
import io

# ... [保留 calculate_advanced_stats 和 audit_engine 函数逻辑] ...

if uploaded_files:
    # 1. 严格读取
    all_raw_dfs = []
    for f in uploaded_files:
        try:
            if f.name.endswith('.xlsx'): t_df = pd.read_excel(f)
            else:
                r = f.read(); enc = chardet.detect(r)['encoding'] or 'utf-8'
                t_df = pd.read_csv(io.BytesIO(r), encoding=enc)
            t_df['__FILE__'] = f.name # 内部标识列
            all_raw_dfs.append(t_df)
        except: st.error(f"读取 {f.name} 出错")

    if all_raw_dfs:
        full_df = pd.concat(all_raw_dfs, ignore_index=True)
        # 获取列名映射
        c_m = {
            'seq': get_col_safe(full_df, ['全部连击']),
            'desk': get_col_safe(full_df, ['初始桌面牌']),
            'diff': get_col_safe(full_df, ['难度']),
            'act': get_col_safe(full_df, ['实际结果']),
            'hand': get_col_safe(full_df, ['初始手牌']),
            'jid': get_col_safe(full_df, ['解集ID'])
        }

        # --- 核心修正：构建绝对唯一的【判决明细库】 ---
        with st.spinner('构建判决明细库...'):
            # 先算单局得分
            scr = full_df.apply(lambda r: pd.Series(audit_engine(r, c_m, base_score)), axis=1)
            full_df[['得分', '红线判定', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = scr

            final_judgments = []
            # 必须包含所有区分维度：源文件、手牌数、解集ID、难度
            # 不进行任何提前去重，确保每一组测试都被记录
            g_keys = ['__FILE__', c_m['hand'], c_m['jid'], c_m['diff']]
            for keys, gp in full_df.groupby(g_keys):
                mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
                red_m = gp['红线判定'] != "通过"
                r_rate = red_m.mean()
                
                # 判定
                reason = "✅ 通过"
                if r_rate >= 0.15: reason = f"❌ 红线拒绝 ({gp[red_m]['红线判定'].mode()[0]})"
                elif mu < mu_limit: reason = "❌ 分值拒绝"
                elif cv > cv_limit: reason = "❌ 稳定性拒绝"
                elif var > var_limit: reason = "❌ 波动拒绝 (方差超标)"
                
                final_judgments.append({
                    "UID": f"{keys[0]}_{keys[1]}_{keys[2]}_{keys[3]}", # 绝对唯一标识
                    "源文件": keys[0], "手牌数": keys[1], "解集ID": keys[2], "难度": keys[3],
                    "μ_均值": mu, "σ²_方差": var, "CV": cv, "判定结论": reason,
                    "is_pass": 1 if "✅" in reason else 0
                })
            
            # 所有的统计和展示只认这个 df_base
            df_base = pd.DataFrame(final_judgments)

        # === 1. 看板展示 (从 df_base 计数) ===
        st.header("📊 算法策略看板")
        summary_data = []
        for h_v, gp_h in df_base.groupby('手牌数'):
            # 各难度通过数 (通过计数行数)
            d_counts = gp_h[gp_h['is_pass'] == 1].groupby('难度').size().to_dict()
            # 去重总通过数 (基于 ID 去重)
            unique_pass = gp_h[gp_h['is_pass'] == 1].drop_duplicates(subset=['源文件', '解集ID']).shape[0]
            total_unique = gp_h.drop_duplicates(subset=['源文件', '解集ID']).shape[0]

            row = {
                "初始手牌数": h_v,
                "牌集总数": total_unique,
                "✅ 总去重通过数": unique_pass,
                "资源覆盖率": unique_pass / total_unique if total_unique > 0 else 0
            }
            # 动态添加列：难度X通过
            for d in sorted(df_base['难度'].unique()):
                row[f"难度{d}通过"] = d_counts.get(d, 0)
            summary_data.append(row)
        
        st.dataframe(pd.DataFrame(summary_data).style.format({"资源覆盖率":"{:.1%}"}), use_container_width=True)

        # === 2. 明细排行 (从 df_base 展示) ===
        st.divider()
        st.subheader("🎯 牌集明细排行")
        # 筛选器
        f_h = st.multiselect("手牌维度", sorted(df_base['手牌数'].unique()), default=sorted(df_base['手牌数'].unique()))
        f_s = st.radio("判定过滤", ["全部", "通过", "拒绝"], horizontal=True)

        # 筛选逻辑：只做行过滤，不做任何合并
        view_df = df_base[df_base['手牌数'].isin(f_h)].copy()
        if f_s == "通过": view_df = view_df[view_df['is_pass'] == 1]
        elif f_s == "拒绝": view_df = view_df[view_df['is_pass'] == 0]

        # 核心核对点：这里的 view_df.shape[0] 必须能推导出看板的数字
        st.dataframe(view_df.drop(columns=['UID', 'is_pass']).style.applymap(
            lambda x: 'color: #ff4b4b' if '❌' in str(x) else 'color: #008000', subset=['判定结论']
        ).format({"μ_均值":"{:.2f}", "σ²_方差":"{:.2f}", "CV":"{:.3f}"}), use_container_width=True)

        # 底部核对信息
        pass_count = view_df[view_df['is_pass'] == 1].shape[0]
        st.info(f"数据对齐核查：当前列表中『判定结论』为通过的行数共有 **{pass_count}** 行。请核对是否等于看板中对应列的数字之和。")
