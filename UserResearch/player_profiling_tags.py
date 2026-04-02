#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
玩家画像多维打标签工具（Streamlit 单文件版）

核心能力：
1) 上传问卷 CSV/XLSX；
2) 选择多个要用于画像的列；
3) 输入预设标签库（逗号分隔）；
4) 并发调用 LLM 生成 1-3 个标签；
5) 将结果回填到原表并导出 Excel。

说明：
- 本文件尽量保持“教学级可读性”，包含大量中文注释与容错逻辑；
- 兼容 OpenAI 风格接口（/chat/completions），可接 Gemini/DeepSeek/Claude/OpenAI 兼容网关；
- 与项目问卷解析口径对齐：优先做问卷星表头规范化，并复用题号分组工具。
"""

from __future__ import annotations

# ---------------------------------------------------------------------
# 0) Windows 事件循环策略修复（必须放在前面，避免 Event loop is closed）
# ---------------------------------------------------------------------
import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import io
import json
import math
import random
import re
from collections import Counter
from typing import Any

import aiohttp
import pandas as pd
import streamlit as st

from survey_tools.config import OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL
from survey_tools.core.question_type import parse_columns_for_questions
from survey_tools.utils.wjx_header import normalize_wjx_headers
from survey_tools.utils.download_filename import safe_download_filename


# ---------------------------------------------------------------------
# 1) 常量区：统一管理可调整参数，便于后续维护
# ---------------------------------------------------------------------
APP_TITLE = "玩家画像多维打标签工具"
DEFAULT_MODEL = OPENAI_MODEL or "gpt-4o-mini"
DEFAULT_BASE_URL = OPENAI_BASE_URL or "https://api.openai.com/v1"
DEFAULT_API_KEY = OPENAI_API_KEY or ""
MAX_CONCURRENCY_MIN = 1
MAX_CONCURRENCY_MAX = 10
DEFAULT_MAX_CONCURRENCY = 5
REQUEST_TIMEOUT_SECONDS = 60
MAX_RETRY_TIMES = 4

# 这些值会被当作“无效回答”过滤掉，避免脏数据污染 LLM 输入
INVALID_CELL_TEXTS = {
    "",
    "-",
    "--",
    "nan",
    "none",
    "null",
    "n/a",
    "na",
    "(空)",
    "（空）",
    "(跳过)",
    "（跳过）",
    "跳过",
}


def normalize_base_url(base_url: str) -> str:
    """将用户输入的 Base URL 规范化为最终请求地址。

    Args:
        base_url: 用户在 UI 中输入的 API Base URL。

    Returns:
        标准化后的完整 chat/completions URL。
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return "https://api.openai.com/v1/chat/completions"
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/chat/completions"


def read_uploaded_table(uploaded_file: Any) -> pd.DataFrame:
    """读取上传文件并返回 DataFrame，支持 CSV/XLSX，多重容错编码。

    Args:
        uploaded_file: Streamlit 上传对象（UploadedFile）。

    Returns:
        读取成功的 DataFrame。

    Raises:
        ValueError: 文件格式不支持或读取失败时抛出。
    """
    if uploaded_file is None:
        raise ValueError("未检测到上传文件。")

    name = (uploaded_file.name or "").lower()
    raw = uploaded_file.getvalue()
    if not raw:
        raise ValueError("上传文件为空，请重新上传。")

    if name.endswith(".xlsx"):
        try:
            return pd.read_excel(io.BytesIO(raw))
        except Exception as exc:
            raise ValueError(f"Excel 读取失败：{exc}") from exc

    if name.endswith(".csv"):
        # 常见编码回退：utf-8-sig -> utf-8 -> gbk -> gb18030
        last_error = None
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
            try:
                return pd.read_csv(io.BytesIO(raw), encoding=enc)
            except Exception as exc:  # noqa: PERF203 - 这里需要保留上下文
                last_error = exc
        raise ValueError(f"CSV 读取失败（已尝试常见编码）：{last_error}")

    raise ValueError("仅支持 .xlsx 或 .csv 文件。")


def parse_preset_tags(raw_text: str) -> list[str]:
    """解析并清洗用户输入的预设标签库（逗号分隔）。

    Args:
        raw_text: 文本框输入字符串。

    Returns:
        去重、去空后的标签列表（保持输入顺序）。
    """
    # 同时兼容中文逗号、英文逗号、顿号、分号与换行
    chunks = re.split(r"[,，、;\n]+", raw_text or "")
    tags = []
    seen = set()
    for t in chunks:
        t2 = t.strip()
        if not t2:
            continue
        if t2 not in seen:
            tags.append(t2)
            seen.add(t2)
    return tags


