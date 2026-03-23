# -*- coding: utf-8 -*-
"""
verify_text_ingestion_io.py

自动化回归用例（Text/IO）：
- 文本工具的数据入口已统一切换到 survey_tools.utils.io.read_table_auto
- 用 test_assets/mock_survey.csv 覆盖 read_table_auto 的 CSV 读取与编码回退路径（utf-8 正常）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def main() -> int:
    from survey_tools.utils.io import read_table_auto

    sample_path = os.path.join(_PROJECT_ROOT, "test_assets", "mock_survey.csv")
    if not os.path.isfile(sample_path):
        raise AssertionError(f"缺少 test_assets 样本: {sample_path}")

    df = read_table_auto(sample_path)
    if df is None or df.empty:
        raise AssertionError("read_table_auto 读取 mock_survey.csv 结果为空")

    print("verify_text_ingestion_io: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

