import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
from io import BytesIO
from survey_tools.core.advanced_modeling import GameExperienceAnalyzer
from survey_tools.utils.io import read_table_auto, ExportBundle, export_xlsx
from survey_tools.utils.download_filename import safe_download_filename
from survey_tools.utils.wjx_header import normalize_wjx_headers
from statsmodels.stats.outliers_influence import variance_inflation_factor
import statsmodels.api as sm
from sklearn.preprocessing import StandardScaler
from factor_analyzer import FactorAnalyzer
from sklearn.metrics import silhouette_score
from sklearn.cluster import KMeans

# 设置 matplotlib 中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']  # 使用黑体
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题


def _corr_matrix_for_export(cm: pd.DataFrame) -> pd.DataFrame:
    """将相关矩阵转为带行名列的表，便于写入 Excel。"""
    out = cm.copy()
    out.insert(0, "模块", out.index.astype(str))
    return out.reset_index(drop=True)


def render_unified_export_sidebar() -> None:
    """侧边栏：合并本会话中已生成的数据表，单文件 Excel 下载。"""
    st.sidebar.divider()
    st.sidebar.subheader("📦 一键整合导出")
    st.sidebar.caption(
        "将已执行步骤产生的**数据表**合并为一个 Excel；图表请在页面查看或截图。"
    )
    sheets: list[tuple[str, pd.DataFrame]] = []
    if st.session_state.get("sat_export_ipa") is not None:
        sheets.append(("IPA四象限明细", st.session_state.sat_export_ipa))
    if st.session_state.get("sat_export_reg") is not None:
        sheets.append(("多元回归诊断", st.session_state.sat_export_reg))
        mi = st.session_state.get("sat_export_reg_model_info")
        if isinstance(mi, pd.DataFrame) and not mi.empty:
            sheets.append(("回归模型健康度", mi))
        sm = st.session_state.get("sat_export_reg_summary")
        if sm:
            sheets.append(("回归自动摘要", pd.DataFrame({"摘要": [sm]})))
    if st.session_state.get("sat_game_corr") is not None:
        sheets.append(("高级_相关性矩阵", _corr_matrix_for_export(st.session_state.sat_game_corr)))
    if st.session_state.get("sat_game_loadings") is not None:
        sheets.append(("高级_因子载荷", st.session_state.sat_game_loadings))
    if st.session_state.get("sat_game_cluster_means") is not None:
        sheets.append(("高级_聚类分群均值", st.session_state.sat_game_cluster_means))
    if st.session_state.get("sat_game_cluster_detail") is not None:
        sheets.append(("高级_聚类样本明细", st.session_state.sat_game_cluster_detail))
    if st.session_state.get("sat_game_reg") is not None:
        sheets.append(("高级_多元回归", st.session_state.sat_game_reg))
    if st.session_state.get("sat_game_kano") is not None:
        sheets.append(("高级_IPA象限", st.session_state.sat_game_kano))
    if st.session_state.get("sat_game_shap") is not None:
        sheets.append(("高级_SHAP", st.session_state.sat_game_shap))
    if st.session_state.get("sat_game_sem") is not None:
        sheets.append(("高级_路径分析SEM", st.session_state.sat_game_sem))

    if not sheets:
        st.sidebar.info("暂无已缓存的导出表。请先在各模块中执行分析（如 IPA、回归、高级 Tab 中的按钮）。")
        return

    if "sat_unified_export_fn" not in st.session_state:
        st.session_state.sat_unified_export_fn = "满意度工具_整合导出.xlsx"
    st.sidebar.text_input("整合导出文件名", key="sat_unified_export_fn")
    buf = BytesIO()
    bundle = ExportBundle(workbook_name="满意度整合导出", sheets=sheets)
    export_xlsx(bundle, buf)
    _fn = safe_download_filename(
        st.session_state.get("sat_unified_export_fn", "满意度工具_整合导出.xlsx"),
        fallback="满意度工具_整合导出.xlsx",
    )
    st.sidebar.download_button(
        label="📥 下载整合 Excel（多 Sheet）",
        data=buf.getvalue(),
        file_name=_fn,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="sat_unified_export_dl",
    )


