# -*- coding: utf-8 -*-
"""
Pipeline 风格交叉表块：长表透视与题目级导出 block（均值行、NPS、T2B 等）。
供 run_playtest_pipeline 与 quant_app 导出共用。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

NPS_KEYWORDS = [
    "nps", "净推荐", "推荐意愿", "推荐可能性", "推荐概率", "recommend",
]


# ---------------------------------------------------------------------------
def extract_option_value(opt_text: str) -> Optional[float]:
    """从选项标签提取开头的数字分值，用于计算均值。

    Args:
        opt_text: 选项文本，如 "4分（比较满意）"、"5"、"非常同意"。

    Returns:
        float 分值，无法提取时返回 None。
    """
    m = re.match(r"^\s*(\d+(?:\.\d+)?)", str(opt_text).strip())
    return float(m.group(1)) if m else None

def simple_pivot(res: dict, option_list: Optional[List[str]] = None) -> pd.DataFrame:
    """将 run_quant_cross_engine 长表透视为宽表（分组→列），并可按大纲选项补全。

    输出列顺序：选项 | 小计(n) | 总体% | [group1] | [group2] | ...
    若 option_list 不为空，按大纲顺序排列选项，未出现的选项补 0。

    Args:
        res: run_quant_cross_engine 返回列表中的单个元素 dict。
        option_list: 大纲中的完整选项列表（用于 reindex，可为 None）。

    Returns:
        透视后的 DataFrame；若失败则返回原始长表。
    """
    df_q = res["数据"]
    q_type = res["题型"]
    if df_q.empty:
        return df_q
    try:
        if q_type in ("单选", "评分", "NPS", "矩阵单选", "矩阵评分"):
            # Step 1: 透视（保留原始选项值）
            pivot = df_q.pivot_table(
                index="选项",
                columns="核心分组",
                values="行百分比",
                aggfunc="first",
                fill_value=0,
            ).reset_index()

            # Step 2: 计算总计（用原始值作为 key）
            total_counts = df_q.groupby("选项")["频次"].sum()
            total_samples = df_q["频次"].sum()
            total_ratio = total_counts / total_samples if total_samples > 0 else 0

            pivot.insert(1, "总体%", pivot["选项"].map(total_ratio).fillna(0))

            # Step 3: 格式化百分比列（总体% 和各分组列，不含选项/人数N）
            pct_cols = [c for c in pivot.columns if c != "选项"]
            for c in pct_cols:
                pivot[c] = pivot[c].apply(
                    lambda v: f"{v:.1%}"
                    if isinstance(v, (float, int)) and not isinstance(v, bool)
                    else v
                )

            # Step 4: 去掉与"总体%"重复的合成分组列
            # 合成分组时 df["_总体_"] = "总体"，pivot_table 会产生名为"总体"的列
            # 当且仅当唯一的分组列恰好叫"总体"时才删除，避免误删真实组名
            _non_stat_cols = {"选项", "总体%"}
            group_cols_in_pivot = [c for c in pivot.columns if c not in _non_stat_cols]
            if len(group_cols_in_pivot) == 1 and group_cols_in_pivot[0] == "总体":
                pivot = pivot.drop(columns=["总体"])

            # Step 5: 在末尾追加人数N列（基于原始值，在选项重命名前计算映射）
            n_map = pivot["选项"].map(total_counts).fillna(0)

            # Step 6: 大纲选项重命名 + 零填充（在统计计算完成后进行）
            # 问卷星 Excel 存储的是数值（如整数 4），大纲选项是文本（如"4分（比较满意）"）
            if option_list:
                # 构建 原始值字符串 → 大纲标签文本 的映射
                val_to_label: Dict[str, str] = {}
                for opt in option_list:
                    v = extract_option_value(str(opt))
                    if v is not None:
                        val_to_label[str(int(v))] = opt    # "4" → "4分（比较满意）"
                        val_to_label[str(v)] = opt         # "4.0" → "4分（比较满意）"

                # 如果数字前缀映射与实际数据完全不重叠（例如选项文本是"50小时以下"
                # 提取出50，但数据值是1/2/3/4/5），则自动降级为按位置映射
                def _build_pos_map(opts: List[str]) -> Dict[str, str]:
                    m: Dict[str, str] = {}
                    for i, o in enumerate(opts):
                        m[str(i + 1)] = o
                        m[f"{i + 1}.0"] = o   # float 字符串变体
                    return m

                if val_to_label:
                    actual_vals = {str(x) for x in pivot["选项"]}
                    if not (actual_vals & set(val_to_label.keys())):
                        # 数字前缀全部失配，尝试位置映射
                        pos_map = _build_pos_map(option_list)
                        if actual_vals & set(pos_map.keys()):
                            val_to_label = pos_map
                else:
                    # 无数字前缀时按位置映射（值"1"→第1个选项，值"2"→第2个选项，…）
                    val_to_label = _build_pos_map(option_list)

                # 将 "选项" 列原始值替换为大纲标签
                if val_to_label:
                    pivot["选项"] = pivot["选项"].apply(
                        lambda x: val_to_label.get(str(x), str(x))
                    )

                # 补全零频次选项（出现在大纲但数据中没有的选项）
                existing = set(pivot["选项"].tolist())
                zero_pct_fmt = "0.0%"
                for opt in option_list:
                    if opt not in existing:
                        zero_row: Dict[str, Any] = {c: zero_pct_fmt for c in pivot.columns}
                        zero_row["选项"] = opt
                        n_map = pd.concat([n_map, pd.Series([0])], ignore_index=True)
                        pivot = pd.concat(
                            [pivot, pd.DataFrame([zero_row])], ignore_index=True
                        )

                # 按大纲选项顺序重排（未在大纲中的附在末尾）
                opt_order = {opt: i for i, opt in enumerate(option_list)}
                sort_idx = pivot["选项"].map(lambda x: opt_order.get(x, len(option_list)))
                pivot = pivot.iloc[sort_idx.argsort().values].reset_index(drop=True)
                n_map = n_map.iloc[sort_idx.argsort().values].reset_index(drop=True)

            pivot["人数N"] = n_map.fillna(0).astype(int)
        else:
            # 多选题 — 与单选格式一致：选项 | 总体% | [group%] | 人数N
            pivot = df_q.pivot_table(
                index="选项",
                columns="核心分组",
                values="提及率",
                aggfunc="first",
                fill_value=0,
            ).reset_index()
            total_mentions = df_q.groupby("选项")["提及人数"].sum()
            total_sample = df_q.groupby("核心分组")["组样本数"].first().sum()
            overall_rate = total_mentions / total_sample if total_sample > 0 else 0
            pivot.insert(1, "总体%", pivot["选项"].map(overall_rate))

            # 去掉与"总体%"重复的合成分组列（与单选一致）
            _non_stat_cols = {"选项", "总体%"}
            group_cols_in_pivot = [c for c in pivot.columns if c not in _non_stat_cols]
            if len(group_cols_in_pivot) == 1 and group_cols_in_pivot[0] == "总体":
                pivot = pivot.drop(columns=["总体"])

            # 格式化百分比列
            pct_cols = [c for c in pivot.columns if c != "选项"]
            for c in pct_cols:
                pivot[c] = pivot[c].apply(
                    lambda v: f"{v:.1%}"
                    if isinstance(v, (float, int)) and not isinstance(v, bool)
                    else v
                )

            # 人数N：提及该选项的人数（跨组求和）
            n_map = pivot["选项"].map(total_mentions).fillna(0)

            # 大纲选项补全 0% 与排序（与单选一致）
            if option_list:
                existing = set(pivot["选项"].tolist())
                zero_pct_fmt = "0.0%"
                for opt in option_list:
                    if opt not in existing:
                        zero_row: Dict[str, Any] = {c: zero_pct_fmt for c in pivot.columns}
                        zero_row["选项"] = opt
                        zero_row["总体%"] = zero_pct_fmt
                        pivot = pd.concat(
                            [pivot, pd.DataFrame([zero_row])], ignore_index=True
                        )
                        n_map = pd.concat([n_map, pd.Series([0])], ignore_index=True)
                # 按大纲选项顺序重排
                opt_order = {opt: i for i, opt in enumerate(option_list)}
                sort_idx = pivot["选项"].map(lambda x: opt_order.get(x, len(option_list)))
                pivot = pivot.iloc[sort_idx.argsort().values].reset_index(drop=True)
                n_map = n_map.iloc[sort_idx.argsort().values].reset_index(drop=True)

            pivot["人数N"] = n_map.fillna(0).astype(int)
        return pivot
    except Exception:
        return df_q


# ---------------------------------------------------------------------------
# 辅助：单道非矩阵题的完整格式化 Block（含均值行 + N 行）
# ---------------------------------------------------------------------------
def build_question_block(
    res: dict,
    option_list: Optional[List[str]] = None,
) -> pd.DataFrame:
    """构建单道非矩阵题的完整格式化 DataFrame block，用于汇总 Sheet 纵向拼接。

    格式：
      [题目标题行]
      [本题平均分行]（仅数值选项题）
      [Banner N 行]（样本量(N) | 总体N | 各组N）
      [列头行]（选项 | 总体% | ...）
      [pivot 数据行]
      [空行]

    Args:
        res: run_quant_cross_engine 结果 dict。
        option_list: 大纲选项列表，传给 simple_pivot 补全 0 值。

    Returns:
        DataFrame，所有列与 pivot_df 对齐。
    """
    question = str(res.get("题目", ""))
    q_type = res.get("题型", "")
    df_q = res["数据"]

    pivot_df = simple_pivot(res, option_list=option_list)
    if pivot_df.empty:
        return pivot_df

    col0 = pivot_df.columns[0]  # "选项"

    def _make_row(label: str) -> pd.DataFrame:
        row = {c: "" for c in pivot_df.columns}
        row[col0] = label
        return pd.DataFrame([row])

    def _is_nps_question(question_text: str, data: pd.DataFrame) -> bool:
        q = str(question_text).strip().lower()
        has_nps_keyword = any(k in q for k in NPS_KEYWORDS)
        # 兼容常见中文问法：同时出现“推荐”与“意愿/可能/多大”
        has_cn_pattern = ("推荐" in q) and any(k in q for k in ("意愿", "可能", "多大"))
        if not (has_nps_keyword or has_cn_pattern):
            return False
        opt_vals = [extract_option_value(str(opt)) for opt in data.get("选项", pd.Series(dtype=object)).unique()]
        numeric_vals = [v for v in opt_vals if v is not None]
        if not numeric_vals:
            return False
        return min(numeric_vals) >= 0 and max(numeric_vals) <= 10

    def _calc_nps_rows(data: pd.DataFrame) -> List[pd.DataFrame]:
        rows: List[pd.DataFrame] = []
        if data.empty:
            return rows

        by_opt = data.groupby("选项")["频次"].sum()
        to_score = {
            opt: extract_option_value(str(opt))
            for opt in by_opt.index
        }

        promoter_opts = [opt for opt, v in to_score.items() if v is not None and v >= 9]
        passive_opts = [opt for opt, v in to_score.items() if v is not None and 7 <= v <= 8]
        detractor_opts = [opt for opt, v in to_score.items() if v is not None and v <= 6]

        grp_n_local = data.groupby("核心分组")["组样本数"].first()
        total_n_local = int(grp_n_local.sum())

        def _rate_for(opts: List[Any]) -> tuple[float, Dict[str, float]]:
            total_cnt = int(data["频次"].sum())
            overall_rate = (data[data["选项"].isin(opts)]["频次"].sum() / total_cnt) if total_cnt > 0 else 0.0
            per_group_rate: Dict[str, float] = {}
            for grp in data["核心分组"].dropna().unique():
                gdf = data[data["核心分组"] == grp]
                g_n = int(gdf["组样本数"].iloc[0]) if not gdf.empty else 0
                g_cnt = int(gdf[gdf["选项"].isin(opts)]["频次"].sum())
                per_group_rate[str(grp)] = (g_cnt / g_n) if g_n > 0 else 0.0
            return overall_rate, per_group_rate

        promoter_overall, promoter_grp = _rate_for(promoter_opts)
        passive_overall, passive_grp = _rate_for(passive_opts)
        detractor_overall, detractor_grp = _rate_for(detractor_opts)

        def _fill_pct_row(label: str, overall: float, grp_map: Dict[str, float]) -> pd.DataFrame:
            r = _make_row(label)
            for j, c in enumerate(pivot_df.columns):
                if c == "选项":
                    continue
                if c == "总体%":
                    r.iloc[0, j] = f"{overall:.1%}"
                elif c in grp_map:
                    r.iloc[0, j] = f"{grp_map[c]:.1%}"
            return r

        rows.append(_fill_pct_row("Promoter占比（9-10）", promoter_overall, promoter_grp))
        rows.append(_fill_pct_row("Passive占比（7-8）", passive_overall, passive_grp))
        rows.append(_fill_pct_row("Detractor占比（0-6）", detractor_overall, detractor_grp))

        nps_row = _make_row("NPS（%Promoter-%Detractor）")
        for j, c in enumerate(pivot_df.columns):
            if c == "选项":
                continue
            if c == "总体%":
                nps_row.iloc[0, j] = f"{(promoter_overall - detractor_overall) * 100:.1f}"
            elif c in promoter_grp and c in detractor_grp:
                nps_row.iloc[0, j] = f"{(promoter_grp[c] - detractor_grp[c]) * 100:.1f}"
            elif c == "人数N":
                nps_row.iloc[0, j] = total_n_local
            elif c in grp_n_local.index:
                nps_row.iloc[0, j] = int(grp_n_local[c])
        rows.append(nps_row)
        return rows

    is_nps = q_type == "NPS" or (
        q_type in ("单选", "评分") and _is_nps_question(question, df_q)
    )

    # 计算均值（仅当选项含数字分值时；NPS 题不输出均值，避免与国际口径混淆）
    mean_val: Optional[float] = None
    group_means: Dict[str, float] = {}
    n_valid = 0
    if q_type in ("单选", "评分") and not df_q.empty and not is_nps:
        try:
            total_counts = df_q.groupby("选项")["频次"].sum()
            opt_vals = {opt: extract_option_value(str(opt)) for opt in total_counts.index}
            numeric_opts = {opt: v for opt, v in opt_vals.items() if v is not None}
            if numeric_opts:
                weighted = sum(
                    numeric_opts[opt] * total_counts.get(opt, 0)
                    for opt in numeric_opts
                )
                n_valid = int(sum(total_counts.get(opt, 0) for opt in numeric_opts))
                if n_valid > 0:
                    mean_val = weighted / n_valid

                # 同时计算各组均值（用于导出时显示及显著性标记）
                for grp in df_q["核心分组"].dropna().unique():
                    gdf = df_q[df_q["核心分组"] == grp]
                    g_total_counts = gdf.groupby("选项")["频次"].sum()
                    g_weighted = sum(
                        numeric_opts.get(opt, 0.0) * g_total_counts.get(opt, 0)
                        for opt in g_total_counts.index
                        if opt in numeric_opts
                    )
                    g_n_valid = int(
                        sum(g_total_counts.get(opt, 0) for opt in g_total_counts.index if opt in numeric_opts)
                    )
                    if g_n_valid > 0:
                        group_means[str(grp)] = g_weighted / g_n_valid
            else:
                n_valid = int(total_counts.sum())
        except Exception:
            pass

    # Banner N 行：各组样本量，与 pivot 列对齐
    grp_n = df_q.groupby("核心分组")["组样本数"].first()
    total_n = int(grp_n.sum())
    banner_n_row = _make_row("")
    banner_n_row.iloc[0, 0] = "样本量(N)"
    for j, col in enumerate(pivot_df.columns):
        if col == "选项":
            continue
        if col == "总体%":
            banner_n_row.iloc[0, j] = total_n
        elif col == "人数N":
            banner_n_row.iloc[0, j] = ""  # 样本量行的人数N列留空
        elif col in grp_n.index:
            banner_n_row.iloc[0, j] = int(grp_n[col])

    # 列头行（选项|总体%|...|人数N）
    header_row = pd.DataFrame([dict(zip(pivot_df.columns, pivot_df.columns))])

    # T2B/B2B 行（仅 5 点量表：选项可解析出 4、5 分）
    t2b_b2b_rows: List[pd.DataFrame] = []
    if q_type in ("单选", "评分") and not df_q.empty and not is_nps:
        opt_vals = {}
        for opt in df_q["选项"].unique():
            v = extract_option_value(str(opt))
            if v is not None:
                opt_vals[opt] = v
        has_4_5 = 4 in opt_vals.values() or 5 in opt_vals.values()
        if has_4_5:
            grp_n = df_q.groupby("核心分组")["组样本数"].first()
            total_n = int(grp_n.sum())
            opts_4_5 = [o for o, v in opt_vals.items() if v in (4, 5)]
            opts_1_2 = [o for o, v in opt_vals.items() if v in (1, 2)]
            pct_cols = [c for c in pivot_df.columns if c not in ("选项", "人数N")]

            def _calc_box(df_in: pd.DataFrame, opts: List[Any]) -> Tuple[float, Dict[str, float]]:
                total_cnt = df_in["频次"].sum()
                if total_cnt == 0:
                    return 0.0, {str(g): 0.0 for g in df_in["核心分组"].unique()}
                box_cnt = df_in[df_in["选项"].isin(opts)]["频次"].sum()
                overall = box_cnt / total_cnt
                per_grp = {}
                for g in df_in["核心分组"].unique():
                    gdf = df_in[df_in["核心分组"] == g]
                    gtot = gdf["组样本数"].iloc[0]
                    gbox = gdf[gdf["选项"].isin(opts)]["频次"].sum()
                    per_grp[str(g)] = gbox / gtot if gtot > 0 else 0.0
                return overall, per_grp

            t2b_overall, t2b_grp = _calc_box(df_q, opts_4_5)
            t2b_row = _make_row("T2B（4+5分）")
            for j, col in enumerate(pivot_df.columns):
                if col == "选项":
                    continue
                if col == "总体%":
                    t2b_row.iloc[0, j] = f"{t2b_overall:.1%}"
                elif col in t2b_grp:
                    t2b_row.iloc[0, j] = f"{t2b_grp[col]:.1%}"
            t2b_b2b_rows.append(t2b_row)

            if opts_1_2:
                b2b_overall, b2b_grp = _calc_box(df_q, opts_1_2)
                b2b_row = _make_row("B2B（1+2分）")
                for j, col in enumerate(pivot_df.columns):
                    if col == "选项":
                        continue
                    if col == "总体%":
                        b2b_row.iloc[0, j] = f"{b2b_overall:.1%}"
                    elif col in b2b_grp:
                        b2b_row.iloc[0, j] = f"{b2b_grp[col]:.1%}"
                t2b_b2b_rows.append(b2b_row)

    # NPS 国际口径：NPS = %Promoter(9-10) - %Detractor(0-6)
    nps_rows: List[pd.DataFrame] = []
    if is_nps:
        nps_rows = _calc_nps_rows(df_q)

    # 拼装 block：题目标题 → [均值] → Banner N → 列头 → 数据 → [T2B/B2B] → 空行
    parts: List[pd.DataFrame] = [
        _make_row(f"【{question}】（{q_type}）"),
    ]
    if mean_val is not None:
        mean_row = _make_row("本题平均分")
        for j, col in enumerate(pivot_df.columns):
            if col == "选项":
                mean_row.iloc[0, j] = "本题平均分"
            elif col == "总体%":
                mean_row.iloc[0, j] = f"{mean_val:.2f}"
            elif col == "人数N":
                mean_row.iloc[0, j] = ""
            elif str(col) in group_means:
                mean_row.iloc[0, j] = f"{group_means[str(col)]:.2f}"
        parts.append(mean_row)
    parts.append(banner_n_row)
    parts.append(header_row)
    parts.append(pivot_df)
    parts.extend(t2b_b2b_rows)
    parts.extend(nps_rows)
    parts.append(_make_row(""))

    return pd.concat(parts, ignore_index=True)

__all__ = [
    "extract_option_value",
    "simple_pivot",
    "build_question_block",
]
