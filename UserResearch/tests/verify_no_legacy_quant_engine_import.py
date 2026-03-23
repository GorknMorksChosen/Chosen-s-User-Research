# -*- coding: utf-8 -*-
"""
verify_no_legacy_quant_engine_import.py

硬收口检查：
- 禁止业务代码新增对 survey_tools.core.quant_v13_engine 的直接依赖。
- 禁止业务代码新增旧函数名调用痕迹：run_v13_like_cross / build_v13_question_specs。
- docs/ 与 archive/ 不在检查范围内（允许历史记录保留旧名称）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


PATTERNS = [
    re.compile(r"from\s+survey_tools\.core\.quant_v13_engine\s+import"),
    re.compile(r"import\s+survey_tools\.core\.quant_v13_engine"),
    re.compile(r"\brun_v13_like_cross\s*\("),
    re.compile(r"\bbuild_v13_question_specs\s*\("),
]


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    violations: list[str] = []

    for py in root.rglob("*.py"):
        rel = py.relative_to(root).as_posix()
        if rel.startswith("docs/") or rel.startswith("archive/"):
            continue
        # 兼容层自身允许存在
        if rel == "survey_tools/core/quant_v13_engine.py":
            continue
        # 本检查脚本自身允许存在关键词
        if rel == "tests/verify_no_legacy_quant_engine_import.py":
            continue

        text = py.read_text(encoding="utf-8", errors="ignore")
        if any(p.search(text) for p in PATTERNS):
            violations.append(rel)

    if violations:
        print("发现不允许的旧引擎依赖/调用痕迹：")
        for v in sorted(violations):
            print(f"- {v}")
        return 1

    print("verify_no_legacy_quant_engine_import: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