def render_ipa_module(df):
    st.header("基础洞察：IPA 四象限分析")
    st.markdown("""
    通过计算细项得分的**均值**（表现）与整体满意度的**相关系数**（重要性），识别“拖累”项。
    """)
    
    columns = df.columns.tolist()
    
    col1, col2 = st.columns(2)
    with col1:
        target_col = st.selectbox("选择【整体满意度】列", options=columns, key="ipa_target")
    with col2:
        feature_cols = st.multiselect("选择【细项满意度】列", 
                                      options=[c for c in columns if c != target_col],
                                      key="ipa_features")

    if target_col and feature_cols:
        # 数据清洗：确保数值型
        try:
            # 移除全局 dropna，改为 pairwise deletion
            # df_calc = df[[target_col] + feature_cols].apply(pd.to_numeric, errors='coerce').dropna()
            df_numeric = df[[target_col] + feature_cols].apply(pd.to_numeric, errors='coerce')
            
            results = []
            for col in feature_cols:
                # 针对当前细项和目标项的 Pairwise Deletion
                pair_data = df_numeric[[target_col, col]].dropna()
                valid_n = len(pair_data)
                
                if valid_n > 0:
                    mean_score = pair_data[col].mean()
                    correlation = pair_data[col].corr(pair_data[target_col])
                    results.append({
                        "细项名称": col,
                        "满意度评分": round(mean_score, 2),
                        "对整体的影响力": round(correlation, 3),
                        "有效样本量(N)": valid_n
                    })
                else:
                    results.append({
                        "细项名称": col,
                        "满意度评分": np.nan,
                        "对整体的影响力": np.nan,
                        "有效样本量(N)": 0
                    })
            
            res_df = pd.DataFrame(results).dropna(subset=["满意度评分", "对整体的影响力"])
            if res_df.empty:
                st.warning("当前选中的细项与整体满意度无有效配对数据（如常数列或全缺失），无法绘制 IPA 矩阵。请检查列选择与数据。")
            else:
                st.divider()
                st.subheader("分析结果")
                x_mean = res_df["满意度评分"].mean()
                y_mean = res_df["对整体的影响力"].mean()
                fig = px.scatter(
                    res_df,
                    x="满意度评分",
                    y="对整体的影响力",
                    text="细项名称",
                    hover_name="细项名称",
                    size_max=60,
                    template="plotly_white",
                    title="满意度 IPA 矩阵（四分图）"
                )
                fig.add_hline(y=y_mean, line_dash="dash", line_color="red", annotation_text="平均影响力")
                fig.add_vline(x=x_mean, line_dash="dash", line_color="red", annotation_text="平均得分")
                fig.update_traces(textposition='top center', marker=dict(size=12, color='royalblue', line=dict(width=2, color='DarkSlateGrey')))
                # H8: 标签定位用数据范围偏移量，避免 x/y_mean 为负或接近零时方向倒置
                _x_range = res_df["满意度评分"].max() - res_df["满意度评分"].min()
                _y_range = res_df["对整体的影响力"].max() - res_df["对整体的影响力"].min()
                _dx = max(_x_range * 0.25, 0.05)
                _dy = max(_y_range * 0.25, 0.05)
                fig.update_layout(
                    height=600,
                    xaxis_title="满意度得分（表现）",
                    yaxis_title="相关系数（重要性）",
                    annotations=[
                        dict(x=x_mean + _dx, y=y_mean + _dy, text="重点保持区", showarrow=False, opacity=0.3, font=dict(size=20)),
                        dict(x=x_mean - _dx, y=y_mean + _dy, text="重点改进区（拖累项）", showarrow=False, opacity=0.3, font=dict(size=20, color="red")),
                        dict(x=x_mean - _dx, y=y_mean - _dy, text="次要改进区", showarrow=False, opacity=0.3, font=dict(size=20)),
                        dict(x=x_mean + _dx, y=y_mean - _dy, text="过度服务区", showarrow=False, opacity=0.3, font=dict(size=20))
                    ]
                )
                st.plotly_chart(fig, use_container_width=True)
                st.subheader("数据明细记录")
                st.dataframe(res_df.sort_values(by="对整体的影响力", ascending=False), use_container_width=True)
                draggers = res_df[(res_df["满意度评分"] < x_mean) & (res_df["对整体的影响力"] > y_mean)]
                if not draggers.empty:
                    st.warning(f"🚨 **分析结论：** 发现以下 {len(draggers)} 个核心拖累项：{', '.join(draggers['细项名称'].tolist())}。这些项影响力大但得分低，应优先优化。")
                else:
                    st.success("✅ 暂时没有发现处于‘重点改进区’的明显拖累项。")
                st.session_state.sat_export_ipa = res_df.copy()
        except Exception as e:
            st.error(f"分析过程中发生错误: {str(e)}。请检查选中的列是否包含有效的数值数据。")

