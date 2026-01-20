import streamlit as st
import pandas as pd
import numpy as np
import chardet
import io

# --- [底层核心算法逻辑：完全锁定，严禁修改] ---
# ... (此处包含 calculate_advanced_stats 和 audit_engine，逻辑与 V1.9.1 保持 100% 一致) ...

# --- [数据流整改部分] ---
if uploaded_files:
    # 1. 原始数据加载 (保留源文件标识)
    all_data_list = []
    for f in uploaded_files:
        try:
            if f.name.endswith('.xlsx'): temp_df = pd.read_excel(f)
            else:
                raw_b = f.read(); enc = chardet.detect(raw_b)['encoding'] or 'utf-8'
                temp_df = pd.read_csv(io.BytesIO(raw_b), encoding=enc)
            temp_df['__ORIGIN__'] = f.name 
            all_data_list.append(temp_df)
        except: st.error(f"读取 {f.name} 失败")

    if all_data_list:
        df = pd.concat(all_data_list, ignore_index=True)
        col_map = {
            'seq': get_col_safe(df, ['全部连击']), 'desk': get_col_safe(df, ['初始桌面牌']),
            'diff': get_col_safe(df, ['难度']), 'act': get_col_safe(df, ['实际结果']),
            'hand': get_col_safe(df, ['初始手牌']), 'jid': get_col_safe(df, ['解集ID'])
        }

        # --- 第一步：构建【唯一判定事实表】 ---
        # 这一步是为了确保看板和明细表引用的“判定结果”来源于同一个内存变量
        with st.spinner('同步审计引擎数据...'):
            # 执行审计引擎计算
            res = df.apply(lambda r: pd.Series(audit_engine(r, col_map, base_score)), axis=1)
            df[['得分', '红线判定', 'c1', 'c2', 'c3', '接力', 'f1', 'f2']] = res

            # 构建判决明细表（判定事实表）
            # 我们通过 [源文件, 初始手牌, 解集ID, 难度] 锁定唯一性
            audit_fact_list = []
            h_col, j_col, d_col = col_map['hand'], col_map['jid'], col_map['diff']
            
            for (f_name, h_val, j_id, d_val), gp in df.groupby(['__ORIGIN__', h_col, j_col, d_col]):
                mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
                red_m = gp['红线判定'] != "通过"
                r_rate = red_m.mean()
                
                # 判定层级对齐
                reason = "✅ 通过"
                if r_rate >= 0.15: reason = f"❌ 红线拒绝 ({gp[red_m]['红线判定'].mode()[0]})"
                elif mu < mu_limit: reason = "❌ 分值拒绝"
                elif cv > cv_limit: reason = "❌ 稳定性拒绝"
                elif var > var_limit: reason = "❌ 波动拒绝 (方差超标)"
                
                audit_fact_list.append({
                    "源文件": f_name, "初始手牌": h_val, "解集ID": j_id, "难度": d_val,
                    "μ_均值": mu, "σ²_方差": var, "CV": cv, "判定结论": reason,
                    "is_pass": 1 if "✅" in reason else 0
                })
            
            # 这张表是看板和明细的“唯一真相”
            df_fact = pd.DataFrame(audit_fact_list)

        # === 2. 总体策略看板 (基于 df_fact 计数) ===
        st.header("📊 算法策略看板")
        strat_summary = []
        for h_v, gp_h in df_fact.groupby('初始手牌'):
            # A. 分难度统计通过数 (此时不再去重解集ID，每个难度独立计数)
            diff_summary = gp_h[gp_h['is_pass'] == 1].groupby('难度').size().to_dict()
            
            # B. 总去重通过数 (同一解集ID在任一难度通过即计为1)
            # 这里必须按 [源文件 + 解集ID] 去重，防止跨文件ID重复
            pass_jid_set = gp_h[gp_h['is_pass'] == 1].drop_duplicates(subset=['源文件', '解集ID'])
            total_distinct_pass = len(pass_jid_set)
            
            # C. 总资源数 (去重后的解集总数)
            total_jids = gp_h.drop_duplicates(subset=['源文件', '解集ID']).shape[0]

            row = {
                "初始手牌数": h_v,
                "牌集总数": total_jids,
                "✅ 总去重通过数": total_distinct_pass,
                "资源覆盖率": total_distinct_pass / total_jids if total_jids > 0 else 0
            }
            # 填充各难度通过列
            for d in sorted(df_fact['难度'].unique()):
                row[f"难度{d}通过"] = diff_summary.get(d, 0)
            strat_summary.append(row)
        
        st.dataframe(pd.DataFrame(strat_summary).style.format({"资源覆盖率":"{:.1%}"}), use_container_width=True)

        # === 3. 牌集明细排行 (直接展示 df_fact) ===
        st.divider()
        st.subheader("🎯 牌集明细排行")
        
        # 筛选器逻辑
        f_h = st.multiselect("手牌筛选", sorted(df_fact['初始手牌'].unique()), default=sorted(df_fact['初始手牌'].unique()))
        f_s = st.radio("判定过滤", ["全部", "通过", "拒绝"], horizontal=True)

        # 核心：直接从 df_fact 过滤，不进行任何聚合，确保所见即所得
        view_df = df_fact[df_fact['初始手牌'].isin(f_h)].copy()
        if f_s == "通过": view_df = view_df[view_df['is_pass'] == 1]
        elif f_s == "拒绝": view_df = view_df[view_df['is_pass'] == 0]

        st.dataframe(view_df.drop(columns=['is_pass']).style.applymap(
            lambda x: 'color: #ff4b4b' if '❌' in str(x) else 'color: #008000', subset=['判定结论']
        ).format({"μ_均值":"{:.2f}", "σ²_方差":"{:.2f}", "CV":"{:.3f}"}), use_container_width=True)

        # 强力校验
        st.info(f"💡 对齐自检：当前明细表显示的通过条目数为 **{view_df[view_df['is_pass']==1].shape[0]}** 行。这应该等于看板中对应行各难度通过数的加总。")
