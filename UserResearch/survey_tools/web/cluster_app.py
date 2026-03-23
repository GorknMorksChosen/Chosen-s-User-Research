import streamlit as st
import pandas as pd
import numpy as np
from survey_tools.utils.io import read_table_auto
from survey_tools.utils.wjx_header import normalize_wjx_headers
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
from scipy.cluster.hierarchy import dendrogram
import os

from survey_tools.config import OPENAI_API_KEY as _DEFAULT_OPENAI_KEY
from survey_tools.core.clustering import (
    check_missing_rates, clean_data, preprocess_features, perform_factor_analysis,
    find_optimal_k, perform_clustering, get_linkage_matrix, evaluate_clustering_algorithms,
    recommend_clustering_algorithm, recommend_k_algorithm_combo, RECOMMENDATION_PROFILES
)

# Optional imports for AI Naming
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
except ImportError:
    ChatOpenAI = None

def render_missing_warning(missing_series):
    """Render warning if any column has > 10% missing values."""
    high_missing = missing_series[missing_series > 0.1]
    if not high_missing.empty:
        st.warning(
            f"⚠️ **高危预警：以下特征缺失率超过 10%**\n\n"
            f"{', '.join([f'{col} ({val:.1%})' for col, val in high_missing.items()])}\n\n"
            "这通常是由于跳题逻辑导致的。强行填充均值会导致严重偏差！\n"
            "建议选择【剔除含空值的玩家】（推荐）或检查问卷逻辑。"
        )
        return True
    return False

def plot_elbow_silhouette(k_results):
    """Plot Elbow and Silhouette charts side-by-side."""
    k_values = k_results['k_values']
    wcss = k_results['wcss']
    silhouette_scores = k_results['silhouette']
    optimal_k = k_results['optimal_k']

    col1, col2 = st.columns(2)
    
    with col1:
        fig_elbow = go.Figure()
        fig_elbow.add_trace(go.Scatter(x=k_values, y=wcss, mode='lines+markers', name='WCSS'))
        if optimal_k:
            fig_elbow.add_vline(x=optimal_k, line_dash="dash", line_color="red", annotation_text=f"K={optimal_k}")
        fig_elbow.update_layout(title="手肘法 (Elbow Method)", xaxis_title="K (Clusters)", yaxis_title="WCSS")
        st.plotly_chart(fig_elbow, use_container_width=True)

    with col2:
        fig_sil = go.Figure()
        fig_sil.add_trace(go.Scatter(x=k_values, y=silhouette_scores, mode='lines+markers', name='Silhouette'))
        max_sil_k = k_values[np.argmax(silhouette_scores)]
        fig_sil.add_vline(x=max_sil_k, line_dash="dash", line_color="green", annotation_text=f"Best={max_sil_k}")
        fig_sil.update_layout(title="轮廓系数 (Silhouette Score)", xaxis_title="K (Clusters)", yaxis_title="Score")
        st.plotly_chart(fig_sil, use_container_width=True)

def plot_pca_scatter(df_labeled, cluster_col='Cluster'):
    """Interactive PCA Scatter Plot."""
    # Simple PCA for visualization if not already reduced to 2D
    # We re-run PCA just for 2D visualization if needed, or use factors if available
    # For robustness, let's just run PCA on numeric columns
    numeric_cols = df_labeled.select_dtypes(include=[np.number]).columns.tolist()
    # Exclude Cluster column itself
    feature_cols = [c for c in numeric_cols if c != cluster_col]
    
    if len(feature_cols) >= 2:
        from sklearn.decomposition import PCA
        pca = PCA(n_components=2)
        components = pca.fit_transform(df_labeled[feature_cols].fillna(0))
        
        df_plot = df_labeled.copy()
        df_plot['PCA1'] = components[:, 0]
        df_plot['PCA2'] = components[:, 1]
        
        fig = px.scatter(
            df_plot, x='PCA1', y='PCA2', color=cluster_col,
            title="全景战情室 A：PCA 降维散点图",
            hover_data=feature_cols[:5] # Show first 5 features on hover
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("特征不足，无法绘制 PCA 散点图")

def plot_radar_chart(cluster_profiles):
    """Radar Chart for Cluster Profiles."""
    # Normalize profiles for better visualization (0-1 scale relative to range)
    # Or just plot raw values if they are already standardized (which they are if using Factor scores or Scaled data)
    # Assuming input is standardized or factor scores which are centered around 0
    
    categories = cluster_profiles.columns.tolist()
    fig = go.Figure()

    for cluster_id, row in cluster_profiles.iterrows():
        fig.add_trace(go.Scatterpolar(
            r=row.values,
            theta=categories,
            fill='toself',
            name=f'Cluster {cluster_id}'
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True)
        ),
        showlegend=True,
        title="全景战情室 B：人群特征雷达图"
    )
    st.plotly_chart(fig, use_container_width=True)

