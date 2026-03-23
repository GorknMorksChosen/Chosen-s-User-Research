#在命令行里先输入：python -m streamlit run （注意末尾留一个空格）。
#用鼠标选中你的那个代码文件，直接拖进黑色命令行窗口里。
#命令行会自动填充该文件的完整路径（例如 "C:\Users\Desktop\my_analysis.py"）。
#按下回车键。
#或使用对应.bat文件启动

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.outliers_influence import variance_inflation_factor
import statsmodels.api as sm
from io import BytesIO

# 1. 页面配置
st.set_page_config(page_title="满意度终极诊断系统", layout="wide")

st.title("🏆 满意度全流程 AI 诊断系统 (Ultimate Edition)")
st.markdown("> **集成统计学严谨性与业务决策逻辑：** 自动处理脏数据、检测信度、计算驱动力并导出报告。")

# 2. 上传文件
uploaded_file = st.file_uploader("第一步：上传 Excel 问卷数据", type=["xlsx", "xls"])

def calculate_cronbach_alpha(df):
    """计算克隆巴赫信度系数"""
    item_vars = df.var(axis=0, ddof=1)
    t_var = df.sum(axis=1).var(ddof=1)
    n_items = df.shape[1]
    return (n_items / (n_items - 1)) * (1 - (item_vars.sum() / t_var))

