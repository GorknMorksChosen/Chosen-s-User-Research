import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
from scipy.cluster.hierarchy import linkage
from survey_tools.core.factor_compat import (
    factor_analyzer_compat,
    is_factor_compat_error,
    build_factor_compat_message,
)

try:
    from factor_analyzer import FactorAnalyzer
except ImportError:
    FactorAnalyzer = None
try:
    from kneed import KneeLocator
except ImportError:
    KneeLocator = None

def check_missing_rates(df: pd.DataFrame, feature_cols: list) -> pd.Series:
    """计算各特征列的缺失率，用于聚类前的数据质量诊断。

    Args:
        df: pd.DataFrame，原始数据。
        feature_cols: list[str]，需要检查的特征列名列表。

    Returns:
        pd.Series，索引为列名，值为缺失率（0~1 浮点数）。
    """
    return df[feature_cols].isnull().mean()

def clean_data(df: pd.DataFrame, feature_cols: list, method: str = 'drop') -> pd.DataFrame:
    """清理缺失值，支持删除含缺失行或按均值/中位数填补。

    Args:
        df: pd.DataFrame，原始数据。
        feature_cols: list[str]，需要清理的特征列名列表。
        method: str，缺失处理方式，支持 'drop'（删行）/ 'mean'（均值填补）/ 'median'（中位数填补）。

    Returns:
        pd.DataFrame，清理后的数据副本（行数可能减少）。

    Raises:
        ValueError: method 不在支持列表中时抛出。
    """
    if method == 'drop':
        return df.dropna(subset=feature_cols).copy()
    elif method == 'mean':
        df_clean = df.copy()
        imputer = SimpleImputer(strategy='mean')
        df_clean[feature_cols] = imputer.fit_transform(df[feature_cols])
        return df_clean
    elif method == 'median':
        df_clean = df.copy()
        imputer = SimpleImputer(strategy='median')
        df_clean[feature_cols] = imputer.fit_transform(df[feature_cols])
        return df_clean
    else:
        raise ValueError("Method must be 'drop', 'mean', or 'median'")

def preprocess_features(df: pd.DataFrame, feature_cols: list) -> tuple[pd.DataFrame, object]:
    """对特征列进行 Z-score 标准化，消除量纲影响。

    Args:
        df: pd.DataFrame，清理后的数据（无缺失值）。
        feature_cols: list[str]，需要标准化的特征列名列表。

    Returns:
        tuple[pd.DataFrame, StandardScaler]，标准化后的 DataFrame 和已拟合的 Scaler 对象。
    """
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(df[feature_cols])
    df_scaled = pd.DataFrame(scaled_data, columns=feature_cols, index=df.index)
    return df_scaled, scaler

def perform_factor_analysis(df_scaled: pd.DataFrame, n_factors: int = None) -> pd.DataFrame:
    """对标准化后的特征数据进行因子分析，提取潜在因子用于降维。

    使用 Varimax 旋转提取因子；若 n_factors 未指定，按 Kaiser 准则（特征值 > 1）自动确定因子数（最少 2 个）。

    Args:
        df_scaled: pd.DataFrame，已标准化的特征 DataFrame。
        n_factors: int or None，提取的因子数量；为 None 时自动确定。

    Returns:
        pd.DataFrame，因子得分矩阵，列名为 Factor_1, Factor_2, ...

    Raises:
        ImportError: factor_analyzer 库未安装时抛出。
        Exception: 因子分析因数值问题失败时重新抛出，附带兼容性提示信息。
    """
    if FactorAnalyzer is None:
        raise ImportError("factor_analyzer library is not installed.")

    try:
        with factor_analyzer_compat():
            if n_factors is None:
                fa_check = FactorAnalyzer(rotation=None)
                fa_check.fit(df_scaled)
                ev, _ = fa_check.get_eigenvalues()
                n_factors = sum(ev > 1)
                n_factors = max(2, n_factors)

            fa = FactorAnalyzer(n_factors=n_factors, rotation='varimax')
            fa.fit(df_scaled)
            factor_scores = fa.transform(df_scaled)
    except Exception as e:
        if is_factor_compat_error(e):
            raise Exception(build_factor_compat_message())
        raise
    
    col_names = [f'Factor_{i+1}' for i in range(n_factors)]
    return pd.DataFrame(factor_scores, columns=col_names, index=df_scaled.index)

