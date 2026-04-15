import pandas as pd
import numpy as np

from factor_analyzer import FactorAnalyzer
from sklearn.preprocessing import StandardScaler
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from semopy import Model
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import silhouette_score
from survey_tools.core.factor_compat import (
    factor_analyzer_compat,
    is_factor_compat_error,
    build_factor_compat_message,
)
from survey_tools.core.missing_strategy import apply_missing_strategy
try:
    import shap
except ImportError:
    shap = None
from scipy import stats

from survey_tools.utils.streamlit_cached_helpers import cached_kmeans_fit, cached_rf_fit


class GameExperienceAnalyzer:
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
        # core 层必须持有副本，避免分析过程中的赋值/清洗污染外部原始数据
        self.data = data.copy()
        # 统一收集 core 层警告，由 web 层按需展示
        self.warnings: list[str] = []

    def _reset_warnings(self) -> None:
        """清空当前实例缓存的警告消息。"""
        self.warnings = []

    def data_quality_check(self, features: list, time_col: str = None, min_duration: int = 30):
        """数据质量检查：检测直线勾选、作答时长过短、缺失值和离群值。

        Args:
            features: list[str]，参与质量检查的特征列名列表（需为数值型）。
            time_col: str or None，作答时长列名；为 None 时跳过时长检查。
            min_duration: int，最短作答时长阈值（秒），低于此值标记为异常（默认 30）。

        Returns:
            dict，质量报告，含以下键：
              - "straight_liners": pd.Index，直线勾选行索引。
              - "short_duration": pd.Index or None，作答时长过短行索引。
              - "missing_rates": pd.Series，各列缺失率。
              - "outliers": pd.Index，离群样本行索引（Z-score > 3）。
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
            # 先整体数值化，再用数值化后的列均值填补，避免原始对象列参与 mean 导致类型错误
            numeric_df = self.data[features].apply(pd.to_numeric, errors='coerce')
            numeric_df = numeric_df.fillna(numeric_df.mean())
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
                raise RuntimeError(build_factor_compat_message()) from te
            raise te
        except Exception as e:
            if is_factor_compat_error(e):
                raise RuntimeError(build_factor_compat_message()) from e
            raise RuntimeError(f"因子分析执行失败: {str(e)}") from e
    
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
        
        # 性能优化：对于大型数据集使用采样
        if len(analysis_df) > 1000:
            sample_size = 1000
            sampled_data = analysis_df.sample(sample_size, random_state=42)
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(sampled_data)
            kmeans = cached_kmeans_fit(
                np.ascontiguousarray(scaled_data, dtype=np.float64),
                n_clusters,
                42,
            )
            # 计算轮廓系数
            silhouette_avg = silhouette_score(scaled_data, kmeans.labels_)
            # 对所有数据进行预测
            all_scaled = scaler.transform(analysis_df)
            labels = kmeans.predict(all_scaled)
        else:
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(analysis_df)
            kmeans = cached_kmeans_fit(
                np.ascontiguousarray(scaled_data, dtype=np.float64),
                n_clusters,
                42,
            )
            silhouette_avg = silhouette_score(scaled_data, kmeans.labels_)
            labels = kmeans.labels_
        
        df_clustered = analysis_df.copy()
        df_clustered['玩家分群'] = labels
        
        return df_clustered, kmeans.cluster_centers_, scaler, silhouette_avg

    def ipa_quadrant_analysis(self, features: list, target: str):
        """执行 IPA 象限分析（非经典双问法 Kano）。

        注意：该方法基于满意度与推导重要性（相关系数）做四象限分类，
        并非经典 Kano 双问法模型。
        """
        self._reset_warnings()
        if not features:
            self.warnings.append("未选择可分析特征，IPA 分析已跳过。")
            return pd.DataFrame()
        missing_cols = [c for c in [target] + features if c not in self.data.columns]
        if missing_cols:
            self.warnings.append(f"IPA 分析存在缺失列：{missing_cols}")
            return pd.DataFrame()

        df_clean = self.data[[target] + features].dropna()
        if df_clean.empty or len(df_clean) < 5:
            self.warnings.append("有效样本过少，IPA 分析结果可能不可靠。")
            return pd.DataFrame()

        y = df_clean[target]
        results = []
        for feat in features:
            corr = df_clean[feat].corr(y)
            mean_score = df_clean[feat].mean()
            results.append(
                {
                    "模块名称": feat,
                    "满意度": mean_score,
                    "推导重要性(相关系数)": corr if pd.notna(corr) else 0.0,
                }
            )

        df_result = pd.DataFrame(results)
        if df_result.empty:
            self.warnings.append("IPA 分析未产出可用结果。")
            return df_result

        crosshair_imp = df_result["推导重要性(相关系数)"].median()
        crosshair_sat = df_result["满意度"].median()

        def classify_quadrant(row: pd.Series) -> str:
            imp = row["推导重要性(相关系数)"]
            sat = row["满意度"]
            if imp >= crosshair_imp and sat < crosshair_sat:
                return "亟待改进 (Must-be/痛点)"
            if imp >= crosshair_imp and sat >= crosshair_sat:
                return "优势保持 (核心卖点)"
            if imp < crosshair_imp and sat >= crosshair_sat:
                return "锦上添花 (魅力属性)"
            return "次要观察 (无差异)"

        df_result["IPA四象限分类"] = df_result.apply(classify_quadrant, axis=1)
        return df_result

    def kano_analysis(self, features: list, target: str):
        """兼容旧调用：转发至 IPA 象限分析。"""
        return self.ipa_quadrant_analysis(features, target)

    def shap_importance(
        self,
        features: list,
        target: str,
        missing_strategy: str = "median",
        missing_group_col: str = None,
    ):
        """使用随机森林模型和 SHAP 值计算各特征对目标变量的重要性排名。

        Args:
            features: list[str]，参与分析的特征列名列表（自变量）。
            target: str，目标变量列名（因变量，如整体满意度分）。

        Returns:
            pd.DataFrame，按 SHAP 重要性降序排列，含 feature/importance 两列。
        """
        self._reset_warnings()
        if not features:
            raise ValueError("未选择特征列，无法进行 SHAP 分析。")
        missing_cols = [c for c in [target] + features if c not in self.data.columns]
        if missing_cols:
            raise ValueError(f"SHAP 分析存在缺失列: {missing_cols}")

        df_source = self.data[[target] + features].copy()
        df_source = df_source.dropna(subset=[target])
        if len(df_source) < 10:
            raise ValueError(f"目标变量有效样本仅剩 {len(df_source)} 条，不足以进行随机森林 SHAP 分析。")

        df_clean = self._apply_missing_strategy(
            df_source,
            strategy=missing_strategy,
            group_col=missing_group_col,
        ).astype(np.float64)
        X = df_clean[features]
        y = df_clean[target]
        feat_tuple = tuple(features)
        model = cached_rf_fit(
            np.ascontiguousarray(X.values.astype(np.float64)),
            np.ascontiguousarray(y.values.astype(np.float64)),
            feat_tuple,
            100,
            42,
        )
        
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
        self._reset_warnings()
        selected_all = [target] + features
        # 增加缺失值比例检查，防止均值填充导致的偏差
        missing_ratios = self.data[selected_all].isnull().mean()
        high_missing_cols = missing_ratios[missing_ratios > 0.1].index.tolist()
        if high_missing_cols:
            missing_info = []
            for col in high_missing_cols:
                rate = missing_ratios[col]
                missing_info.append(f"- {col}: 缺失 {rate:.1%}")
            self.warnings.append(
                "数据健康度预警：检测到高缺失率列（常见于跳题逻辑）。\n"
                + "\n".join(missing_info)
                + "\n风险提示：对分支题目强行填补会导致回归失真，建议先做人群筛选。"
            )

        df_source = self.data[selected_all].copy()
        if cluster is not None and '玩家分群' in self.data.columns:
            cluster_mask = self.data['玩家分群'] == cluster
            df_source = df_source.loc[cluster_mask].copy()
        df_clean = self._apply_missing_strategy(df_source, strategy=missing_strategy, group_col=missing_group_col).astype(np.float64)
        
        # 如果指定了聚类群体，只分析该群体的数据
        if cluster is not None:
            # 确保聚类信息存在
            if '玩家分群' in self.data.columns:
                if df_clean.shape[0] < 10:
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

        def vif_penalty(v):
            if v > 10:
                return 0.1
            if v > 5:
                return 0.5
            return 1.0

        sig_weights = results_df["P值(显著性)"].apply(sig_weight)
        vif_penalties = results_df["共线性(VIF)"].apply(vif_penalty)
        # TODO: 当前 VIF 惩罚为业务启发式规则。长期可引入逐步回归或 Ridge 双轨模型。
        priority_raw = score_severity * beta_strength * sig_weights * vif_penalties
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
            raise RuntimeError(f"路径分析执行失败: {str(e)}") from e
    
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
