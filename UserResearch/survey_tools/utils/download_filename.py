# -*- coding: utf-8 -*-
"""浏览器下载用文件名：将用户输入清理为安全的 Content-Disposition 文件名。"""

from __future__ import annotations

import os
import re

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_LEN = 180


def safe_download_filename(user_input: str, *, fallback: str) -> str:
    """
    将用户在界面填写的文件名转为可安全用于 st.download_button 的 file_name。

    - 去掉路径（只保留最后一段）
    - 替换 Windows / 浏览器不友好的字符
    - 若用户未写扩展名，则沿用 fallback 的扩展名
    """
    fb = (fallback or "export.xlsx").strip() or "export.xlsx"
    _, fb_ext = os.path.splitext(fb)

    raw = (user_input or "").strip()
    raw = raw.replace("\\", "/").split("/")[-1]
    raw = _INVALID_FILENAME_CHARS.sub("_", raw)
    raw = raw.strip(" .")
    if not raw:
        return fb

    _root, user_ext = os.path.splitext(raw)
    if not user_ext and fb_ext:
        raw = raw + fb_ext
    if len(raw) > _MAX_LEN:
        root, ext = os.path.splitext(raw)
        raw = root[: _MAX_LEN - len(ext)] + ext
    return raw or fb
