# -*- coding: utf-8 -*-
"""兼容层：保留旧导入路径，内部转发到 `survey_tools.core.quant` 单入口。

硬收口策略：
- 本模块仅用于历史兼容，禁止新增业务逻辑。
- 计划移除版本：v2026.06（若下游已完成迁移可提前移除）。
"""

from __future__ import annotations

import warnings
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

from survey_tools.core.quant import (
    QuestionSpec,
    build_question_specs,
    run_quant_cross_engine,
)


def build_v13_question_specs(
    original_df: pd.DataFrame,
    question_types: Dict[str, Sequence[int]],
) -> List[QuestionSpec]:
    warnings.warn(
        "build_v13_question_specs() 已弃用，请改用 survey_tools.core.quant.build_question_specs()。",
        DeprecationWarning,
        stacklevel=2,
    )
    return build_question_specs(original_df, question_types)


def run_v13_like_cross(
    df: pd.DataFrame,
    *,
    core_segment_col: str,
    question_specs: Sequence[QuestionSpec],
    selected_cols_set: Optional[Iterable[str]] = None,
    ignored_cols_set: Optional[Iterable[str]] = None,
    explicit_single_cols: Optional[Sequence[str]] = None,
    explicit_rating_cols: Optional[Sequence[str]] = None,
) -> List[dict]:
    warnings.warn(
        "run_v13_like_cross() 已弃用，请改用 survey_tools.core.quant.run_quant_cross_engine()。",
        DeprecationWarning,
        stacklevel=2,
    )
    return run_quant_cross_engine(
        df,
        core_segment_col=core_segment_col,
        question_specs=question_specs,
        selected_cols_set=selected_cols_set,
        ignored_cols_set=ignored_cols_set,
        explicit_single_cols=explicit_single_cols,
        explicit_rating_cols=explicit_rating_cols,
    )

