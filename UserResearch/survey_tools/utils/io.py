# -*- coding: utf-8 -*-
"""
IO 工具：数据读取（含 .sav）与统一导出协议。

.sav 读取依赖 pyreadstat，需在 requirements.txt 中注明。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional, Tuple, Union

import pandas as pd

__all__ = [
    "load_sav",
    "read_table_auto",
    "read_table_auto_with_meta",
    "apply_sav_labels",
    "load_survey_data",
    "get_latest_local_data",
    "ExportBundle",
    "export_xlsx",
]


def load_sav(
    path_or_file: Union[str, BinaryIO],
) -> Tuple[pd.DataFrame, Dict[str, str], Dict[str, Dict[float, str]]]:
    """
    读取 .sav（SPSS）文件，完整提取数据、变量标签与值标签。

    Args:
        path_or_file: 文件路径或已打开的文件对象（支持 .read() 的二进制流）。

    Returns:
        (df, variable_labels, value_labels)
        - df: 数据表
        - variable_labels: 列名 -> 变量标签（中文/说明）
        - value_labels: 列名 -> { 编码值: 值标签 }，便于将数值映射回选项文字

    Raises:
        ImportError: 未安装 pyreadstat
        Exception: 文件无法读取
    """
    try:
        import pyreadstat
    except ImportError:
        raise ImportError(
            "读取 .sav 需要安装 pyreadstat，请在 requirements.txt 中注明并执行: pip install pyreadstat"
        )
    path: Optional[str] = None
    is_temp = False
    if isinstance(path_or_file, str):
        path = path_or_file
    else:
        data = path_or_file.read() if hasattr(path_or_file, "read") else path_or_file
        with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
            tmp.write(data)
            path = tmp.name
            is_temp = True
    try:
        df, meta = pyreadstat.read_sav(path)
    finally:
        if is_temp and path:
            try:
                import os
                os.unlink(path)
            except Exception:
                pass
    variable_labels = dict(meta.column_names_to_labels or {})
    # 列→取值→选项文字：用 variable_value_labels（变量名→{值→标签}）；meta.value_labels 为标签集定义，非按列映射
    value_labels = dict(getattr(meta, "variable_value_labels", None) or {})
    return df, variable_labels, value_labels


def read_table_auto(
    path_or_file: Union[str, BinaryIO],
    *,
    sheet_name: Union[int, str, List[int], List[str], None] = 0,
    encoding: Optional[str] = None,
    encoding_fallback: str = "gbk",
) -> pd.DataFrame:
    """
    根据扩展名或内容自动选择读取方式（csv / xlsx / sav）。
    若为 .sav，仅返回 DataFrame，不返回标签；需要标签时请直接调用 load_sav。
    支持 pd.ExcelFile 对象直接传入。
    """
    # H6: pd.ExcelFile 对象没有 .name，需提前处理，否则走到 raise ValueError
    if isinstance(path_or_file, pd.ExcelFile):
        return pd.read_excel(path_or_file, sheet_name=sheet_name)
    if hasattr(path_or_file, "name"):
        name = (path_or_file.name or "").lower()
    elif isinstance(path_or_file, str):
        name = path_or_file.lower()
    else:
        name = ""
    if name.endswith(".sav"):
        df, _, _ = load_sav(path_or_file)
        return df
    if name.endswith(".csv"):
        try:
            return pd.read_csv(path_or_file, encoding=encoding or "utf-8")
        except UnicodeDecodeError:
            # L7: 读取失败后需将文件指针回到起点再重试
            if hasattr(path_or_file, "seek"):
                path_or_file.seek(0)
            return pd.read_csv(path_or_file, encoding=encoding or encoding_fallback)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(path_or_file, sheet_name=sheet_name)
    raise ValueError(f"不支持的文件类型或无法推断: {name}")


def read_table_auto_with_meta(
    path_or_file: Union[str, BinaryIO],
    *,
    sheet_name: Union[int, str, List[int], List[str], None] = 0,
    encoding: Optional[str] = None,
    encoding_fallback: str = "gbk",
) -> Tuple[
    pd.DataFrame,
    Optional[Dict[str, str]],
    Optional[Dict[str, Dict[float, str]]],
]:
    """
    与 read_table_auto 相同，但对 .sav 额外返回 (variable_labels, value_labels)。
    对 CSV/Excel 返回 (df, None, None)。支持 pd.ExcelFile 对象直接传入。
    """
    # H6: pd.ExcelFile 对象支持
    if isinstance(path_or_file, pd.ExcelFile):
        return pd.read_excel(path_or_file, sheet_name=sheet_name), None, None
    if hasattr(path_or_file, "name"):
        name = (path_or_file.name or "").lower()
    elif isinstance(path_or_file, str):
        name = path_or_file.lower()
    else:
        name = ""
    if name.endswith(".sav"):
        df, variable_labels, value_labels = load_sav(path_or_file)
        return df, variable_labels, value_labels
    if name.endswith(".csv"):
        try:
            df = pd.read_csv(path_or_file, encoding=encoding or "utf-8")
        except UnicodeDecodeError:
            if hasattr(path_or_file, "seek"):
                path_or_file.seek(0)
            df = pd.read_csv(path_or_file, encoding=encoding or encoding_fallback)
        return df, None, None
    if name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(path_or_file, sheet_name=sheet_name)
        return df, None, None
    raise ValueError(f"不支持的文件类型或无法推断: {name}")


def apply_sav_labels(
    df: pd.DataFrame,
    variable_labels: Optional[Dict[str, str]] = None,
    value_labels: Optional[Dict[str, Dict[float, str]]] = None,
    *,
    apply_variable_labels: bool = True,
    apply_value_labels: bool = True,
) -> pd.DataFrame:
    """
    用 .sav 的变量标签/值标签替换列名与取值，返回新 DataFrame（不原地修改）。

    - 列名：若 variable_labels 中存在且 apply_variable_labels，则列名替换为变量标签（仅当标签非空时）；
      若替换后出现重复列名，对重复标签加后缀 _2, _3 等，保证列名唯一。
    - 取值：若 value_labels 中该列存在且 apply_value_labels，则将该列取值映射为选项文字，保留 NaN 及未在字典中的编码。
      值标签按原列名查找，因此先应用值标签再重命名列。
    """
    out = df.copy()
    if value_labels and apply_value_labels:
        for col in list(out.columns):
            if col not in value_labels:
                continue
            mapping = value_labels[col]
            if not mapping:
                continue
            out[col] = out[col].map(
                lambda x: mapping.get(x, x) if pd.notna(x) and x in mapping else x
            )
    if variable_labels and apply_variable_labels:
        rename_map: Dict[str, str] = {}
        # H5: used_names 包含所有「不会被重命名」的列名，防止新标签与未标记列名碰撞
        used_names: set = {
            str(col)
            for col in out.columns
            if col not in variable_labels or not (variable_labels[col] or "").strip()
        }
        for col in out.columns:
            if col not in variable_labels or not (variable_labels[col] or "").strip():
                continue
            base_label = (variable_labels[col] or "").strip()
            new_name = base_label
            suffix = 2
            while new_name in used_names:
                new_name = f"{base_label}_{suffix}"
                suffix += 1
            used_names.add(new_name)
            rename_map[col] = new_name
        if rename_map:
            out = out.rename(columns=rename_map)
    return out


# ---------- 统一入口：智能加载 + 自动清洗 ----------


def load_survey_data(
    source: Union[str, Path, BinaryIO],
    *,
    sheet_name: Union[int, str] = 0,
    apply_value_labels: bool = True,
    apply_variable_labels: bool = True,
    normalize_headers: bool = True,
) -> pd.DataFrame:
    """统一入口：智能识别来源，读取问卷数据并自动清洗表头。

    同时支持 CLI 路径模式（str / pathlib.Path）和 Web UploadedFile 模式。
    SAV 文件默认自动应用值标签，使输出对人类可读。
    读取完成后自动调用 normalize_wjx_headers 规范问卷星表头格式。

    Args:
        source: 文件路径（str 或 Path，CLI 模式）或 Streamlit UploadedFile 对象（Web 模式）。
        sheet_name: Excel 读取时的 Sheet 索引或名称，默认第 0 张。
        apply_value_labels: SAV 文件是否将编码值映射为选项文字，默认 True。
        apply_variable_labels: SAV 文件是否将列名替换为变量标签，默认 True。
        normalize_headers: 是否调用 normalize_wjx_headers 规范表头，默认 True。

    Returns:
        清洗后的 pd.DataFrame，列名已规范化。

    Raises:
        FileNotFoundError: 传入路径不存在时。
        ValueError: 不支持的文件格式时。
    """
    if isinstance(source, (str, Path)):
        p = Path(source)
        if not p.exists():
            raise FileNotFoundError(
                f"找不到数据文件：{p}\n"
                "请检查路径是否正确，或将数据文件放入 data/raw/ 目录后重试。"
            )
        source = str(p)

    df, variable_labels, value_labels = read_table_auto_with_meta(
        source, sheet_name=sheet_name
    )

    if variable_labels is not None or value_labels is not None:
        df = apply_sav_labels(
            df,
            variable_labels=variable_labels,
            value_labels=value_labels,
            apply_variable_labels=apply_variable_labels,
            apply_value_labels=apply_value_labels,
        )

    if normalize_headers:
        try:
            from survey_tools.utils.wjx_header import normalize_wjx_headers
            df, _ = normalize_wjx_headers(df)
        except Exception:
            pass

    df.columns = [str(c).strip() for c in df.columns]
    return df


def get_latest_local_data(
    folder_path: Union[str, Path] = "data/raw",
) -> Path:
    """扫描本地目录，返回最近修改的问卷数据文件路径。

    支持的格式：.sav / .csv / .xlsx / .xls。
    用于 CLI 自动化模式，配合 load_survey_data 使用：

        path = get_latest_local_data("data/raw")
        df = load_survey_data(path)

    Args:
        folder_path: 要扫描的目录路径，默认 "data/raw"。

    Returns:
        最新文件的 Path 对象。

    Raises:
        FileNotFoundError: 目录不存在或目录内无支持的数据文件时，抛出友好中文提示。
    """
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(
            f"数据目录不存在：{folder}\n"
            "请先创建该目录并将问卷数据文件（.sav / .csv / .xlsx）放入其中。"
        )

    candidates: List[Path] = []
    for ext in ("*.sav", "*.csv", "*.xlsx", "*.xls"):
        candidates.extend(folder.glob(ext))

    if not candidates:
        raise FileNotFoundError(
            f"在目录 {folder} 中未找到任何支持的数据文件（.sav / .csv / .xlsx / .xls）。\n"
            "请将问卷数据文件放入该目录后重试。"
        )

    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return latest


# ---------- 统一导出：单工作簿多 Sheet ----------


class ExportBundle:
    """
    统一导出包：单工作簿、多 Sheet。
    各工具将结果组装成 ExportBundle，再交给 export_xlsx 写出，以符合「单工作簿多 Sheet」约定。
    """

    __slots__ = ("workbook_name", "sheets")

    def __init__(
        self,
        workbook_name: str,
        sheets: List[Tuple[str, pd.DataFrame]],
    ):
        self.workbook_name = workbook_name
        self.sheets = list(sheets)  # [(sheet_name, df), ...]


def export_xlsx(bundle: ExportBundle, path_or_buffer: Union[str, BinaryIO]) -> None:
    """
    将 ExportBundle 写出为单工作簿多 Sheet 的 .xlsx。
    """
    with pd.ExcelWriter(path_or_buffer, engine="openpyxl") as writer:
        used_sheet_names: set = set()
        for name, df in bundle.sheets:
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df) if df is not None else pd.DataFrame()
            # L6: Sheet 名截断后可能重名，需去重
            base = name[:28] if len(name) > 28 else name
            safe_name = base
            suffix = 2
            while safe_name in used_sheet_names:
                safe_name = f"{base[:25]}_{suffix}"
                suffix += 1
            used_sheet_names.add(safe_name)
            df.to_excel(writer, sheet_name=safe_name, index=False)
