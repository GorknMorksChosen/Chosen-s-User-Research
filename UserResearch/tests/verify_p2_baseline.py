import os
import runpy
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from survey_tools.core.advanced_modeling import GameExperienceAnalyzer as CoreAnalyzer
from game_analyst import GameExperienceAnalyzer as FlagAnalyzer


def pick_group_col(df, excluded_cols):
    for c in df.columns:
        if c in excluded_cols:
            continue
        ser = df[c]
        non_na = ser.notna().sum()
        uniq = ser.nunique(dropna=True)
        if non_na >= 10 and 2 <= uniq <= 50:
            return c
    return None


def verify_missing_strategy_matrix(files):
    ok_count = 0
    skip_count = 0
    for fp in files:
        df = pd.read_excel(fp)
        num = df.select_dtypes(include=[np.number]).columns.tolist()
        if len(num) < 4:
            converted = df.apply(pd.to_numeric, errors="coerce")
            num = [c for c in converted.columns if converted[c].notna().sum() >= 10]
            df = converted.combine_first(df)
        if len(num) < 4:
            skip_count += 1
            print(f"[SKIP] 缺失值策略矩阵跳过: {os.path.basename(fp)} (数值列不足)")
            continue
        target = num[0]
        features = num[1:4]
        group_col = pick_group_col(df, excluded_cols=[target] + features)
        if group_col is None:
            ranks = pd.to_numeric(df[target], errors="coerce").rank(method="first")
            df = df.copy()
            df["__auto_group__"] = pd.qcut(ranks, q=3, labels=["G1", "G2", "G3"]).astype(str)
            group_col = "__auto_group__"
        try:
            for analyzer_cls, tag in [(CoreAnalyzer, "core"), (FlagAnalyzer, "flag")]:
                analyzer = analyzer_cls(df.copy())
                for strategy in ["drop", "mean", "median", "group_mean", "group_median"]:
                    kwargs = {}
                    if strategy.startswith("group_"):
                        kwargs["missing_group_col"] = group_col
                    result = analyzer.regression_analysis(
                        features,
                        target,
                        missing_strategy=strategy,
                        **kwargs,
                    )
                    if int(result["sample_size"]) <= 0:
                        raise RuntimeError(f"{tag}:{strategy} 样本量异常: {fp}")
        except Exception as e:
            if "有效样本量较少" in str(e):
                skip_count += 1
                print(f"[SKIP] 缺失值策略矩阵跳过: {os.path.basename(fp)} ({e})")
                continue
            raise
        ok_count += 1
        print(f"[OK] 缺失值策略矩阵通过: {os.path.basename(fp)}")
    if ok_count == 0:
        raise RuntimeError("缺失值策略矩阵未命中任何可验证样本。")
    print(f"缺失值策略矩阵完成: ok={ok_count}, skip={skip_count}, total={len(files)}")


def verify_text_export(files):
    module = runpy.run_path(os.path.join(_PROJECT_ROOT, "问卷文本分析工具 v1.py"))
    build_export = module["build_export_workbook_bytes"]
    ok_count = 0
    for fp in files:
        xls = pd.ExcelFile(fp)
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])
        data = build_export(
            adf=df,
            deep_report_text="报告行1\n报告行2",
            ppt_text="PPT行1\nPPT行2",
            segment_reports={"A组": "A组报告", "B组": "B组报告"},
        )
        if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
            raise RuntimeError(f"导出字节为空: {fp}")
        ok_count += 1
        print(f"[OK] 文本导出构建通过: {os.path.basename(fp)}")
    print(f"文本导出构建完成: ok={ok_count}, total={len(files)}")


def main():
    example_dir = os.path.join(_PROJECT_ROOT, "example")
    test_assets_dir = os.path.join(_PROJECT_ROOT, "test_assets")
    files = []
    if os.path.isdir(example_dir):
        files = [
            os.path.join(example_dir, f)
            for f in os.listdir(example_dir)
            if f.lower().endswith(".xlsx")
        ]
    if not files and os.path.isdir(test_assets_dir):
        files = [
            os.path.join(test_assets_dir, f)
            for f in os.listdir(test_assets_dir)
            if f.lower().endswith(".xlsx")
        ]
    if not files:
        print("P2 baseline skipped: 未找到 example/ 或 test_assets/ 下的 .xlsx。")
        sys.exit(0)
    files = sorted(files)
    for fp in files:
        if not os.path.exists(fp):
            raise FileNotFoundError(fp)
    verify_missing_strategy_matrix(files)
    verify_text_export(files)
    print("P2 baseline verification passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"P2 baseline verification failed: {e}")
        sys.exit(1)