def plot_heatmap(cluster_profiles):
    """Heatmap of feature means."""
    fig = px.imshow(
        cluster_profiles.T, 
        aspect="auto",
        color_continuous_scale="RdBu_r",
        title="全景战情室 C：特征均值差异热力图"
    )
    st.plotly_chart(fig, use_container_width=True)

def get_ai_naming(cluster_profiles, api_key):
    """Call OpenAI to name clusters based on their profiles."""
    if not ChatOpenAI:
        st.error("LangChain or OpenAI library not installed.")
        return {}
        
    llm = ChatOpenAI(api_key=api_key, model="gpt-3.5-turbo", temperature=0.3)
    
    prompt_text = """
    你是一个专业的游戏用户研究专家。请根据以下各聚类簇的特征均值（Standardized Scores），为每个簇起一个生动、准确的画像名称（4-6个字）。
    
    特征均值数据：
    {data}
    
    请直接返回一个JSON格式的字典，Key是Cluster ID（如 0, 1, ...），Value是名称。不要包含其他废话。
    """
    
    prompt = ChatPromptTemplate.from_template(prompt_text)
    chain = prompt | llm
    
    try:
        response = chain.invoke({"data": cluster_profiles.to_string()})
        import json
        # Extract JSON from response content (simple heuristic)
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
            
        return json.loads(content)
    except Exception as e:
        st.error(f"AI 命名失败: {e}")
        return {}

