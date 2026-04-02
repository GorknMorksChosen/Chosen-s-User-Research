# -*- coding: utf-8 -*-
"""
问卷大纲解析：问卷星 / 腾讯问卷导出的大纲（.docx 或 .txt）提取题号、题型、选项、子题目。

供 Pipeline CLI 与 quant_app Web 共享；Web 端通过 ``parse_outline_for_platform``
按用户选择的平台选择解析管线。
"""
from __future__ import annotations

import html
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import zipfile


def docx_bytes_to_plain_text(data: bytes) -> str:
    """从 .docx 二进制内容抽取纯文本（去 XML 标签，保留换行）。

    与问卷星大纲解析使用相同的 document.xml 读取与清洗规则；
    腾讯大纲若以 Word 保存，可先经此函数再交给 ``parse_outline_txt``。
    """
    z = zipfile.ZipFile(io.BytesIO(data))
    xml_bytes = z.read("word/document.xml").decode("utf-8")
    xml_text = re.sub(r"<w:br[^/]*/?>", "\n", xml_bytes)
    xml_text = re.sub(r"</w:p>", "\n", xml_text)
    xml_text = re.sub(r"<[^>]+>", "", xml_text)
    return xml_text


def parse_outline_docx(source: Union[str, Path, bytes]) -> Dict[int, dict]:
    """解析问卷星导出的大纲 .docx，提取每题的结构信息。

    支持题型：单选题、多选题、评分题、填空题、矩阵单选题、矩阵文本题。

    Args:
        source: .docx 文件路径或文件内容（bytes）。

    Returns:
        dict 以题号（int）为键，每题信息包含：
          - type (str): 题型，如 "单选题"、"矩阵单选题"
          - title (str): 题目文本
          - options (list[str]): 量表选项标签（矩阵题为列头），单选题为选项列表
          - sub_items (list[str]): 矩阵题子题目列表（单选题为空）
          - branching (str | None): 跳题逻辑描述
    """
    if isinstance(source, bytes):
        xml_text = docx_bytes_to_plain_text(source)
    else:
        with open(Path(source), "rb") as f:
            xml_text = docx_bytes_to_plain_text(f.read())

    lines = [ln.strip() for ln in xml_text.splitlines() if ln.strip()]

    # 处理题目标题与题型标签分行的情况（Word 手动换行导致）
    TYPE_TAG_RE = re.compile(r"^\[.+?\]\s*\*?\s*$")
    merged: List[str] = []
    i = 0
    while i < len(lines):
        curr = lines[i]
        if (
            i + 1 < len(lines)
            and TYPE_TAG_RE.match(lines[i + 1])
            and re.match(r"^\d+\.", curr)
        ):
            merged.append(curr.rstrip() + " " + lines[i + 1])
            i += 2
        else:
            merged.append(curr)
            i += 1
    lines = merged

    Q_HEADER = re.compile(r"^(\d+)\.\s*(.+?)\s*\[([^\]]+)\]\s*\*?\s*$")

    questions: Dict[int, dict] = {}
    current_q: Optional[int] = None
    current_type: str = ""
    pre_o_lines: List[str] = []
    o_buffer: int = 0
    seen_first_o_block: bool = False

    def _flush_o_block() -> None:
        nonlocal seen_first_o_block, o_buffer
        if not seen_first_o_block and o_buffer > 0 and current_q is not None:
            seen_first_o_block = True
            q = questions[current_q]
            if len(pre_o_lines) >= 1:
                q["options"] = pre_o_lines[:-1]
                if pre_o_lines[-1]:
                    q["sub_items"].append(pre_o_lines[-1])
            o_buffer = 0

    for line in lines:
        m = Q_HEADER.match(line)
        if m:
            if current_q is not None and "矩阵" in current_type:
                _flush_o_block()

            current_q = int(m.group(1))
            current_type = m.group(3).strip()
            pre_o_lines = []
            o_buffer = 0
            seen_first_o_block = False
            questions[current_q] = {
                "type": current_type,
                "title": m.group(2).strip(),
                "options": [],
                "sub_items": [],
                "branching": None,
            }
            continue

        if current_q is None:
            continue
        q = questions[current_q]

        if line.startswith("依赖于"):
            q["branching"] = line
            continue

        # 跳过“____”或“____)”这类换行残片，避免被当成独立选项
        if re.fullmatch(r"[\s_＿()（）]+", line):
            continue

        if "矩阵" in current_type:
            if line == "○":
                o_buffer += 1
            else:
                if o_buffer > 0:
                    _flush_o_block()
                    o_buffer = 0

                if not seen_first_o_block:
                    pre_o_lines.append(line)
                else:
                    clean = re.sub(r"[\(（]请跳至.+?[\)）]", "", line).strip()
                    if clean:
                        q["sub_items"].append(clean)
            continue

        if line.startswith("○"):
            option = line[1:].strip()
            option = re.sub(r"[\(（]请跳至.+?[\)）]", "", option).strip()
            if option:
                q["options"].append(option)

    if current_q is not None and "矩阵" in current_type:
        _flush_o_block()

    return questions