if uploaded_file:
    df_raw = pd.read_excel(uploaded_file)
    cols = df_raw.columns.tolist()

    # 3. 变量选择
    c1, c2 = st.columns(2)
    with c1:
        target_col = st.selectbox("第二步：选择【整体满意度】(Y)", options=cols)
    with c2:
        feature_cols = st.multiselect("第三步：选择【细项满意度】(X)", options=[c for c in cols if c != target_col])

    if target_col and len(feature_cols) >= 2:
        # --- A. 数据清洗与质量检查 ---
        selected_all = [target_col] + feature_cols
        df_clean = df_raw[selected_all].apply(pd.to_numeric, errors='coerce')
        df_clean = df_clean.fillna(df_clean.mean()).dropna().astype(np.float64)

        st.divider()
        st.subheader("🛡️ 数据质量监控")
        q1, q2, q3 = st.columns(3)
        
        # 1. 信度检查
        alpha = calculate_cronbach_alpha(df_clean[feature_cols])
        q1.metric("问卷信度 (Cronbach's α)", f"{round(alpha, 3)}", 
                  help=">0.7 说明问卷内部一致性良好")
        
        # 2. 样本量检查
        sample_size = len(df_clean)
        q2.metric("有效样本量", f"{sample_size} 份")
        
        # 3. 解释力检查 (预跑回归获取)
        X_simple = df_clean[feature_cols]
        y_simple = df_clean[target_col]
        scaler = StandardScaler()
        X_std = pd.DataFrame(scaler.fit_transform(X_simple), columns=feature_cols)
        model_temp = sm.OLS(y_simple.values, sm.add_constant(X_std)).fit()
        q3.metric("模型总解释力 (R²)", f"{round(model_temp.rsquared * 100, 1)}%")

        with st.expander("查看细项分布偏度 (检测天花板效应)"):
            skews = df_clean[feature_cols].skew()
            skew_df = pd.DataFrame({"细项名称": skews.index, "偏度 (Skewness)": skews.values})
            st.write("注：偏度 > 1 表示打分过度集中在高分段，可能导致分析灵敏度下降。")
            st.dataframe(skew_df.T)

        # --- B. 共线性 (VIF) 与 显著性 (P值) 计算 ---
        X = df_clean[feature_cols]
        y = df_clean[target_col]
        
        # VIF 计算
        X_vif_input = sm.add_constant(X)
        vif_values = [variance_inflation_factor(X_vif_input.values, i + 1) for i in range(len(feature_cols))]

        # VIF 阈值与提示（提高分析客观性）
        st.sidebar.subheader("🔍 共线性健康度设置")
        vif_threshold = st.sidebar.number_input(
            "VIF 警戒线（>10 一般认为共线性严重）",
            min_value=1.0, max_value=50.0, value=10.0, step=0.5
        )
        high_vif_items = [feature_cols[i] for i, v in enumerate(vif_values) if v > vif_threshold]
        if high_vif_items:
            st.sidebar.warning(
                "以下细项存在 **较强共线性**，建议在业务上评估是否合并或剔除：\n- " +
                "\n- ".join(high_vif_items)
            )
        else:
            st.sidebar.success("当前所有细项的 VIF 均低于设定警戒线，共线性处于可接受范围。")
        
        # 显著性与 Beta 计算
        X_scaled_with_const = sm.add_constant(X_std)
        final_model = sm.OLS(y.values, X_scaled_with_const).fit()
        
        # 结果汇总表（全量模型）
        results_df = pd.DataFrame({
            "细项名称": feature_cols,
            "平均得分": np.round(X.mean().values, 2),
            "影响力(Beta系数)": np.round(final_model.params[1:], 3),
            "P值(显著性)": np.round(final_model.pvalues[1:], 3),
            "共线性(VIF)": np.round(vif_values, 2)
        }).reset_index(drop=True)

        def get_stat_conclusion(p):
            if p < 0.01: return "极显著 ✅"
            if p < 0.05: return "显著 ✅"
            return "不显著 (噪音) ❌"

        def get_vif_conclusion(v):
            if v <= 5:
                return "共线性正常"
            if v <= 10:
                return "中度共线（需关注）"
            return "严重共线（建议剔除/合并）"

        results_df["统计结论"] = results_summary = results_df["P值(显著性)"].apply(get_stat_conclusion)
        results_df["共线性结论"] = results_df["共线性(VIF)"].apply(get_vif_conclusion)

        # 自动变量筛选：显著性 + 共线性（核心模型）
        st.sidebar.subheader("🧠 自动变量筛选（核心模型）")
        auto_filter = st.sidebar.checkbox("启用基于显著性与共线性的核心模型推荐", value=True)
        p_threshold = st.sidebar.selectbox(
            "显著性阈值（P 值）",
            options=[0.01, 0.05, 0.1],
            index=1,
            format_func=lambda x: f"{x}"
        )

        if auto_filter:
            core_mask = (results_df["P值(显著性)"] < p_threshold) & (results_df["共线性(VIF)"] <= vif_threshold)
        else:
            core_mask = pd.Series([True] * len(results_df), index=results_df.index)

        results_df["是否纳入核心模型"] = np.where(core_mask, "是", "否")

        # 统一改进优先级得分：越高越需要优先改进
        score_range = results_df["平均得分"].max() - results_df["平均得分"].min()
        score_severity = (results_df["平均得分"].max() - results_df["平均得分"]) / (score_range + 1e-6)

        beta_abs = results_df["影响力(Beta系数)"].abs()
        beta_range = beta_abs.max() - beta_abs.min()
        beta_strength = (beta_abs - beta_abs.min()) / (beta_range + 1e-6)

        def sig_weight(p):
            if p < 0.01:
                return 2.0
            if p < 0.05:
                return 1.5
            return 0.5

        sig_weights = results_df["P值(显著性)"].apply(sig_weight)
        priority_raw = score_severity * beta_strength * sig_weights
        priority_norm = priority_raw / (priority_raw.max() + 1e-6)
        results_df["改进优先级得分"] = np.round(priority_norm, 3)

        # --- C. IPA 矩阵图 ---
        st.divider()
        st.subheader("🎯 驱动力决策矩阵 (IPA)")
        
        m_score = results_df["平均得分"].mean()
        m_beta = results_df["影响力(Beta系数)"].mean()

        fig = px.scatter(
            results_df, x="平均得分", y="影响力(Beta系数)", text="细项名称",
            color="统计结论",
            color_discrete_map={"极显著 ✅": "#ef553b", "显著 ✅": "#636efa", "不显著 (噪音) ❌": "#ababab"},
            hover_data=["P值(显著性)", "共线性(VIF)", "共线性结论", "改进优先级得分", "是否纳入核心模型"],
            template="plotly_white", height=600
        )
        fig.add_hline(y=m_beta, line_dash="dash", line_color="red", annotation_text="高影响力标准")
        fig.add_vline(x=m_score, line_dash="dash", line_color="red", annotation_text="得分均值线")
        st.plotly_chart(fig, use_container_width=True)

        # --- D. 诊断结论与导出 ---
        st.divider()
        col_res, col_export = st.columns([2, 1])

        with col_res:
            st.subheader("📋 核心诊断结论")
            # 拖累项：核心模型中，影响力高于均值且得分低于均值
            draggers = results_df[
                (results_df["是否纳入核心模型"] == "是") &
                (results_df["影响力(Beta系数)"] > m_beta) & 
                (results_df["平均得分"] < m_score)
            ]

            # 护城河项：核心模型中，影响力高于均值且得分不低于均值
            moats = results_df[
                (results_df["是否纳入核心模型"] == "是") &
                (results_df["影响力(Beta系数)"] > m_beta) & 
                (results_df["平均得分"] >= m_score)
            ]
            
            if not draggers.empty:
                st.error(f"识别到核心拖累项：{', '.join(draggers['细项名称'].tolist())}")
                st.write("💡 **改进建议：** 这些项在统计学上对总分有显著拉动作用，但目前得分偏低。改善这些项将最快提升整体满意度。")
            else:
                st.success("🎉 目前没有显著的核心拖累项。")

            if not moats.empty:
                st.info(f"识别到优势护城河项：{', '.join(moats['细项名称'].tolist())}")
                st.write("✅ 这些项对整体满意度有显著正向拉动，且当前得分较高，建议作为优势重点维护，避免体验下滑。")

            # 自动生成文字摘要，便于直接复制进报告/PPT
            summary_lines = []
            summary_lines.append(
                f"模型健康度：有效样本量 {sample_size} 份，问卷信度 Cronbach's α = {alpha:.3f}，模型 R² = {final_model.rsquared:.3f}。"
            )
            if high_vif_items:
                summary_lines.append(
                    f"共线性诊断：存在 VIF 高于设定阈值的细项（{', '.join(high_vif_items)}），已在侧边栏中提示，解释时需注意共线性风险。"
                )
            else:
                summary_lines.append("共线性诊断：当前所有细项的 VIF 低于设定警戒线，共线性处于可接受范围。")

            if not draggers.empty:
                summary_lines.append(
                    "核心拖累项：{}。这些指标在统计上对整体满意度具有较高正向影响力，但当前得分偏低，建议优先作为改进抓手。"
                    .format("、".join(draggers["细项名称"].tolist()))
                )
            else:
                summary_lines.append("核心拖累项：本次分析未识别到明显的核心拖累项。")

            if not moats.empty:
                summary_lines.append(
                    "优势护城河：{}。这些指标对整体满意度拉动显著，且当前得分较高，建议在资源允许的情况下保持投入并持续监测趋势。"
                    .format("、".join(moats["细项名称"].tolist()))
                )

            summary_lines.append(
                "改进优先级：结合得分高低、影响力强弱与显著性，‘改进优先级得分’越高的细项越值得优先投入资源。"
            )

            text_summary = "\n".join(summary_lines)
            st.markdown("**自动生成分析摘要（可直接复制到报告/PPT）**")
            st.text_area("", value=text_summary, height=180)

        with col_export:
            st.subheader("💾 导出报告")
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                results_df.to_excel(writer, index=False, sheet_name='统计诊断汇总')
                # 记录模型整体信息
                model_info = pd.DataFrame({
                    "指标": ["样本量", "R-Squared", "Cronbach's Alpha"],
                    "数值": [sample_size, final_model.rsquared, alpha]
                })
                model_info.to_excel(writer, index=False, sheet_name='模型健康度')
                # 写入自动生成的文字摘要
                summary_df = pd.DataFrame({"自动分析摘要": text_summary.split("\n")})
                summary_df.to_excel(writer, index=False, sheet_name='自动摘要')
            
            st.download_button(
                label="📥 下载完整 Excel 分析报告",
                data=output.getvalue(),
                file_name="满意度归因诊断报告_终极版.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        st.subheader("数据明细表")
        st.dataframe(results_df.sort_values("影响力(Beta系数)", ascending=False), use_container_width=True)

    else:
        st.warning("💡 请在上方勾选至少 2 个细项满意度以启动分析。")