def is_meaningful_cell(value: Any) -> bool:
    """判断单元格是否为“有意义回答”。

    Args:
        value: 任意单元格值。

    Returns:
        True 表示应纳入 LLM 输入；False 表示应忽略。
    """
    # 先处理 NaN/None
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False

    text = str(value).strip()
    if not text:
        return False
    if text.lower() in INVALID_CELL_TEXTS:
        return False
    return True


def build_structured_profile_text(row: pd.Series, selected_columns: list[str]) -> str:
    """将一行问卷数据组装为结构化文本（题头+回答），并跳过无效值。

    Args:
        row: 单个玩家（DataFrame 一行）。
        selected_columns: 用户选择用于画像的列。

    Returns:
        可直接喂给 LLM 的结构化文本；若全部为空，返回空字符串。
    """
    lines: list[str] = []
    for col in selected_columns:
        # 双保险：列不存在就跳过（防止中途数据结构变化）
        if col not in row.index:
            continue
        val = row[col]
        if not is_meaningful_cell(val):
            continue
        lines.append(f"【{col}】：{str(val).strip()}")
    return "\n".join(lines)


def build_prompt(profile_text: str, preset_tags: list[str]) -> list[dict[str, str]]:
    """构建 Chat Completions 消息，强约束模型输出 JSON 且仅可选标签库。

    Args:
        profile_text: 结构化玩家画像原始信息。
        preset_tags: 预设标签库。

    Returns:
        OpenAI 风格消息列表（system + user）。
    """
    tag_text = "、".join(preset_tags)
    system_prompt = (
        "你是资深游戏用户研究分析助手。"
        "你的任务是从【预设标签库】中，给玩家选择1-3个最贴切标签。"
        "严禁创造标签库之外的任何新标签。"
        "必须严格输出 JSON，不要输出 JSON 之外的任何字符。"
    )
    user_prompt = (
        "请基于以下玩家问卷结构化信息，选择最贴切的标签。\n\n"
        f"【预设标签库】\n{tag_text}\n\n"
        "【玩家信息】\n"
        f"{profile_text}\n\n"
        "【输出要求】\n"
        "1. 只能从预设标签库中选择 1-3 个标签；\n"
        "2. 输出必须是严格 JSON，格式如下：\n"
        '{"tags": ["标签1", "标签2"], "reasoning": "一句话理由"}\n'
        "3. reasoning 要简短，不超过 50 字。"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型返回文本中尽力提取 JSON 对象。

    Args:
        text: 模型返回内容（可能干净 JSON，也可能混有前后缀文本）。

    Returns:
        解析成功返回 dict；失败返回 None。
    """
    if not text:
        return None

    # 1) 先尝试整体解析（最理想路径）
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 2) 再尝试截取第一个 { ... } 片段解析（容错）
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    candidate = match.group(0)
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def sanitize_llm_result(raw: dict[str, Any] | None, preset_tags: list[str]) -> tuple[str, str]:
    """清洗模型结果：确保标签来自预设库，并输出稳定可写入表格的字符串。

    Args:
        raw: LLM JSON 解析结果。
        preset_tags: 预设标签库。

    Returns:
        (tags_joined, reason)：
        - tags_joined: 用 | 拼接的标签字符串；
        - reason: 一句话理由。
    """
    if not raw:
        return "待人工复核", "模型返回无法解析为 JSON。"

    tags_any = raw.get("tags", [])
    reason_any = raw.get("reasoning", "")

    # 兼容 tags 不是 list 的异常情况
    if isinstance(tags_any, str):
        tags_list = [x.strip() for x in re.split(r"[|,，、]+", tags_any) if x.strip()]
    elif isinstance(tags_any, list):
        tags_list = [str(x).strip() for x in tags_any if str(x).strip()]
    else:
        tags_list = []

    # 强制仅保留预设标签库中的标签
    preset_set = set(preset_tags)
    deduped: list[str] = []
    seen = set()
    for t in tags_list:
        if t in preset_set and t not in seen:
            deduped.append(t)
            seen.add(t)

    # 保底：如果模型没按规则给有效标签，给一个可追踪占位值
    if not deduped:
        deduped = ["待人工复核"]

    # 限制最多 3 个，满足业务约束
    deduped = deduped[:3]
    reason = str(reason_any).strip() if reason_any is not None else ""
    if not reason:
        reason = "未返回有效理由。"
    return "|".join(deduped), reason


async def infer_single_row(
    session: aiohttp.ClientSession,
    row: pd.Series,
    selected_columns: list[str],
    preset_tags: list[str],
    api_url: str,
    api_key: str,
    model: str,
) -> tuple[str, str]:
    """对单个玩家行执行打标，作为并发 worker 的最小复用单元。

    Args:
        session: aiohttp 会话。
        row: 玩家单行数据。
        selected_columns: 画像输入列。
        preset_tags: 预设标签库。
        api_url: 模型接口 URL。
        api_key: API Key。
        model: 模型名称。

    Returns:
        (tags, reason) 二元组，均为可直接写入表格的字符串。
    """
    profile_text = build_structured_profile_text(row, selected_columns)

    if not profile_text:
        return "信息不足", "选中字段均为空或无有效内容。"

    messages = build_prompt(profile_text=profile_text, preset_tags=preset_tags)
    raw_obj = await request_llm_with_retry(
        session=session,
        api_url=api_url,
        api_key=api_key,
        model=model,
        messages=messages,
    )
    return sanitize_llm_result(raw=raw_obj, preset_tags=preset_tags)


async def request_llm_with_retry(
    session: aiohttp.ClientSession,
    api_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    max_retries: int = MAX_RETRY_TIMES,
) -> dict[str, Any] | None:
    """调用 LLM（OpenAI 兼容接口）并执行指数退避重试。

    Args:
        session: 复用的 aiohttp 会话。
        api_url: 完整接口 URL（通常是 .../chat/completions）。
        api_key: 鉴权密钥。
        model: 模型名称。
        messages: prompt 消息体。
        temperature: 采样温度。
        max_retries: 最大重试次数。

    Returns:
        解析后的 JSON dict；若持续失败返回 None。
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},  # 兼容支持该字段的服务
    }

    for attempt in range(max_retries + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            async with session.post(api_url, headers=headers, json=payload, timeout=timeout) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"HTTP {resp.status}: {text[:300]}")
                data = json.loads(text)
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                return extract_json_object(content)
        except Exception:
            # 超过重试次数后返回 None（交由上层做“人工复核”兜底）
            if attempt >= max_retries:
                return None
            # 指数退避 + 抖动：1s,2s,4s,8s...，并加随机抖动，降低雪崩重试风险
            backoff = (2 ** attempt) + random.uniform(0, 0.5)
            await asyncio.sleep(backoff)
    return None


