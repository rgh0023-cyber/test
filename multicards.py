import streamlit as st
import pandas as pd
import numpy as np
import chardet
import io

# ... [保留 get_col_safe, calculate_advanced_stats, audit_engine (V1.9.13版本) 逻辑] ...

# --- 核心计算流程 ---
if uploaded_files:
    # [文件加载逻辑保持不变...]
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

        with st.spinner('执行红线风险概率统计...'):
            res = df.apply(lambda r: pd.Series(audit_engine(r, col_map, base_score, burst_win, burst_thr)), axis=1)
            df[['得分', '红线判定', 'c1', 'c2', 'c3', '接力', 'f1', 'f2', 'max_burst']] = res

            fact_records = []
            h_col, j_col, d_col = col_map['hand'], col_map['jid'], col_map['diff']
            for (f_name, h_val, j_id, d_val), gp in df.groupby(['__ORIGIN__', h_col, j_col, d_col]):
                mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
                
                # 统计红线明细
                total_runs = len(gp)
                is_red = gp['红线判定'] != "通过"
                
                # 计算各分项概率
                prob_break = (gp['红线判定'].str.contains("数值崩坏")).sum() / total_runs
                prob_auto = (gp['红线判定'].str.contains("自动化局")).sum() / total_runs
                prob_logic = (gp['红线判定'].str.contains("逻辑违逆")).sum() / total_runs
                prob_burst = (gp['红线判定'].str.contains("消除高度集中")).sum() / total_runs
                total_red_rate = is_red.mean()
                
                # 确定唯一结论结论 (优先级逻辑)
                reason = "✅ 通过"
                if total_red_rate >= 0.15: 
                    reason = f"❌ 红线拒绝 ({gp[is_red]['红线判定'].mode()[0]})"
                elif mu < mu_limit: reason = "❌ 分值拒绝"
                elif cv > cv_limit: reason = "❌ 稳定性拒绝"
                elif var > var_limit: reason = "❌ 波动拒绝"
                
                fact_records.append({
                    "源文件": f_name, "初始手牌": h_val, "解集ID": j_id, "难度": d_val,
                    "μ_均值": mu, "σ²_方差": var, "CV": cv, "判定结论": reason,
                    "总红线率": total_red_rate,
                    "数值崩坏率": prob_break,
                    "自动化率": prob_auto,
                    "逻辑违逆率": prob_logic,
                    "爆发集中率": prob_burst,
                    "is_pass": 1 if "✅" in reason else 0
                })
            df_fact = pd.DataFrame(fact_records)

        # === 看板展示保持不变 ===
        st.header("📊 算法策略看板")
        # ... (此处省略与 V1.9.13 相同的看板 DataFrame 生成代码) ...
        # [代码逻辑：按手牌数分组，展示各难度通过数和去重总数]
        summary_rows = []
        for h_v, gp_h in df_fact.groupby('初始手牌'):
            diff_counts = gp_h[gp_h['is_pass'] == 1].groupby('难度').size().to_dict()
            total_pass_jid = gp_h[gp_h['is_pass'] == 1].drop_duplicates(subset=['源文件', '解集ID']).shape[0]
            total_unique_jid = gp_h.drop_duplicates(subset=['源文件', '解集ID']).shape[0]
            row = {"初始手牌数": h_v, "牌集总数": total_unique_jid, "✅ 总通过数": total_pass_jid, "覆盖率": total_pass_jid/total_unique_jid if total_unique_jid>0 else 0}
            for d in sorted(df_fact['难度'].unique()): row[f"难度{d}通过"] = diff_counts.get(d, 0)
            summary_rows.append(row)
        st.dataframe(pd.DataFrame(summary_rows).style.format({"覆盖率":"{:.1%}"}), use_container_width=True)

        # === 🎯 牌集明细排行 (新增概率展示) ===
        st.divider()
        st.subheader("🎯 牌集风险明细排行")
        f_h = st.multiselect("手牌维度", sorted(df_fact['初始手牌'].unique()), default=sorted(df_fact['初始手牌'].unique()))
        f_s = st.radio("判定过滤", ["全部", "通过", "拒绝"], horizontal=True)

        view_df = df_fact[df_fact['初始手牌'].isin(f_h)].copy()
        if f_s == "通过": view_df = view_df[view_df['is_pass'] == 1]
        elif f_s == "拒绝": view_df = view_df[view_df['is_pass'] == 0]

        # 重新排序展示，突出风险概率
        display_cols = [
            "初始手牌", "解集ID", "难度", "μ_均值", "σ²_方差", "判定结论", 
            "总红线率", "数值崩坏率", "自动化率", "逻辑违逆率", "爆发集中率"
        ]
        
        st.dataframe(view_df[display_cols].style.applymap(
            lambda x: 'color: #ff4b4b' if '❌' in str(x) else 'color: #008000', subset=['判定结论']
        ).format({
            "μ_均值":"{:.2f}", "σ²_方差":"{:.2f}", 
            "总红线率":"{:.1%}", "数值崩坏率":"{:.1%}", 
            "自动化率":"{:.1%}", "逻辑违逆率":"{:.1%}", "爆发集中率":"{:.1%}"
        }), use_container_width=True)

        st.info(f"💡 风险提示：若某项红线概率 > 15%，该牌集将直接被判定为拒绝。")