def render_regression_module(df):
    st.header("核心诊断：满意度多元回归")
    st.markdown("> **集成统计学严谨性与业务决策逻辑：** 自动处理脏数据、检测信度、计算驱动力并导出报告。")
    
    cols = df.columns.tolist()
    c1, c2 = st.columns(2)
    with c1:
        target_col = st.selectbox("选择【整体满意度】(Y)", options=cols, key="reg_target")
    with c2:
        feature_cols = st.multiselect("选择【细项满意度】(X)", options=[c for c in cols if c != target_col], key="reg_features")

    if target_col and len(feature_cols) >= 2:
        # 数据清洗
        selected_all = [target_col] + feature_cols
        
        # 缺失率预警 (Before dropna/fillna)
        missing_ratios = df[selected_all].isnull().mean()
        high_missing_cols = missing_ratios[missing_ratios > 0.1].index.tolist()
        
        if high_missing_cols:
            missing_info = []
            for col in high_missing_cols:
                rate = missing_ratios[col]
                missing_info.append(f"- **{col}**: 缺失 {rate:.1%}")
            
            st.warning(
                f"""
                **⚠️ 数据健康度预警**
                
                检测到以下细项的缺失率较高（>10%），这通常是由于问卷的【跳题逻辑】导致的：
                {chr(10).join(missing_info)}
                
                **风险提示**：将跳题强行填入均值参与多元回归会导致模型严重失真！
                **强烈建议**：仅选择所有人都必答的全局题目进行回归分析；对于分支题目，请先在外部筛选特定人群后再上传分析。
                """
            )

        df_clean = df[selected_all].apply(pd.to_numeric, errors='coerce')
        # M7: 高缺失率时不应无条件 fillna(mean)，给用户选择权
        if high_missing_cols:
            _missing_handling = st.radio(
                "⚠️ 存在高缺失率列，如何处理？",
                options=["剔除缺失样本（推荐）", "均值填补（可能失真）"],
                key="reg_missing_handling",
                horizontal=True,
            )
            if "剔除" in _missing_handling:
                df_clean = df_clean.dropna().astype(np.float64)
            else:
                df_clean = df_clean.fillna(df_clean.mean()).dropna().astype(np.float64)
        else:
            df_clean = df_clean.fillna(df_clean.mean()).dropna().astype(np.float64)

        analyzer = GameExperienceAnalyzer(df) # 复用 Analyzer 的部分功能
        
        st.divider()
        st.subheader("数据质量监控")
        q1, q2, q3 = st.columns(3)
        
        # 1. 信度检查
        alpha = analyzer.calculate_cronbach_alpha(df_clean[feature_cols])
        q1.metric("问卷信度 (Cronbach's α)", f"{round(alpha, 3)}", help=">0.7 说明问卷内部一致性良好")
        
        # 2. 样本量检查
        sample_size = len(df_clean)
        q2.metric("有效样本量", f"{sample_size} 份")
        
        # 3. 解释力检查
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

        # VIF & Regression
        X = df_clean[feature_cols]
        y = df_clean[target_col]
        
        X_vif_input = sm.add_constant(X)
        vif_values = [variance_inflation_factor(X_vif_input.values, i + 1) for i in range(len(feature_cols))]

        st.sidebar.subheader("🔍 共线性健康度设置")
        vif_threshold = st.sidebar.number_input("VIF 警戒线", min_value=1.0, max_value=50.0, value=10.0, step=0.5, key="reg_vif_thresh")
        
        X_scaled_with_const = sm.add_constant(X_std)
        final_model = sm.OLS(y.values, X_scaled_with_const).fit()
        
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
            if v <= 5: return "共线性正常"
            if v <= 10: return "中度共线（需关注）"
            return "严重共线（建议剔除/合并）"

        results_df["统计结论"] = results_df["P值(显著性)"].apply(get_stat_conclusion)
        results_df["共线性结论"] = results_df["共线性(VIF)"].apply(get_vif_conclusion)

        st.sidebar.subheader("🧠 自动变量筛选")
        auto_filter = st.sidebar.checkbox("启用基于显著性与共线性的核心模型推荐", value=True, key="reg_auto_filter")
        p_threshold = st.sidebar.selectbox("显著性阈值（P 值）", options=[0.01, 0.05, 0.1], index=1, key="reg_p_thresh")

        if auto_filter:
            core_mask = (results_df["P值(显著性)"] < p_threshold) & (results_df["共线性(VIF)"] <= vif_threshold)
        else:
            core_mask = pd.Series([True] * len(results_df), index=results_df.index)

        results_df["是否纳入核心模型"] = np.where(core_mask, "是", "否")

        # 优先级得分
        score_range = results_df["平均得分"].max() - results_df["平均得分"].min()
        score_severity = (results_df["平均得分"].max() - results_df["平均得分"]) / (score_range + 1e-6)
        beta_abs = results_df["影响力(Beta系数)"].abs()
        beta_range = beta_abs.max() - beta_abs.min()
        beta_strength = (beta_abs - beta_abs.min()) / (beta_range + 1e-6)
        def sig_weight(p):
            if p < 0.01: return 2.0
            if p < 0.05: return 1.5
            return 0.5
        sig_weights = results_df["P值(显著性)"].apply(sig_weight)
        priority_raw = score_severity * beta_strength * sig_weights
        priority_norm = priority_raw / (priority_raw.max() + 1e-6)
        results_df["改进优先级得分"] = np.round(priority_norm, 3)

        model_info = pd.DataFrame(
            {"指标": ["样本量", "R-Squared", "Alpha"], "数值": [sample_size, final_model.rsquared, alpha]}
        )

        # IPA Plot
        st.divider()
        st.subheader("驱动力决策矩阵 (IPA)")
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

        # 结论与导出
        st.divider()
        col_res, col_export = st.columns([2, 1])
        with col_res:
            st.subheader("核心诊断结论")
            draggers = results_df[(results_df["是否纳入核心模型"] == "是") & (results_df["影响力(Beta系数)"] > m_beta) & (results_df["平均得分"] < m_score)]
            moats = results_df[(results_df["是否纳入核心模型"] == "是") & (results_df["影响力(Beta系数)"] > m_beta) & (results_df["平均得分"] >= m_score)]
            
            if not draggers.empty:
                st.error(f"核心拖累项：{', '.join(draggers['细项名称'].tolist())}")
            else:
                st.success("无明显核心拖累项。")
                
            # 自动生成摘要
            summary_lines = [f"模型 R² = {final_model.rsquared:.3f}，信度 α = {alpha:.3f}。"]
            if not draggers.empty:
                summary_lines.append(f"建议优先改进：{', '.join(draggers['细项名称'].tolist())}。")
            if not moats.empty:
                summary_lines.append(f"优势保持项：{', '.join(moats['细项名称'].tolist())}。")
            
            text_summary = "\n".join(summary_lines)
            st.text_area("自动分析摘要", value=text_summary, height=100)
            st.session_state.sat_export_reg = results_df.copy()
            st.session_state.sat_export_reg_model_info = model_info
            st.session_state.sat_export_reg_summary = text_summary

        with col_export:
            st.subheader("导出报告")
            if "sat_export_filename" not in st.session_state:
                st.session_state.sat_export_filename = "满意度归因诊断报告.xlsx"
            st.text_input("下载文件名（可修改）", key="sat_export_filename")
            sheet_诊断 = st.checkbox("统计诊断汇总", value=True, key="exp_diag")
            sheet_健康度 = st.checkbox("模型健康度", value=True, key="exp_health")
            sheet_摘要 = st.checkbox("自动摘要", value=True, key="exp_summary")
            sheets_list = []
            if sheet_诊断:
                sheets_list.append(("统计诊断汇总", results_df))
            if sheet_健康度:
                sheets_list.append(("模型健康度", model_info))
            if sheet_摘要:
                sheets_list.append(("自动摘要", pd.DataFrame({"摘要": [text_summary]})))
            if sheets_list:
                bundle = ExportBundle(workbook_name="满意度归因诊断报告", sheets=sheets_list)
                output = BytesIO()
                export_xlsx(bundle, output)
                _sat_fn = safe_download_filename(
                    st.session_state.get("sat_export_filename", "满意度归因诊断报告.xlsx"),
                    fallback="满意度归因诊断报告.xlsx",
                )
                st.download_button(
                    "📥 下载所选 Excel 报告",
                    data=output.getvalue(),
                    file_name=_sat_fn,
                    key="sat_export_dl",
                )
            else:
                st.caption("请至少勾选一个 sheet 再下载。")

        st.subheader("数据明细表")
        st.dataframe(results_df.sort_values("影响力(Beta系数)", ascending=False), use_container_width=True)

