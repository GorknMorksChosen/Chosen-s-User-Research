import numpy as np
import pandas as pd
import re
from itertools import combinations
from typing import Tuple
from scipy import stats
from scipy.stats import kruskal, f_oneway
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from statsmodels.stats.multitest import multipletests
from scikit_posthocs import posthoc_dunn


def calculate_eta_squared_anova(data_groups):
    """基于 ANOVA 组间 SS 计算 Eta-squared 效应量。

    Args:
        data_groups: list of array-like，每个元素为一组的数值数据。

    Returns:
        float，Eta-squared 值（0~1）；无法计算时返回 np.nan。
    """
    all_data = np.concatenate(data_groups)
    total_mean = np.mean(all_data)
    ss_total = np.sum((all_data - total_mean) ** 2)
    ss_between = 0
    for group in data_groups:
        group_mean = np.mean(group)
        n_group = len(group)
        ss_between += n_group * (group_mean - total_mean) ** 2
    if ss_total == 0:
        return np.nan
    return ss_between / ss_total


def calculate_eta_squared_kruskal(H_statistic, n_groups, n_total):
    """基于 Kruskal-Wallis H 统计量估算 Eta-squared 效应量。

    Args:
        H_statistic: float，Kruskal-Wallis H 值。
        n_groups: int，分组数量。
        n_total: int，所有组合并后的总样本量。

    Returns:
        float，Eta-squared 估算值（最小为 0）；自由度不足时返回 np.nan。
    """
    if n_total - n_groups <= 0:
        return np.nan
    eta_sq = (H_statistic - n_groups + 1) / (n_total - n_groups)
    return max(0.0, eta_sq)


def calculate_cramers_v(contingency_table):
    """计算列联表的 Cramér's V 效应量（卡方检验的标准化效应量）。

    Args:
        contingency_table: pd.DataFrame，交叉频数列联表，行列均应为分类变量。

    Returns:
        float，Cramér's V 值（0~1）；表格为空或维度不足时返回 np.nan。
    """
    if contingency_table.empty or min(contingency_table.shape) < 2:
        return np.nan
    try:
        table = contingency_table.astype(int)
    except ValueError:
        return np.nan
    if table.to_numpy().sum() == 0:
        return np.nan
    chi2, _, _, _ = stats.chi2_contingency(table)
    n = table.to_numpy().sum()
    min_dim = min(table.shape) - 1
    if n == 0 or min_dim == 0:
        return np.nan
    v = np.sqrt(chi2 / (n * min_dim))
    return v


def calculate_rating_metrics(df, value_col, group_col=None):
    """计算评分题的描述统计指标（均值、标准差、偏度、峰度、有效 n）。

    Args:
        df: pd.DataFrame，问卷数据，行为受访者。
        value_col: str，评分列名。
        group_col: str or None，分组列名；为 None 时计算整体统计。

    Returns:
        pd.DataFrame，每行对应一个分组（或"ALL"），列为 group/mean/std/skew/kurtosis/n。
    """
    ser = pd.to_numeric(df[value_col], errors="coerce").dropna()
    if group_col is None:
        if ser.empty:
            return pd.DataFrame(
                columns=["group", "mean", "std", "skew", "kurtosis", "n"]
            )
        metrics = {
            "group": ["ALL"],
            "mean": [float(ser.mean())],
            "std": [float(ser.std(ddof=1)) if ser.size > 1 else np.nan],
            "skew": [float(ser.skew())],
            "kurtosis": [float(ser.kurtosis())],
            "n": [int(ser.size)],
        }
        return pd.DataFrame(metrics)
    records = []
    grouped = df[[group_col, value_col]].copy()
    grouped[value_col] = pd.to_numeric(grouped[value_col], errors="coerce")
    for g, sub in grouped.groupby(group_col, dropna=False):
        s = sub[value_col].dropna()
        if s.empty:
            records.append(
                {
                    "group": g,
                    "mean": np.nan,
                    "std": np.nan,
                    "skew": np.nan,
                    "kurtosis": np.nan,
                    "n": 0,
                }
            )
        else:
            records.append(
                {
                    "group": g,
                    "mean": float(s.mean()),
                    "std": float(s.std(ddof=1)) if s.size > 1 else np.nan,
                    "skew": float(s.skew()),
                    "kurtosis": float(s.kurtosis()),
                    "n": int(s.size),
                }
            )
    return pd.DataFrame(records)


def _build_empty_overall(test_name=None):
    return {
        "test": test_name,
        "stat": np.nan,
        "p_value": np.nan,
        "effect_size": np.nan,
    }


def _extract_option_label(option_col):
    s = str(option_col).strip()
    if "：" in s:
        right = s.split("：", 1)[1].strip()
        return right if right else s
    if ":" in s:
        right = s.split(":", 1)[1].strip()
        return right if right else s
    return s


def _to_binary_mention(series):
    """将多选列统一转换为 0/1 提及编码。

    规则：
    - 数值可解析时：仅 >0 视为提及（0/0.0/负值均视为未提及）
    - 文本不可解析时：按无效值词表判定（含 0 与 0.0）
    """
    invalid_raw = {"", "0", "0.0", "否", "未选", "nan", "none", "无", "na", "n/a"}
    invalid_lower = {s.lower() for s in invalid_raw}

    numeric = pd.to_numeric(series, errors="coerce")
    is_numeric = numeric.notna()
    numeric_mention = numeric > 0

    ser_str = series.astype(str).str.strip()
    text_mention = (~series.isna()) & (~ser_str.str.lower().isin(invalid_lower))

    return pd.Series(
        np.where(is_numeric, numeric_mention, text_mention),
        index=series.index,
    ).astype(int)


def _two_proportion_z_test(x1: int, n1: int, x2: int, n2: int) -> Tuple[float, float]:
    """两独立样本比例 z 检验（双侧），返回 (z, p_value)。"""
    if n1 <= 0 or n2 <= 0:
        return float("nan"), float("nan")
    p1 = x1 / n1
    p2 = x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    if p_pool <= 0 or p_pool >= 1:
        return float("nan"), float("nan")
    se = np.sqrt(p_pool * (1 - p_pool) * (1.0 / n1 + 1.0 / n2))
    if se == 0:
        return float("nan"), float("nan")
    z = (p1 - p2) / se
    p_val = 2 * (1 - stats.norm.cdf(abs(z)))
    return float(z), float(p_val)