def find_optimal_k(data: pd.DataFrame, k_range: range = range(2, 9)) -> dict:
    """通过肘部法和轮廓系数推荐最优 K 值范围内的最佳聚类数。

    遍历 k_range 中每个 K，计算 KMeans 的 WCSS（组内平方和）和轮廓系数，
    使用 KneeLocator 定位肘部，回退时取轮廓系数最大的 K。

    Args:
        data: pd.DataFrame，标准化后的特征数据（或因子得分矩阵）。
        k_range: range，候选 K 值范围（默认 2~8）。

    Returns:
        dict，含以下键：
          - "wcss": list[float]，各 K 对应的 WCSS 值。
          - "silhouette": list[float]，各 K 对应的轮廓系数。
          - "k_values": list[int]，测试的 K 值列表。
          - "optimal_k": int，推荐的最优 K 值。
    """
    wcss = []
    silhouette_scores = []
    
    for k in k_range:
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        kmeans.fit(data)
        wcss.append(kmeans.inertia_)
        
        # Silhouette requires at least 2 clusters
        score = silhouette_score(data, kmeans.labels_)
        silhouette_scores.append(score)
    
    optimal_k = None
    if KneeLocator:
        kl = KneeLocator(list(k_range), wcss, curve="convex", direction="decreasing")
        optimal_k = kl.elbow
    
    # Fallback if KneeLocator fails or isn't installed: use max silhouette
    if optimal_k is None:
        optimal_k = k_range[np.argmax(silhouette_scores)]

    return {
        'wcss': wcss,
        'silhouette': silhouette_scores,
        'k_values': list(k_range),
        'optimal_k': optimal_k
    }

def _fit_predict_by_algorithm(df_features: pd.DataFrame, k: int, algorithm: str, random_state: int = 42):
    if algorithm == "kmeans":
        model = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        labels = model.fit_predict(df_features)
        return labels
    if algorithm == "gmm":
        model = GaussianMixture(n_components=k, random_state=random_state)
        labels = model.fit_predict(df_features)
        return labels
    if algorithm == "agglomerative":
        model = AgglomerativeClustering(n_clusters=k)
        labels = model.fit_predict(df_features)
        return labels
    raise ValueError(f"不支持的聚类算法: {algorithm}")

def evaluate_clustering_algorithms(
    df_features: pd.DataFrame,
    k: int,
    algorithms: list = None,
    random_state: int = 42,
) -> pd.DataFrame:
    """在指定 K 值下对多种聚类算法进行评估，计算三项质量指标。

    对每个算法分别执行聚类，计算轮廓系数（越高越好）、
    Calinski-Harabasz 指数（越高越好）、Davies-Bouldin 指数（越低越好）
    及分群规模不均衡比。

    Args:
        df_features: pd.DataFrame，用于聚类的特征数据（标准化或因子得分）。
        k: int，聚类数量。
        algorithms: list[str] or None，待评估的算法列表；
            默认为 ["kmeans", "gmm", "agglomerative"]。
        random_state: int，随机种子（默认 42）。

    Returns:
        pd.DataFrame，每行对应一个算法，列包含
        algorithm/silhouette/calinski_harabasz/davies_bouldin/
        min_cluster_size/max_cluster_size/imbalance_ratio/status。
    """
    if algorithms is None:
        algorithms = ["kmeans", "gmm", "agglomerative"]
    rows = []
    for algo in algorithms:
        try:
            labels = _fit_predict_by_algorithm(df_features, k, algo, random_state=random_state)
            unique_labels = np.unique(labels)
            if len(unique_labels) < 2:
                raise ValueError("聚类结果簇数量不足，无法计算评估指标。")
            sil = silhouette_score(df_features, labels)
            ch = calinski_harabasz_score(df_features, labels)
            db = davies_bouldin_score(df_features, labels)
            cluster_sizes = pd.Series(labels).value_counts()
            min_size = int(cluster_sizes.min())
            max_size = int(cluster_sizes.max())
            imbalance = (max_size / min_size) if min_size > 0 else np.nan
            rows.append(
                {
                    "algorithm": algo,
                    "silhouette": sil,
                    "calinski_harabasz": ch,
                    "davies_bouldin": db,
                    "min_cluster_size": min_size,
                    "max_cluster_size": max_size,
                    "imbalance_ratio": imbalance,
                    "status": "ok",
                }
            )
        except Exception as e:
            rows.append(
                {
                    "algorithm": algo,
                    "silhouette": np.nan,
                    "calinski_harabasz": np.nan,
                    "davies_bouldin": np.nan,
                    "min_cluster_size": np.nan,
                    "max_cluster_size": np.nan,
                    "imbalance_ratio": np.nan,
                    "status": f"error: {e}",
                }
            )
    return pd.DataFrame(rows)