async def process_all_rows_async(
    df: pd.DataFrame,
    selected_columns: list[str],
    preset_tags: list[str],
    api_url: str,
    api_key: str,
    model: str,
    max_concurrency: int,
    progress_bar: Any,
    status_placeholder: Any,
) -> tuple[list[str], list[str]]:
    """并发处理所有玩家行，返回标签列和理由列。

    Args:
        df: 原始问卷 DataFrame。
        selected_columns: 参与打标的列名列表。
        preset_tags: 预设标签库。
        api_url: 目标接口 URL。
        api_key: API Key。
        model: 模型名。
        max_concurrency: 最大并发数（建议 5~10）。
        progress_bar: Streamlit 进度条对象。
        status_placeholder: Streamlit 状态文本占位对象。

    Returns:
        (all_tags, all_reasons) 两个与 df 行数等长的列表。
    """
    sem = asyncio.Semaphore(max_concurrency)
    total = len(df)
    done = 0
    all_tags = [""] * total
    all_reasons = [""] * total

    async with aiohttp.ClientSession() as session:
        async def _worker(idx: int, row: pd.Series) -> None:
            nonlocal done
            async with sem:
                tags, reason = await infer_single_row(
                    session=session,
                    row=row,
                    selected_columns=selected_columns,
                    preset_tags=preset_tags,
                    api_url=api_url,
                    api_key=api_key,
                    model=model,
                )
                all_tags[idx] = tags
                all_reasons[idx] = reason

                done += 1
                progress_bar.progress(min(done / max(total, 1), 1.0))
                status_placeholder.caption(f"处理中：{done}/{total}")

        tasks = [_worker(i, row) for i, (_, row) in enumerate(df.iterrows())]
        await asyncio.gather(*tasks)

    return all_tags, all_reasons