def run_group_difference_test(
    df, group_col, value_col, question_type, min_group_size=3, alpha: float = 0.05
):
    """对问卷题目进行分组差异检验，自动选择参数/非参数方法。

    根据题型分别执行：单选→卡方/Fisher 精确检验；评分→k=2 时 Welch t 检验，
    k>2 时 ANOVA/Kruskal-Wallis；多选→逐选项卡方检验并做 FDR 校正。

    Args:
        df: pd.DataFrame，问卷数据，行为受访者。
        group_col: str，分组列名（核心分段变量）。
        value_col: str or list[str]，题目列名；多选题传列表。
        question_type: str，题型，支持 "单选" / "评分" / "多选"。
        min_group_size: int，最小组样本量，低于此值的组被排除（默认 3）。
        alpha: float，显著性水平（默认 0.05），用于 pipeline_summary 与事后标记。

    Returns:
        dict，含以下键：
          - "overall": dict，整体检验结果（test/stat/p_value/effect_size）。
          - "pairwise": pd.DataFrame or None，两两事后比较结果（评分题显著时提供）。
          - "details": list[dict]，逐选项结果（多选题专有）。
          - "assumption_checks": dict，前置检验结果（评分题专有）。
          - "pipeline_summary": dict，供 Pipeline 导出（p_value、is_significant、cells 等）。
    """
    result = {"overall": None, "pairwise": None}
    if group_col not in df.columns:
        result["overall"] = _build_empty_overall()
        result["pipeline_summary"] = {
            "p_value": np.nan,
            "is_significant": False,
            "alpha": alpha,
            "direction_by_group": {},
            "cells": [],
        }
        return result

    if question_type == "单选":
        if value_col not in df.columns:
            result["overall"] = _build_empty_overall("chi-square")
            result["pipeline_summary"] = {
                "p_value": np.nan,
                "is_significant": False,
                "alpha": alpha,
                "direction_by_group": {},
                "cells": [],
            }
            return result
        data = df[[group_col, value_col]].copy().dropna(subset=[group_col, value_col])
        if data.empty:
            result["overall"] = _build_empty_overall("chi-square")
            result["pipeline_summary"] = {
                "p_value": np.nan,
                "is_significant": False,
                "alpha": alpha,
                "direction_by_group": {},
                "cells": [],
            }
            return result
        group_sizes = data[group_col].value_counts(dropna=False)
        valid_groups = group_sizes[group_sizes >= min_group_size].index
        data = data[data[group_col].isin(valid_groups)]
        contingency = pd.crosstab(data[group_col], data[value_col])
        if contingency.empty or contingency.shape[0] < 2 or contingency.shape[1] < 2:
            result["overall"] = _build_empty_overall("chi-square")
            result["pipeline_summary"] = {
                "p_value": np.nan,
                "is_significant": False,
                "alpha": alpha,
                "direction_by_group": {},
                "cells": [],
            }
            return result
        chi2, p_chi, _, expected = stats.chi2_contingency(contingency)
        test_name = "chi-square"
        stat_val = chi2
        if contingency.shape == (2, 2) and expected.min() < 5:
            try:
                oddsratio, p_fish = stats.fisher_exact(contingency)
                test_name = "fisher_exact"
                stat_val = oddsratio
                p_chi = p_fish
            except Exception:
                pass
        effect = calculate_cramers_v(contingency)
        result["overall"] = {
            "test": test_name,
            "stat": float(stat_val) if pd.notna(stat_val) else np.nan,
            "p_value": float(p_chi) if pd.notna(p_chi) else np.nan,
            "effect_size": float(effect) if pd.notna(effect) else np.nan,
        }
        arrow_map = {}
        cells_export = []
        try:
            observed = contingency
            row_totals = observed.sum(axis=1)
            col_totals = observed.sum(axis=0)
            n = observed.sum().sum()
            expected_df = pd.DataFrame(
                expected, index=observed.index, columns=observed.columns
            )
            for r_idx in observed.index:
                for c_idx in observed.columns:
                    O = observed.loc[r_idx, c_idx]
                    E = expected_df.loc[r_idx, c_idx]
                    r_prop = row_totals[r_idx] / n
                    c_prop = col_totals[c_idx] / n
                    denom = np.sqrt(E * (1 - r_prop) * (1 - c_prop))
                    asr = 0 if denom == 0 else (O - E) / denom
                    if asr > 1.96:
                        arrow_map[(r_idx, c_idx)] = "▲"
                    elif asr < -1.96:
                        arrow_map[(r_idx, c_idx)] = "▼"
                    if abs(asr) > 1.96:
                        cells_export.append(
                            {
                                "group": str(r_idx),
                                "option": str(c_idx),
                                "is_significant": True,
                                "direction": "higher" if asr > 0 else "lower",
                                "metric": "proportion",
                            }
                        )
        except Exception:
            pass
        if arrow_map:
            result["posthoc_arrows"] = arrow_map
        result["pipeline_summary"] = {
            "p_value": float(p_chi) if pd.notna(p_chi) else np.nan,
            "is_significant": bool(pd.notna(p_chi) and p_chi < alpha),
            "alpha": alpha,
            "direction_by_group": {},
            "cells": cells_export,
        }
        return result

    if question_type == "多选":
        result["details"] = []
        empty_ps_multi = {
            "p_value": np.nan,
            "is_significant": False,
            "alpha": alpha,
            "direction_by_group": {},
            "cells": [],
        }
        if not isinstance(value_col, list) or len(value_col) == 0:
            result["overall"] = _build_empty_overall("multi-option")
            result["pipeline_summary"] = empty_ps_multi
            return result
        option_cols = [c for c in value_col if c in df.columns]
        missing_cols = [c for c in value_col if c not in df.columns]
        if not option_cols:
            result["overall"] = _build_empty_overall("multi-option")
            result["pipeline_summary"] = empty_ps_multi
            return result
        valid_mask = df[option_cols].notna().any(axis=1)
        data = df.loc[valid_mask, [group_col] + option_cols].copy().dropna(subset=[group_col])
        if data.empty:
            result["overall"] = _build_empty_overall("multi-option")
            result["pipeline_summary"] = empty_ps_multi
            return result
        group_sizes = data[group_col].value_counts(dropna=False)
        valid_groups = group_sizes[group_sizes >= min_group_size].index
        data = data[data[group_col].isin(valid_groups)]
        if data.empty:
            result["overall"] = _build_empty_overall("multi-option")
            result["pipeline_summary"] = empty_ps_multi
            return result
        details = []
        for col in option_cols:
            try:
                mention = _to_binary_mention(data[col])
                contingency = pd.crosstab(data[group_col], mention)
                if 0 not in contingency.columns:
                    contingency[0] = 0
                if 1 not in contingency.columns:
                    contingency[1] = 0
                contingency = contingency[[0, 1]]
                if contingency.shape[0] < 2 or contingency[1].sum() == 0:
                    continue
                chi2, p_val, _, expected = stats.chi2_contingency(contingency)
                test_name = "chi-square"
                stat_val = chi2
                if contingency.shape == (2, 2) and expected.min() < 5:
                    try:
                        oddsratio, p_fish = stats.fisher_exact(contingency)
                        test_name = "fisher_exact"
                        stat_val = oddsratio
                        p_val = p_fish
                    except Exception:
                        pass
                effect = calculate_cramers_v(contingency)
                details.append(
                    {
                        "option": col,
                        "option_label": _extract_option_label(col),
                        "test": test_name,
                        "stat": float(stat_val) if pd.notna(stat_val) else np.nan,
                        "p_value": float(p_val) if pd.notna(p_val) else np.nan,
                        "effect_size": float(effect) if pd.notna(effect) else np.nan,
                        "group_n": int(contingency.shape[0]),
                    }
                )
            except Exception:
                continue
        if not details:
            result["overall"] = _build_empty_overall("multi-option")
            result["details"] = []
            result["pipeline_summary"] = {
                "p_value": np.nan,
                "is_significant": False,
                "alpha": alpha,
                "direction_by_group": {},
                "cells": [],
            }
            if missing_cols:
                result["missing_options"] = missing_cols
            return result
        # FDR 校正（v1.3 行为）：对每选项 p 值做 Benjamini–Hochberg 校正
        valid_idx = [i for i, d in enumerate(details) if pd.notna(d.get("p_value"))]
        p_vals = [details[i]["p_value"] for i in valid_idx]
        for i in range(len(details)):
            details[i]["p_value_corrected"] = np.nan
        if p_vals:
            try:
                _, p_corrected, _, _ = multipletests(p_vals, method="fdr_bh")
                for k, i in enumerate(valid_idx):
                    details[i]["p_value_corrected"] = float(p_corrected[k])
            except Exception:
                pass
        p_values = [d["p_value"] for d in details if pd.notna(d["p_value"])]
        p_corr_values = [d["p_value_corrected"] for d in details if pd.notna(d.get("p_value_corrected"))]
        effect_sizes = [d["effect_size"] for d in details if pd.notna(d["effect_size"])]
        max_eff = max(effect_sizes) if effect_sizes else np.nan
        sig_count = sum(
            1
            for d in details
            if pd.notna(d.get("p_value_corrected")) and d["p_value_corrected"] < alpha
        )
        # M4: overall.p_value 优先用 FDR 校正后最小值，与 sig_count 口径一致；无校正值则降级用原始最小值
        min_p_corr = min(p_corr_values) if p_corr_values else np.nan
        min_p_raw = min(p_values) if p_values else np.nan
        rep_p = float(min_p_corr) if pd.notna(min_p_corr) else (float(min_p_raw) if pd.notna(min_p_raw) else np.nan)
        result["overall"] = {
            "test": "multi-option",
            "stat": np.nan,
            "p_value": rep_p,
            "effect_size": float(max_eff) if pd.notna(max_eff) else np.nan,
            "tested_options": int(len(details)),
            "significant_options": int(sig_count),
            "p_value_corrected_applied": bool(p_corr_values),
        }
        result["details"] = details
        if missing_cols:
            result["missing_options"] = missing_cols
        # 每组 vs 其余组：提及率差异（双侧 z 检验），供 Pipeline 逐格打标
        cells_export = []
        for col in option_cols:
            try:
                mention = _to_binary_mention(data[col])
                opt_label = _extract_option_label(col)
                for g in valid_groups:
                    g_mask = data[group_col] == g
                    rest_mask = ~g_mask
                    x1 = int(mention[g_mask].sum())
                    n1 = int(g_mask.sum())
                    x2 = int(mention[rest_mask].sum())
                    n2 = int(rest_mask.sum())
                    if n1 < min_group_size or n2 < min_group_size:
                        continue
                    _, p_z = _two_proportion_z_test(x1, n1, x2, n2)
                    if not np.isfinite(p_z):
                        continue
                    p1 = x1 / n1 if n1 else 0.0
                    p2 = x2 / n2 if n2 else 0.0
                    direction = "higher" if p1 > p2 else "lower"
                    cells_export.append(
                        {
                            "group": str(g),
                            "option": str(opt_label),
                            "p_value": float(p_z),
                            "is_significant": bool(p_z < alpha),
                            "direction": direction,
                            "metric": "mention_rate",
                        }
                    )
            except Exception:
                continue
        result["pipeline_summary"] = {
            "p_value": float(rep_p) if np.isfinite(rep_p) else np.nan,
            "is_significant": bool(np.isfinite(rep_p) and rep_p < alpha),
            "alpha": alpha,
            "direction_by_group": {},
            "cells": cells_export,
        }
        return result
            
    if question_type == "评分":
        empty_ps = {
            "p_value": np.nan,
            "is_significant": False,
            "alpha": alpha,
            "direction_by_group": {},
            "cells": [],
        }
        data = df[[group_col, value_col]].copy()
        data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
        data = data.dropna(subset=[value_col])
        if data.empty:
            result["overall"] = {
                "test": None,
                "stat": np.nan,
                "p_value": np.nan,
                "effect_size": np.nan,
            }
            result["pipeline_summary"] = empty_ps
            return result
        groups = []
        group_labels = []
        for g, sub in data.groupby(group_col, dropna=False):
            vals = sub[value_col].dropna().to_numpy()
            if vals.size >= min_group_size:
                groups.append(vals)
                group_labels.append(g)
        if len(groups) < 2:
            result["overall"] = {
                "test": None,
                "stat": np.nan,
                "p_value": np.nan,
                "effect_size": np.nan,
            }
            result["pipeline_summary"] = empty_ps
            return result
        all_vals = np.concatenate(groups)
        grand_mean = float(np.mean(all_vals))

        def _direction_by_welch_vs_rest() -> dict:
            direction_by_group = {}
            for i, g in enumerate(group_labels):
                vals = groups[i]
                others = np.concatenate([groups[j] for j in range(len(groups)) if j != i])
                if len(others) < min_group_size or len(vals) < min_group_size:
                    direction_by_group[str(g)] = {
                        "direction": None,
                        "p_value": None,
                        "is_significant": False,
                    }
                    continue
                try:
                    _, p_rest = stats.ttest_ind(
                        vals, others, equal_var=False, nan_policy="omit"
                    )
                    p_rest = float(p_rest)
                except Exception:
                    p_rest = np.nan
                mean_g = float(np.mean(vals))
                direction = "higher" if mean_g > grand_mean else "lower"
                direction_by_group[str(g)] = {
                    "direction": direction,
                    "p_value": p_rest if np.isfinite(p_rest) else None,
                    "is_significant": bool(np.isfinite(p_rest) and p_rest < alpha),
                }
            return direction_by_group

        # k=2：强制 Welch；k>2：ANOVA / Kruskal-Wallis；每组 vs 其余组 Welch 用于导出打标
        if len(groups) == 2:
            t_stat, p_val = stats.ttest_ind(
                groups[0], groups[1], equal_var=False, nan_policy="omit"
            )
            pooled = np.concatenate(groups)
            cohen_d = (float(np.mean(groups[0])) - float(np.mean(groups[1]))) / (
                float(np.std(pooled, ddof=1)) + 1e-12
            )
            result["overall"] = {
                "test": "welch_t",
                "stat": float(t_stat),
                "p_value": float(p_val),
                "effect_size": float(abs(cohen_d)),
            }
            m0, m1 = float(np.mean(groups[0])), float(np.mean(groups[1]))
            result["pairwise"] = pd.DataFrame(
                [
                    {
                        "group1": group_labels[0],
                        "group2": group_labels[1],
                        "p_value": float(p_val),
                        "mean_diff": m0 - m1,
                    }
                ]
            )
            result["assumption_checks"] = {
                "decision": "welch_t",
                "reason": "k=2，两独立样本 Welch t 检验",
            }
            direction_by_group = _direction_by_welch_vs_rest()
        else:
            normal_flags = []
            for arr in groups:
                if arr.size >= 8:
                    _, p_norm = stats.normaltest(arr)
                    normal_flags.append(p_norm > 0.05)
                elif arr.size >= 3:
                    # 小样本不再默认“通过”，改用 Shapiro 保守判断
                    _, p_norm = stats.shapiro(arr)
                    normal_flags.append(p_norm > 0.05)
                else:
                    # 样本过小，按不满足正态处理，避免误入参数法
                    normal_flags.append(False)
            if len(groups) >= 2 and all(len(arr) >= 2 for arr in groups):
                _, levene_p = stats.levene(*groups)
            else:
                levene_p = 1.0
            if all(normal_flags) and levene_p > 0.05:
                f_val, p_val = f_oneway(*groups)
                overall_test = "ANOVA"
                overall_stat = f_val
                overall_p = p_val
                overall_es = calculate_eta_squared_anova(groups)
                result["assumption_checks"] = {
                    "normality_ok": True,
                    "levene_p": float(levene_p),
                    "decision": "ANOVA",
                    "reason": "正态性与方差齐性均满足",
                }
            else:
                h_val, p_val = kruskal(*groups)
                overall_test = "Kruskal-Wallis"
                overall_stat = h_val
                overall_p = p_val
                n_total = sum(len(arr) for arr in groups)
                overall_es = calculate_eta_squared_kruskal(
                    h_val, len(groups), n_total
                )
                result["assumption_checks"] = {
                    "normality_ok": bool(all(normal_flags)),
                    "levene_p": float(levene_p),
                    "decision": "Kruskal-Wallis",
                    "reason": "未满足正态性或方差齐性，改用非参数检验",
                }
            result["overall"] = {
                "test": overall_test,
                "stat": float(overall_stat),
                "p_value": float(overall_p),
                "effect_size": float(overall_es)
                if not np.isnan(overall_es)
                else np.nan,
            }
            pair_records = []
            if overall_p < alpha:
                if overall_test == "ANOVA":
                    try:
                        tukey = pairwise_tukeyhsd(
                            endog=data[value_col].values,
                            groups=data[group_col].values,
                            alpha=alpha,
                        )
                        tukey_df = pd.DataFrame(
                            tukey._results_table.data[1:],
                            columns=[
                                "group1",
                                "group2",
                                "mean_diff",
                                "p_value",
                                "lower",
                                "upper",
                                "reject",
                            ],
                        )
                        for _, row in tukey_df.iterrows():
                            pair_records.append(
                                {
                                    "group1": row["group1"],
                                    "group2": row["group2"],
                                    "p_value": float(row["p_value"]),
                                    "mean_diff": float(row["mean_diff"]),
                                }
                            )
                    except Exception:
                        pass
                else:
                    try:
                        dunn_res = posthoc_dunn(
                            data,
                            val_col=value_col,
                            group_col=group_col,
                            p_adjust="fdr_bh",
                        )
                        dunn_stack = dunn_res.stack().reset_index()
                        dunn_stack.columns = ["group1", "group2", "p_value"]
                        for _, row in dunn_stack.iterrows():
                            if row["group1"] == row["group2"]:
                                continue
                            pair_records.append(
                                {
                                    "group1": row["group1"],
                                    "group2": row["group2"],
                                    "p_value": float(row["p_value"]),
                                }
                            )
                    except Exception:
                        pass
            if pair_records:
                result["pairwise"] = pd.DataFrame(pair_records)
            direction_by_group = _direction_by_welch_vs_rest()

        ov_p = result["overall"].get("p_value", np.nan)
        result["pipeline_summary"] = {
            "p_value": float(ov_p) if pd.notna(ov_p) else np.nan,
            "is_significant": bool(pd.notna(ov_p) and ov_p < alpha),
            "alpha": alpha,
            "direction_by_group": direction_by_group,
            "cells": [],
        }
        return result
    result["overall"] = {
        "test": None,
        "stat": np.nan,
        "p_value": np.nan,
        "effect_size": np.nan,
    }
    result["pipeline_summary"] = {
        "p_value": np.nan,
        "is_significant": False,
        "alpha": alpha,
        "direction_by_group": {},
        "cells": [],
    }
    return result