def render_game_experience_module(df):
    st.header("高级模式：全链路体验建模")
    st.markdown("通过 **相关性 -> 因子聚类 -> 玩家分群 -> 因果回归 -> 路径分析** 的全链路逻辑，帮您揪出体验中的“幕后黑手”。")
    
    analyzer = GameExperienceAnalyzer(df)
    all_cols = df.columns.tolist()
    
    tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(["数据看板与体检", "相关性分析", "因子与聚类", "回归与因果", "IPA象限与 SHAP", "路径分析 (SEM)"])

    # --- TAB 0: 数据看板与体检 ---
    with tab0:
        st.subheader("分析参数配置")
        c1, c2 = st.columns(2)
        with c1:
            selected_features = st.multiselect("1. 选择要分析的满意度细项 (数值型)", all_cols, key="game_features")
        with c2:
            target_col = st.selectbox("2. 选择‘整体满意度’作为回归目标", all_cols, key="game_target")
            id_col = st.selectbox("3. 可选：选择样本标识字段", ["（使用问卷行号代替）"] + all_cols, key="game_id_col")

        st.divider()
        st.subheader("数据清洗与质量体检")
        
        c3, c4 = st.columns(2)
        with c3:
            time_col = st.selectbox("选择作答时长字段 (可选)", ["无"] + all_cols, key="game_time_col")
        with c4:
            min_duration = st.number_input("最小作答时长 (秒)", value=30, key="game_min_duration")

        if st.button("执行全量数据体检", use_container_width=True):
            if not selected_features:
                st.error("请先选择分析细项。")
            else:
                report = analyzer.data_quality_check(selected_features, time_col if time_col != "无" else None, min_duration)
                st.session_state.game_report = report
                
        if 'game_report' in st.session_state:
            report = st.session_state.game_report
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("直线勾选", f"{report['straight_liners_count']}")
            c2.metric("作答过快", f"{report['too_fast_count']}")
            c3.metric("离群值", f"{report['outliers_count']}")
            c4.metric("缺失项", f"{report['total_missing']}")

    # Check for features before proceeding
    if len(selected_features) < 3:
        st.info("请至少选择 3 个细项以解锁后续分析。")
        return

    analysis_df = df[selected_features].dropna()
    # M8: dropna 后样本量过小时提前终止，避免下游聚类/因子崩溃
    if len(analysis_df) < 10:
        st.error(f"剔除缺失值后有效样本仅 {len(analysis_df)} 条，不足以进行分析（至少需要 10 条）。请检查所选列的缺失情况。")
        return

    # --- TAB 1: 相关性分析 ---
    with tab1:
        st.subheader("模块关联矩阵")
        if st.button("计算相关性矩阵"):
            corr_matrix = analysis_df.corr(method='spearman')
            st.session_state.sat_game_corr = corr_matrix.copy()
            fig_corr = px.imshow(corr_matrix, text_auto=".2f", aspect="auto", color_continuous_scale='RdBu_r', range_color=[-1, 1])
            st.plotly_chart(fig_corr, use_container_width=True)

    # --- TAB 2: 因子与聚类 ---
    with tab2:
        st.subheader("因子分析")
        if st.button("计算碎石图"):
            fa_temp = FactorAnalyzer(rotation=None, n_factors=len(selected_features))
            fa_temp.fit(analysis_df)
            ev, v = fa_temp.get_eigenvalues()
            fig_scree = px.line(x=range(1, len(ev)+1), y=ev, title="碎石图 (Scree Plot)")
            fig_scree.add_hline(y=1, line_dash="dash", line_color="red")
            st.plotly_chart(fig_scree, use_container_width=True)

        n_factors = st.number_input("设定因子数量", 1, len(selected_features), 3, key="game_n_factors")
        if st.button("执行因子分析"):
            loadings, ev = analyzer.factor_analysis(selected_features, n_factors)
            st.session_state.sat_game_loadings = loadings.copy()
            st.plotly_chart(px.imshow(loadings, text_auto=".2f", color_continuous_scale='RdBu_r'), use_container_width=True)

        st.divider()
        st.subheader("玩家聚类")
        n_clusters = st.slider("选择聚类数量", 2, 6, 3, key="game_n_clusters")
        if st.button("执行聚类分析"):
            df_clustered, centers, scaler, sil_avg = analyzer.cluster_analysis(selected_features, n_clusters)
            st.success(f"轮廓系数: {sil_avg:.3f}")
            st.session_state.cluster_results = {'df_clustered': df_clustered}
            
            # Show cluster means
            cluster_means = df_clustered.groupby('玩家分群').mean()
            st.session_state.sat_game_cluster_means = cluster_means.copy()
            st.session_state.sat_game_cluster_detail = pd.DataFrame({
                "问卷行号": df_clustered.index,
                "玩家分群": df_clustered["玩家分群"].values,
            })
            if id_col != "（使用问卷行号代替）" and id_col in df.columns:
                st.session_state.sat_game_cluster_detail.insert(
                    1, id_col, df[id_col].loc[df_clustered.index].values
                )
            st.write(cluster_means)

    # --- TAB 3: 回归与因果 ---
    with tab3:
        st.subheader("多元回归")
        cluster_option = "整体数据"
        if 'cluster_results' in st.session_state:
             available_clusters = sorted(st.session_state.cluster_results['df_clustered']['玩家分群'].unique().tolist())
             cluster_options = ["整体数据"] + [f"聚类群体 {i}" for i in available_clusters]
             cluster_option = st.selectbox("选择数据群体", cluster_options, key="game_reg_cluster")
             
             # Need to merge cluster info back to main data for analysis if not already
             # In a real app, we should handle data flow better. For now, assume '玩家分群' is added to analyzer.data if present
             if '玩家分群' in st.session_state.cluster_results['df_clustered'].columns:
                  # M9: 用 reindex 对齐 index，防止行数/顺序不一致时静默错位
                  cluster_labels = st.session_state.cluster_results['df_clustered']['玩家分群']
                  analyzer.data = analyzer.data.copy()
                  analyzer.data['玩家分群'] = cluster_labels.reindex(analyzer.data.index)

        missing_strategy_options = {
            "剔除缺失样本": "drop",
            "均值填补": "mean",
            "中位数填补": "median",
            "按分组均值填补": "group_mean",
            "按分组中位数填补": "group_median",
        }
        missing_strategy_label = st.selectbox(
            "缺失值处理策略",
            options=list(missing_strategy_options.keys()),
            index=1,
            key="satisfaction_missing_strategy",
        )
        missing_strategy = missing_strategy_options[missing_strategy_label]
        missing_group_col = None
        if missing_strategy in ("group_mean", "group_median"):
            group_candidates = [c for c in df.columns if c not in [target_col] + selected_features]
            if not group_candidates:
                st.warning("未找到可用分组列，当前策略将自动回退为整体均值填补。")
                missing_strategy = "mean"
                missing_group_col = None
            else:
                missing_group_col = st.selectbox(
                    "选择分组填补列",
                    options=group_candidates,
                    key="satisfaction_missing_group_col",
                )

        if st.button("执行回归分析"):
            # M10: split()[-1] 在 AI 命名后可能非数字，需保护
            try:
                selected_cluster = int(cluster_option.split()[-1]) if cluster_option != "整体数据" else None
            except (ValueError, IndexError):
                selected_cluster = None
            try:
                reg_res = analyzer.regression_analysis(
                    selected_features,
                    target_col,
                    cluster=selected_cluster,
                    missing_strategy=missing_strategy,
                    missing_group_col=missing_group_col,
                )
                for w in analyzer.warnings:
                    st.warning(w)
                st.metric("R²", f"{reg_res['final_model'].rsquared:.3f}")
                st.dataframe(reg_res['results_df'].sort_values("改进优先级得分", ascending=False), use_container_width=True)
                st.session_state.sat_game_reg = reg_res["results_df"].copy()
            except Exception as e:
                st.error(f"回归分析失败: {e}")

    # --- TAB 4: Kano & SHAP ---
    with tab4:
        st.subheader("IPA 象限与 SHAP")
        if st.button("执行 IPA 象限分析"):
            ipa_res = analyzer.ipa_quadrant_analysis(selected_features, target_col)
            for w in analyzer.warnings:
                st.warning(w)
            if ipa_res.empty:
                st.info("当前数据未产出可展示的 IPA 结果。")
            else:
                st.session_state.sat_game_kano = ipa_res.copy()
                st.dataframe(ipa_res, use_container_width=True)
                fig_ipa = px.scatter(
                    ipa_res,
                    x="满意度",
                    y="推导重要性(相关系数)",
                    text="模块名称",
                    color="IPA四象限分类",
                    title="IPA 象限分类图",
                )
                st.plotly_chart(fig_ipa, use_container_width=True)
            
        st.divider()
        if st.button("执行 SHAP 重要性分析"):
            try:
                imp_df, shap_values, X = analyzer.shap_importance(
                    selected_features,
                    target_col,
                    missing_strategy=missing_strategy,
                    missing_group_col=missing_group_col,
                )
                st.session_state.sat_game_shap = imp_df.copy()
                st.dataframe(imp_df, use_container_width=True)
                if shap_values is not None:
                     st.info("SHAP 值计算成功 (图表展示需 shap 库支持)")
            except Exception as e:
                st.error(f"SHAP 分析失败: {e}")

    # --- TAB 5: 路径分析 ---
    with tab5:
        st.subheader("路径分析 (SEM)")
        if st.button("生成推荐模型结构"):
            spec = analyzer.generate_recommended_model_spec(selected_features, target_col)
            st.text_area("模型结构 (semopy语法)", value=spec, height=150, key="game_sem_spec")
        
        user_spec = st.session_state.get("game_sem_spec", "")
        if user_spec and st.button("执行路径分析"):
            try:
                path_res = analyzer.path_analysis(selected_features, target_col, user_spec)
                st.session_state.sat_game_sem = path_res["estimates"].copy()
                st.dataframe(path_res['estimates'], use_container_width=True)
            except Exception as e:
                st.error(f"路径分析失败: {e}")