async def process_selected_rows_async(
    df: pd.DataFrame,
    target_indices: list[int],
    selected_columns: list[str],
    preset_tags: list[str],
    api_url: str,
    api_key: str,
    model: str,
    max_concurrency: int,
    progress_bar: Any,
    status_placeholder: Any,
) -> dict[int, tuple[str, str]]:
    """仅对指定行索引做并发重跑，返回索引到结果的映射。

    Args:
        df: 原始问卷 DataFrame。
        target_indices: 需要重跑的行索引列表（基于 df.index 的位置索引）。
        selected_columns: 参与打标的列名列表。
        preset_tags: 预设标签库。
        api_url: 模型接口 URL。
        api_key: API Key。
        model: 模型名。
        max_concurrency: 最大并发数。
        progress_bar: Streamlit 进度条对象。
        status_placeholder: Streamlit 文本对象。

    Returns:
        dict[int, tuple[str, str]]，键为行号，值为 (tags, reason)。
    """
    sem = asyncio.Semaphore(max_concurrency)
    total = len(target_indices)
    done = 0
    results: dict[int, tuple[str, str]] = {}

    async with aiohttp.ClientSession() as session:
        async def _worker(idx: int) -> None:
            nonlocal done
            async with sem:
                row = df.iloc[idx]
                tags, reason = await infer_single_row(
                    session=session,
                    row=row,
                    selected_columns=selected_columns,
                    preset_tags=preset_tags,
                    api_url=api_url,
                    api_key=api_key,
                    model=model,
                )
                results[idx] = (tags, reason)
                done += 1
                progress_bar.progress(min(done / max(total, 1), 1.0))
                status_placeholder.caption(f"失败样本重跑中：{done}/{total}")

        await asyncio.gather(*[_worker(i) for i in target_indices])
    return results


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """将 DataFrame 导出为 Excel 二进制，供 Streamlit 下载按钮使用。"""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="玩家画像结果")
    return buffer.getvalue()


def build_delivery_df(df: pd.DataFrame, prefer_final: bool) -> pd.DataFrame:
    """构建业务交付口径表（可选优先使用“最终”列）。

    Args:
        df: 当前结果 DataFrame。
        prefer_final: 是否优先最终列。

    Returns:
        可导出的交付 DataFrame 副本。
    """
    out = df.copy()
    if not prefer_final:
        return out

    # 统一交付口径列：画像标签/打标理由/标签来源
    # 规则：有最终列优先最终；否则回退 AI 列。
    if "画像标签(交付口径)" not in out.columns:
        out["画像标签(交付口径)"] = ""
    if "打标理由(交付口径)" not in out.columns:
        out["打标理由(交付口径)"] = ""
    if "标签来源(交付口径)" not in out.columns:
        out["标签来源(交付口径)"] = ""

    final_tag_col = "最终画像标签"
    final_reason_col = "最终打标理由"
    final_src_col = "最终标签来源"
    ai_tag_col = "AI画像标签"
    ai_reason_col = "AI打标理由"

    for i in range(len(out)):
        final_tag = str(out.at[i, final_tag_col]).strip() if final_tag_col in out.columns else ""
        final_reason = str(out.at[i, final_reason_col]).strip() if final_reason_col in out.columns else ""
        final_src = str(out.at[i, final_src_col]).strip() if final_src_col in out.columns else ""
        ai_tag = str(out.at[i, ai_tag_col]).strip() if ai_tag_col in out.columns else ""
        ai_reason = str(out.at[i, ai_reason_col]).strip() if ai_reason_col in out.columns else ""

        # 优先最终，没有最终时回退 AI
        if final_tag:
            out.at[i, "画像标签(交付口径)"] = final_tag
            out.at[i, "打标理由(交付口径)"] = final_reason if final_reason else ai_reason
            out.at[i, "标签来源(交付口径)"] = final_src if final_src else "人工复核"
        else:
            out.at[i, "画像标签(交付口径)"] = ai_tag
            out.at[i, "打标理由(交付口径)"] = ai_reason
            out.at[i, "标签来源(交付口径)"] = "AI"
    return out


def to_failed_rows_excel_bytes(df: pd.DataFrame) -> bytes:
    """导出失败样本清单为 Excel（二进制）。

    失败样本判定规则复用 `find_retry_indices`，即标签含“待人工复核”。

    Args:
        df: 当前结果表。

    Returns:
        Excel bytes，可直接用于 Streamlit 下载按钮。
    """
    retry_indices = find_retry_indices(df)
    failed_df = df.iloc[retry_indices].copy() if retry_indices else df.head(0).copy()

    # 加一个“原始行号”列，方便研究员回表定位
    if not failed_df.empty:
        failed_df.insert(0, "原始行号", retry_indices)
        # 增加人工复核模板列，便于直接离线闭环
        if "人工复核标签" not in failed_df.columns:
            failed_df["人工复核标签"] = ""
        if "人工复核理由" not in failed_df.columns:
            failed_df["人工复核理由"] = ""
        if "是否确认" not in failed_df.columns:
            failed_df["是否确认"] = "待确认"
        if "复核人" not in failed_df.columns:
            failed_df["复核人"] = ""
        if "复核时间" not in failed_df.columns:
            failed_df["复核时间"] = ""
    else:
        # 即使空表也保留模板列结构，方便提前发模板
        for col in ("人工复核标签", "人工复核理由", "是否确认", "复核人", "复核时间"):
            if col not in failed_df.columns:
                failed_df[col] = ""

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        failed_df.to_excel(writer, index=False, sheet_name="失败样本清单")
    return buffer.getvalue()