def main():
    st.set_page_config(page_title="智能玩家分群引擎", layout="wide")
    st.title("🧩 智能玩家分群引擎 (Flagship)")
    st.markdown("---")

    # --- 1. Upload & Setup ---
    uploaded_file = st.file_uploader("上传问卷数据 (Excel/CSV/SAV)", type=["xlsx", "xls", "csv", "sav"])
    if not uploaded_file:
        st.info("请先上传数据文件开始分析。")
        return

    try:
        name = (uploaded_file.name or "").lower()
        if name.endswith(".xlsx") or name.endswith(".xls"):
            xls = pd.ExcelFile(uploaded_file)
            sheet_names = xls.sheet_names
            if len(sheet_names) > 1:
                sheet_name = st.selectbox("请选择要分析的工作表 (Sheet)", sheet_names, key="cluster_sheet_selector")
            else:
                sheet_name = sheet_names[0]
            df = read_table_auto(xls, sheet_name=sheet_name)
        else:
            df = read_table_auto(uploaded_file)
        df, wjx_modified = normalize_wjx_headers(df)
        if wjx_modified:
            st.info("已自动规范化问卷星表头，便于多选/矩阵题识别。")
    except Exception as e:
        st.error(f"文件读取失败: {e}")
        return

    if "cluster_algorithm" not in st.session_state:
        st.session_state["cluster_algorithm"] = "kmeans"
    if "cluster_eval_df" not in st.session_state:
        st.session_state["cluster_eval_df"] = None
    if "cluster_recommendation" not in st.session_state:
        st.session_state["cluster_recommendation"] = None
    if "cluster_eval_k" not in st.session_state:
        st.session_state["cluster_eval_k"] = None
    if "cluster_k" not in st.session_state:
        st.session_state["cluster_k"] = 3
    if "cluster_global_recommendation" not in st.session_state:
        st.session_state["cluster_global_recommendation"] = None
    if "cluster_strategy_profile" not in st.session_state:
        st.session_state["cluster_strategy_profile"] = "balanced"

    with st.sidebar:
        st.header("⚙️ 设置面板")
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        feature_cols = st.multiselect("选择用于聚类的特征列", numeric_cols, default=numeric_cols[:5] if len(numeric_cols) > 5 else numeric_cols)
        
        if not feature_cols:
            st.warning("请至少选择一个特征列。")
            return

        # --- 2. Cleaning & Warning ---
        st.subheader("1. 数据清洗")
        missing_rates = check_missing_rates(df, feature_cols)
        has_high_risk = render_missing_warning(missing_rates)
        
        clean_method = st.radio(
            "缺失值处理策略",
            ["drop", "mean", "median"],
            format_func=lambda x: (
                "剔除含空值的玩家 (推荐)"
                if x == "drop"
                else "使用均值填充 (慎用)"
                if x == "mean"
                else "使用中位数填充 (稳健)"
            ),
            index=0 if has_high_risk else 0
        )
        
        # --- 3. Reduction Strategy ---
        st.subheader("2. 降维策略")
        reduction_mode = st.radio(
            "降维模式",
            ["raw", "factor"],
            format_func=lambda x: "直接基于原始特征聚类" if x == "raw" else "因子分析提取潜在特征 (推荐)"
        )
        
        n_factors = None
        if reduction_mode == "factor":
            auto_factor = st.checkbox("自动决定因子数量 (Eigenvalues > 1)", value=True)
            if not auto_factor:
                n_factors = st.number_input("指定因子数量", min_value=2, max_value=20, value=3)
        st.subheader("3. 聚类算法")
        algorithm = st.selectbox(
            "执行算法",
            ["kmeans", "gmm", "agglomerative"],
            format_func=lambda x: (
                "KMeans（默认稳定）"
                if x == "kmeans"
                else "GMM（高斯混合）"
                if x == "gmm"
                else "Agglomerative（层次聚类）"
            ),
            key="cluster_algorithm",
        )
        st.subheader("4. 推荐口径")
        st.selectbox(
            "策略模板",
            list(RECOMMENDATION_PROFILES.keys()),
            format_func=lambda x: (
                "balanced（均衡）"
                if x == "balanced"
                else "stability_first（稳定优先）"
                if x == "stability_first"
                else "discrimination_first（区分度优先）"
            ),
            key="cluster_strategy_profile",
        )

    # --- Process Data ---
    df_clean = clean_data(df, feature_cols, method=clean_method)
    st.sidebar.info(f"原始样本: {len(df)} | 清洗后样本: {len(df_clean)}")
    
    if len(df_clean) < 10:
        st.error("有效样本过少，无法进行聚类分析。")
        return

    df_scaled, _ = preprocess_features(df_clean, feature_cols)
    
    if reduction_mode == "factor":
        try:
            df_for_clustering = perform_factor_analysis(df_scaled, n_factors)
            # H9: 因子分析内部可能 dropna，导致行数少于 df_clean，后续 index 对齐失败
            if len(df_for_clustering) != len(df_clean):
                st.warning(
                    f"因子分析后样本量从 {len(df_clean)} 变为 {len(df_for_clustering)}，"
                    "已自动截断 df_clean 对齐。聚类仅在有效因子得分样本上进行。"
                )
                df_clean = df_clean.iloc[: len(df_for_clustering)].reset_index(drop=True)
                df_for_clustering = df_for_clustering.reset_index(drop=True)
            st.success(f"✅ 因子分析完成，提取了 {df_for_clustering.shape[1]} 个潜在因子")
        except Exception as e:
            st.error(f"因子分析失败: {e}")
            return
    else:
        df_for_clustering = df_scaled

    # --- 4. Find K ---
    st.header("1. 寻找最佳 K 值")
    if st.button("开始分析最佳 K 值"):
        with st.spinner("正在计算 WCSS 和 轮廓系数..."):
            k_results = find_optimal_k(df_for_clustering)
            plot_elbow_silhouette(k_results)
            
            # Dendrogram
            with st.expander("查看层次聚类树状图 (Dendrogram)"):
                try:
                    Z = get_linkage_matrix(df_for_clustering)
                    fig_dendro, ax = plt.subplots(figsize=(10, 5))
                    dendrogram(Z, truncate_mode='lastp', p=30, leaf_rotation=90., leaf_font_size=8., show_contracted=True)
                    st.pyplot(fig_dendro)
                except Exception as e:
                    st.warning(f"树状图生成失败: {e}")

    # --- 5. Clustering Execution ---
    st.header("2. 执行聚类与画像")
    
    # Initialize session state for results if not present
    if 'clustering_results' not in st.session_state:
        st.session_state.clustering_results = None
        
    k_final = st.slider("选择最终聚类数量 (K)", 2, 8, 3, key="cluster_k")
    if st.button("评估多算法（当前K）"):
        with st.spinner("正在评估多算法表现..."):
            eval_df = evaluate_clustering_algorithms(df_for_clustering, k_final)
            recommendation = recommend_clustering_algorithm(
                eval_df,
                fallback="kmeans",
                profile=st.session_state["cluster_strategy_profile"],
            )
            st.session_state["cluster_eval_df"] = eval_df
            st.session_state["cluster_recommendation"] = recommendation
            st.session_state["cluster_eval_k"] = k_final
    if st.button("智能推荐K+算法"):
        with st.spinner("正在联合评估 K 与算法..."):
            global_rec = recommend_k_algorithm_combo(
                df_for_clustering,
                k_values=range(2, 9),
                fallback_k=k_final,
                fallback_algorithm=st.session_state.get("cluster_algorithm", "kmeans"),
                profile=st.session_state["cluster_strategy_profile"],
            )
            st.session_state["cluster_global_recommendation"] = global_rec

    eval_df = st.session_state.get("cluster_eval_df")
    recommendation = st.session_state.get("cluster_recommendation")
    eval_k = st.session_state.get("cluster_eval_k")
    if eval_df is not None and not eval_df.empty:
        st.markdown(f"**多算法评估结果（K={eval_k}）**")
        view_df = eval_df.copy()
        if recommendation and "scored_df" in recommendation and not recommendation["scored_df"].empty:
            rank_map = recommendation["scored_df"].set_index("algorithm")["recommendation_score"].to_dict()
            view_df["recommendation_score"] = view_df["algorithm"].map(rank_map)
            view_df = view_df.sort_values(by=["recommendation_score", "silhouette"], ascending=[True, False])
        st.dataframe(
            view_df.style.format(
                {
                    "silhouette": "{:.4f}",
                    "calinski_harabasz": "{:.2f}",
                    "davies_bouldin": "{:.4f}",
                    "imbalance_ratio": "{:.3f}",
                    "recommendation_score": "{:.3f}",
                }
            ),
            use_container_width=True,
        )
        if recommendation:
            rec_algo = recommendation.get("recommended_algorithm", "kmeans")
            rec_reason = recommendation.get("reason", "")
            rec_profile = recommendation.get("profile", st.session_state["cluster_strategy_profile"])
            st.success(f"推荐算法：{rec_algo}（模板: {rec_profile}）。{rec_reason}")
            if st.button("一键采用推荐算法"):
                st.session_state["cluster_algorithm"] = rec_algo
                st.rerun()
    global_rec = st.session_state.get("cluster_global_recommendation")
    if global_rec:
        try:
            rec_k = int(float(global_rec.get("recommended_k", k_final)))
        except (TypeError, ValueError):
            rec_k = k_final
        rec_algo = global_rec.get("recommended_algorithm", st.session_state.get("cluster_algorithm", "kmeans"))
        rec_reason = global_rec.get("reason", "")
        rec_profile = global_rec.get("profile", st.session_state["cluster_strategy_profile"])
        scored_df = global_rec.get("scored_df")
        st.markdown("**联合推荐结果（K + 算法）**")
        st.success(f"推荐配置：K={rec_k}, 算法={rec_algo}（模板: {rec_profile}）。{rec_reason}")
        if isinstance(scored_df, pd.DataFrame) and not scored_df.empty:
            st.dataframe(
                scored_df[["k", "algorithm", "silhouette", "calinski_harabasz", "davies_bouldin", "imbalance_ratio", "recommendation_score"]]
                .head(12)
                .style.format(
                    {
                        "silhouette": "{:.4f}",
                        "calinski_harabasz": "{:.2f}",
                        "davies_bouldin": "{:.4f}",
                        "imbalance_ratio": "{:.3f}",
                        "recommendation_score": "{:.3f}",
                    }
                ),
                use_container_width=True,
            )
        if st.button("一键采用推荐K+算法"):
            st.session_state["cluster_k"] = rec_k
            st.session_state["cluster_algorithm"] = rec_algo
            st.rerun()
    
    if st.button("执行聚类", type="primary"):
        with st.spinner(f"正在执行 {algorithm} 聚类..."):
            labeled_df, profiles, metrics = perform_clustering(
                df_clean,
                df_for_clustering,
                k_final,
                algorithm=algorithm,
            )
            
            # Store results in session state
            st.session_state.clustering_results = {
                'labeled_df': labeled_df,
                'profiles': profiles,
                'names': {i: f"簇 {i}" for i in range(k_final)},
                'metrics': metrics,
            }
            st.success("聚类完成！请查看下方全景战情室。")
            st.rerun()

    # Check if results exist to display
    if st.session_state.clustering_results is not None:
        results = st.session_state.clustering_results
        labeled_df = results['labeled_df']
        profiles = results['profiles']
        cluster_names = results['names']
        metrics = results.get('metrics', {})
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("算法", metrics.get("algorithm", "kmeans"))
        col_m2.metric("Silhouette", f"{metrics.get('silhouette', np.nan):.4f}")
        col_m3.metric("Calinski-Harabasz", f"{metrics.get('calinski_harabasz', np.nan):.2f}")
        col_m4.metric("Davies-Bouldin", f"{metrics.get('davies_bouldin', np.nan):.4f}")
        
        # --- 6. Visualization ---
        st.subheader("全景战情室")
        
        # Update profiles with current names for better visualization
        profiles_display = profiles.copy()
        profiles_display.index = profiles_display.index.map(cluster_names)
        
        tab1, tab2, tab3 = st.tabs(["PCA 散点图", "雷达图", "热力图"])
        with tab1:
            # Map names to labeled_df for visualization
            df_viz = labeled_df.copy()
            df_viz['Cluster Name'] = df_viz['Cluster'].map(cluster_names)
            plot_pca_scatter(df_viz, 'Cluster Name')
        with tab2:
            plot_radar_chart(profiles_display)
        with tab3:
            plot_heatmap(profiles_display)

        # --- 7. Naming & Export ---
        st.header("3. 智能命名与导出")
        
        col_ai, col_manual = st.columns([1, 2])
        
        with col_ai:
            st.markdown("#### 🤖 AI 命名助手")
            api_key_input = st.text_input("OpenAI API Key", type="password", help="如果没有设置环境变量，请在此输入")
            api_key = _DEFAULT_OPENAI_KEY or api_key_input
            
            if st.button("生成画像名称"):
                if not api_key:
                    st.error("请输入 API Key")
                else:
                    with st.spinner("AI 正在分析画像特征..."):
                        # We pass the profiles (numeric) to AI
                        ai_names = get_ai_naming(profiles, api_key)
                        if ai_names:
                            # Update session state names
                            for k, v in ai_names.items():
                                try:
                                    # Handle both string and int keys from JSON
                                    st.session_state.clustering_results['names'][int(k)] = v
                                except (ValueError, KeyError, TypeError):
                                    pass 
                            st.success("AI 命名完成！")
                            st.rerun()

        with col_manual:
            st.markdown("#### 📝 人工校对与导出")
            # Create a dataframe for editing names
            name_data = [{"Cluster ID": k, "Name": v} for k, v in cluster_names.items()]
            name_df = pd.DataFrame(name_data)
            
            edited_names_df = st.data_editor(
                name_df, 
                column_config={
                    "Cluster ID": st.column_config.NumberColumn(disabled=True),
                    "Name": st.column_config.TextColumn("画像名称 (双击修改)")
                },
                hide_index=True,
                use_container_width=True,
                key="editor"
            )
            
            # Sync edits back to session state on change
            # Note: data_editor updates session_state.editor automatically, 
            # but we need to push it back to our main results structure
            current_names_map = dict(zip(edited_names_df['Cluster ID'], edited_names_df['Name']))
            if current_names_map != st.session_state.clustering_results['names']:
                 st.session_state.clustering_results['names'] = current_names_map
                 st.rerun()
        
        # Final Export
        st.markdown("---")
        df_final_export = labeled_df.copy()
        df_final_export['Cluster Name'] = df_final_export['Cluster'].map(st.session_state.clustering_results['names'])
        
        # L8: 按钮标签写「Excel」但实际输出 CSV，已修正为如实标注
        st.download_button(
            label="📥 导出最终结果 (CSV)",
            data=df_final_export.to_csv(index=False).encode('utf-8_sig'),
            file_name="player_segmentation_result.csv",
            mime="text/csv",
            type="primary"
        )

if __name__ == "__main__":
    main()