def main():
    st.set_page_config(page_title="满意度与体验建模工具", layout="wide")
    
    # Global Sidebar
    st.sidebar.title("导航")
    app_mode = st.sidebar.radio("选择功能模块", [
        "基础洞察：IPA 四象限分析",
        "核心诊断：满意度多元回归",
        "高级模式：全链路体验建模"
    ])
    
    # Global File Uploader
    st.markdown("### 📂 全局数据入口")
    # Use a fixed key to prevent component recreation, but uploader clears on rerun if not careful?
    # Actually streamlit file uploader persists in session state if key is provided? No.
    # The file uploader widget state is preserved if key is same.
    uploaded_file = st.file_uploader("上传 Excel/CSV/SAV 数据 (所有模块共享)", type=["xlsx", "xls", "csv", "sav"], key="global_uploader")
    
    if uploaded_file:
        try:
            # Check if we need to reload
            # We can use file name and size as a simple check, or just reload every time (safer but slower for huge files)
            # Given typical survey data size, reloading is acceptable.
            name = (uploaded_file.name or "").lower()
            if name.endswith(".xlsx") or name.endswith(".xls"):
                xls = pd.ExcelFile(uploaded_file)
                sheet_names = xls.sheet_names
                if len(sheet_names) > 1:
                    sheet_name = st.selectbox("请选择要分析的工作表 (Sheet)", sheet_names, key="global_sheet_selector")
                else:
                    sheet_name = sheet_names[0]
                df = read_table_auto(xls, sheet_name=sheet_name)
            else:
                df = read_table_auto(uploaded_file)
            df, wjx_modified = normalize_wjx_headers(df)
            if wjx_modified:
                st.info("已自动规范化问卷星表头，便于多选/矩阵题识别。")
            # Normalize columns to string to avoid issues
            df.columns = df.columns.astype(str)
            
            st.session_state.df = df
            st.success(f"数据加载成功！包含 {len(df)} 行，{len(df.columns)} 列。")
        except Exception as e:
            st.error(f"数据加载失败: {e}")
            return
    
    if 'df' in st.session_state:
        df = st.session_state.df
        render_unified_export_sidebar()
        st.divider()
        
        if app_mode == "基础洞察：IPA 四象限分析":
            render_ipa_module(df)
        elif app_mode == "核心诊断：满意度多元回归":
            render_regression_module(df)
        elif app_mode == "高级模式：全链路体验建模":
            render_game_experience_module(df)
    else:
        st.info("👈 请在上方上传数据文件以开始分析。")

if __name__ == "__main__":
    main()