def process_ranking_data(
    df, label_col, rank_cols, weights=None, top_n=(1, 2)
):
    """处理排序题数据，计算加权得分、Top-N 率并生成需求分类结论。

    按排名位置计算默认权重（第 1 位权重最高），统计各分组内各选项的平均得分
    和 Top1/Top2 率，并调用 classify_ranking_demand 对选项进行分类。

    Args:
        df: pd.DataFrame，原始问卷数据，行为受访者。
        label_col: str，分组列名（如「用户分类」）。
        rank_cols: list[str]，排名列列表，按排名顺序排列（第 1 列为第 1 名）。
        weights: dict or None，列名→权重映射；为 None 时按位置降序自动生成。
        top_n: tuple，需要计算 Top-N 率的 N 值集合（默认 (1, 2)）。

    Returns:
        dict，含以下键：
          - "long_df": pd.DataFrame，长格式数据（label/option/score/is_topN）。
          - "avg_score": pd.DataFrame，各分组×选项的平均加权得分。
          - "top1_rate": pd.DataFrame or None，Top1 率（百分比）。
          - "top2_rate": pd.DataFrame or None，Top2 率（百分比）。
          - "summary": pd.DataFrame，汇总表，含需求分类结论列。
    """
    if weights is None:
        weights = {rank_cols[i]: len(rank_cols) - i for i in range(len(rank_cols))}
    records = []
    for _, row in df.iterrows():
        label = row[label_col]
        for col in rank_cols:
            option = row[col]
            if pd.isna(option):
                continue
            score = weights.get(col, 0)
            rec = {
                "label": label,
                "option": option,
                "score": score,
            }
            if 1 in top_n:
                rec["is_top1"] = 1 if col == rank_cols[0] else 0
            if 2 in top_n:
                rec["is_top2"] = 1 if col in rank_cols[:2] else 0
            records.append(rec)
    long_df = pd.DataFrame(records)
    long_df = long_df.dropna(subset=["option"])
    if long_df.empty:
        return {
            "long_df": long_df,
            "avg_score": pd.DataFrame(),
            "top1_rate": pd.DataFrame(),
            "top2_rate": pd.DataFrame(),
            "summary": pd.DataFrame(),
        }
    # H2: 分母应为「每组真实受访者数」，而非长格式行数（每人贡献 len(rank_cols) 行）
    respondent_counts = df.groupby(label_col).size()
    avg_score = (
        long_df.groupby(["label", "option"])["score"].mean().unstack(fill_value=0)
    )
    top1_rate = None
    top2_rate = None
    if 1 in top_n:
        top1 = long_df[long_df.get("is_top1", 0) == 1]
        top1_rate = (
            top1.groupby(["label", "option"]).size().unstack(fill_value=0).div(
                respondent_counts, axis=0
            )
            * 100
        )
    if 2 in top_n:
        top2 = long_df[long_df.get("is_top2", 0) == 1]
        top2_rate = (
            top2.groupby(["label", "option"]).size().unstack(fill_value=0).div(
                respondent_counts, axis=0
            )
            * 100
        )
    summary_records = []
    if not avg_score.empty:
        for label in avg_score.index:
            for option in avg_score.columns:
                s = float(avg_score.loc[label, option])
                if top1_rate is not None and not top1_rate.empty:
                    r1 = float(top1_rate.loc[label, option]) if (
                        label in top1_rate.index and option in top1_rate.columns
                    ) else 0.0
                else:
                    r1 = 0.0
                if top2_rate is not None and not top2_rate.empty:
                    r2 = float(top2_rate.loc[label, option]) if (
                        label in top2_rate.index and option in top2_rate.columns
                    ) else 0.0
                else:
                    r2 = 0.0
                cat = classify_ranking_demand(s, r1, r2)
                summary_records.append(
                    {
                        "用户分组": label,
                        "选项": option,
                        "加权得分": s,
                        "Top1率": r1,
                        "Top2率": r2,
                        "需求分类结论": cat,
                    }
                )
    summary_df = pd.DataFrame(summary_records)
    return {
        "long_df": long_df,
        "avg_score": avg_score,
        "top1_rate": top1_rate,
        "top2_rate": top2_rate,
        "summary": summary_df,
    }


