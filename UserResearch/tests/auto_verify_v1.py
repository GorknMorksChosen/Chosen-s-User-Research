# -*- coding: utf-8 -*-
"""
auto_verify_v1.py — 核心统计与导出 schema 的自动化验收脚本

- 使用 test_assets 下脱敏小样本或内存 mock 数据，不依赖 input_example 的玩家数据。
- 调用 survey_tools.core 的统计函数，断言返回结果包含约定字段（p_value、effect_size、
  assumption_checks/decision 等）。断言失败时输出详细失败报告。
- 运行方式：在 UserResearch 目录下执行  python tests/auto_verify_v1.py
"""

from __future__ import annotations

import os
import sys

# 保证可导入 survey_tools（tests/ 上一级为 UserResearch）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import numpy as np


def _load_mock_or_test_assets():
    """优先加载 test_assets/mock_survey.csv；若无则生成内存 mock。
    mock 使用足够大的样本（n=120）并构造明显的组间差异，确保 p_value < 0.05 以覆盖 pairwise 分支。
    """
    path = os.path.join(_PROJECT_ROOT, "test_assets", "mock_survey.csv")
    if os.path.isfile(path):
        return pd.read_csv(path)
    np.random.seed(42)
    n = 120
    # 构造显著组间差异：G1 均值 3, G2 均值 5, G3 均值 7
    g1 = np.clip(np.random.randn(n // 3) * 0.5 + 3, 1, 7)
    g2 = np.clip(np.random.randn(n // 3) * 0.5 + 5, 1, 7)
    g3 = np.clip(np.random.randn(n // 3) * 0.5 + 7, 1, 7)
    score = np.concatenate([g1, g2, g3]).round(1)
    # 单选：G1 偏向选项 1，G2 偏向选项 2，G3 偏向选项 3（构造显著差异）
    s1 = np.random.choice([1, 2, 3], size=n // 3, p=[0.8, 0.1, 0.1])
    s2 = np.random.choice([1, 2, 3], size=n // 3, p=[0.1, 0.8, 0.1])
    s3 = np.random.choice([1, 2, 3], size=n // 3, p=[0.1, 0.1, 0.8])
    single_choice = np.concatenate([s1, s2, s3])
    # 排序列：模拟排序题（3个选项，填1/2/3表示排名）
    opts = ["选项A", "选项B", "选项C"]
    rank1 = [np.random.choice(opts) for _ in range(n)]
    remaining = [[x for x in opts if x != r] for r in rank1]
    rank2 = [np.random.choice(r) for r in remaining]
    remaining2 = [[x for x in opts if x != rank1[i] and x != rank2[i]] for i in range(n)]
    rank3 = [r[0] for r in remaining2]
    return pd.DataFrame({
        "group": np.repeat(["G1", "G2", "G3"], n // 3),
        "score": score,
        "single_choice": single_choice,
        "opt1": (np.random.rand(n) > 0.5).astype(int),
        "opt2": (np.random.rand(n) > 0.5).astype(int),
        "opt3": (np.random.rand(n) > 0.5).astype(int),
        "rank1": rank1,
        "rank2": rank2,
        "rank3": rank3,
    })


def run_verification():
    from survey_tools.core.quant import run_group_difference_test, run_question_analysis, process_ranking_data

    df = _load_mock_or_test_assets()
    failures = []

    # ---- 1) 评分 + 分组：p_value, effect_size, assumption_checks（正态/方差齐性→ANOVA/Kruskal）----
    try:
        res = run_group_difference_test(df, "group", "score", "评分", min_group_size=2)
        overall = res.get("overall")
        if overall is None:
            failures.append({"case": "评分-分组", "error": "overall 为 None"})
        else:
            for key in ("p_value", "effect_size", "test", "stat"):
                if key not in overall:
                    failures.append({"case": "评分-分组", "error": f"overall 缺少 {key}", "keys": list(overall.keys())})
            if "test" in overall and overall["test"] not in ("ANOVA", "Kruskal-Wallis", None):
                failures.append({"case": "评分-分组", "error": f"overall.test 应为 ANOVA/Kruskal-Wallis，实际: {overall['test']}"})
            if "effect_size" in overall and pd.notna(overall["effect_size"]) and not isinstance(overall["effect_size"], (int, float, np.floating)):
                failures.append({"case": "评分-分组", "error": "effect_size 应为数值类型", "type": str(type(overall["effect_size"]))})
        if "assumption_checks" not in res:
            failures.append({"case": "评分-分组", "error": "缺少 assumption_checks（正态/方差齐性→ANOVA/Kruskal 决策）"})
        else:
            ac = res["assumption_checks"]
            for key in ("decision", "normality_ok", "levene_p", "reason"):
                if key not in ac:
                    failures.append({"case": "评分-分组", "error": f"assumption_checks 缺少 {key}", "keys": list(ac.keys())})
            if ac.get("decision") not in ("ANOVA", "Kruskal-Wallis"):
                failures.append({"case": "评分-分组", "error": f"assumption_checks.decision 应为 ANOVA 或 Kruskal-Wallis，实际: {ac.get('decision')}"})
    except Exception as e:
        failures.append({"case": "评分-分组", "error": f"异常: {e}"})

    # ---- 2) 单选 + 分组：卡方/Fisher，p_value, effect_size（Cramer's V）, test ----
    try:
        res = run_group_difference_test(df, "group", "single_choice", "单选", min_group_size=2)
        overall = res.get("overall")
        if overall is None:
            failures.append({"case": "单选-分组", "error": "overall 为 None"})
        else:
            for key in ("p_value", "effect_size", "test", "stat"):
                if key not in overall:
                    failures.append({"case": "单选-分组", "error": f"overall 缺少 {key}", "keys": list(overall.keys())})
            if "test" in overall and overall["test"] not in ("chi-square", "fisher_exact", None):
                failures.append({"case": "单选-分组", "error": f"overall.test 应为 chi-square/fisher_exact，实际: {overall['test']}"})
    except Exception as e:
        failures.append({"case": "单选-分组", "error": f"异常: {e}"})

    # ---- 3) 多选 + 分组：overall.test=multi-option, p_value, effect_size, details 各选项 ----
    try:
        res = run_group_difference_test(df, "group", ["opt1", "opt2", "opt3"], "多选", min_group_size=2)
        overall = res.get("overall")
        if overall is None:
            failures.append({"case": "多选-分组", "error": "overall 为 None"})
        else:
            for key in ("p_value", "effect_size", "test"):
                if key not in overall:
                    failures.append({"case": "多选-分组", "error": f"overall 缺少 {key}", "keys": list(overall.keys())})
            if overall.get("test") != "multi-option":
                failures.append({"case": "多选-分组", "error": f"overall.test 应为 multi-option，实际: {overall.get('test')}"})
        if "details" in res and isinstance(res["details"], list) and len(res["details"]) > 0:
            d0 = res["details"][0]
            for key in ("option", "p_value", "effect_size", "test"):
                if key not in d0:
                    failures.append({"case": "多选-分组-details", "error": f"details[0] 缺少 {key}", "keys": list(d0.keys())})
    except Exception as e:
        failures.append({"case": "多选-分组", "error": f"异常: {e}"})

    # ---- 4) run_question_analysis mode=between 多选：支持 value_cols ----
    try:
        res = run_question_analysis(
            df, question_type="多选", mode="between",
            group_col="group", value_cols=["opt1", "opt2", "opt3"], min_group_size=2
        )
        if res.get("overall") is None and res.get("pairwise") is None:
            failures.append({"case": "run_question_analysis-多选-between", "error": "返回 overall/pairwise 均为 None，可能未支持 value_cols"})
        elif res.get("overall") is not None and res.get("overall", {}).get("test") != "multi-option":
            failures.append({"case": "run_question_analysis-多选-between", "error": "多选 between 应返回 test=multi-option 的 overall"})
    except Exception as e:
        failures.append({"case": "run_question_analysis-多选-between", "error": f"异常: {e}"})

    # ---- 5) run_question_analysis mode=describe 评分：返回 describe 表（映射：数据探索）----
    try:
        res = run_question_analysis(
            df, question_type="评分", mode="describe",
            value_col="score", group_col="group"
        )
        if "describe" not in res:
            failures.append({"case": "run_question_analysis-评分-describe", "error": "缺少 describe 键"})
        else:
            desc = res["describe"]
            if not isinstance(desc, pd.DataFrame):
                failures.append({"case": "run_question_analysis-评分-describe", "error": "describe 应为 DataFrame"})
            elif desc.empty and len(df) > 0:
                failures.append({"case": "run_question_analysis-评分-describe", "error": "describe 表不应为空（有数据时）"})
            else:
                for col in ("group", "mean", "n"):
                    if col not in desc.columns:
                        failures.append({"case": "run_question_analysis-评分-describe", "error": f"describe 缺少列 {col}", "cols": list(desc.columns)})
    except Exception as e:
        failures.append({"case": "run_question_analysis-评分-describe", "error": f"异常: {e}"})

    # ---- 6) 评分分组差异：pairwise 结构校验（不依赖 p < 0.05 才断言）----
    try:
        res = run_group_difference_test(df, "group", "score", "评分", min_group_size=2)
        overall = res.get("overall")
        # QA3: 移除 p < 0.05 保护，无条件检查 pairwise 结构（若存在）
        pw = res.get("pairwise")
        if pw is not None:
            if isinstance(pw, pd.DataFrame):
                for col in ("group1", "group2", "p_value"):
                    if col not in pw.columns:
                        failures.append({"case": "评分-pairwise", "error": f"pairwise 缺少列 {col}", "cols": list(pw.columns)})
            else:
                failures.append({"case": "评分-pairwise", "error": f"pairwise 应为 DataFrame，实际: {type(pw)}"})
        # 注：不在此处强制断言 p < 0.05，因为测试数据可能本身差异不显著
    except Exception as e:
        failures.append({"case": "评分-pairwise", "error": f"异常: {e}"})

    # ---- 7) 排序题：process_ranking_data 应返回 avg_score / top1_rate / summary ----
    try:
        rank_cols = [c for c in ("rank1", "rank2", "rank3") if c in df.columns]
        if not rank_cols:
            # 外部 CSV 没有排序列时，用内存数据补充
            np.random.seed(0)
            _n = len(df)
            opts = ["选项A", "选项B", "选项C"]
            _r1 = [np.random.choice(opts) for _ in range(_n)]
            _remaining = [[x for x in opts if x != r] for r in _r1]
            _r2 = [np.random.choice(r) for r in _remaining]
            _r3 = [[x for x in opts if x != _r1[i] and x != _r2[i]][0] for i in range(_n)]
            df = df.copy()
            df["rank1"], df["rank2"], df["rank3"] = _r1, _r2, _r3
            rank_cols = ["rank1", "rank2", "rank3"]
        if rank_cols:
            rr = process_ranking_data(df, "group", rank_cols)
            for key in ("long_df", "avg_score", "top1_rate", "summary"):
                if key not in rr:
                    failures.append({"case": "排序题", "error": f"process_ranking_data 缺少 '{key}' 键"})
            summary = rr.get("summary")
            if isinstance(summary, pd.DataFrame) and not summary.empty:
                for col in ("用户分组", "选项", "加权得分", "Top1率", "Top2率", "需求分类结论"):
                    if col not in summary.columns:
                        failures.append({"case": "排序题-summary", "error": f"summary 缺少列 '{col}'", "cols": list(summary.columns)})
                # Top1率不应超过 100%（H2 修复验证）
                max_top1 = summary["Top1率"].max() if "Top1率" in summary.columns else 0
                if max_top1 > 100:
                    failures.append({"case": "排序题-Top1率", "error": f"Top1率最大值 {max_top1:.1f}% > 100%，分母计算错误（H2 未修复）"})
    except Exception as e:
        failures.append({"case": "排序题", "error": f"异常: {e}"})

    return failures


def main():
    print("auto_verify_v1: 核心 schema 验收（mock / test_assets）")
    failures = run_verification()
    if not failures:
        print("全部断言通过。")
        return 0
    print("\n===== 失败报告 =====")
    for i, f in enumerate(failures, 1):
        print(f"{i}. [{f['case']}] {f['error']}")
        if "keys" in f:
            print(f"   实际 keys: {f['keys']}")
        if "cols" in f:
            print(f"   实际 cols: {f['cols']}")
        if "type" in f:
            print(f"   type: {f['type']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
