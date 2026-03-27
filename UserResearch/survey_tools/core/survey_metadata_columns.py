# -*- coding: utf-8 -*-
"""
问卷导出表中的「元数据列」识别：与 Playtest Pipeline 的 _auto_classify_columns 一致，
用于自动将序号、答卷时间、所用时间等列标为「忽略」，避免误参与交叉统计。

定量工具与 scripts/run_playtest_pipeline 共用本模块，避免关键词分叉。
"""

from __future__ import annotations

# 与 run_playtest_pipeline._FORCE_IGNORE_KEYWORDS 保持同步（子串匹配，作用于归一化后列名）
METADATA_IGNORE_KEYWORDS = [
    "答卷时间",
    "ip",
    "所用时间",
    "序号",
    "总分",
    "答卷编号",
    "逻辑",
    "跳转",
]


def normalize_column_name_for_metadata(col_name: str) -> str:
    """与 Pipeline 一致：去中英文括号后再做子串匹配。"""
    s = (
        str(col_name)
        .replace("【", "")
        .replace("】", "")
        .replace("[", "")
        .replace("]", "")
        .strip()
        .lower()
    )
    return s


def is_metadata_column(col_name: str) -> bool:
    """
    列名是否应视为问卷元数据（非题目），自动识别题型时默认标为「忽略」。

    用户仍可在题型微调中改为其他题型。
    """
    col_norm = normalize_column_name_for_metadata(col_name)
    return any(k in col_norm for k in METADATA_IGNORE_KEYWORDS)


__all__ = [
    "METADATA_IGNORE_KEYWORDS",
    "normalize_column_name_for_metadata",
    "is_metadata_column",
]