def parse_outline_txt(source: Union[str, Path, bytes]) -> Dict[int, dict]:
    """解析腾讯问卷导出的大纲 .txt，提取每题的结构信息。

    腾讯问卷 .txt 格式特征：
      - 题目行格式：``题目文本[题型][必答/选答]``
      - 矩阵题：首条内容行为量表描述，后续行为子题目
      - ``===分页===`` 为分页符

    Args:
        source: .txt 文件路径、文件内容（bytes），或已从 docx 抽取的纯文本（str）。

    Returns:
        dict 以题号（int）为键，每题信息包含 type, title, options, sub_items, branching。
    """
    if isinstance(source, str):
        raw = html.unescape(source)
    elif isinstance(source, bytes):
        try:
            raw = source.decode("utf-8")
        except UnicodeDecodeError:
            raw = source.decode("gbk")
        raw = html.unescape(raw)
    else:
        path = Path(source)
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = path.read_text(encoding="gbk")
        raw = html.unescape(raw)
    lines = [ln.strip() for ln in raw.splitlines()]

    Q_HEADER = re.compile(
        r"^(.+?)\["
        r"(单选题|多选题|矩阵量表题|矩阵单选题|量表题|NPS题"
        r"|多行文本题|单行文本题|段落说明)"
        r"\]\[(?:必答|选答)\]"
    )

    MATRIX_TYPES = {"矩阵量表题", "矩阵单选题"}
    IGNORE_TYPES = {"多行文本题", "单行文本题", "段落说明"}

    questions: Dict[int, dict] = {}
    current_q: int = 0
    current_type: str = ""

    for line in lines:
        if not line or line.startswith("==="):
            continue

        m = Q_HEADER.match(line)
        if m:
            current_q += 1
            title = m.group(1).strip()
            title = re.sub(r"\s*[\(（]第\d+题.+$", "", title).strip()
            current_type = m.group(2).strip()
            questions[current_q] = {
                "type": current_type,
                "title": title,
                "options": [],
                "sub_items": [],
                "branching": None,
            }
            continue

        if current_q == 0:
            continue

        if current_type in IGNORE_TYPES:
            continue

        if re.fullmatch(r"[\s_＿()（）]+", line):
            continue

        q = questions[current_q]

        if current_type in MATRIX_TYPES:
            if not q["options"]:
                q["options"].append(line)
            else:
                q["sub_items"].append(line)
        else:
            q["options"].append(line)

    return questions


def parse_outline(source: Union[str, Path, bytes], fmt: str = "auto") -> Dict[int, dict]:
    """根据格式解析大纲，返回题号→题型信息的映射。

    Args:
        source: 文件路径或文件内容（bytes）。Streamlit 上传时传 file.read()。
        fmt: "docx" | "txt" | "auto"。auto 时根据 source 类型或扩展名推断。

    Returns:
        dict 以题号（int）为键的题型信息。
    """
    if fmt == "auto":
        if isinstance(source, bytes):
            fmt = "docx"  # 无法从 bytes 推断，默认 docx
        elif isinstance(source, (str, Path)):
            p = Path(source)
            ext = p.suffix.lower() if p.suffix else ""
            if ext == ".txt":
                fmt = "txt"
            else:
                fmt = "docx"

    if fmt == "txt":
        return parse_outline_txt(source)
    return parse_outline_docx(source)


def parse_outline_for_platform(
    data: bytes,
    filename: str,
    platform: Literal["wjx", "tencent"],
) -> Dict[int, dict]:
    """按平台选择解析器（与文件扩展名解耦，由调用方显式指定来源）。

    Args:
        data: 上传或读取的文件二进制内容。
        filename: 原始文件名（用于判断 .docx / .txt）。
        platform: ``wjx`` 问卷星大纲语法；``tencent`` 腾讯问卷大纲语法。

    Returns:
        题号 → 题目信息 dict，与 ``parse_outline_docx`` / ``parse_outline_txt`` 一致。

    Raises:
        ValueError: 平台与后缀组合不支持时（含说明文案）。
    """
    name = (filename or "").lower()
    is_txt = name.endswith(".txt")
    is_docx = name.endswith(".docx")

    if not (is_txt or is_docx):
        raise ValueError("大纲文件后缀须为 .docx 或 .txt")

    if platform == "wjx":
        if not is_docx:
            raise ValueError(
                "问卷星大纲解析仅支持导出的大纲 .docx；当前为 .txt。"
                "若内容实为腾讯格式，请在「大纲来源」中选择「腾讯问卷」。"
            )
        return parse_outline_docx(data)

    # tencent
    if is_txt:
        return parse_outline_txt(data)
    plain = docx_bytes_to_plain_text(data)
    return parse_outline_txt(plain)


def outline_to_q_num_type(outline: Dict[int, dict]) -> Dict[int, str]:
    """将大纲解析结果转换为题号→v13 题型的映射，供题型识别使用。

    与 Pipeline _auto_classify_columns 中的大纲覆盖逻辑一致。
    """
    q_num_to_type: Dict[int, str] = {}
    for q_num, info in outline.items():
        otype = info.get("type", "")
        if "矩阵评分" in otype:
            q_num_to_type[q_num] = "矩阵评分"
        elif "矩阵" in otype:
            if "文本" in otype or "填空" in otype:
                q_num_to_type[q_num] = "忽略"
            else:
                q_num_to_type[q_num] = "矩阵单选"
        elif "多选" in otype:
            q_num_to_type[q_num] = "多选"
        elif "填空" in otype or "文本" in otype:
            q_num_to_type[q_num] = "忽略"
        elif "NPS" in str(otype).upper() or "nps" in str(otype).lower():
            q_num_to_type[q_num] = "NPS"
        elif "量表" in otype:
            q_num_to_type[q_num] = "评分"
        elif "单选" in otype:
            q_num_to_type[q_num] = "单选"
    return q_num_to_type