def build_column_selector_options(df: pd.DataFrame) -> tuple[list[str], dict[str, str]]:
    """构建列选择器显示文本：优先按题号聚合展示，保持与项目题号识别口径一致。

    Args:
        df: 当前数据表。

    Returns:
        (options, label_to_col):
        - options: 前端展示文本列表；
        - label_to_col: 展示文本 -> 原始列名映射。
    """
    cols = [str(c) for c in df.columns]
    qmap = parse_columns_for_questions(cols)
    qnum_lookup: dict[str, int] = {}
    for q_num, info in qmap.items():
        for c in info.get("all_cols", []):
            qnum_lookup[str(c)] = q_num

    options: list[str] = []
    label_to_col: dict[str, str] = {}
    for c in cols:
        q_num = qnum_lookup.get(c)
        if q_num is not None:
            label = f"[Q{q_num}] {c}"
        else:
            label = c
        # 若 label 冲突，增加后缀保证唯一
        unique_label = label
        n = 2
        while unique_label in label_to_col:
            unique_label = f"{label} ({n})"
            n += 1
        options.append(unique_label)
        label_to_col[unique_label] = c
    return options, label_to_col


def find_retry_indices(result_df: pd.DataFrame) -> list[int]:
    """识别可重试样本：当前策略为标签含“待人工复核”的行。

    Args:
        result_df: 已打标结果表，包含 `AI画像标签` 列。

    Returns:
        需要重试的行位置索引列表（int）。
    """
    if "AI画像标签" not in result_df.columns:
        return []
    retry_list: list[int] = []
    for i, val in enumerate(result_df["AI画像标签"].tolist()):
        text = str(val or "").strip()
        if "待人工复核" in text:
            retry_list.append(i)
    return retry_list


def build_tag_dashboard_df(result_df: pd.DataFrame) -> pd.DataFrame:
    """构建标签统计面板数据（标签 -> 命中人数/占比）。

    Args:
        result_df: 已打标结果表。

    Returns:
        含列 `标签`、`命中人数`、`命中占比` 的 DataFrame（按人数降序）。
    """
    if "AI画像标签" not in result_df.columns or result_df.empty:
        return pd.DataFrame(columns=["标签", "命中人数", "命中占比"])

    tags_counter: Counter[str] = Counter()
    for cell in result_df["AI画像标签"].fillna("").astype(str).tolist():
        # 标签列使用 | 拼接；同时兼容用户手动改成逗号的情况
        pieces = [x.strip() for x in re.split(r"[|,，、]+", cell) if x.strip()]
        for t in pieces:
            # 这两个是系统兜底标签，不纳入画像分布统计
            if t in {"待人工复核", "信息不足"}:
                continue
            tags_counter[t] += 1

    if not tags_counter:
        return pd.DataFrame(columns=["标签", "命中人数", "命中占比"])

    total_players = len(result_df)
    rows = []
    for tag, cnt in tags_counter.most_common():
        ratio = f"{(cnt / max(total_players, 1)) * 100:.2f}%"
        rows.append({"标签": tag, "命中人数": int(cnt), "命中占比": ratio})
    return pd.DataFrame(rows)


