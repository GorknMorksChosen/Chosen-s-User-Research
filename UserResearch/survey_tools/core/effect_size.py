EFFECT_SIZE_THRESHOLDS = {
    "Cramer's V": {"small": 0.10, "medium": 0.30, "large": 0.50},
    "Eta-squared": {"small": 0.01, "medium": 0.06, "large": 0.14},
    "Cohen's d": {"small": 0.20, "medium": 0.50, "large": 0.80},
    "Rank-biserial correlation": {"small": 0.10, "medium": 0.30, "large": 0.50},
    "Relative Difference in Proportions": {
        "small": 0.10,
        "medium": 0.30,
        "large": 0.50,
    },
    "Cohen's g": {"small": 0.10, "medium": 0.30, "large": 0.50},
}


def interpret_effect_size(metric_name: str, value):
    """将数值效应量转换为可读的文字等级描述（接近于0/小效应/中等效应/大效应）。

    Args:
        metric_name: str，效应量指标名称，如 "Cohen's d"、"Cramer's V" 等；
            须在 EFFECT_SIZE_THRESHOLDS 中有对应阈值，否则返回空字符串。
        value: float or None，效应量数值；为 None 或 NaN 时返回空字符串。

    Returns:
        str，格式如 "中等效应 (|0.52|)"；无法解析或无对应阈值时返回 ""。
    """
    if value is None:
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    if v != v:
        return ""
    thresholds = EFFECT_SIZE_THRESHOLDS.get(metric_name)
    if not thresholds:
        return ""
    small = thresholds["small"]
    medium = thresholds["medium"]
    large = thresholds["large"]
    av = abs(v)
    if av < small:
        level = "接近于0"
    elif av < medium:
        level = "小效应"
    elif av < large:
        level = "中等效应"
    else:
        level = "大效应"
    return f"{level} (|{v:.2f}|)"

