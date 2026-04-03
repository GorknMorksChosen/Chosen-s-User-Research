# -*- coding: utf-8 -*-
"""
Playtest 自动化分析流水线 — CLI 入口。

核心实现与维护约定见 ``survey_tools.core.playtest_pipeline`` 模块 docstring
及 ``docs/PLAYTEST_PIPELINE.md``。本文件仅负责：

- 将 UserResearch 根目录加入 ``sys.path``（便于 ``python scripts/run_playtest_pipeline.py``）
- Windows 下将 stdout/stderr 设为 UTF-8，避免控制台乱码
- 调用 Click 主函数 ``main``
"""
from __future__ import annotations

import io as _io
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from survey_tools.core.playtest_pipeline import main

if __name__ == "__main__":
    main()