RECOMMENDATION_PROFILES = {
    "balanced": {
        "weights": {
            "rank_silhouette": 0.4,
            "rank_ch": 0.3,
            "rank_db": 0.2,
            "rank_imbalance": 0.1,
            "rank_k": 0.1,
        },
        "fallback_guard": {"sil_gain": 0.015, "db_gain": 0.05, "imbalance_gain": 0.2},
    },
    "stability_first": {
        "weights": {
            "rank_silhouette": 0.3,
            "rank_ch": 0.15,
            "rank_db": 0.25,
            "rank_imbalance": 0.2,
            "rank_k": 0.1,
        },
        "fallback_guard": {"sil_gain": 0.02, "db_gain": 0.08, "imbalance_gain": 0.3},
    },
    "discrimination_first": {
        "weights": {
            "rank_silhouette": 0.5,
            "rank_ch": 0.25,
            "rank_db": 0.15,
            "rank_imbalance": 0.05,
            "rank_k": 0.05,
        },
        "fallback_guard": {"sil_gain": 0.01, "db_gain": 0.03, "imbalance_gain": 0.1},
    },
}

def _resolve_profile(profile: str) -> tuple[str, dict]:
    normalized = (profile or "balanced").strip().lower()
    if normalized not in RECOMMENDATION_PROFILES:
        normalized = "balanced"
    return normalized, RECOMMENDATION_PROFILES[normalized]

def _score_recommendation_dataframe(df: pd.DataFrame, profile_cfg: dict) -> pd.DataFrame:
    scored = df.copy()
    scored["rank_silhouette"] = scored["silhouette"].rank(ascending=False, method="min")
    scored["rank_ch"] = scored["calinski_harabasz"].rank(ascending=False, method="min")
    scored["rank_db"] = scored["davies_bouldin"].rank(ascending=True, method="min")
    scored["rank_imbalance"] = scored["imbalance_ratio"].rank(ascending=True, method="min")
    if "k" in scored.columns:
        scored["rank_k"] = scored["k"].rank(ascending=True, method="min")
    else:
        scored["rank_k"] = 0.0
    w = profile_cfg["weights"]
    scored["recommendation_score"] = (
        w["rank_silhouette"] * scored["rank_silhouette"]
        + w["rank_ch"] * scored["rank_ch"]
        + w["rank_db"] * scored["rank_db"]
        + w["rank_imbalance"] * scored["rank_imbalance"]
        + w["rank_k"] * scored["rank_k"]
    )
    return scored

