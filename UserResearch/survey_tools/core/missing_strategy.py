import pandas as pd


SUPPORTED_MISSING_STRATEGIES = {
    "drop",
    "mean",
    "median",
    "group_mean",
    "group_median",
}


def apply_missing_strategy(
    df: pd.DataFrame,
    strategy: str = "mean",
    group_values: pd.Series = None,
    group_col_name: str = None,
) -> pd.DataFrame:
    """对 DataFrame 执行指定的缺失值处理策略，用于回归/建模前的数据准备。

    Args:
        df: pd.DataFrame，待处理的特征数据（列均应为数值型）。
        strategy: str，缺失值策略，支持：
            "drop"（删行）/ "mean"（全局均值填补）/ "median"（全局中位数填补）/
            "group_mean"（按分组均值填补）/ "group_median"（按分组中位数填补）。
        group_values: pd.Series or None，分组标签序列（"group_mean"/"group_median" 策略必填）。
        group_col_name: str or None，分组列名（用于冲突检测，分组列不应与特征列重名）。

    Returns:
        pd.DataFrame，处理后的数值型 DataFrame，不含 NaN 行。

    Raises:
        ValueError: 策略为 group_mean/group_median 时 group_values 为 None，
            或 group_col_name 与特征列重名，或不支持的 strategy 值。
    """
    numeric_df = df.apply(pd.to_numeric, errors="coerce")
    if strategy == "drop":
        return numeric_df.dropna()
    if strategy == "mean":
        return numeric_df.fillna(numeric_df.mean()).dropna()
    if strategy == "median":
        return numeric_df.fillna(numeric_df.median()).dropna()
    if strategy in ("group_mean", "group_median"):
        if group_values is None:
            raise ValueError("分组填补策略需要有效的分组数据。")
        if group_col_name and group_col_name in numeric_df.columns:
            raise ValueError("分组列不能与回归特征或目标变量重名。")
        groups = group_values.reindex(numeric_df.index)
        if groups.isna().all():
            raise ValueError("分组数据全部为空，无法执行分组填补。")
        base = numeric_df.copy()
        agg_fn = "mean" if strategy == "group_mean" else "median"
        grouped_values = base.groupby(groups).transform(agg_fn)
        base = base.fillna(grouped_values)
        base = base.fillna(base.mean())
        return base.dropna()
    raise ValueError(f"不支持的缺失值处理策略: {strategy}")
