import streamlit as st
# 游研专家分析工具 - 已修复路径分析缩进
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import plotly.express as px

from factor_analyzer import FactorAnalyzer
from sklearn.cluster import MiniBatchKMeans, KMeans
from sklearn.preprocessing import StandardScaler
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from semopy import Model
import io
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import silhouette_score
try:
    import shap
except ImportError:
    shap = None
import plotly.graph_objects as go
from scipy import stats
from survey_tools.core.factor_compat import (
    factor_analyzer_compat,
    is_factor_compat_error,
    build_factor_compat_message,
)
from survey_tools.core.missing_strategy import apply_missing_strategy
from survey_tools.core.advanced_modeling import GameExperienceAnalyzer
from survey_tools.utils.io import read_table_auto
from survey_tools.utils.download_filename import safe_download_filename
from survey_tools.utils.wjx_header import normalize_wjx_headers

# 版本兼容性处理将在具体函数中通过try-except方式处理

class LegacyGameExperienceAnalyzer:
    """
    游戏体验深度分析工具类
    提供全链路分析：数据体检 → 相关性 → 因子聚类 → 玩家分群 → 因果回归 → 路径分析
    """
    
    def __init__(self, data: pd.DataFrame):
        """
        初始化分析器
        
        Args:
            data: 输入的问卷数据
        """
        self.data = data.copy()

    def data_quality_check(self, features: list, time_col: str = None, min_duration: int = 30):
        """
        数据质量检查：检测直线勾选、作答时长、缺失值和离群值
        """
        report = {}
        
        # 1. 直线勾选检测 (所有题目得分一致)
        if len(features) > 1:
            # 这里的 features 必须是数值型的
            numeric_df = self.data[features].apply(pd.to_numeric, errors='coerce')
            straight_liners = numeric_df.std(axis=1) == 0
            report['straight_liners_count'] = straight_liners.sum()
            report['straight_liners_indices'] = self.data.index[straight_liners].tolist()
        else:
            report['straight_liners_count'] = 0
            
        # 2. 作答时长过滤
        if time_col and time_col in self.data.columns:
            # 假设 time_col 是秒数或可以转换为秒
            durations = pd.to_numeric(self.data[time_col], errors='coerce')
            too_fast = durations < min_duration
            report['too_fast_count'] = too_fast.sum()
            report['too_fast_indices'] = self.data.index[too_fast].tolist()
        else:
            report['too_fast_count'] = 0
            
        # 3. 缺失值检查
        missing_report = self.data[features].isnull().sum()
        report['missing_values'] = missing_report
        report['total_missing'] = missing_report.sum()
        
        # 4. 离群值检测 (基于 Z-score)
        outlier_indices = set()
        if len(features) > 0:
            numeric_df = self.data[features].apply(pd.to_numeric, errors='coerce').fillna(self.data[features].mean())
            z_scores = np.abs(stats.zscore(numeric_df))
            outliers = (z_scores > 3).any(axis=1)
            report['outliers_count'] = outliers.sum()
            report['outliers_indices'] = self.data.index[outliers].tolist()
            
        return report

    def calculate_cronbach_alpha(self, df: pd.DataFrame) -> float:
        """
        计算克隆巴赫信度系数，用于评估一组题目是否测量同一潜在维度。
        
        Args:
            df: 要计算信度的DataFrame
            
        Returns:
            float: 克隆巴赫信度系数
        """
        if df.shape[1] < 2:
            return np.nan
        item_vars = df.var(axis=0, ddof=1)
        t_var = df.sum(axis=1).var(ddof=1)
        n_items = df.shape[1]
        if t_var == 0:
            return np.nan
        return (n_items / (n_items - 1)) * (1 - (item_vars.sum() / t_var))

    def _apply_missing_strategy(self, df: pd.DataFrame, strategy: str = "mean", group_col: str = None):
        group_values = None
        if strategy in ("group_mean", "group_median"):
            if not group_col or group_col not in self.data.columns:
                raise ValueError("分组填补策略需要有效的分组列。")
            group_values = self.data[group_col]
        return apply_missing_strategy(
            df=df,
            strategy=strategy,
            group_values=group_values,
            group_col_name=group_col,
        )
    
    def factor_analysis(self, features: list, n_factors: int = 3):
        """
        执行因子分析
        
        Args:
            features: 要分析的特征列表
            n_factors: 因子数量
            
        Returns:
            tuple: (因子载荷矩阵, 特征值)
        """
        analysis_df = self.data[features].dropna()
        
        try:
            with factor_analyzer_compat():
                fa = FactorAnalyzer(rotation="varimax", n_factors=n_factors)
                fa.fit(analysis_df)
            ev, v = fa.get_eigenvalues()
            loadings = pd.DataFrame(fa.loadings_, index=features, columns=[f"维度 {i+1}" for i in range(n_factors)])
            return loadings, ev
        except TypeError as te:
            if is_factor_compat_error(te):
                raise Exception(build_factor_compat_message())
            raise te
        except Exception as e:
            if is_factor_compat_error(e):
                raise Exception(build_factor_compat_message())
            raise Exception(f"因子分析执行失败: {str(e)}")
    
    def cluster_analysis(self, features: list, n_clusters: int = 3):
        """
        执行玩家聚类分析
        
        Args:
            features: 要分析的特征列表
            n_clusters: 聚类数量
            
        Returns:
            tuple: (聚类结果, 聚类中心, 标准化器, silhouette_avg)
        """
        analysis_df = self.data[features].dropna()
        
        # 性能优化：对于大型数据集使用 MiniBatchKMeans 以提升速度，无需采样
        if len(analysis_df) > 5000:
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(analysis_df)
            # 使用 MiniBatchKMeans 处理大规模数据
            kmeans = MiniBatchKMeans(n_clusters=n_clusters, random_state=42, batch_size=1024).fit(scaled_data)
            labels = kmeans.labels_
            # 对于超大数据集，计算 silhouette_score 依然昂贵，可以选择跳过或仅计算部分
            # 这里为了性能，对 >5000 样本仅计算采样轮廓系数
            if len(analysis_df) > 10000:
                silhouette_avg = silhouette_score(scaled_data, labels, sample_size=1000)
            else:
                silhouette_avg = silhouette_score(scaled_data, labels)
        else:
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(analysis_df)
            kmeans = KMeans(n_clusters=n_clusters, random_state=42).fit(scaled_data)
            silhouette_avg = silhouette_score(scaled_data, kmeans.labels_)
            labels = kmeans.labels_
        
        df_clustered = analysis_df.copy()
        df_clustered['玩家分群'] = labels
        
        return df_clustered, kmeans.cluster_centers_, scaler, silhouette_avg

    def kano_analysis(self, features: list, target: str):
        """
        Kano模型分析 (基于满意度与重要性的非对称分析)
        通常使用回归分析中，表现好时的提升与表现差时的下降来分类
        """
        df_clean = self.data[[target] + features].dropna()
        y = df_clean[target]
        X = df_clean[features]
        
        # 这里使用一种简化的Kano方法：相关系数 vs 满意度分布
        # 或者更专业的：使用惩罚回归或分段回归。
        # 为了通用性，我们计算每个属性的平均得分（满意度）和它与总分的皮尔逊相关系数（重要性）
        results = []
        for feat in features:
            corr = df_clean[feat].corr(y)
            mean_score = df_clean[feat].mean()
            # 简单Kano分类逻辑：
            # 魅力属性 (Attractive): 表现好时极大提升满意度，表现一般时用户也能接受
            # 必备属性 (Must-be): 表现不好时极大降低满意度，表现好时用户认为理所当然
            # 一元属性 (One-dimensional): 满意度与表现线性相关
            # 无差异属性 (Indifferent): 表现好坏不影响满意度
            results.append({
                "模块名称": feat,
                "满意度": mean_score,
                "重要性(相关系数)": corr
            })
        return pd.DataFrame(results)

    def shap_importance(self, features: list, target: str):
        """
        使用随机森林和SHAP值计算特征重要性
        """
        df_clean = self.data[[target] + features].dropna()
        X = df_clean[features]
        y = df_clean[target]
        
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X, y)
        
        importance_df = pd.DataFrame({
            "模块名称": features,
            "RF重要性": model.feature_importances_
        })
        
        shap_values = None
        if shap:
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X)
            importance_df["SHAP重要性"] = np.abs(shap_values).mean(axis=0)
            
        return importance_df.sort_values("RF重要性", ascending=False), shap_values, X
    
    def regression_analysis(self, features: list, target: str, cluster=None, missing_strategy: str = "mean", missing_group_col: str = None):
        """
        执行多元回归分析
        
        Args:
            features: 特征列表
            target: 目标变量
            cluster: 可选，指定要分析的聚类群体
            
        Returns:
            dict: 回归分析结果
        """
        selected_all = [target] + features
        # 增加缺失值比例检查，防止均值填充导致的偏差
        missing_ratios = self.data[selected_all].isnull().mean()
        high_missing_cols = missing_ratios[missing_ratios > 0.1].index.tolist()
        if high_missing_cols:
             st.warning(f"⚠️ 警告：以下变量缺失率超过 10%，均值填充可能导致回归偏差：{', '.join(high_missing_cols)}。建议剔除这些变量或使用更完整的样本。")
        df_source = self.data[selected_all].copy()
        if cluster is not None and '玩家分群' in self.data.columns:
            cluster_mask = self.data['玩家分群'] == cluster
            df_source = df_source.loc[cluster_mask].copy()
        df_clean = self._apply_missing_strategy(
            df_source,
            strategy=missing_strategy,
            group_col=missing_group_col,
        ).astype(np.float64)
        if cluster is not None and df_clean.shape[0] < 10:
            raise Exception(f"聚类群体 {cluster} 的有效样本量较少（<10），回归结果可能不稳定")
        
        if df_clean.shape[0] < 10:
            raise Exception("有效样本量较少（<10），回归结果可能不稳定")
        
        # 计算Cronbach's α
        alpha = self.calculate_cronbach_alpha(df_clean[features])
        sample_size = len(df_clean)
        
        # 标准化数据
        X_simple = df_clean[features]
        y_simple = df_clean[target]
        scaler = StandardScaler()
        X_std = pd.DataFrame(scaler.fit_transform(X_simple), columns=features)
        
        # 构建模型
        X_scaled_with_const = sm.add_constant(X_std)
        final_model = sm.OLS(y_simple.values, X_scaled_with_const).fit()
        
        # 计算VIF
        X_vif_input = sm.add_constant(X_simple, has_constant="add")
        vif_values = [variance_inflation_factor(X_vif_input.values, i + 1) for i in range(len(features))]
        
        # 构建结果DataFrame
        results_df = pd.DataFrame({
            "模块名称": features,
            "平均得分": np.round(X_simple.mean().values, 2),
            "影响力(Beta系数)": np.round(final_model.params[1:], 3),
            "P值(显著性)": np.round(final_model.pvalues[1:], 3),
            "共线性(VIF)": np.round(vif_values, 2)
        }).reset_index(drop=True)
        
        # 添加统计结论和共线性结论
        def get_stat_conclusion(p):
            if p < 0.01:
                return "极显著 ✅"
            if p < 0.05:
                return "显著 ✅"
            return "不显著 (噪音) ❌"
        
        def get_vif_conclusion(v):
            if v <= 5:
                return "共线性正常"
            if v <= 10:
                return "中度共线（需关注）"
            return "严重共线（建议剔除/合并）"
        
        results_df["统计结论"] = results_df["P值(显著性)"].apply(get_stat_conclusion)
        results_df["共线性结论"] = results_df["共线性(VIF)"].apply(get_vif_conclusion)
        
        # 计算改进优先级得分
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
        
        # 构建未标准化模型（用于模拟）
        X_raw = sm.add_constant(df_clean[features])
        y_raw = df_clean[target]
        model_raw = sm.OLS(y_raw, X_raw).fit()
        
        return {
            "results_df": results_df,
            "final_model": final_model,
            "model_raw": model_raw,
            "alpha": alpha,
            "sample_size": sample_size,
            "df_clean": df_clean
        }
    
    def path_analysis(self, features: list, target: str, model_spec: str, cluster=None):
        """
        执行路径分析
        
        Args:
            features: 特征列表
            target: 目标变量
            model_spec: 模型规格
            cluster: 可选，指定要分析的聚类群体
            
        Returns:
            dict: 路径分析结果
        """
        # 为避免中文题干、空格等导致 semopy 语法错误，生成安全变量名
        sem_cols = list(dict.fromkeys(features + [target]))
        safe_names = {col: f"V{i+1}" for i, col in enumerate(sem_cols)}
        inv_safe_names = {v: k for k, v in safe_names.items()}
        
        # 准备数据
        df_sem = self.data[sem_cols].rename(columns=safe_names)
        
        # 如果指定了聚类群体，只分析该群体的数据
        if cluster is not None:
            # 确保聚类信息存在
            if '玩家分群' in self.data.columns:
                cluster_mask = self.data['玩家分群'] == cluster
                df_sem = df_sem.loc[cluster_mask].copy()
                if df_sem.shape[0] < 10:
                    raise Exception(f"聚类群体 {cluster} 的有效样本量较少（<10），路径分析结果可能不稳定")
        
        try:
            sem_model = Model(model_spec)
            sem_model.fit(df_sem)
            estimates = sem_model.inspect()
            return {
                "estimates": estimates,
                "safe_names": safe_names,
                "inv_safe_names": inv_safe_names,
                "sem_cols": sem_cols
            }
        except Exception as e:
            raise Exception(f"路径分析执行失败: {str(e)}")
    
    def generate_recommended_model_spec(self, features: list, target: str, cluster=None):
        """
        生成推荐的路径分析模型规格
        
        Args:
            features: 特征列表
            target: 目标变量
            cluster: 可选，指定要分析的聚类群体
            
        Returns:
            str: 推荐的模型规格
        """
        # 为避免中文题干、空格等导致 semopy 语法错误，生成安全变量名
        sem_cols = list(dict.fromkeys(features + [target]))
        safe_names = {col: f"V{i+1}" for i, col in enumerate(sem_cols)}
        
        try:
            feat_safe_cols = [safe_names[col] for col in features]
            # 基于 Spearman 相关度，将高度相关的题目聚为潜在因子
            df_sem = self.data[sem_cols].rename(columns=safe_names)
            
            # 如果指定了聚类群体，只分析该群体的数据
            if cluster is not None:
                # 确保聚类信息存在
                if '玩家分群' in self.data.columns:
                    cluster_mask = self.data['玩家分群'] == cluster
                    df_sem = df_sem.loc[cluster_mask].copy()
            corr_sem = df_sem[feat_safe_cols].corr(method="spearman")
            threshold_sem = 0.5
            unassigned = set(feat_safe_cols)
            clusters = []
            while unassigned:
                v = unassigned.pop()
                cluster = [v]
                to_remove = []
                for u in unassigned:
                    if abs(corr_sem.loc[v, u]) >= threshold_sem:
                        cluster.append(u)
                        to_remove.append(u)
                for u in to_remove:
                    unassigned.remove(u)
                clusters.append(cluster)

            factor_lines = []
            latent_idx = 1
            for cluster in clusters:
                # 只对至少 2 个高度相关题目的簇构造潜在因子
                if len(cluster) >= 2:
                    rhs = " + ".join(cluster)
                    factor_lines.append(f"F{latent_idx} =~ {rhs}")
                    latent_idx += 1

            # 如果没有任何簇满足条件，则退回到最简单结构
            if not factor_lines and len(feat_safe_cols) >= 2:
                factor_lines.append(f"F1 =~ {feat_safe_cols[0]} + {feat_safe_cols[1]}")

            # 使用多元回归识别对整体满意度影响最大的题目，作为路径端点
            outcome_var = safe_names[target]
            X_sem = sm.add_constant(df_sem[feat_safe_cols])
            y_sem = df_sem[outcome_var]
            ols_sem = sm.OLS(y_sem, X_sem).fit()
            coefs = ols_sem.params.drop("const", errors="ignore")
            top_predictors = coefs.reindex(feat_safe_cols).abs().sort_values(ascending=False).head(3).index.tolist()

            latent_names = [line.split("=~")[0].strip() for line in factor_lines]
            rhs_terms = latent_names.copy()
            for v in top_predictors:
                if v not in rhs_terms:
                    rhs_terms.append(v)

            if rhs_terms:
                reg_line = f"{outcome_var} ~ " + " + ".join(rhs_terms)
                all_lines = factor_lines + [reg_line]
            else:
                # 极端兜底：直接用前两个题目回归整体满意度
                base_terms = feat_safe_cols[:2]
                all_lines = [f"{outcome_var} ~ " + " + ".join(base_terms)]

            recommended_spec = "\n".join(all_lines)
            return recommended_spec
        except Exception:
            # 如果自动推荐失败，使用最简单的默认结构
            default_safe_feats = [safe_names[c] for c in features[:2]]
            recommended_spec = (
                f"F1 =~ {default_safe_feats[0]} + {default_safe_feats[1]}\n"
                f"{safe_names[target]} ~ F1"
            )
            return recommended_spec