def classify_ranking_demand(avg_score, top1_rate, top2_rate):
    """根据加权得分和 Top-N 率将排序题选项分类为需求类型。

    分类逻辑：众望所归型 / 小众狂热型 / 安全备胎型 / 两极分化型 / 表现平平/待定。
    阈值为经验值，可在后续版本通过配置参数暴露。

    Args:
        avg_score: float，选项的平均加权得分。
        top1_rate: float，选项被排为第 1 名的比例（百分比，0~100）。
        top2_rate: float，选项被排在前 2 名的比例（百分比，0~100）。

    Returns:
        str，需求分类标签，如 "众望所归型"、"安全备胎型" 等。
    """
    s = float(avg_score) if avg_score is not None else 0.0
    r1 = float(top1_rate) if top1_rate is not None else 0.0
    r2 = float(top2_rate) if top2_rate is not None else 0.0
    if r1 > 30 and r2 > 55 and s > 3.5:
        return "众望所归型"
    if r1 > 30 and r2 <= 55:
        return "小众狂热型"
    if r1 <= 30 and r2 > 55 and s > 3.0:
        return "安全备胎型"
    if r1 > 25 and s <= 3.0:
        return "两极分化型"
    return "表现平平/待定"


def run_within_group_multi_choice(df, option_cols, min_total=10):
    """对多选题各选项做组内两两 McNemar 检验，分析配对差异。

    将各列转为 0/1 二进制编码，对所有选项对做 McNemar 检验，
    计算 Cohen's g 效应量，适用于同一批受访者在不同选项间的选择差异分析。

    Args:
        df: pd.DataFrame，问卷数据，行为受访者。
        option_cols: list[str]，多选题各选项的列名列表（0/1 编码）。
        min_total: int，最小样本量要求；低于此值直接返回空 DataFrame（默认 10）。

    Returns:
        pd.DataFrame，列为 option1/option2/p_value/effect_size_g；
        行为所有选项对的检验结果。
    """
    bin_df = df[option_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    bin_df = (bin_df > 0).astype(int)
    total_n = len(bin_df)
    if total_n < min_total or len(option_cols) < 2:
        return pd.DataFrame(
            columns=["option1", "option2", "p_value", "effect_size_g"]
        )
    records = []
    for a, b in combinations(option_cols, 2):
        a1b1 = int(((bin_df[a] == 1) & (bin_df[b] == 1)).sum())
        a1b0 = int(((bin_df[a] == 1) & (bin_df[b] == 0)).sum())
        a0b1 = int(((bin_df[a] == 0) & (bin_df[b] == 1)).sum())
        a0b0 = int(((bin_df[a] == 0) & (bin_df[b] == 0)).sum())
        table = np.array([[a1b1, a1b0], [a0b1, a0b0]])
        off_sum = a1b0 + a0b1
        if off_sum == 0:
            p_val = np.nan
            g = 0.0
        else:
            try:
                res = mcnemar(table, exact=False, correction=True)
                p_val = float(res.pvalue)
            except Exception:
                p_val = np.nan
            g = abs(a1b0 - a0b1) / off_sum
        records.append(
            {
                "option1": a,
                "option2": b,
                "p_value": p_val,
                "effect_size_g": g,
            }
        )
    return pd.DataFrame(records)


def calculate_cohens_d_paired(group1_data, group2_data):
    """计算配对样本的 Cohen's d 效应量（基于差值标准差）。

    Args:
        group1_data: array-like，第一组观测值，与 group2_data 一一对应。
        group2_data: array-like，第二组观测值，长度须与 group1_data 相同。

    Returns:
        float，Cohen's d 值；形状不匹配或样本量不足时返回 np.nan。
    """
    data1 = np.asarray(group1_data)
    data2 = np.asarray(group2_data)
    if data1.shape != data2.shape or data1.size <= 1:
        return np.nan
    diff = data1 - data2
    std_diff = np.std(diff, ddof=1)
    if std_diff == 0:
        return np.nan
    d = np.mean(diff) / std_diff
    return d


def run_within_group_matrix_rating(df, value_cols, min_pairs=5):
    """对矩阵评分题各子题做组内 Friedman 检验及两两 Wilcoxon 事后比较。

    适用于同一批受访者对多个维度/子题同时打分的分析场景，
    Friedman 检验结果显著时再做逐对 Wilcoxon 符号秩检验。

    Args:
        df: pd.DataFrame，问卷数据，行为受访者。
        value_cols: list[str]，矩阵评分各子题的列名列表（数值型）。
        min_pairs: int，两两比较中所需的最小有效配对数（默认 5）。

    Returns:
        dict，含以下键：
          - "overall": dict，Friedman 检验结果（test/stat/p_value）。
          - "pairwise": pd.DataFrame，两两 Wilcoxon 结果（item1/item2/p_value/effect_size_d）。
    """
    if len(value_cols) < 2:
        return {
            "overall": {
                "test": None,
                "stat": np.nan,
                "p_value": np.nan,
            },
            "pairwise": pd.DataFrame(
                columns=["item1", "item2", "p_value", "effect_size_d"]
            ),
        }
    sub = df[value_cols].apply(pd.to_numeric, errors="coerce")
    sub = sub.dropna()
    if sub.empty:
        return {
            "overall": {
                "test": None,
                "stat": np.nan,
                "p_value": np.nan,
            },
            "pairwise": pd.DataFrame(
                columns=["item1", "item2", "p_value", "effect_size_d"]
            ),
        }
    arrays = [sub[c].values for c in value_cols]
    try:
        friedman_stat, friedman_p = stats.friedmanchisquare(*arrays)
    except Exception:
        friedman_stat, friedman_p = np.nan, np.nan
    overall = {
        "test": "Friedman",
        "stat": float(friedman_stat) if not np.isnan(friedman_stat) else np.nan,
        "p_value": float(friedman_p) if not np.isnan(friedman_p) else np.nan,
    }
    records = []
    for a, b in combinations(value_cols, 2):
        pair = sub[[a, b]].dropna()
        if len(pair) < min_pairs:
            p_val = np.nan
            d = np.nan
        else:
            try:
                _, p_val = stats.wilcoxon(pair[a], pair[b])
                p_val = float(p_val)
            except Exception:
                p_val = np.nan
            d = calculate_cohens_d_paired(pair[a].values, pair[b].values)
        records.append(
            {
                "item1": a,
                "item2": b,
                "p_value": p_val,
                "effect_size_d": d,
            }
        )
    pairwise_df = pd.DataFrame(records)
    return {"overall": overall, "pairwise": pairwise_df}


def calculate_rank_biserial_correlation(group1_data, group2_data):
    """计算两组独立样本的秩双列相关系数（Mann-Whitney U 的效应量）。

    基于 Mann-Whitney U 统计量推导，取值范围 [-1, 1]，
    正值表示 group1 整体大于 group2。

    Args:
        group1_data: array-like，第一组数值数据（含 NaN 时自动去除）。
        group2_data: array-like，第二组数值数据（含 NaN 时自动去除）。

    Returns:
        float，秩双列相关系数；任一组为空时返回 np.nan。
    """
    x = np.asarray(group1_data)
    y = np.asarray(group2_data)
    x = x[~np.isnan(x)]
    y = y[~np.isnan(y)]
    n1 = len(x)
    n2 = len(y)
    if n1 == 0 or n2 == 0:
        return np.nan
    try:
        u_stat, _ = stats.mannwhitneyu(x, y, alternative="two-sided", method="auto")
    except TypeError:
        u_stat, _ = stats.mannwhitneyu(x, y, alternative="two-sided")
    rb = 1 - (2 * u_stat) / (n1 * n2)
    rb = max(-1.0, min(1.0, rb))
    return rb


def calculate_paired_rank_biserial_correlation(data1, data2):
    """计算配对样本的秩双列相关系数（Wilcoxon 符号秩检验的效应量）。

    基于正秩和与负秩和之差推导，取值范围 [-1, 1]。

    Args:
        data1: array-like，第一组配对观测值。
        data2: array-like，第二组配对观测值，须与 data1 等长。

    Returns:
        float，配对秩双列相关系数；差值全为 0 或形状不匹配时返回 np.nan。
    """
    a = np.asarray(data1)
    b = np.asarray(data2)
    if a.shape != b.shape or a.size == 0:
        return np.nan
    diff = a - b
    diff_nonzero = diff[diff != 0]
    if diff_nonzero.size == 0:
        return np.nan
    ranks = stats.rankdata(abs(diff_nonzero))
    w_pos = float(ranks[diff_nonzero > 0].sum())
    w_neg = float(ranks[diff_nonzero < 0].sum())
    if w_pos + w_neg == 0:
        return np.nan
    return (w_pos - w_neg) / (w_pos + w_neg)


def calculate_cohens_g_mcnemar(contingency_table_2x2):
    """计算 McNemar 检验的 Cohen's g 效应量。

    Cohen's g = |b - c| / (b + c)，其中 b、c 为 2×2 配对列联表的
    非对角元素，取值范围 [0, 1]。

    Args:
        contingency_table_2x2: pd.DataFrame or array-like，2×2 配对列联表。

    Returns:
        float，Cohen's g 值（0~1）；格式不符或 b+c=0 时返回 0.0 或 np.nan。
    """
    try:
        if isinstance(contingency_table_2x2, pd.DataFrame):
            table_arr = contingency_table_2x2.values
        else:
            table_arr = np.asarray(contingency_table_2x2)
        if table_arr.shape != (2, 2):
            return np.nan
        b = float(table_arr[0, 1])
        c = float(table_arr[1, 0])
        if b + c == 0:
            return 0.0
        g = abs(b - c) / (b + c)
        return g
    except Exception:
        return np.nan


def calculate_cohens_d(group1_data, group2_data):
    """计算两组独立样本的 Cohen's d 效应量（合并标准差方法）。

    Args:
        group1_data: array-like，第一组数值数据。
        group2_data: array-like，第二组数值数据。

    Returns:
        float，Cohen's d 值；任一组样本量 ≤1 或合并标准差为 0 时返回 np.nan。
    """
    data1 = np.asarray(group1_data)
    data2 = np.asarray(group2_data)
    n1 = len(data1)
    n2 = len(data2)
    if n1 <= 1 or n2 <= 1:
        return np.nan
    mean1 = np.mean(data1)
    mean2 = np.mean(data2)
    var1 = np.var(data1, ddof=1)
    var2 = np.var(data2, ddof=1)
    if (n1 + n2 - 2) <= 0:
        return np.nan
    pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled_std == 0:
        return np.nan
    d = (mean1 - mean2) / pooled_std
    return d


def advanced_split(col_name):
    """将问卷列名分割为题干部分和选项部分。

    优先在问号之后寻找冒号作为分隔点（兼容"题干？：选项"格式），
    其次使用最后一个冒号作为分隔。

    Args:
        col_name: str，问卷列名，如 "Q1. 您喜欢哪种游戏类型：RPG"。

    Returns:
        tuple[str, str]，(题干部分, 选项部分)；无法分割时返回 (原始列名, "")。
    """
    if not isinstance(col_name, str):
        col_name = str(col_name)
    original = col_name
    normalized = original.replace("：", ":")
    q_mark_pos = -1
    try:
        q_mark_pos = normalized.index("?")
    except ValueError:
        try:
            q_mark_pos = normalized.index("？")
        except ValueError:
            q_mark_pos = -1
    if q_mark_pos != -1:
        try:
            colon_pos = normalized.index(":", q_mark_pos + 1)
            stem_part = normalized[:colon_pos]
            option_part = normalized[colon_pos + 1 :]
            return stem_part, option_part
        except ValueError:
            pass
    if ":" in normalized:
        stem_part, option_part = normalized.rsplit(":", 1)
        return stem_part, option_part
    return normalized, ""


def extract_qnum(col_name):
    """从列名中提取题目序号（如 "Q3" → "3"）。

    匹配顺序：Q 前缀格式（Q3.xxx）→ 数字加标点格式（3、xxx）→ 关键词格式（问题 3）。
    括号内内容会被预处理清除，以避免干扰匹配。

    Args:
        col_name: str，问卷列名，如 "Q3. 您的年龄" 或 "3、性别"。

    Returns:
        str or None，题目序号字符串（如 "3"）；未匹配时返回 None。
    """
    col_str = str(col_name).strip()
    m = re.match(r"^\s*Q(\d+)(?:[.\s_\-]|$)", col_str)
    if m:
        return m.group(1)
    # 兼容问卷星多选子列：`31(选项...)` / `31（选项...）`
    m = re.match(r"^\s*(\d+)\s*[（(]", col_str)
    if m:
        return m.group(1)
    col_tmp = re.sub(r"（.*?）", "", col_str)
    col_tmp = re.sub(r"\(.*?\)", "", col_tmp)
    patterns = [
        # 问卷星常见：`31.` / `31、` / `31)` / `31(` / `31（`
        r"^(\d+)\s*[、.)（(]",
        r"\bQ?(\d+)[\s_\-]",
        r"(?:问题|题目|Question)\s*(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, col_tmp)
        if m and m.group(1):
            return m.group(1)
    return None


def extract_option(col_name, question_num):
    """从列名中提取选项文本（冒号之后的部分）。

    Args:
        col_name: str，问卷列名，如 "Q3. 您最常玩的游戏类型：RPG"。
        question_num: str or int，题目序号（当前仅用于调用 advanced_split，实际不影响结果）。

    Returns:
        str，选项文本；无冒号时返回空字符串。
    """
    col_str = str(col_name).strip()
    _, option_part = advanced_split(col_str)
    return option_part.strip()


def get_question_stem(original_df, question_number):
    """从 DataFrame 列名中提取指定题号的最完整题干文本。

    优先匹配 "Q{num}." 前缀，其次使用正则匹配数字标点或关键词格式，
    返回所有匹配列中题干部分最长的一个。

    Args:
        original_df: pd.DataFrame，原始问卷 DataFrame，行为受访者，列为题目。
        question_number: str or int，题目序号，如 3 或 "3"。

    Returns:
        str，题干文本，格式为 "Q{num}.{题干}"；未匹配时返回 "Q{num}. 问题（未匹配到题干）"。
    """
    q_num_str = str(question_number)
    cols = [
        c
        for c in original_df.columns
        if str(c).strip().startswith(f"Q{q_num_str}.")
    ]
    if not cols:
        pattern = re.compile(
            rf"^({re.escape(q_num_str)}[、.])|(Q{re.escape(q_num_str)}\b)|(问题{re.escape(q_num_str)})"
        )
        cols = [c for c in original_df.columns if pattern.search(str(c))]
        if cols:
            return max(cols, key=len)
        return f"Q{q_num_str}. 问题（未匹配到题干）"
    longest = ""
    for c in cols:
        stem_part, _ = advanced_split(str(c))
        current = stem_part.replace(f"Q{q_num_str}.", "", 1).strip()
        if len(current) > len(longest):
            longest = current
    if longest:
        return f"Q{q_num_str}.{longest}"
    return f"Q{q_num_str}. 问题（未匹配到题干）"


def clean_question_stem(question_stem):
    """清理题干文本，去除题号前缀、括号注释和多余标点。

    Args:
        question_stem: str，原始题干，如 "Q3.您最常玩的游戏类型（必填）："。

    Returns:
        str，清理后的纯题目文字，如 "您最常玩的游戏类型"。
    """
    s = str(question_stem)
    s = re.sub(r"^Q\d+\.", "", s).strip()
    s = re.sub(r"^\d+[、.]", "", s).strip()
    s = re.sub(r"\[.*?\]", "", s)
    s = re.sub(r"（.*?）", "", s)
    s = s.replace("：", "").strip()
    return s


def make_safe_sheet_name(name, fallback_prefix="Q", index=1):
    """将任意字符串转换为合法的 Excel 工作表名称（最长 31 字符）。

    去除 Excel 不允许的特殊字符（\\/*?:[]'），并自动截断超长名称。

    Args:
        name: str，原始名称，如题干或列名。
        fallback_prefix: str，名称为空时的回退前缀（默认 "Q"）。
        index: int，名称为空时追加的序号（默认 1）。

    Returns:
        str，合法的工作表名称（1~31 字符）。
    """
    if not isinstance(name, str):
        name = str(name)
    s = name.replace("：", ":").strip()
    if not s:
        s = f"{fallback_prefix}{index}"
    invalid_chars = r"[\\/*?:\[\]']"
    s = re.sub(invalid_chars, "-", s)
    s = s.strip("'")
    if len(s) > 31:
        s = s[:31].strip()
    if not s:
        s = f"{fallback_prefix}{index}"
    return s


def run_question_analysis(
    df,
    question_type,
    mode,
    group_col=None,
    value_col=None,
    value_cols=None,
    label_col=None,
    rank_cols=None,
    min_group_size=3,
):
    """统一入口：根据题型和分析模式分发到具体分析函数。

    整合描述统计、分组差异（between）、组内比较（within）、排序题分析四种模式，
    供 Streamlit 层和 CLI 层统一调用，减少调用方对具体函数的感知。

    Args:
        df: pd.DataFrame，问卷数据，行为受访者。
        question_type: str，题型，如 "单选"/"评分"/"多选"/"矩阵评分"/"排序"。
        mode: str，分析模式，支持 "describe" / "between" / "within" / "ranking"。
        group_col: str or None，分组列名（between 模式必填）。
        value_col: str or None，单列题目列名（单选/评分题使用）。
        value_cols: list[str] or None，多列题目列名（多选/矩阵题使用）。
        label_col: str or None，排序题的分组标签列名（ranking 模式使用）。
        rank_cols: list[str] or None，排名列列表（ranking 模式使用）。
        min_group_size: int，between 模式中最小组样本量（默认 3）。

    Returns:
        dict，分析结果；格式取决于 mode 和 question_type，空结果返回 {}。
    """
    if mode == "describe" and question_type in ("评分", "NPS") and value_col is not None:
        return {"describe": calculate_rating_metrics(df, value_col, group_col)}
    if mode == "between":
        if question_type == "多选" and group_col is not None and (value_cols is not None or value_col is not None):
            col_arg = value_cols if (value_cols is not None and len(value_cols) > 0) else ([value_col] if value_col is not None else None)
            if col_arg is not None:
                return run_group_difference_test(df, group_col, col_arg, question_type, min_group_size)
        if question_type in ("单选", "评分", "NPS") and value_col is not None and group_col is not None:
            qt = "评分" if question_type == "NPS" else question_type
            return run_group_difference_test(df, group_col, value_col, qt, min_group_size)
        return {"overall": None, "pairwise": None}
    if mode == "within":
        if question_type in ("多选", "矩阵单选") and value_cols:
            df_res = run_within_group_multi_choice(df, value_cols)
            return {"pairwise": df_res}
        if question_type == "矩阵评分" and value_cols:
            return run_within_group_matrix_rating(df, value_cols)
        return {"pairwise": None}
    if mode == "ranking" and question_type == "排序" and label_col and rank_cols:
        return process_ranking_data(df, label_col, rank_cols)
    return {}


from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class QuestionSpec:
    q_type: str  # '单选'|'多选'|'评分'|'NPS'|'矩阵单选'|'矩阵评分'
    q_num: int
    option_order: Optional[List[str]] = None


def _v13_cols_for_qnum(
    df: pd.DataFrame,
    q_num_str: str,
    *,
    want_colon: Optional[bool] = None,
) -> List[str]:
    cols: List[str] = []
    for c in df.columns:
        s = str(c)
        if extract_qnum(s) != q_num_str:
            continue
        if want_colon is True and ":" not in s and "：" not in s:
            continue
        if want_colon is False and (":" in s or "：" in s):
            continue
        cols.append(c)
    return cols


def _v13_new_format_cols(
    df: pd.DataFrame, q_num_str: str, *, want_colon: Optional[bool] = None
) -> List[str]:
    cols: List[str] = []
    for c in df.columns:
        s = str(c)
        if not s.startswith(f"Q{q_num_str}."):
            continue
        if want_colon is True and ":" not in s and "：" not in s:
            continue
        if want_colon is False and (":" in s or "：" in s):
            continue
        cols.append(c)
    return cols


def build_question_specs(
    original_df: pd.DataFrame,
    question_types: dict,
) -> List[QuestionSpec]:
    """构建定量交叉引擎题目规格（单入口版本）。"""
    from survey_tools.core.question_type import get_option_label

    specs: List[QuestionSpec] = []
    for q_type, q_nums in (question_types or {}).items():
        if q_type not in ("单选", "多选", "评分", "NPS", "矩阵单选", "矩阵评分"):
            continue
        for q_num in q_nums:
            q_num_str = str(q_num)
            option_order: Optional[List[str]] = None
            if q_type == "多选":
                cols = _v13_new_format_cols(original_df, q_num_str, want_colon=True)
                if not cols:
                    cols = _v13_cols_for_qnum(original_df, q_num_str, want_colon=None)
                if cols:
                    labels = [get_option_label(c) for c in cols]
                    labels = [lbl for lbl in labels if str(lbl).strip()]
                    option_order = list(dict.fromkeys(labels))
            elif q_type in ("矩阵单选", "矩阵评分"):
                cols = _v13_new_format_cols(original_df, q_num_str, want_colon=True)
                if cols:
                    seen_labels: set = set()
                    option_order = []
                    for _c in cols:
                        _lbl = get_option_label(_c)
                        if _lbl not in seen_labels:
                            seen_labels.add(_lbl)
                            option_order.append(_lbl)
            specs.append(
                QuestionSpec(q_type=q_type, q_num=int(q_num), option_order=option_order)
            )
    return specs


def normalize_cross_segment_label(value) -> str:
    """统一交叉长表「核心分组」取值，避免 pivot 列名为 int 而统计 dict 键为 str 时导出错位。

    典型场景：分组列为 1/2/3 次对局时，pandas 透视列名为 int，而 str(grp) 为 '1'/'2'/'3'。
    """
    if pd.isna(value):
        return ""
    if isinstance(value, (bool, np.bool_)):
        return str(value)
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, float):
        if not np.isfinite(value):
            return str(value)
        if value == int(value):
            return str(int(value))
        return str(value)
    return str(value).strip()


def apply_column_type_labels_to_cross_results(
    results: List[dict],
    column_type_map: Optional[Dict[str, str]],
) -> List[dict]:
    """导出前用当前「列名→题型」映射覆盖 ``res['题型']``，与题型微调一致。

    对每条结果做浅拷贝后再改 ``题型``，避免污染 ``session_state.analysis_results``。
    仅当映射值与当前 ``题型`` 均为「单选 / 评分 / NPS」之一时才覆盖，避免把矩阵题等误标成单选。
    """
    if not results or not column_type_map:
        return list(results) if results else []
    interchangeable = frozenset({"单选", "评分", "NPS"})
    out: List[dict] = []
    for res in results:
        q = res.get("题目")
        if q is None:
            out.append(res)
            continue
        mapped = column_type_map.get(str(q))
        if mapped is None or mapped not in interchangeable:
            out.append(res)
            continue
        cur = res.get("题型", "")
        if str(cur) not in interchangeable:
            out.append(res)
            continue
        if mapped == cur:
            out.append(res)
            continue
        out.append({**res, "题型": mapped})
    return out


def run_quant_cross_engine(
    df: pd.DataFrame,
    *,
    core_segment_col: str,
    question_specs: Sequence[QuestionSpec],
    selected_cols_set: Optional[Iterable[str]] = None,
    ignored_cols_set: Optional[Iterable[str]] = None,
    explicit_single_cols: Optional[Sequence[str]] = None,
    explicit_rating_cols: Optional[Sequence[str]] = None,
    explicit_nps_cols: Optional[Sequence[str]] = None,
    alpha: float = 0.05,
    min_group_size: int = 5,
) -> List[dict]:
    """统一定量交叉引擎（兼容原 run_v13_like_cross 返回结构）。"""
    from survey_tools.core.question_type import count_mentions, get_option_label, get_prefix

    selected = set(selected_cols_set or df.columns.tolist())
    ignored = set(ignored_cols_set or [])

    def ok_col(c: str) -> bool:
        return (c in selected) and (c not in ignored)

    def analyze_single_choice(df_in: pd.DataFrame, group_col: str, q_col: str) -> pd.DataFrame:
        records = []
        grouped = df_in.groupby(group_col, dropna=True)
        for seg_value, group in grouped:
            total = int(group[q_col].notna().sum())
            if total == 0:
                continue
            vc = group[q_col].value_counts(dropna=True)
            for option, count in vc.items():
                if pd.isna(option):
                    continue
                ratio = count / total if total > 0 else 0
                records.append(
                    {
                        "题目": q_col,
                        "核心分组": normalize_cross_segment_label(seg_value),
                        "选项": str(option),
                        "频次": int(count),
                        "行百分比": float(ratio),
                        "组样本数": int(total),
                    }
                )
        if not records:
            return pd.DataFrame(columns=["题目", "核心分组", "选项", "频次", "行百分比", "组样本数"])
        return pd.DataFrame(records)

    def analyze_multi_choice(
        df_in: pd.DataFrame, group_col: str, prefix: str, option_cols: Sequence[str]
    ) -> pd.DataFrame:
        records = []
        grouped = df_in.groupby(group_col, dropna=True)
        for seg_value, group in grouped:
            subset = group[list(option_cols)]
            valid_n = len(subset.dropna(how="all"))
            total = valid_n
            if total == 0:
                continue
            for col in option_cols:
                option_label = get_option_label(col)
                # 跳过“____)”这类填空附属残片列，避免污染多选选项文本与统计结果
                if not str(option_label).strip():
                    continue
                mentions = count_mentions(group[col])
                ratio = mentions / total if total > 0 else 0
                records.append(
                    {
                        "题目": prefix,
                        "核心分组": normalize_cross_segment_label(seg_value),
                        "选项": option_label,
                        "提及人数": int(mentions),
                        "提及率": float(ratio),
                        "组样本数": int(total),
                    }
                )
        if not records:
            return pd.DataFrame(columns=["题目", "核心分组", "选项", "提及人数", "提及率", "组样本数"])
        return pd.DataFrame(records)

    def _compute_stats(q_col_or_cols, q_type_for_test: str):
        try:
            return run_group_difference_test(
                df,
                core_segment_col,
                q_col_or_cols,
                q_type_for_test,
                min_group_size=min_group_size,
                alpha=alpha,
            )
        except Exception:
            return None

    results: List[dict] = []
    seen_single_like: set[str] = set()
    for col in (explicit_single_cols or []):
        if not ok_col(col):
            continue
        table = analyze_single_choice(df, core_segment_col, col)
        results.append({"题目": col, "题型": "单选", "数据": table, "stats": _compute_stats(col, "单选")})
        seen_single_like.add(str(col))

    for col in (explicit_rating_cols or []):
        if not ok_col(col):
            continue
        table = analyze_single_choice(df, core_segment_col, col)
        results.append({"题目": col, "题型": "评分", "数据": table, "stats": _compute_stats(col, "评分")})
        seen_single_like.add(str(col))

    for col in (explicit_nps_cols or []):
        if not ok_col(col):
            continue
        table = analyze_single_choice(df, core_segment_col, col)
        results.append({"题目": col, "题型": "NPS", "数据": table, "stats": _compute_stats(col, "评分")})
        seen_single_like.add(str(col))

    for spec in question_specs:
        q_num_str = str(spec.q_num)
        if spec.q_type in ("单选", "评分", "NPS"):
            cols = _v13_new_format_cols(df, q_num_str, want_colon=False)
            if not cols:
                cols = _v13_cols_for_qnum(df, q_num_str, want_colon=False)
            cols = [c for c in cols if ok_col(c)]
            if not cols:
                continue
            col = cols[0]
            if str(col) in seen_single_like:
                continue
            table = analyze_single_choice(df, core_segment_col, col)
            test_kind = "评分" if spec.q_type == "NPS" else spec.q_type
            out_type = "NPS" if spec.q_type == "NPS" else spec.q_type
            results.append(
                {"题目": col, "题型": out_type, "数据": table, "stats": _compute_stats(col, test_kind)}
            )
        elif spec.q_type == "多选":
            cols = _v13_new_format_cols(df, q_num_str, want_colon=True)
            if not cols:
                cols = _v13_cols_for_qnum(df, q_num_str, want_colon=None)
            cols = [c for c in cols if ok_col(c)]
            cols = [c for c in cols if str(get_option_label(c)).strip()]
            if not cols:
                continue
            prefix = get_prefix(cols[0])
            table = analyze_multi_choice(df, core_segment_col, prefix, cols)
            results.append(
                {
                    "题目": prefix,
                    "题型": "多选",
                    "数据": table,
                    "option_order": spec.option_order,
                    "stats": _compute_stats(list(cols), "多选"),
                }
            )
        elif spec.q_type in ("矩阵单选", "矩阵评分"):
            cols = _v13_new_format_cols(df, q_num_str, want_colon=True)
            if not cols:
                cols = _v13_cols_for_qnum(df, q_num_str, want_colon=True)
            cols = [c for c in cols if ok_col(c)]
            if not cols:
                continue
            for col in cols:
                table = analyze_single_choice(df, core_segment_col, col)
                test_q_type = "评分" if spec.q_type == "矩阵评分" else "单选"
                results.append({"题目": col, "题型": spec.q_type, "数据": table, "stats": _compute_stats(col, test_q_type)})
    return results
