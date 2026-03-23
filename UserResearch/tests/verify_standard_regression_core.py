# -*- coding: utf-8 -*-
"""
verify_standard_regression_core.py

自动化回归用例（Standard/core）：
- 不依赖 Streamlit 界面
- 使用内存 mock，调用 survey_tools.core.advanced_modeling.GameExperienceAnalyzer.regression_analysis
- 断言关键输出 schema（results_df 列、alpha/sample_size 等）
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def main() -> int:
    from survey_tools.core.advanced_modeling import GameExperienceAnalyzer

    rng = np.random.default_rng(42)
    n = 40
    df = pd.DataFrame(
        {
            "F1": rng.normal(loc=0, scale=1, size=n),
            "F2": rng.normal(loc=0.5, scale=1.2, size=n),
            "F3": rng.normal(loc=-0.2, scale=0.8, size=n),
        }
    )
    # 造一个线性目标（带噪声）
    df["Y"] = 3.0 + 0.6 * df["F1"] - 0.2 * df["F2"] + 0.1 * df["F3"] + rng.normal(0, 0.4, size=n)
    # 引入少量缺失，覆盖 missing_strategy 路径
    df.loc[0, "F2"] = np.nan
    df.loc[1, "F3"] = np.nan

    analyzer = GameExperienceAnalyzer(df)
    res = analyzer.regression_analysis(features=["F1", "F2", "F3"], target="Y", missing_strategy="mean")

    for key in ("results_df", "final_model", "model_raw", "alpha", "sample_size", "df_clean"):
        if key not in res:
            raise AssertionError(f"regression_analysis 返回缺少 key: {key}")

    results_df = res["results_df"]
    if not isinstance(results_df, pd.DataFrame) or results_df.empty:
        raise AssertionError("results_df 应为非空 DataFrame")

    required_cols = {"模块名称", "平均得分", "影响力(Beta系数)", "P值(显著性)", "共线性(VIF)", "改进优先级得分"}
    missing = required_cols - set(results_df.columns)
    if missing:
        raise AssertionError(f"results_df 缺少列: {sorted(missing)}; 实际列: {list(results_df.columns)}")

    if not isinstance(res["sample_size"], (int, np.integer)) or int(res["sample_size"]) < 10:
        raise AssertionError(f"sample_size 异常: {res['sample_size']}")

    print("verify_standard_regression_core: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

