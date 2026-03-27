from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from survey_tools.core.quant import QuestionSpec, run_group_difference_test, run_quant_cross_engine
from survey_tools.core.survey_metadata_columns import is_metadata_column


def _build_base_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "seg": ["A"] * 12 + ["B"] * 12,
            "single_q": ["x"] * 10 + ["y"] * 2 + ["x"] * 4 + ["y"] * 8,
            "rating_q": [5, 5, 4, 5, 4, 5, 5, 4, 5, 4, 5, 4] + [1, 2, 1, 2, 2, 1, 2, 1, 2, 1, 2, 1],
            "multi_a": [1, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 0] + [0] * 12,
            "multi_b": [0.0] * 12 + [1, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0],
            "Q3.矩阵评分：子项1": [5, 4, 5, 4, 5, 4, 5, 4, 5, 4, 5, 4] + [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2],
            "Q3.矩阵评分：子项2": [4, 4, 5, 5, 4, 4, 5, 5, 4, 4, 5, 5] + [2, 2, 1, 1, 2, 2, 1, 1, 2, 2, 1, 1],
        }
    )


def test_single_choice_between_group_has_pvalue():
    df = _build_base_df()
    res = run_group_difference_test(df, "seg", "single_q", "单选", alpha=0.05)
    assert res["overall"]["test"] in ("chi-square", "fisher_exact")
    assert pd.notna(res["overall"]["p_value"])


def test_multi_choice_handles_float_zero_consistently():
    df = _build_base_df()
    res = run_group_difference_test(df, "seg", ["multi_a", "multi_b"], "多选", alpha=0.05)
    assert res["overall"]["test"] == "multi-option"
    assert "details" in res and len(res["details"]) > 0
    # 确认 0.0 不会被误判为提及导致全显著噪声
    assert any(d["option"] == "multi_b" for d in res["details"])


def test_rating_small_sample_prefers_nonparametric_when_needed():
    df = pd.DataFrame(
        {
            "seg": ["A", "A", "A", "B", "B", "B", "C", "C", "C"],
            "rating_q": [1, 5, 1, 5, 1, 5, 2, 2, 2],
        }
    )
    res = run_group_difference_test(df, "seg", "rating_q", "评分", min_group_size=3, alpha=0.05)
    assert "assumption_checks" in res
    assert res["assumption_checks"]["decision"] in ("ANOVA", "Kruskal-Wallis")


def test_nps_spec_outputs_nps_type_and_uses_rating_test():
    df = pd.DataFrame(
        {
            "seg": ["A"] * 6 + ["B"] * 6,
            "Q3.您有多大的意愿推荐": [9, 10, 8, 7, 6, 5] + [5, 4, 3, 2, 1, 0],
        }
    )
    specs = [QuestionSpec(q_type="NPS", q_num=3, option_order=None)]
    out = run_quant_cross_engine(
        df,
        core_segment_col="seg",
        question_specs=specs,
        selected_cols_set=set(df.columns),
        ignored_cols_set=set(),
        alpha=0.05,
        min_group_size=3,
    )
    assert len(out) == 1
    assert out[0]["题型"] == "NPS"
    assert out[0]["stats"] is not None
    assert out[0]["stats"]["overall"]["test"] in ("welch_t", "ANOVA", "Kruskal-Wallis")


def test_matrix_rating_routes_to_rating_stats_in_cross_engine():
    df = _build_base_df()
    specs = [QuestionSpec(q_type="矩阵评分", q_num=3, option_order=None)]
    out = run_quant_cross_engine(
        df,
        core_segment_col="seg",
        question_specs=specs,
        selected_cols_set=set(df.columns),
        ignored_cols_set=set(),
        alpha=0.05,
        min_group_size=3,
    )
    assert len(out) >= 2
    for row in out:
        assert row["题型"] == "矩阵评分"
        assert row["stats"] is not None
        assert row["stats"]["overall"]["test"] in ("welch_t", "ANOVA", "Kruskal-Wallis")


def test_metadata_column_keywords_align_with_pipeline():
    assert is_metadata_column("序号")
    assert is_metadata_column("【序号】")
    assert is_metadata_column("提交答卷时间")
    assert is_metadata_column("所用时间（秒）")
    assert not is_metadata_column("Q1.满意度")
