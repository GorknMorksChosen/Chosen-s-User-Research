# -*- coding: utf-8 -*-
"""
verify_clustering_recommendation_core.py

自动化回归用例（聚类/core）：
- 不依赖 Streamlit 界面
- 使用内存 mock 特征
- 覆盖 evaluate_clustering_algorithms / recommend_clustering_algorithm / recommend_k_algorithm_combo
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
    from survey_tools.core.clustering import (
        evaluate_clustering_algorithms,
        recommend_clustering_algorithm,
        recommend_k_algorithm_combo,
    )

    rng = np.random.default_rng(7)
    n = 60
    df_features = pd.DataFrame(
        {
            "A": rng.normal(0, 1, size=n),
            "B": rng.normal(1, 0.8, size=n),
            "C": rng.normal(-0.5, 1.1, size=n),
        }
    )

    eval_df = evaluate_clustering_algorithms(df_features, k=3, algorithms=["kmeans", "gmm", "agglomerative"])
    if eval_df.empty or "status" not in eval_df.columns:
        raise AssertionError("evaluate_clustering_algorithms 返回异常（空或缺列）")

    rec_algo = recommend_clustering_algorithm(eval_df, fallback="kmeans", profile="balanced")
    for key in ("recommended_algorithm", "reason", "scored_df", "profile"):
        if key not in rec_algo:
            raise AssertionError(f"recommend_clustering_algorithm 缺少 key: {key}")
    if rec_algo["recommended_algorithm"] not in ("kmeans", "gmm", "agglomerative"):
        raise AssertionError(f"recommended_algorithm 异常: {rec_algo['recommended_algorithm']}")

    rec_combo = recommend_k_algorithm_combo(
        df_features,
        k_values=range(2, 6),
        algorithms=["kmeans", "gmm", "agglomerative"],
        fallback_k=3,
        fallback_algorithm="kmeans",
        profile="balanced",
    )
    for key in ("recommended_k", "recommended_algorithm", "reason", "grid_df", "scored_df", "profile"):
        if key not in rec_combo:
            raise AssertionError(f"recommend_k_algorithm_combo 缺少 key: {key}")
    if not isinstance(rec_combo["recommended_k"], int) or rec_combo["recommended_k"] < 2:
        raise AssertionError(f"recommended_k 异常: {rec_combo['recommended_k']}")

    print("verify_clustering_recommendation_core: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

