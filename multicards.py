import streamlit as st
import pandas as pd
import numpy as np
import chardet
import io

# ... [保留 get_col_safe, calculate_advanced_stats, audit_engine (V1.9.15版本) 逻辑] ...

if uploaded_files:
    # [文件加载与列映射逻辑保持不变...]
    # ... 

    if all_raw_dfs:
        # [执行 audit_engine 后得到 df]
        # 此时 df['红线判定'] 存储的是类似 "通过" 或 "数值崩坏,消除高度集中" 的字符串
        
        with st.spinner('正在执行严格并集风控审计...'):
            fact_list = []
            h_col, j_col, d_col = col_map['hand'], col_map['jid'], col_map['diff']
            
            for (f_name, h_val, j_id, d_val), gp in df.groupby(['__ORIGIN__', h_col, j_col, d_col]):
                total_runs = len(gp)
                
                # --- 核心修正：构建布尔矩阵确保不重复计算 ---
                # 判定每一局是否触发了特定的红线 (True/False)
                has_break = gp['红线判定'].str.contains("数值崩坏")
                has_auto  = gp['红线判定'].str.contains("自动化局")
                has_logic = gp['红线判定'].str.contains("逻辑违逆")
                has_burst = gp['红线判定'].str.contains("消除高度集中")
                
                # 只要触发了任意一个，这一局就是“红线局”
                is_any_red = has_break | has_auto | has_logic | has_burst
                
                # 计算概率
                prob_break = has_break.sum() / total_runs
                prob_auto  = has_auto.sum() / total_runs
                prob_logic = has_logic.sum() / total_runs
                prob_burst = has_burst.sum() / total_runs
                
                # 总红线率：这是并集概率，绝对不会大于分项之和
                total_red_rate = is_any_red.sum() / total_runs
                
                # 统计通过逻辑
                mu, var, cv = calculate_advanced_stats(gp['得分'], trim_val)
                reason = "✅ 通过"
                if total_red_rate >= 0.15: 
                    # 结论展示：取最频繁出现的红线作为主因
                    main_reason = gp[is_any_red]['红线判定'].str.split(',').explode().mode()[0]
                    reason = f"❌ 红线拒绝 ({main_reason})"
                elif mu < mu_limit: reason = "❌ 分值拒绝"
                elif cv > cv_limit: reason = "❌ 稳定性拒绝"
                elif var > var_limit: reason = "❌ 波动拒绝"
                
                fact_list.append({
                    "源文件": f_name, "初始手牌": h_val, "解集ID": j_id, "难度": d_val,
                    "μ_均值": mu, "σ²_方差": var, "判定结论": reason,
                    "总红线率": total_red_rate, 
                    "数值崩坏率": prob_break, "自动化率": prob_auto,
                    "逻辑违逆率": prob_logic, "爆发集中率": prob_burst,
                    "is_pass": 1 if "✅" in reason else 0
                })
            df_fact = pd.DataFrame(fact_list)

        # === 4. 结果展示 (保持对齐逻辑) ===
        st.header("📊 算法策略看板")
        # [看板逻辑：统计 df_fact 中 is_pass==1 的行...]
        # ... 

        st.divider()
        st.subheader("🎯 牌集风险明细排行 (并集概率核对)")
        # 展示数据
        # ... 
        st.dataframe(df_fact.style.format({
            "总红线率":"{:.1%}", "数值崩坏率":"{:.1%}", "自动化率":"{:.1%}", 
            "逻辑违逆率":"{:.1%}", "爆发集中率":"{:.1%}"
        }).background_gradient(subset=['总红线率'], cmap='Reds'))