# 设置页面配置
st.set_page_config(page_title="游戏体验深度分析工具", layout="wide")

# 添加中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei']  # 使用黑体
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

# 添加自定义CSS来调整侧边栏宽度
st.markdown("""
<style>
/* 调整侧边栏宽度 */
[data-testid="stSidebar"] {
    min-width: 300px;
    max-width: 400px;
}

/* 调整侧边栏内元素的字体大小 */
[data-testid="stSidebar"] .stMultiSelect, 
[data-testid="stSidebar"] .stSelectbox, 
[data-testid="stSidebar"] .stButton {
    font-size: 14px;
}

/* 调整侧边栏标题字体大小 */
[data-testid="stSidebar"] h1, 
[data-testid="stSidebar"] h2, 
[data-testid="stSidebar"] h3 {
    font-size: 16px;
}
</style>
""", unsafe_allow_html=True)

st.title("🎮 资深游研专家：游戏模块关联与归因分析系统")
st.markdown("""
本工具通过 **相关性 -> 因子聚类 -> 玩家分群 -> 因果回归 -> 路径分析** 的全链路逻辑，帮您揪出体验中的"幕后黑手"。
""")

# 1. 数据上传
uploaded_file = st.sidebar.file_uploader(
    "第一步：上传问卷数据（Excel/CSV/SAV）",
    type=["xlsx", "xls", "csv", "sav"],
    key="game_analyst_uploader",
)

