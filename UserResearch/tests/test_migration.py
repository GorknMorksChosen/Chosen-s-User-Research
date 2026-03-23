import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from survey_core_quant import run_group_difference_test as run_old
from survey_tools.core.quant import (
    build_question_specs,
    run_group_difference_test as run_new,
    run_quant_cross_engine,
)


TOL = 1e-6


def approx_equal(a, b, tol=TOL):
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return abs(a - b) <= tol


def build_test_dataframe(seed=42, n=200):
    rng = np.random.default_rng(seed)
    group = rng.choice(["A", "B", "C"], size=n, p=[0.4, 0.35, 0.25])
    single_choice = rng.choice(["X", "Y", "Z"], size=n, p=[0.5, 0.3, 0.2])
    multi_choice = rng.choice(["选1", "选2", "未选择"], size=n, p=[0.3, 0.3, 0.4])
    rating = rng.integers(1, 6, size=n).astype(float)

    nan_indices = rng.choice(n, size=int(0.1 * n), replace=False)
    group_nan = nan_indices[: int(len(nan_indices) / 2)]
    value_nan = nan_indices[int(len(nan_indices) / 2) :]

    group[group_nan] = None
    single_choice[value_nan] = None
    multi_choice[value_nan] = None
    rating[value_nan] = np.nan

    df = pd.DataFrame(
        {
            "group": group,
            "single_choice": single_choice,
            "multi_choice": multi_choice,
            "rating": rating,
        }
    )
    return df


def compare_case(df, group_col, value_col, question_type, label):
    old_res = run_old(df.copy(), group_col, value_col, question_type)
    new_res = run_new(df.copy(), group_col, value_col, question_type)

    old_overall = old_res.get("overall") or {}
    new_overall = new_res.get("overall") or {}

    old_p = old_overall.get("p_value")
    new_p = new_overall.get("p_value")
    old_es = old_overall.get("effect_size")
    new_es = new_overall.get("effect_size")

    p_diff = None
    es_diff = None
    if not (pd.isna(old_p) and pd.isna(new_p)):
        if not (pd.isna(old_p) or pd.isna(new_p)):
            p_diff = abs(old_p - new_p)
    if not (pd.isna(old_es) and pd.isna(new_es)):
        if not (pd.isna(old_es) or pd.isna(new_es)):
            es_diff = abs(old_es - new_es)

    p_ok = approx_equal(old_p, new_p)
    es_ok = approx_equal(old_es, new_es)

    if not p_ok or not es_ok:
        print(f"Difference detected in case [{label}] (question_type={question_type})")
        print(f"  old p_value={old_p}, new p_value={new_p}, abs_diff={p_diff}")
        print(f"  old effect_size={old_es}, new effect_size={new_es}, abs_diff={es_diff}")
        return False
    return True


def main():
    df = build_test_dataframe()
    all_ok = True

    all_ok &= compare_case(df, "group", "single_choice", "单选", "single_choice_with_nan")
    all_ok &= compare_case(df, "group", "multi_choice", "多选", "multi_choice_with_nan")
    all_ok &= compare_case(df, "group", "rating", "评分", "rating_with_nan")
    specs = build_question_specs(
        df,
        {
            "单选": [],
            "多选": [],
            "评分": [],
            "矩阵单选": [],
            "矩阵评分": [],
        },
    )
    cross_res = run_quant_cross_engine(
        df,
        core_segment_col="group",
        question_specs=specs,
        explicit_single_cols=["single_choice"],
        explicit_rating_cols=["rating"],
    )
    all_ok &= len(cross_res) == 2

    if all_ok:
        print(f"All compared cases matched within tolerance {TOL}.")
    else:
        print("FAIL: 部分对比用例与期望不符，请检查上方差异报告。")
        sys.exit(1)


if __name__ == "__main__":
    main()

