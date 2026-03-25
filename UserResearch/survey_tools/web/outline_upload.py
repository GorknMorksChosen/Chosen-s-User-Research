# -*- coding: utf-8 -*-
"""问卷大纲上传与解析（Streamlit 与各工具共享）。

仅覆盖「需要题型/选项对齐」的入口（如 Quant、Playtest Pipeline），避免在全站重复实现
`parse_outline_for_platform` 与 UploadedFile 读写约定。
"""

from __future__ import annotations

from typing import Dict

from survey_tools.utils.outline_parser import outline_to_q_num_type, parse_outline_for_platform

OUTLINE_CAPTION = (
    "解析方式由「大纲来源」决定，与扩展名无关；"
    "问卷星大纲请选「问卷星」并上传 .docx；"
    "腾讯大纲可选 .txt 或 .docx，并选「腾讯问卷」。"
)

OUTLINE_PLATFORM_OPTIONS = ["问卷星", "腾讯问卷"]


def platform_label_to_code(label: str) -> str:
    """问卷星 / 腾讯问卷 → outline_parser 使用的 platform 代码。"""
    return "wjx" if label == "问卷星" else "tencent"


def parse_uploaded_outline_file(uploaded_file, platform_label: str) -> Dict[int, dict]:
    """从 Streamlit UploadedFile 解析大纲，返回题号 → 题目信息 dict。

    使用 ``getvalue()`` 读取，并在读前 ``seek(0)``，避免 rerun 时流指针为空。
    """
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    raw = uploaded_file.getvalue()
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    code = platform_label_to_code(platform_label)
    return parse_outline_for_platform(
        data=raw,
        filename=str(uploaded_file.name),
        platform=code,
    )


def outline_raw_to_quant_type_map(outline: Dict[int, dict]) -> Dict[int, str]:
    """大纲解析结果 → Quant 题型表使用的题号→短题型映射（与 Pipeline 覆盖口径一致）。"""
    return outline_to_q_num_type(outline)