def build_top_combo_df(result_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """统计标签组合 TopN（将同一行标签排序后作为组合键）。

    Args:
        result_df: 已打标结果表。
        top_n: 返回前 N 组组合。

    Returns:
        含列 `标签组合`、`人数` 的 DataFrame。
    """
    if "AI画像标签" not in result_df.columns or result_df.empty:
        return pd.DataFrame(columns=["标签组合", "人数"])

    combo_counter: Counter[str] = Counter()
    for cell in result_df["AI画像标签"].fillna("").astype(str).tolist():
        tags = [x.strip() for x in cell.split("|") if x.strip()]
        tags = [t for t in tags if t not in {"待人工复核", "信息不足"}]
        if not tags:
            continue
        combo_key = "|".join(sorted(set(tags)))
        combo_counter[combo_key] += 1

    rows = [{"标签组合": k, "人数": v} for k, v in combo_counter.most_common(top_n)]
    return pd.DataFrame(rows)


def normalize_confirm_text(value: Any) -> str:
    """将“是否确认”文本归一化，用于稳定判断是否人工确认。"""
    return str(value or "").strip().lower()


def merge_human_review_result(
    base_df: pd.DataFrame,
    review_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """将人工复核结果回写到主结果表（写入“最终”列，不覆盖 AI 原列）。

    回写规则（MVP）：
    1) review_df 必须包含 `原始行号`；
    2) 仅处理 `是否确认` 属于“确认/已确认/yes/true/1”的行；
    3) 标签优先取 `人工复核标签`，理由优先取 `人工复核理由`；
    4) 回写到 `最终画像标签`、`最终打标理由`，并同步 `最终标签来源=人工复核`。

    Args:
        base_df: 当前主结果表（含 AI 标签列）。
        review_df: 人工复核清单 DataFrame。

    Returns:
        (merged_df, stats)：回写后的结果表与统计信息。
    """
    merged_df = base_df.copy()
    if "最终画像标签" not in merged_df.columns:
        merged_df["最终画像标签"] = merged_df.get("AI画像标签", "")
    if "最终打标理由" not in merged_df.columns:
        merged_df["最终打标理由"] = merged_df.get("AI打标理由", "")
    if "最终标签来源" not in merged_df.columns:
        merged_df["最终标签来源"] = "AI"

    stats = {"total_review_rows": len(review_df), "confirmed_rows": 0, "updated_rows": 0, "skipped_rows": 0}

    if "原始行号" not in review_df.columns:
        raise ValueError("复核文件缺少必填列：原始行号")

    confirm_whitelist = {"确认", "已确认", "yes", "true", "1", "y"}

    for _, r in review_df.iterrows():
        row_id_raw = r.get("原始行号", None)
        try:
            row_id = int(row_id_raw)
        except Exception:
            stats["skipped_rows"] += 1
            continue

        if row_id < 0 or row_id >= len(merged_df):
            stats["skipped_rows"] += 1
            continue

        confirm_text = normalize_confirm_text(r.get("是否确认", ""))
        if confirm_text not in confirm_whitelist:
            stats["skipped_rows"] += 1
            continue
        stats["confirmed_rows"] += 1

        human_tags = str(r.get("人工复核标签", "")).strip()
        human_reason = str(r.get("人工复核理由", "")).strip()

        if not human_tags:
            # 若已确认但未填人工标签，则跳过，避免写入空值覆盖
            stats["skipped_rows"] += 1
            continue

        merged_df.at[row_id, "最终画像标签"] = human_tags
        merged_df.at[row_id, "最终打标理由"] = human_reason if human_reason else "人工复核确认（未填写理由）"
        merged_df.at[row_id, "最终标签来源"] = "人工复核"
        stats["updated_rows"] += 1

    return merged_df, stats


def main() -> None:
    """Streamlit 应用主入口。"""
    st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="wide")
    st.title(APP_TITLE)
    st.caption("上传问卷数据，按多维回答自动生成玩家画像标签。")

    # -------------------------------
    # Sidebar：基础配置 + 文件上传
    # -------------------------------
    with st.sidebar:
        st.header("基础配置")
        base_url = st.text_input("API Base URL", value=DEFAULT_BASE_URL, help="例如：https://api.openai.com/v1")
        api_key = st.text_input("API Key", value=DEFAULT_API_KEY, type="password")
        model_name = st.text_input("模型名称", value=DEFAULT_MODEL)
        max_concurrency = st.slider(
            "最大并发数",
            min_value=MAX_CONCURRENCY_MIN,
            max_value=MAX_CONCURRENCY_MAX,
            value=DEFAULT_MAX_CONCURRENCY,
            help="建议 5-10。并发越大越快，但更容易触发限流。",
        )
        st.divider()
        uploaded_file = st.file_uploader("上传问卷数据文件", type=["xlsx", "csv"])

    # 初始化会话状态，确保 rerun 后下载按钮不会消失
    if "result_df" not in st.session_state:
        st.session_state["result_df"] = None
    if "result_excel" not in st.session_state:
        st.session_state["result_excel"] = None
    if "prefer_final_export" not in st.session_state:
        st.session_state["prefer_final_export"] = True
    if "player_prof_fail_dl_name" not in st.session_state:
        st.session_state["player_prof_fail_dl_name"] = "玩家画像失败样本清单.xlsx"
    if "player_prof_main_dl_name" not in st.session_state:
        st.session_state["player_prof_main_dl_name"] = "玩家画像打标结果.xlsx"

    if uploaded_file is None:
        st.info("请先在左侧上传 .xlsx 或 .csv 文件。")
        return

    # 读取数据 + 预览
    try:
        raw_df = read_uploaded_table(uploaded_file)
    except Exception as exc:
        st.error(f"文件读取失败：{exc}")
        return

    if raw_df.empty:
        st.warning("上传成功，但表格为空。请检查数据源。")
        return

    # 对齐项目口径：优先规范化问卷星原始表头
    try:
        df, renamed = normalize_wjx_headers(raw_df)
        if renamed:
            st.success("已自动完成问卷星表头规范化（对齐项目解析口径）。")
    except Exception as exc:
        # 容错：规范化失败时不阻断主流程，直接使用原始表
        df = raw_df.copy()
        st.warning(f"表头规范化失败，已回退原始列名继续：{exc}")

    st.subheader("数据预览（前 3 行）")
    st.dataframe(df.head(3), use_container_width=True)

    # 列选择器（显示题号增强）
    options, label_to_col = build_column_selector_options(df)
    selected_labels = st.multiselect(
        "选择用于画像打标的列（至少选 1 列）",
        options=options,
        help="建议选择能反映玩法偏好、动机与行为倾向的题目列。",
    )
    selected_columns = [label_to_col[x] for x in selected_labels if x in label_to_col]

    # 标签库输入区
    default_tags = "硬核搜打撤玩家, 泛动作RPG受众, 轻度风景党, 竞技型MOBA玩家"
    tag_text = st.text_area(
        "预设标签库（逗号分隔）",
        value=default_tags,
        height=120,
    )

    # 运行按钮
    run_clicked = st.button("开始生成玩家画像标签", type="primary")

    if run_clicked:
        # 1) 参数校验：尽量在调用前发现问题
        if not api_key.strip():
            st.error("请先填写 API Key。")
            return
        if not model_name.strip():
            st.error("请先填写模型名称。")
            return
        if not selected_columns:
            st.error("请至少选择 1 个用于分析的列。")
            return
        preset_tags = parse_preset_tags(tag_text)
        if len(preset_tags) < 1:
            st.error("预设标签库不能为空，请至少输入 1 个标签。")
            return

        st.info(f"即将处理 {len(df)} 名玩家，标签库共 {len(preset_tags)} 个标签。")
        progress_bar = st.progress(0.0)
        status_placeholder = st.empty()
        final_api_url = normalize_base_url(base_url)

        try:
            # 2) 执行异步并发打标
            all_tags, all_reasons = asyncio.run(
                process_all_rows_async(
                    df=df,
                    selected_columns=selected_columns,
                    preset_tags=preset_tags,
                    api_url=final_api_url,
                    api_key=api_key.strip(),
                    model=model_name.strip(),
                    max_concurrency=max_concurrency,
                    progress_bar=progress_bar,
                    status_placeholder=status_placeholder,
                )
            )
        except Exception as exc:
            st.error(f"打标流程异常中断：{exc}")
            return

        # 3) 结果回填（注意 copy，避免污染原 df）
        out_df = df.copy()
        out_df["AI画像标签"] = all_tags
        out_df["AI打标理由"] = all_reasons

        st.session_state["result_df"] = out_df
        st.session_state["result_excel"] = to_excel_bytes(out_df)
        st.success("玩家画像标签生成完成。")

    # 结果展示与下载按钮（必须放在按钮块外，避免 rerun 后消失）
    if st.session_state.get("result_df") is not None:
        # -------------------------------
        # 增强 1：仅重跑失败样本（不重跑成功行）
        # -------------------------------
        st.subheader("失败样本重试")
        retry_candidates = find_retry_indices(st.session_state["result_df"])
        st.caption(f"当前可重试样本数：{len(retry_candidates)}（判定规则：AI画像标签含“待人工复核”）")
        retry_clicked = st.button("仅重跑失败样本")

        if retry_clicked:
            if not api_key.strip():
                st.error("请先填写 API Key。")
                return
            if not model_name.strip():
                st.error("请先填写模型名称。")
                return
            if not selected_columns:
                st.error("请至少选择 1 个用于分析的列（重跑也依赖该配置）。")
                return
            preset_tags = parse_preset_tags(tag_text)
            if len(preset_tags) < 1:
                st.error("预设标签库不能为空，请至少输入 1 个标签。")
                return
            if not retry_candidates:
                st.info("当前没有需要重跑的失败样本。")
            else:
                retry_progress = st.progress(0.0)
                retry_status = st.empty()
                final_api_url = normalize_base_url(base_url)
                try:
                    updates = asyncio.run(
                        process_selected_rows_async(
                            df=df,
                            target_indices=retry_candidates,
                            selected_columns=selected_columns,
                            preset_tags=preset_tags,
                            api_url=final_api_url,
                            api_key=api_key.strip(),
                            model=model_name.strip(),
                            max_concurrency=max_concurrency,
                            progress_bar=retry_progress,
                            status_placeholder=retry_status,
                        )
                    )
                except Exception as exc:
                    st.error(f"失败样本重跑中断：{exc}")
                    return

                merged_df = st.session_state["result_df"].copy()
                for idx, (tags, reason) in updates.items():
                    if 0 <= idx < len(merged_df):
                        merged_df.at[idx, "AI画像标签"] = tags
                        merged_df.at[idx, "AI打标理由"] = reason

                st.session_state["result_df"] = merged_df
                st.session_state["result_excel"] = to_excel_bytes(merged_df)
                st.success(f"失败样本重跑完成：共更新 {len(updates)} 条。")

        st.subheader("结果预览（前 10 行）")
        st.dataframe(st.session_state["result_df"].head(10), use_container_width=True)

        # 失败样本导出清单：便于线下人工复核
        failed_export_bytes = to_failed_rows_excel_bytes(st.session_state["result_df"])
        st.caption("失败样本清单已内置人工复核模板列：人工复核标签 / 人工复核理由 / 是否确认 / 复核人 / 复核时间。")
        st.text_input("失败清单下载文件名（可修改）", key="player_prof_fail_dl_name")
        _fail_fn = safe_download_filename(
            st.session_state.get("player_prof_fail_dl_name", "玩家画像失败样本清单.xlsx"),
            fallback="玩家画像失败样本清单.xlsx",
        )
        st.download_button(
            label="下载失败样本清单（仅待人工复核）",
            data=failed_export_bytes,
            file_name=_fail_fn,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # -------------------------------
        # 增强 2：标签命中统计看板
        # -------------------------------
        st.subheader("标签命中统计看板")
        dashboard_df = build_tag_dashboard_df(st.session_state["result_df"])
        if dashboard_df.empty:
            st.info("暂无可统计标签（可能全部为“待人工复核/信息不足”）。")
        else:
            total_players = len(st.session_state["result_df"])
            unique_tags = dashboard_df["标签"].nunique()
            st.caption(f"样本量：{total_players} | 命中标签数：{unique_tags}")

            st.dataframe(dashboard_df, use_container_width=True)

            # 条形图用数字列展示更直观
            chart_df = dashboard_df.copy()
            chart_df = chart_df.set_index("标签")[["命中人数"]]
            st.bar_chart(chart_df)

            combo_df = build_top_combo_df(st.session_state["result_df"], top_n=10)
            st.markdown("**Top10 标签组合**")
            if combo_df.empty:
                st.caption("暂无有效标签组合。")
            else:
                st.dataframe(combo_df, use_container_width=True)

        prefer_final_export = st.checkbox(
            "导出时优先使用最终列（最终画像标签/最终打标理由）",
            value=bool(st.session_state.get("prefer_final_export", True)),
            help="开启后将新增“交付口径”列：优先取最终列，若无则回退 AI 列。",
        )
        st.session_state["prefer_final_export"] = prefer_final_export

        delivery_df = build_delivery_df(
            st.session_state["result_df"],
            prefer_final=prefer_final_export,
        )
        delivery_excel = to_excel_bytes(delivery_df)

        st.text_input("主结果下载文件名（可修改）", key="player_prof_main_dl_name")
        _main_fn = safe_download_filename(
            st.session_state.get("player_prof_main_dl_name", "玩家画像打标结果.xlsx"),
            fallback="玩家画像打标结果.xlsx",
        )
        st.download_button(
            label="下载结果 Excel（含 AI画像标签 / AI打标理由）",
            data=delivery_excel,
            file_name=_main_fn,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # -------------------------------
        # 增强 3：人工复核回写（可选，不影响默认流程）
        # -------------------------------
        with st.expander("人工复核回写（可选）", expanded=False):
            st.caption(
                "上传“失败样本清单（人工已填写）”，系统仅回写“是否确认=确认”的记录，"
                "写入到最终列，不覆盖 AI 原始列。"
            )
            review_file = st.file_uploader(
                "上传人工复核清单（xlsx/csv）",
                type=["xlsx", "csv"],
                key="review_file_uploader",
            )
            apply_review_clicked = st.button("应用人工复核回写")

            if apply_review_clicked:
                if review_file is None:
                    st.error("请先上传人工复核清单文件。")
                else:
                    try:
                        review_df = read_uploaded_table(review_file)
                        merged_df, merge_stats = merge_human_review_result(
                            base_df=st.session_state["result_df"],
                            review_df=review_df,
                        )
                    except Exception as exc:
                        st.error(f"人工复核回写失败：{exc}")
                    else:
                        st.session_state["result_df"] = merged_df
                        st.session_state["result_excel"] = to_excel_bytes(merged_df)
                        st.success(
                            "回写完成："
                            f"复核表 {merge_stats['total_review_rows']} 行，"
                            f"确认 {merge_stats['confirmed_rows']} 行，"
                            f"成功回写 {merge_stats['updated_rows']} 行，"
                            f"跳过 {merge_stats['skipped_rows']} 行。"
                        )


if __name__ == "__main__":
    main()
