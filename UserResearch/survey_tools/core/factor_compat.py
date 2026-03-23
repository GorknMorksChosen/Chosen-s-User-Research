from contextlib import contextmanager

import sklearn
from sklearn.utils import validation


@contextmanager
def factor_analyzer_compat():
    """临时 Monkey-patch 兼容层：解决 factor_analyzer 与高版本 scikit-learn 的 check_array 参数冲突。

    在 with 块内将 `force_all_finite` 参数自动转换为 `ensure_all_finite`，
    退出 with 块后恢复原始函数，不影响其他代码。

    Yields:
        None，供 with 语句使用。
    """
    original_validation_check_array = validation.check_array
    original_sklearn_check_array = getattr(sklearn.utils, "check_array", None)
    fa_module = None
    original_fa_check_array = None
    try:
        import factor_analyzer.factor_analyzer as fa_module
        original_fa_check_array = getattr(fa_module, "check_array", None)
    except Exception:
        fa_module = None

    def patched_check_array(*args, **kwargs):
        if "force_all_finite" in kwargs and "ensure_all_finite" not in kwargs:
            kwargs["ensure_all_finite"] = kwargs.pop("force_all_finite")
        return original_validation_check_array(*args, **kwargs)

    validation.check_array = patched_check_array
    if original_sklearn_check_array is not None:
        sklearn.utils.check_array = patched_check_array
    if fa_module is not None and original_fa_check_array is not None:
        fa_module.check_array = patched_check_array
    try:
        yield
    finally:
        validation.check_array = original_validation_check_array
        if original_sklearn_check_array is not None:
            sklearn.utils.check_array = original_sklearn_check_array
        if fa_module is not None and original_fa_check_array is not None:
            fa_module.check_array = original_fa_check_array


def is_factor_compat_error(exc: Exception) -> bool:
    """判断异常是否由 factor_analyzer 与 scikit-learn 版本不兼容引起。

    Args:
        exc: Exception，捕获到的异常对象。

    Returns:
        bool，True 表示是已知兼容性错误，可给出特定修复提示。
    """
    msg = str(exc)
    patterns = [
        "force_all_finite",
        "ensure_all_finite",
        "unexpected keyword argument",
        "check_array",
    ]
    return any(p in msg for p in patterns)


def build_factor_compat_message() -> str:
    """生成 factor_analyzer 兼容性错误的用户友好提示文本。

    Returns:
        str，包含错误原因和两种修复建议的说明字符串。
    """
    return (
        "因子分析环境兼容性错误：检测到 factor_analyzer 与当前 scikit-learn 版本不兼容。\n"
        "建议修复：\n"
        "1. 尝试降低 scikit-learn 版本：pip install scikit-learn==1.2.2\n"
        "2. 或更新 factor_analyzer 库。"
    )