def recommend_clustering_algorithm(
    eval_df: pd.DataFrame,
    fallback: str = "kmeans",
    profile: str = "balanced",
) -> dict:
    """根据多指标评估结果推荐最佳聚类算法。

    基于加权综合得分对算法排名；若推荐算法与 KMeans 差异不显著（由 profile 守卫阈值控制），
    则保守回退到 KMeans 以提升稳定性。

    Args:
        eval_df: pd.DataFrame，evaluate_clustering_algorithms 的输出结果。
        fallback: str，评估失败或无有效结果时的回退算法（默认 "kmeans"）。
        profile: str，推荐策略，支持 "balanced" / "stability_first" / "discrimination_first"。

    Returns:
        dict，含以下键：
          - "recommended_algorithm": str，推荐算法名称。
          - "reason": str，推荐理由说明。
          - "scored_df": pd.DataFrame，各算法加权得分详情。
          - "profile": str，实际使用的策略名称。
    """
    required_cols = {
        "algorithm",
        "silhouette",
        "calinski_harabasz",
        "davies_bouldin",
        "imbalance_ratio",
        "status",
    }
    profile_name, profile_cfg = _resolve_profile(profile)
    if eval_df is None or eval_df.empty or not required_cols.issubset(eval_df.columns):
        return {
            "recommended_algorithm": fallback,
            "reason": "评估结果为空，回退默认算法。",
            "scored_df": pd.DataFrame(),
            "profile": profile_name,
        }
    ok_df = eval_df[eval_df["status"] == "ok"].copy()
    if ok_df.empty:
        return {
            "recommended_algorithm": fallback,
            "reason": "无可用评估结果，回退默认算法。",
            "scored_df": pd.DataFrame(),
            "profile": profile_name,
        }
    ok_df = ok_df.dropna(
        subset=["silhouette", "calinski_harabasz", "davies_bouldin", "imbalance_ratio"]
    )
    if ok_df.empty:
        return {
            "recommended_algorithm": fallback,
            "reason": "评估指标存在缺失，回退默认算法。",
            "scored_df": pd.DataFrame(),
            "profile": profile_name,
        }
    ok_df = _score_recommendation_dataframe(ok_df, profile_cfg)
    scored_df = ok_df.sort_values(
        by=["recommendation_score", "silhouette", "davies_bouldin"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    top = scored_df.iloc[0]
    recommended = top["algorithm"]
    if "kmeans" in scored_df["algorithm"].values:
        km = scored_df[scored_df["algorithm"] == "kmeans"].iloc[0]
        sil_delta = float(top["silhouette"] - km["silhouette"])
        db_delta = float(km["davies_bouldin"] - top["davies_bouldin"])
        guard = profile_cfg["fallback_guard"]
        if recommended != "kmeans" and sil_delta < guard["sil_gain"] and db_delta < guard["db_gain"]:
            recommended = "kmeans"
            reason = "与KMeans差异不显著，保持默认稳定策略。"
        else:
            reason = (
                f"{recommended} 综合得分更优，"
                f"silhouette={top['silhouette']:.4f}，"
                f"davies_bouldin={top['davies_bouldin']:.4f}。"
            )
    else:
        reason = (
            f"{recommended} 综合得分最优，"
            f"silhouette={top['silhouette']:.4f}，"
            f"davies_bouldin={top['davies_bouldin']:.4f}。"
        )
    return {
        "recommended_algorithm": recommended,
        "reason": reason,
        "scored_df": scored_df,
        "profile": profile_name,
    }

def recommend_k_algorithm_combo(
    df_features: pd.DataFrame,
    k_values=range(2, 9),
    algorithms: list = None,
    random_state: int = 42,
    fallback_k: int = 3,
    fallback_algorithm: str = "kmeans",
    profile: str = "balanced",
) -> dict:
    """联合搜索最优 K 值与聚类算法组合，给出一体化推荐。

    遍历所有 K×算法 组合，用加权多指标综合得分选出最优组合；
    若最优组合相对回退基准（fallback_k + fallback_algorithm）优势不显著，则保持当前配置。

    Args:
        df_features: pd.DataFrame，用于聚类的特征数据。
        k_values: range or list，候选 K 值范围（默认 2~8）。
        algorithms: list[str] or None，候选算法列表；默认 ["kmeans", "gmm", "agglomerative"]。
        random_state: int，随机种子（默认 42）。
        fallback_k: int，无有效结果时的回退 K 值（默认 3）。
        fallback_algorithm: str，无有效结果时的回退算法（默认 "kmeans"）。
        profile: str，推荐策略，支持 "balanced" / "stability_first" / "discrimination_first"。

    Returns:
        dict，含以下键：
          - "recommended_k": int，推荐 K 值。
          - "recommended_algorithm": str，推荐算法。
          - "reason": str，推荐理由说明。
          - "grid_df": pd.DataFrame，所有 K×算法 的原始评估结果。
          - "scored_df": pd.DataFrame，加权得分排名详情。
          - "profile": str，实际使用的策略名称。
    """
    profile_name, profile_cfg = _resolve_profile(profile)
    k_list = list(k_values)
    if not k_list:
        return {
            "recommended_k": fallback_k,
            "recommended_algorithm": fallback_algorithm,
            "reason": "K 候选为空，回退默认配置。",
            "grid_df": pd.DataFrame(),
            "scored_df": pd.DataFrame(),
            "profile": profile_name,
        }
    frames = []
    for k in k_list:
        eval_df = evaluate_clustering_algorithms(
            df_features,
            k=int(k),
            algorithms=algorithms,
            random_state=random_state,
        )
        eval_df = eval_df.copy()
        eval_df["k"] = int(k)
        frames.append(eval_df)
    grid_df = pd.concat(frames, ignore_index=True)
    ok_df = grid_df[grid_df["status"] == "ok"].copy()
    ok_df = ok_df.dropna(
        subset=["silhouette", "calinski_harabasz", "davies_bouldin", "imbalance_ratio"]
    )
    if ok_df.empty:
        return {
            "recommended_k": fallback_k,
            "recommended_algorithm": fallback_algorithm,
            "reason": "联合评估无有效结果，回退默认配置。",
            "grid_df": grid_df,
            "scored_df": pd.DataFrame(),
            "profile": profile_name,
        }
    ok_df = _score_recommendation_dataframe(ok_df, profile_cfg)
    scored_df = ok_df.sort_values(
        by=["recommendation_score", "silhouette", "davies_bouldin", "imbalance_ratio"],
        ascending=[True, False, True, True],
    ).reset_index(drop=True)
    top = scored_df.iloc[0]
    recommended_k = int(top["k"])
    recommended_algorithm = top["algorithm"]
    reason = (
        f"联合评分最优：K={recommended_k}, 算法={recommended_algorithm}，"
        f"silhouette={top['silhouette']:.4f}, "
        f"davies_bouldin={top['davies_bouldin']:.4f}。"
    )
    baseline_df = scored_df[
        (scored_df["k"] == int(fallback_k)) & (scored_df["algorithm"] == fallback_algorithm)
    ]
    if not baseline_df.empty:
        base = baseline_df.iloc[0]
        sil_gain = float(top["silhouette"] - base["silhouette"])
        db_gain = float(base["davies_bouldin"] - top["davies_bouldin"])
        imbalance_gain = float(base["imbalance_ratio"] - top["imbalance_ratio"])
        guard = profile_cfg["fallback_guard"]
        if (
            (recommended_k != int(fallback_k) or recommended_algorithm != fallback_algorithm)
            and sil_gain < guard["sil_gain"]
            and db_gain < guard["db_gain"]
            and imbalance_gain < guard["imbalance_gain"]
        ):
            recommended_k = int(fallback_k)
            recommended_algorithm = fallback_algorithm
            reason = "相对当前配置优势不显著，保持当前 K 与算法。"
    return {
        "recommended_k": recommended_k,
        "recommended_algorithm": recommended_algorithm,
        "reason": reason,
        "grid_df": grid_df,
        "scored_df": scored_df,
        "profile": profile_name,
    }

def perform_clustering(
    df_original: pd.DataFrame,
    df_features: pd.DataFrame,
    k: int,
    algorithm: str = "kmeans",
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """执行聚类分析，返回打标签的 DataFrame、分群画像和质量指标。

    Args:
        df_original: pd.DataFrame，原始数据（用于追加聚类标签列）。
        df_features: pd.DataFrame，用于聚类计算的特征数据（标准化或因子得分）。
        k: int，聚类数量。
        algorithm: str，聚类算法，支持 "kmeans" / "gmm" / "agglomerative"（默认 "kmeans"）。
        random_state: int，随机种子（默认 42）。

    Returns:
        tuple[pd.DataFrame, pd.DataFrame, dict]：
          - labeled_df：原始数据加 "Cluster" 列。
          - cluster_profiles：各分群的特征均值画像。
          - metrics：含 silhouette/calinski_harabasz/davies_bouldin 的质量指标 dict。
    """
    labels = _fit_predict_by_algorithm(df_features, k, algorithm, random_state=random_state)
    
    labeled_df = df_original.copy()
    labeled_df['Cluster'] = labels
    
    # Calculate profiles based on the features used for clustering
    # We append the cluster labels to the feature dataframe to calculate means
    df_features_with_labels = df_features.copy()
    df_features_with_labels['Cluster'] = labels
    cluster_profiles = df_features_with_labels.groupby('Cluster').mean()
    unique_labels = np.unique(labels)
    if len(unique_labels) >= 2:
        sil = silhouette_score(df_features, labels)
        ch = calinski_harabasz_score(df_features, labels)
        db = davies_bouldin_score(df_features, labels)
    else:
        sil = np.nan
        ch = np.nan
        db = np.nan
    metrics = {
        "algorithm": algorithm,
        "silhouette": sil,
        "calinski_harabasz": ch,
        "davies_bouldin": db,
    }
    return labeled_df, cluster_profiles, metrics

def get_linkage_matrix(df_features: pd.DataFrame, method: str = 'ward', metric: str = 'euclidean'):
    """生成用于绘制层次聚类树状图的连接矩阵（linkage matrix）。

    数据量超过 2000 行时自动随机采样，避免树状图渲染过慢。

    Args:
        df_features: pd.DataFrame，用于聚类的特征数据。
        method: str，连接方法，如 'ward' / 'complete' / 'average'（默认 'ward'）。
        metric: str，距离度量，如 'euclidean' / 'cosine'（默认 'euclidean'）。

    Returns:
        np.ndarray，scipy linkage 格式的连接矩阵，可直接传入 dendrogram()。
    """
    # Sampling for performance if dataset is too large (>10k rows is usually the limit for dendrogram visualization)
    if len(df_features) > 2000:
        data_sample = df_features.sample(n=2000, random_state=42)
    else:
        data_sample = df_features
        
    return linkage(data_sample, method=method, metric=metric)
