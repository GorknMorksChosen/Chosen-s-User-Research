# -*- coding: utf-8 -*-
"""
问卷星表头规范化：将「题干+首选项」与「纯选项」列名统一为「Qn. 题干: 选项」，
便于 parse_columns_for_questions 正确分组多选/矩阵题。
"""

from __future__ import annotations

import re
from typing import Tuple

import pandas as pd

from survey_tools.core.quant import advanced_split, extract_qnum


# 不参与分组的列名（如序号列）
_SKIP_PREFIXES = ("Q序号", "序号", "序号.")


def _skip_column(col_name: str) -> bool:
    s = str(col_name).strip()
    for prefix in _SKIP_PREFIXES:
        if s == prefix or s.startswith(prefix + " ") or s.startswith(prefix + "."):
            return True
    return False


def _is_user_tag_column(col_name: str) -> bool:
    """列名是否为用户标签（如 type.玩家分类 A1），不归入前一题的选项。"""
    s = str(col_name).strip()
    return s.lower().startswith("type.")


def _is_leader_column(col_name: str) -> bool:
    """列名是否以 Q数字 开头（题干+首选项列）。"""
    s = str(col_name).strip()
    if _skip_column(s):
        return False
    return bool(re.match(r"^\s*Q\d+[.\s_\-]", s)) and extract_qnum(s) is not None


def _already_normalized(col_name: str) -> bool:
    """是否已是「Qn. 题干: 选项」格式（含冒号）。"""
    s = str(col_name).strip()
    if ":" in s or "：" in s:
        q = extract_qnum(s)
        if q:
            return True
    return False


def _split_stem_first_option(col_str: str, q_num: str) -> Tuple[str, str]:
    """
    从「题干+首选项」列名拆出 stem（Qn. 题干）与首选项。
    优先按 ] 分割，使题干含 [多选…] 等，首选项为 ] 后内容；否则按 ？、? 分割。
    """
    col_str = str(col_str).strip()
    rest = re.sub(r"^\s*Q\d+[.\s_\-]+", "", col_str, count=1).strip()
    if not rest:
        return ("Q" + q_num + ".", "")
    prefix = "Q" + q_num + ". "
    if "]" in rest:
        idx = rest.rindex("]")
        stem = prefix + rest[: idx + 1].strip()
        option1 = rest[idx + 1 :].strip()
        if option1:
            return (stem, option1)
    for sep in ("？", "?"):
        if sep in rest:
            idx = rest.index(sep)
            stem = prefix + rest[: idx + 1].strip()
            option1 = rest[idx + 1 :].strip()
            return (stem, option1)
    return (prefix + rest, "")


def normalize_wjx_headers(df: pd.DataFrame) -> Tuple[pd.DataFrame, bool]:
    """
    检测问卷星原始表头（一题一列「Qn. 题干+首选项」后跟若干「纯选项」列），
    并重写为「Qn. 题干: 选项」格式，便于下游按题分组。

    Returns:
        (df_renamed, was_modified): 若发生重写则 was_modified 为 True。
    """
    if df is None or df.empty:
        return (df, False)
    columns = list(df.columns)
    rename_map = {}
    current_stem = None
    current_q_num = None

    for i, col in enumerate(columns):
        col_str = str(col).strip()
        if _skip_column(col_str) or _is_user_tag_column(col_str):
            continue
        q_num = extract_qnum(col_str)
        is_leader = bool(q_num and re.match(r"^\s*Q\d+[.\s_\-]", col_str))

        if is_leader:
            if _already_normalized(col_str):
                stem_part, _ = advanced_split(col_str)
                current_stem = stem_part.strip()
                current_q_num = q_num
                continue
            stem, opt1 = _split_stem_first_option(col_str, q_num)
            current_stem = stem
            current_q_num = q_num
            if opt1:
                rename_map[col] = stem + ": " + opt1
            else:
                rename_map[col] = stem
        else:
            if current_stem is not None and current_q_num is not None:
                rename_map[col] = current_stem + ": " + col_str

    if not rename_map:
        return (df, False)
    out = df.rename(columns=rename_map)
    return (out, True)


__all__ = ["normalize_wjx_headers"]
