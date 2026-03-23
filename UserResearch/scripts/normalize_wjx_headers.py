# -*- coding: utf-8 -*-
"""
独立预处理脚本：将问卷星原始表头规范化为「Qn. 题干: 选项」格式后写回文件。
用途：希望先得到「表头修改后」文件再在 Excel 里做其他编辑、或给他人使用时，可只跑本脚本生成新文件。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 保证从 UserResearch 根目录可导入 survey_tools
_SCRIPT_DIR = Path(__file__).resolve().parent
_USER_RESEARCH = _SCRIPT_DIR.parent
if str(_USER_RESEARCH) not in sys.path:
    sys.path.insert(0, str(_USER_RESEARCH))

import pandas as pd
from survey_tools.utils.io import read_table_auto
from survey_tools.utils.wjx_header import normalize_wjx_headers


def main() -> None:
    parser = argparse.ArgumentParser(
        description="将问卷星原始表头规范化为「Qn. 题干: 选项」格式并写回文件。"
    )
    parser.add_argument("input", type=str, help="输入文件路径（xlsx / csv）")
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="输出文件路径（可选）；不指定时默认为「输入名_表头规范.原后缀」",
    )
    parser.add_argument(
        "-s", "--sheet",
        type=str,
        default=0,
        help="Excel 工作表名或索引（默认 0）",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"错误：输入文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    name_lower = input_path.name.lower()
    if not (name_lower.endswith(".xlsx") or name_lower.endswith(".xls") or name_lower.endswith(".csv")):
        print("错误：仅支持 .xlsx / .xls / .csv 文件。", file=sys.stderr)
        sys.exit(1)

    sheet_name = args.sheet
    if isinstance(sheet_name, str) and sheet_name.isdigit():
        sheet_name = int(sheet_name)

    try:
        df = read_table_auto(str(input_path.resolve()), sheet_name=sheet_name)
    except Exception as e:
        print(f"读取文件失败: {e}", file=sys.stderr)
        sys.exit(1)

    df.columns = [str(c).strip() for c in df.columns]
    df, was_modified = normalize_wjx_headers(df)

    if not was_modified:
        print("未检测到问卷星原始表头，未做修改。")
        return

    if args.output:
        out_path = Path(args.output)
    else:
        stem = input_path.stem
        suffix = input_path.suffix.lower()
        out_path = input_path.parent / f"{stem}_表头规范{suffix}"

    try:
        if out_path.suffix.lower() == ".csv":
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
        else:
            df.to_excel(out_path, index=False, sheet_name="Sheet1")
        print(f"已规范化表头并写入: {out_path}")
    except Exception as e:
        print(f"写入文件失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