# 显式刷新按钮：在不改变当前上传文件和已选参数的前提下，强制重算整个分析
if st.sidebar.button("🔄 重新计算所有分析"):
    st.cache_data.clear()
    st.rerun()

if uploaded_file:
    # 使用 session_state 存储清洗后的数据；换文件或切换 Sheet 时按标识重新加载
    name = (uploaded_file.name or "").lower()
    selected_sheet_name = None
    if name.endswith(".xlsx") or name.endswith(".xls"):
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names
        current_sheet = st.session_state.get("game_analyst_sheet_name", sheet_names[0])
        if current_sheet not in sheet_names:
            current_sheet = sheet_names[0]
        if len(sheet_names) > 1:
            selected_sheet_name = st.sidebar.selectbox(
                "选择工作表 (Sheet)",
                sheet_names,
                index=sheet_names.index(current_sheet),
                key="game_analyst_sheet_selector",
            )
        else:
            selected_sheet_name = sheet_names[0]
        st.session_state.game_analyst_sheet_name = selected_sheet_name

    file_id = (uploaded_file.name, getattr(uploaded_file, "size", 0), selected_sheet_name)
    if (
        'df_cleaned' not in st.session_state
        or st.session_state.get('uploaded_file_id') != file_id
    ):
        st.session_state.uploaded_file_id = file_id
        if name.endswith(".xlsx") or name.endswith(".xls"):
            st.session_state.df_cleaned = read_table_auto(xls, sheet_name=selected_sheet_name or 0)
        else:
            st.session_state.df_cleaned = read_table_auto(uploaded_file)
        _df, _wjx_mod = normalize_wjx_headers(st.session_state.df_cleaned)
        if _wjx_mod:
            st.info("已自动规范化问卷星表头，便于多选/矩阵题识别。")
        st.session_state.df_cleaned = _df
    df = st.session_state.df_cleaned
    
    # 初始化分析器
    analyzer = GameExperienceAnalyzer(df)
    
    # 2. 参数选择 (整合至第一个 Tab)
    all_cols = df.columns.tolist()
    
    tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 数据看板与体检", "📊 相关性分析", "🔍 因子与聚类", "📈 回归与因果", "💡 Kano & SHAP", "🕸️ 路径分析(SEM)"])

    # --- TAB 0: 数据看板与体检 ---
    with tab0:
        st.subheader("🛠️ 分析参数配置")
        col_param1, col_param2 = st.columns(2)
        with col_param1:
            selected_features = st.multiselect("1. 选择要分析的满意度细项 (数值型)", all_cols, key="selected_features_tab")
        with col_param2:
            target_col = st.selectbox("2. 选择‘整体满意度’作为回归目标", all_cols, key="target_col_tab")
            id_col = st.selectbox("3. 可选：选择样本标识字段", options=["（使用问卷行号代替）"] + all_cols, key="id_col_tab")

        st.divider()
        st.subheader("🧼 数据清洗与质量体检")
        
        col_clean1, col_clean2 = st.columns(2)
        with col_clean1:
            time_col_clean = st.selectbox("选择作答时长字段 (可选)", ["无"] + all_cols, key="time_col_clean")
        with col_clean2:
            min_duration_clean = st.number_input("最小作答时长 (秒)", value=30, key="min_duration_clean")

        if st.button("🚀 执行全量数据体检", use_container_width=True):
            if not selected_features:
                st.error("请先选择分析细项后再执行体检。")
            else:
                report = analyzer.data_quality_check(selected_features, 
                                                   time_col_clean if time_col_clean != "无" else None, 
                                                   min_duration_clean)
                
                st.session_state.last_report = report
                
        if 'last_report' in st.session_state:
            report = st.session_state.last_report
            st.markdown("#### 体检结果摘要")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("直线勾选 (疑似敷衍)", f"{report['straight_liners_count']} 份")
            c2.metric("作答过快", f"{report['too_fast_count']} 份")
            c3.metric("离群值 (异常表现)", f"{report['outliers_count']} 份")
            c4.metric("总缺失项", f"{report['total_missing']} 项")
            
            if report['straight_liners_count'] > 0 or report['too_fast_count'] > 0:
                st.warning(f"检测到共 {report['straight_liners_count'] + report['too_fast_count']} 份疑似异常样本。")
                if st.button("🔥 一键剔除异常并应用到后续分析", type="primary"):
                    bad_indices = set(report['straight_liners_indices'] + report['too_fast_indices'])
                    st.session_state.df_cleaned = df.drop(index=list(bad_indices))
                    st.success(f"已成功剔除 {len(bad_indices)} 份问卷！所有分析 Tab 将同步更新。")
                    st.rerun()
        
        st.divider()
        st.subheader("📈 数据分布预览")
        st.write(df.head(10))
        st.write(f"当前可用总样本量: **{len(df)}**")

    if len(selected_features) >= 3:
        analysis_df = df[selected_features].dropna()
        
        # --- TAB 1: 相关性分析 ---
        with tab1:
            st.subheader("📊 模块关联矩阵 (识别‘同生共死’模块)")
            corr_matrix = analysis_df.corr(method='spearman')
            
            # 使用 Plotly 展示关联矩阵
            fig_corr = px.imshow(corr_matrix, text_auto=".2f", aspect="auto",
                                title="Spearman 相关系数矩阵",
                                color_continuous_scale='RdBu_r', range_color=[-1, 1])
            st.plotly_chart(fig_corr, use_container_width=True)
            
            # 自动识别高相关模块对（相互关联的模块）
            st.markdown("**自动识别高相关模块对（绝对相关系数 ≥ 0.6）**")
            high_pairs = []
            threshold = 0.6
            cols = corr_matrix.columns.tolist()
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    r = corr_matrix.iloc[i, j]
                    if abs(r) >= threshold:
                        high_pairs.append({
                            "模块A": cols[i],
                            "模块B": cols[j],
                            "相关系数(Spearman)": round(r, 3)
                        })
            if high_pairs:
                pairs_df = pd.DataFrame(high_pairs).sort_values(by="相关系数(Spearman)", ascending=False)
                st.dataframe(pairs_df, use_container_width=True)
            else:
                st.info("当前未发现绝对相关系数 ≥ 0.6 的模块对。")

        # --- TAB 2: 因子分析与玩家聚类 ---
        with tab2:
            st.subheader("🔍 因子分析 (寻找幕后维度)")
            try:
                with factor_analyzer_compat():
                    fa_temp = FactorAnalyzer(rotation=None, n_factors=len(selected_features))
                    fa_temp.fit(analysis_df)
                ev, v = fa_temp.get_eigenvalues()
                
                fig_scree = px.line(x=range(1, len(ev)+1), y=ev, title="碎石图 (Scree Plot)",
                                   labels={'x': '因子数量', 'y': '特征值 (Eigenvalue)'})
                fig_scree.add_hline(y=1, line_dash="dash", line_color="red", annotation_text="Kaiser准则线 (EV=1)")
                st.plotly_chart(fig_scree, use_container_width=True)
                
                n_factors_auto = sum(ev > 1)
                st.info(f"💡 根据Kaiser准则（特征值>1），建议因子数量为: {n_factors_auto}")

                n_factors = st.number_input("设定因子数量", min_value=1, max_value=len(selected_features), value=min(n_factors_auto, 5))
                
                # 使用分析器执行因子分析
                loadings, _ = analyzer.factor_analysis(selected_features, n_factors=n_factors)
                
                # 使用 Plotly 展示因子载荷热力图
                fig_loadings = px.imshow(loadings, text_auto=".2f", aspect="auto",
                                        title="因子载荷矩阵 (识别哪些细项属于同一底层逻辑)",
                                        color_continuous_scale='RdBu_r')
                st.plotly_chart(fig_loadings, use_container_width=True)
                st.info("💡 载荷值越高（如>0.5），说明该细项越属于这个‘维度’。")

            except Exception as e:
                st.error(f"因子分析执行失败: {str(e)}")
                st.warning("⚠️ 建议方案：1) 检查数据是否有常数列 2) 确保样本量大于特征数")

            st.subheader("👥 玩家交叉聚类 (识别‘受害人群’)")
            
            # 自动计算手肘法和轮廓系数
            distortions = []
            silhouettes = []
            K_range = range(2, 7)
            scaler_temp = StandardScaler()
            scaled_temp = scaler_temp.fit_transform(analysis_df)
            
            for k in K_range:
                km = KMeans(n_clusters=k, random_state=42).fit(scaled_temp)
                distortions.append(km.inertia_)
                silhouettes.append(silhouette_score(scaled_temp, km.labels_))
            
            c1, c2 = st.columns(2)
            with c1:
                fig_elbow = px.line(x=list(K_range), y=distortions, title="手肘法 (Elbow Method)",
                                   labels={'x': '聚类数量', 'y': '畸变程度 (Inertia)'})
                st.plotly_chart(fig_elbow, use_container_width=True)
            with c2:
                fig_sil = px.line(x=list(K_range), y=silhouettes, title="轮廓系数 (Silhouette Score)",
                                 labels={'x': '聚类数量', 'y': '轮廓系数 (越高越好)'})
                st.plotly_chart(fig_sil, use_container_width=True)

            n_clusters = st.slider("选择聚类数量", 2, 6, int(K_range[np.argmax(silhouettes)]))
            
            # 使用分析器执行聚类分析
            df_clustered, cluster_centers, scaler, silhouette_avg = analyzer.cluster_analysis(selected_features, n_clusters=n_clusters)
            st.success(f"当前聚类轮廓系数: {silhouette_avg:.3f}")
            
            # 存储聚类结果到全局变量
            cluster_results = {
                'df_clustered': df_clustered,
                'cluster_centers': cluster_centers,
                'scaler': scaler,
                'n_clusters': n_clusters,
                'target_col': target_col,
                'df': df
            }

            # 聚类结果概览：每群的平均得分（含整体满意度）
            st.write("各玩家分群的平均得分概览（含整体满意度）：")
            cluster_overview = df_clustered.copy()
            # 将整体满意度对齐到与 analysis_df 相同的样本索引
            cluster_overview[target_col] = df[target_col].loc[df_clustered.index].values
            cluster_means = cluster_overview.groupby('玩家分群').mean()
            st.write(cluster_means)

            # 不同分群下的玩家数量
            st.write("各玩家分群的样本数量：")
            cluster_counts = df_clustered["玩家分群"].value_counts().sort_index()
            st.write(cluster_counts.rename("样本数量"))

            # 手动选择要对比的群体，并绘制雷达图
            try:
                # 获取所有可用的群体
                available_clusters = sorted(cluster_means.index.tolist())
                
                # 自动识别低分群组和高分群组作为默认选项
                sat_by_cluster = cluster_means[target_col]
                low_cluster = sat_by_cluster.idxmin()
                high_cluster = sat_by_cluster.idxmax()
                
                # 添加手动选择群体的选项
                st.markdown(f"**自动识别的低分群组：分群 {low_cluster}；高分群组：分群 {high_cluster}**")
                st.markdown("**手动选择要对比的群体（可多选）：**")
                
                # 默认选择低分群组和高分群组
                default_clusters = [low_cluster, high_cluster]
                selected_clusters = st.multiselect(
                    "选择要对比的群体",
                    options=available_clusters,
                    default=default_clusters,
                    key="selected_clusters"
                )

                # 只对满意度细项画雷达图
                radar_features = selected_features
                if len(radar_features) >= 3 and len(selected_clusters) >= 2:
                    # 定义颜色循环
                    colors = ['r', 'g', 'b', 'y', 'm']
                    
                    # 闭合雷达图
                    angles = np.linspace(0, 2 * np.pi, len(radar_features), endpoint=False)
                    angles = np.concatenate((angles, [angles[0]]))

                    fig_radar, ax_radar = plt.subplots(subplot_kw={'polar': True}, figsize=(8, 6))
                    
                    # 为每个选择的群体绘制雷达图
                    for i, cluster in enumerate(selected_clusters):
                        vals = cluster_means.loc[cluster, radar_features].values
                        plot_vals = np.concatenate((vals, [vals[0]]))
                        color = colors[i % len(colors)]
                        ax_radar.plot(angles, plot_vals, f'{color}-', linewidth=2, label=f'分群 {cluster}')
                        ax_radar.fill(angles, plot_vals, color, alpha=0.15)
                    
                    ax_radar.set_thetagrids(angles[:-1] * 180 / np.pi, radar_features, fontsize=8)
                    ax_radar.set_title(f"多群体雷达图对比 ({', '.join(map(str, selected_clusters))})", fontsize=12)
                    ax_radar.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
                    st.pyplot(fig_radar)

                    # 群体对比分析
                    st.markdown("**群体对比分析：**")
                    comparison_df = cluster_means.loc[selected_clusters, radar_features]
                    st.dataframe(comparison_df, use_container_width=True)
                    
                    # 如果选择了至少两个群体，提供基础型需求识别
                    if len(selected_clusters) >= 2:
                        # 使用第一个选择的群体作为基准（通常是低分群组）
                        base_cluster = selected_clusters[0]
                        # 使用第二个选择的群体作为对比（通常是高分群组）
                        comp_cluster = selected_clusters[1]
                        
                        # 基础型需求识别：基准群体极差，对比群体仅一般
                        base_needs = []
                        for feat in radar_features:
                            base_score = cluster_means.loc[base_cluster, feat]
                            comp_score = cluster_means.loc[comp_cluster, feat]
                            overall_mean = cluster_overview[feat].mean()
                            # 阈值基于 1-5 量表经验设定，可按需要调整
                            if (overall_mean - base_score) >= 0.7 and abs(comp_score - overall_mean) <= 0.3:
                                base_needs.append({
                                    "模块名称": feat,
                                    f"{base_cluster}分群均值": round(base_score, 2),
                                    f"{comp_cluster}分群均值": round(comp_score, 2),
                                    "全体均值": round(overall_mean, 2),
                                    "判定": "基础型需求（失败强烈拉低整体）"
                                })
                        st.markdown(f"**基础型需求识别（以分群 {base_cluster} 为基准）：**")
                        if base_needs:
                            base_df = pd.DataFrame(base_needs)
                            st.dataframe(base_df, use_container_width=True)
                            st.info('这些模块在基准分群中表现明显偏差，但在对比分群中仅达到一般水平，属于"打不好会极大拖累整体"的基础型体验。')
                        else:
                            st.write("当前未识别到明显的基础型需求模块（按当前阈值判断）。")
                elif len(radar_features) < 3:
                    st.info("当前选择的满意度细项少于 3 个，暂不绘制雷达图。")
                else:
                    st.info("请至少选择 2 个群体进行对比。")
            except Exception as e:
                st.warning(f"在构建群体对比雷达图时出现问题：{e}")

            # 样本级聚类结果：行号 / 可选样本标识 / 分群标签
            st.markdown("**样本级聚类结果（查看每个问卷样本被分到哪个群）**")
            cluster_detail = pd.DataFrame({
                "问卷行号": df_clustered.index
            })
            if id_col != "（使用问卷行号代替）" and id_col in df.columns:
                cluster_detail[id_col] = df[id_col].loc[df_clustered.index].values
            cluster_detail["玩家分群"] = df_clustered["玩家分群"].values

            st.dataframe(cluster_detail, use_container_width=True)

        # --- TAB 3: 多元回归（驱动力与优先级诊断） ---
        with tab3:
            st.subheader("📈 多元回归：模块驱动力与优先级诊断")

            # 聚类群体选择
            cluster_option = "整体数据"
            if cluster_results is not None:
                # 将聚类结果添加到原始数据中，以便在回归分析中使用
                df['玩家分群'] = cluster_results['df_clustered']['玩家分群']
                analyzer.data['玩家分群'] = cluster_results['df_clustered']['玩家分群']
                
                # 提供聚类群体选择
                available_clusters = sorted(cluster_results['df_clustered']['玩家分群'].unique().tolist())
                cluster_options = ["整体数据"] + [f"聚类群体 {i}" for i in available_clusters]
                cluster_option = st.selectbox(
                    "选择要分析的数据群体",
                    options=cluster_options,
                    key="cluster_option_regression"
                )

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
                key="game_regression_missing_strategy",
            )
            missing_strategy = missing_strategy_options[missing_strategy_label]
            missing_group_col = None
            if missing_strategy in ("group_mean", "group_median"):
                group_candidates = [c for c in df.columns if c not in [target_col] + selected_features]
                if not group_candidates:
                    st.warning("未找到可用分组列，当前策略将自动回退为整体均值填补。")
                    missing_strategy = "mean"
                else:
                    missing_group_col = st.selectbox(
                        "选择分组填补列",
                        options=group_candidates,
                        key="game_regression_missing_group_col",
                    )

            try:
                # 确定要分析的聚类群体
                selected_cluster = None
                if cluster_option != "整体数据":
                    # 提取聚类群体编号
                    selected_cluster = int(cluster_option.split()[-1])
                
                # 使用分析器执行回归分析
                regression_results = analyzer.regression_analysis(
                    selected_features,
                    target_col,
                    cluster=selected_cluster,
                    missing_strategy=missing_strategy,
                    missing_group_col=missing_group_col,
                )
                
                results_df = regression_results["results_df"]
                final_model = regression_results["final_model"]
                model_raw = regression_results["model_raw"]
                alpha = regression_results["alpha"]
                sample_size = regression_results["sample_size"]
                df_clean = regression_results["df_clean"]

                # 模型健康度总览
                st.divider()
                st.subheader("🛡️ 模型健康度总览")
                c1, c2, c3 = st.columns(3)

                c1.metric("题目内部一致性 (Cronbach's α)", f"{alpha:.3f}" if not np.isnan(alpha) else "NA")
                c2.metric("有效样本量", f"{sample_size} 份")
                c3.metric("整体满意度解释力 (R²)", f"{final_model.rsquared:.3f}")

                # 共线性与显著性计算
                st.divider()
                st.subheader("🔍 模块共线性与显著性")

                X = df_clean[selected_features]
                
                # VIF
                X_vif_input = sm.add_constant(X)
                vif_values = [variance_inflation_factor(X_vif_input.values, i + 1) for i in range(len(selected_features))]

                st.sidebar.subheader("🔍 共线性健康度设置（多元回归）")
                vif_threshold = st.sidebar.number_input(
                    "VIF 警戒线（>10 一般认为共线性严重）",
                    min_value=1.0, max_value=50.0, value=10.0, step=0.5,
                    key="vif_threshold_regression"
                )
                high_vif_items = [selected_features[i] for i, v in enumerate(vif_values) if v > vif_threshold]
                if high_vif_items:
                    st.sidebar.warning(
                        "以下模块存在 **较强共线性**，在解读回归结果时需谨慎，可考虑合并或剔除：\n- " +
                        "\n-".join(high_vif_items)
                    )
                else:
                    st.sidebar.success("当前所有模块的 VIF 均低于设定警戒线，共线性处于可接受范围。")

                # 自动变量筛选：显著性 + 共线性（核心模型）
                st.sidebar.subheader("🧠 自动变量筛选（核心回归模型）")
                auto_filter = st.sidebar.checkbox(
                    "启用基于显著性与共线性的核心模型推荐",
                    value=True,
                    key="auto_filter_regression"
                )
                p_threshold = st.sidebar.selectbox(
                    "显著性阈值（P 值）",
                    options=[0.01, 0.05, 0.1],
                    index=1,
                    format_func=lambda x: f"{x}",
                    key="p_threshold_regression"
                )

                if auto_filter:
                    core_mask = (results_df["P值(显著性)"] < p_threshold) & (results_df["共线性(VIF)"] <= vif_threshold)
                else:
                    core_mask = pd.Series([True] * len(results_df), index=results_df.index)

                results_df["是否纳入核心模型"] = np.where(core_mask, "是", "否")

                # IPA 驱动力矩阵
                st.divider()
                st.subheader("🎯 模块驱动力决策矩阵 (IPA)")

                m_score = results_df["平均得分"].mean()
                m_beta = results_df["影响力(Beta系数)"].mean()

                # 增强 IPA：加入气泡大小（这里用 Beta 的绝对值 * 10 作为演示，用户可以自定义）
                results_df["气泡大小"] = results_df["影响力(Beta系数)"].abs() * 10

                fig_ipa = px.scatter(
                    results_df, x="平均得分", y="影响力(Beta系数)", text="模块名称",
                    size="气泡大小",
                    color="统计结论",
                    color_discrete_map={
                        "极显著 ✅": "#ef553b",
                        "显著 ✅": "#636efa",
                        "不显著 (噪音) ❌": "#ababab"
                    },
                    hover_data=["P值(显著性)", "共线性(VIF)", "共线性结论", "改进优先级得分", "是否纳入核心模型"],
                    template="plotly_white", height=600
                )
                fig_ipa.add_hline(y=m_beta, line_dash="dash", line_color="red", annotation_text="高影响力标准")
                fig_ipa.add_vline(x=m_score, line_dash="dash", line_color="red", annotation_text="得分均值线")
                st.plotly_chart(fig_ipa, use_container_width=True)

                # 拖累项 & 护城河 + 文本总结
                st.divider()
                col_res, col_detail = st.columns([2, 1])

                with col_res:
                    st.subheader("📋 核心诊断结论")

                    draggers = results_df[
                        (results_df["是否纳入核心模型"] == "是") &
                        (results_df["影响力(Beta系数)"] > m_beta) &
                        (results_df["平均得分"] < m_score)
                    ]

                    moats = results_df[
                        (results_df["是否纳入核心模型"] == "是") &
                        (results_df["影响力(Beta系数)"] > m_beta) &
                        (results_df["平均得分"] >= m_score)
                    ]

                    if not draggers.empty:
                        st.error(f"识别到核心拖累模块：{', '.join(draggers['模块名称'].tolist())}")
                        st.write("💡 **改进建议：** 这些模块在统计上对整体满意度有显著拉动作用，但当前体验得分偏低，优先作为改进抓手。")
                    else:
                        st.success("🎉 当前未识别到显著的核心拖累模块。")

                    if not moats.empty:
                        st.info(f"识别到优势护城河模块：{', '.join(moats['模块名称'].tolist())}")
                        st.write("✅ 这些模块对整体满意度有显著正向拉动，且当前评价较高，建议作为优势重点维护。")

                    summary_lines = []
                    alpha_str = f"{alpha:.3f}" if not np.isnan(alpha) else "NA"
                    summary_lines.append(
                        f"模型健康度：有效样本量 {sample_size} 份，Cronbach's α = {alpha_str}，回归 R² = {final_model.rsquared:.3f}。"
                    )
                    if high_vif_items:
                        summary_lines.append(
                            f"共线性诊断：存在 VIF 高于设定阈值的模块（{', '.join(high_vif_items)}），"
                            f"解读这些模块的系数时需注意共线性风险。"
                        )
                    else:
                        summary_lines.append("共线性诊断：当前所有模块的 VIF 均低于设定警戒线，共线性处于可接受范围。")

                    if not draggers.empty:
                        summary_lines.append(
                            "核心拖累模块：{}。这些模块对整体满意度影响力较高但得分偏低，"
                            "建议优先投入资源进行体验修复。"
                            .format("、".join(draggers["模块名称"].tolist()))
                        )
                    else:
                        summary_lines.append("核心拖累模块：本次分析未识别到明显的核心拖累模块。")

                    if not moats.empty:
                        summary_lines.append(
                            "优势护城河模块：{}。这些模块对整体满意度拉动显著且当前评价高，"
                            "建议在保持投入的同时持续监测趋势。"
                            .format("、".join(moats["模块名称"].tolist()))
                        )

                    summary_lines.append(
                        "改进优先级：综合得分高低、影响力强弱与显著性，‘改进优先级得分’越高的模块越值得优先投入资源。"
                    )

                    text_summary = "\n".join(summary_lines)
                    st.markdown("**自动生成回归诊断摘要（可直接复制到报告/PPT）**")
                    st.text_area("", value=text_summary, height=200)

                with col_detail:
                    st.subheader("📊 模块回归明细表")
                    st.dataframe(
                        results_df.sort_values("改进优先级得分", ascending=False),
                        use_container_width=True
                    )

                # 保留简单场景模拟（基于未标准化模型系数）
                st.subheader("🧪 模块提升模拟：如果某个模块提升，会带动整体满意度多少？")
                
                simul_feature = st.selectbox(
                    "选择要模拟提升的模块",
                    options=[c for c in selected_features if c in model_raw.params.index],
                    key="simul_feature_regression"
                )
                delta = st.number_input(
                    "假设该模块平均分提升多少分？",
                    min_value=-5.0, max_value=5.0, value=0.5, step=0.1,
                    key="delta_regression"
                )

                if simul_feature:
                    beta = model_raw.params.get(simul_feature, 0.0)
                    delta_overall = beta * delta
                    st.write(
                        f"根据当前回归模型估计：如果 **[{simul_feature}]** 平均分提升 {delta:.2f} 分，"
                        f"整体满意度预计平均变化约 **{delta_overall:.3f} 分**（正数为提升，负数为下降）。"
                    )
                    
            except Exception as e:
                st.error(f"回归分析执行失败: {str(e)}")
                st.warning("⚠️ 请检查数据格式是否正确，确保所有选择的变量都是数值型。")
            
        # --- TAB 4: Kano & SHAP (多维归因) ---
        with tab4:
            st.subheader("💡 Kano模型分析 (识别‘必备’与‘魅力’属性)")
            kano_df = analyzer.kano_analysis(selected_features, target_col)
            
            # Kano 分类逻辑
            m_sat = kano_df["满意度"].mean()
            m_imp = kano_df["重要性(相关系数)"].mean()
            
            def classify_kano(row):
                if row["重要性(相关系数)"] > m_imp:
                    return "必备属性" if row["满意度"] < m_sat else "魅力属性"
                else:
                    return "期望属性" if row["满意度"] > m_sat else "无差异属性"
            
            kano_df["Kano分类"] = kano_df.apply(classify_kano, axis=1)
            
            fig_kano = px.scatter(kano_df, x="满意度", y="重要性(相关系数)", text="模块名称",
                                 color="Kano分类", size_max=40,
                                 title="Kano分析矩阵 (非对称满意度分析)")
            fig_kano.add_hline(y=m_imp, line_dash="dash")
            fig_kano.add_vline(x=m_sat, line_dash="dash")
            st.plotly_chart(fig_kano, use_container_width=True)
            
            st.subheader("🌳 机器学习归因 (Random Forest + SHAP)")
            if shap:
                with st.spinner("正在计算 SHAP 值..."):
                    shap_df, shap_values, X_shap = analyzer.shap_importance(selected_features, target_col)
                    
                    st.write("SHAP 特征重要性 (处理非线性交互):")
                    fig_shap = px.bar(shap_df, x="SHAP重要性", y="模块名称", orientation='h',
                                     title="SHAP 特征重要性 (绝对值平均)")
                    st.plotly_chart(fig_shap, use_container_width=True)
                    
                    st.info("💡 SHAP 值比传统回归系数更能捕捉特征间的非线性交互作用。")
            else:
                st.warning("⚠️ 未检测到 `shap` 库，展示随机森林特征重要性：")
                shap_df, _, _ = analyzer.shap_importance(selected_features, target_col)
                st.dataframe(shap_df)

        # --- TAB 5: 路径分析 (SEM) ---
        with tab5:
            st.subheader("🕸️ 路径分析 (模块间的传导机制)")
            st.markdown("构建模型语法示例: `Latent1 =~ V1 + V2 \n Y ~ Latent1`")

            # 聚类群体选择
            cluster_option = "整体数据"
            if cluster_results is not None:
                # 确保聚类结果已经添加到原始数据中
                if '玩家分群' not in df.columns:
                    df['玩家分群'] = cluster_results['df_clustered']['玩家分群']
                    analyzer.data['玩家分群'] = cluster_results['df_clustered']['玩家分群']
                
                # 提供聚类群体选择
                available_clusters = sorted(cluster_results['df_clustered']['玩家分群'].unique().tolist())
                cluster_options = ["整体数据"] + [f"聚类群体 {i}" for i in available_clusters]
                cluster_option = st.selectbox(
                    "选择要分析的数据群体",
                    options=cluster_options,
                    key="cluster_option_path"
                )

            # 确定要分析的聚类群体
            selected_cluster = None
            if cluster_option != "整体数据":
                # 提取聚类群体编号
                selected_cluster = int(cluster_option.split()[-1])

            # 为避免中文题干、空格等导致 semopy 语法错误，这里为 SEM 单独生成安全变量名
            sem_cols = list(dict.fromkeys(selected_features + [target_col]))
            safe_names = {col: f"V{i+1}" for i, col in enumerate(sem_cols)}
            inv_safe_names = {v: k for k, v in safe_names.items()}
            df_sem = df[sem_cols].rename(columns=safe_names)

            # 基于相关性 + 多元回归结果，自动推荐一个 SEM 模型语法（避免因子分析在某些版本下失败）
            recommended_spec = analyzer.generate_recommended_model_spec(selected_features, target_col, cluster=selected_cluster)

            st.markdown("**自动推荐的模型语法（可按需修改）：**")
            model_spec = st.text_area("输入路径模型 (semopy 语法)", recommended_spec, height=120)

            st.markdown("**变量名对照表（请在上方模型语法中使用左侧自动变量名）：**")
            mapping_df = pd.DataFrame({
                "自动变量名": [safe_names[c] for c in sem_cols],
                "原始题目": sem_cols
            })
            st.dataframe(mapping_df, use_container_width=True)
            
            if st.button("运行路径分析"):
                try:
                    # 使用分析器执行路径分析
                    path_results = analyzer.path_analysis(selected_features, target_col, model_spec, cluster=selected_cluster)
                    estimates = path_results["estimates"]
                    inv_safe_names = path_results["inv_safe_names"]
                    
                    st.write("原始估计结果表：")
                    st.dataframe(estimates, use_container_width=True)

                    # 结果可读性提升：根据 estimates 自动生成文字总结
                    try:
                        summary_lines = []

                        # 1) 潜在因子结构：op == '=~'
                        if "op" in estimates.columns:
                            loading_rows = estimates[estimates["op"] == "=~"]
                            if not loading_rows.empty:
                                summary_lines.append("【潜在因子与题目关系】")
                                for latent in loading_rows["lval"].unique():
                                    rows_l = loading_rows[loading_rows["lval"] == latent]
                                    items_desc = []
                                    for _, r in rows_l.iterrows():
                                        v_name = r["rval"]
                                        try:
                                            est_value = r.get("Estimate", r.get("estimate", 0.0))
                                            est = float(est_value) if est_value != '-' else 0.0
                                        except (ValueError, TypeError):
                                            est = 0.0
                                        orig_name = inv_safe_names.get(v_name, v_name)
                                        items_desc.append(f"{orig_name}（载荷 {est:.2f}）")
                                    if items_desc:
                                        summary_lines.append(
                                            f"- 因子 {latent} 主要由：{ '，'.join(items_desc) } 共同反映。"
                                        )

                        # 2) 路径关系：op == '~'
                        if "op" in estimates.columns:
                            path_rows = estimates[estimates["op"] == "~"]
                            if not path_rows.empty:
                                summary_lines.append("\n【路径与影响方向】")
                                for _, r in path_rows.iterrows():
                                    dst = r["lval"]
                                    src = r["rval"]
                                    try:
                                        est_value = r.get("Estimate", r.get("estimate", 0.0))
                                        est = float(est_value) if est_value != '-' else 0.0
                                    except (ValueError, TypeError):
                                        est = 0.0
                                    try:
                                        pval_value = r.get("P-value", r.get("p-value", r.get("pval", 1.0)))
                                        pval = float(pval_value) if pval_value != '-' else 1.0
                                    except (ValueError, TypeError):
                                        pval = 1.0

                                    # 将整体满意度变量名翻译回原始题目
                                    dst_name = inv_safe_names.get(dst, dst)
                                    src_name = inv_safe_names.get(src, src)

                                    signif_tag = "显著" if pval < 0.05 else "不显著"
                                    direction = "正向提升" if est > 0 else "负向影响"
                                    summary_lines.append(
                                        f"- {src_name} → {dst_name}：系数约为 {est:.2f}（P={pval:.3f}，{signif_tag}），"
                                        f"影响方向为 {direction}。"
                                    )

                        if summary_lines:
                            st.markdown("**路径分析文字总结（可直接复制到报告）**")
                            st.text_area("", value="\n".join(summary_lines), height=200)
                            
                            # 路径图可视化 (使用 Plotly)
                            st.subheader("🕸️ 动态路径图")
                            path_rows = estimates[estimates["op"] == "~"]
                            if not path_rows.empty:
                                # 为可视化构建节点位置
                                nodes = list(set(path_rows["lval"].tolist() + path_rows["rval"].tolist()))
                                pos = {node: [np.random.rand(), np.random.rand()] for node in nodes}
                                
                                edge_x = []
                                edge_y = []
                                for _, r in path_rows.iterrows():
                                    x0, y0 = pos[r["rval"]]
                                    x1, y1 = pos[r["lval"]]
                                    edge_x.extend([x0, x1, None])
                                    edge_y.extend([y0, y1, None])
                                
                                fig_path = go.Figure()
                                fig_path.add_trace(go.Scatter(x=edge_x, y=edge_y, line=dict(width=2, color='#888'),
                                                             hoverinfo='none', mode='lines'))
                                
                                node_x = [pos[node][0] for node in nodes]
                                node_y = [pos[node][1] for node in nodes]
                                node_text = [inv_safe_names.get(node, node) for node in nodes]
                                
                                fig_path.add_trace(go.Scatter(x=node_x, y=node_y, mode='markers+text',
                                                             text=node_text, textposition="top center",
                                                             marker=dict(size=20, color='SkyBlue')))
                                fig_path.update_layout(title="路径分析节点图", showlegend=False)
                                st.plotly_chart(fig_path, use_container_width=True)
                        else:
                            st.info("未能生成文字总结，请检查模型语法或结果格式。")
                    except Exception as e:
                        st.warning(f"在生成路径分析文字总结时出现问题：{e}")
                        st.info("请直接参考上方原始估计结果表进行解读。")
                except Exception as e:
                    st.error(f"路径分析执行失败: {str(e)}")
                    st.warning("⚠️ 建议：1) 检查模型语法是否正确 2) 确保变量名与左侧对照表一致 3) 尝试简化模型结构")

        # --- 决策中心 (决策模拟与一键报告) ---
        st.divider()
        st.header("🎯 决策中心")
        
        col_sim, col_report = st.columns(2)
        
        with col_sim:
            st.subheader("🔋 资源分配模拟器")
            st.write("假设你有 100 点人力资源，请分配给不同模块：")
            
            # 使用回归系数作为权重
            try:
                # 重新计算一次整体回归以获取系数
                reg_all = analyzer.regression_analysis(
                    selected_features,
                    target_col,
                    missing_strategy=missing_strategy,
                    missing_group_col=missing_group_col,
                )
                coeffs = reg_all["results_df"].set_index("模块名称")["影响力(Beta系数)"]
                
                allocation = {}
                total_points = 0
                for feat in selected_features:
                    allocation[feat] = st.slider(f"分配给 [{feat}]", 0, 100, 0)
                    total_points += allocation[feat]
                
                if total_points > 100:
                    st.error(f"总点数 ({total_points}) 超过了 100 点！")
                else:
                    # 计算预计提升
                    # 假设 1 点人力提升 0.01 分 (这只是一个示例比例)
                    improvement = sum(allocation[feat] * coeffs[feat] * 0.01 for feat in selected_features)
                    st.metric("预计整体满意度提升", f"+{improvement:.3f} 分")
                    st.info(f"剩余人力点数: {100 - total_points}")
            except:
                st.info("请先完成回归分析以启用模拟器。")

        with col_report:
            st.subheader("📄 自动化一键报告")
            st.write("将所有分析结果（包含建议与图表说明）导出。")
            
            # 生成简单的报告文本
            report_text = f"游戏体验分析报告\n目标变量: {target_col}\n分析模块: {', '.join(selected_features)}\n\n"
            report_text += "--- 核心结论 ---\n"
            # 这里可以从之前的分析结果中提取更多文字
            
            if "game_analyst_report_fn" not in st.session_state:
                st.session_state.game_analyst_report_fn = "game_analysis_report.txt"
            st.text_input("下载文件名（可修改）", key="game_analyst_report_fn")
            _ga_fn = safe_download_filename(
                st.session_state.get("game_analyst_report_fn", "game_analysis_report.txt"),
                fallback="game_analysis_report.txt",
            )
            st.download_button(
                label="下载分析简报 (TXT格式)",
                data=report_text,
                file_name=_ga_fn,
                mime="text/plain",
            )
            
            st.info("💡 高级版可集成 python-docx 生成带图表的 Word 文档。")
