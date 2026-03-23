import json
import os
import runpy
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from survey_tools.core.advanced_modeling import GameExperienceAnalyzer
from survey_tools.core.clustering import (
    RECOMMENDATION_PROFILES,
    clean_data,
    evaluate_clustering_algorithms,
    perform_clustering,
    preprocess_features,
    recommend_clustering_algorithm,
    recommend_k_algorithm_combo,
)


def load_first_sheet(path: Path) -> pd.DataFrame:
    xls = pd.ExcelFile(path)
    return pd.read_excel(xls, sheet_name=xls.sheet_names[0])


def run_script_with_log(base_dir: Path, script: str, log_dir: Path) -> dict:
    cmd = [sys.executable, str(base_dir / script)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(base_dir))
    log_path = log_dir / f"{Path(script).stem}.log"
    merged = []
    merged.append(f"$ {' '.join(cmd)}")
    merged.append(f"exit_code={proc.returncode}")
    merged.append("")
    merged.append("=== STDOUT ===")
    merged.append(proc.stdout or "")
    merged.append("")
    merged.append("=== STDERR ===")
    merged.append(proc.stderr or "")
    log_path.write_text("\n".join(merged), encoding="utf-8")
    return {"script": script, "exit_code": proc.returncode, "log": str(log_path)}


def choose_regression_columns(df: pd.DataFrame) -> tuple[str, list]:
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    valid = [c for c in numeric_cols if pd.to_numeric(df[c], errors="coerce").notna().sum() >= 20]
    if len(valid) < 4:
        converted = df.apply(pd.to_numeric, errors="coerce")
        valid = [c for c in converted.columns if converted[c].notna().sum() >= 20]
    if len(valid) < 4:
        return None, []
    target = valid[0]
    features = valid[1:7]
    if len(features) < 3:
        return None, []
    return target, features


def choose_cluster_features(df: pd.DataFrame) -> list:
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    valid = [c for c in numeric_cols if pd.to_numeric(df[c], errors="coerce").notna().sum() >= 20]
    if len(valid) >= 3:
        return valid[:8]
    converted = df.apply(pd.to_numeric, errors="coerce")
    valid2 = [c for c in converted.columns if converted[c].notna().sum() >= 20]
    return valid2[:8]


def main():
    base_dir = _PROJECT_ROOT
    example_dir = base_dir / "example"
    if not example_dir.exists():
        raise FileNotFoundError(f"缺少样本目录: {example_dir}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = base_dir / "review_outputs" / ts
    log_dir = out_dir / "logs"
    text_dir = out_dir / "text_exports"
    cluster_dir = out_dir / "cluster_exports"
    reg_dir = out_dir / "regression_exports"
    summary_dir = out_dir / "summary"
    for d in [log_dir, text_dir, cluster_dir, reg_dir, summary_dir]:
        d.mkdir(parents=True, exist_ok=True)

    script_results = []
    for script in [
        "tests/verify_dependency_matrix.py",
        "tests/test_migration.py",
        "tests/verify_current_v1_logic.py",
        "tests/verify_p2_baseline.py",
        "tests/verify_p24_clustering.py",
        "tests/run_quality_matrix.py",
    ]:
        script_results.append(run_script_with_log(base_dir, script, log_dir))

    text_module = runpy.run_path(str(base_dir / "问卷文本分析工具 v1.py"))
    build_export = text_module["build_export_workbook_bytes"]

    file_summaries = []
    files = sorted([p for p in example_dir.iterdir() if p.suffix.lower() == ".xlsx"])
    if not files:
        raise FileNotFoundError("example 下未找到 xlsx 文件。")

    for fp in files:
        item = {
            "file": fp.name,
            "rows": 0,
            "cols": 0,
            "text_export": "skip",
            "cluster_export": "skip",
            "regression_export": "skip",
            "cluster_profile": "",
            "cluster_k": "",
            "cluster_algorithm": "",
        }
        try:
            df = load_first_sheet(fp)
            item["rows"] = int(df.shape[0])
            item["cols"] = int(df.shape[1])
        except Exception as e:
            item["error"] = f"读取失败: {e}"
            file_summaries.append(item)
            continue

        try:
            wb_bytes = build_export(
                adf=df,
                deep_report_text=f"{fp.name} 深度摘要",
                ppt_text=f"{fp.name} PPT摘要",
                segment_reports={"A组": "A组摘要", "B组": "B组摘要"},
            )
            (text_dir / f"{fp.stem}_text_export.xlsx").write_bytes(wb_bytes)
            item["text_export"] = "ok"
        except Exception as e:
            item["text_export"] = f"fail: {e}"

        try:
            cluster_features = choose_cluster_features(df)
            if len(cluster_features) >= 3:
                df_clean = clean_data(df, cluster_features, method="median")
                if len(df_clean) >= 20:
                    df_scaled, _ = preprocess_features(df_clean, cluster_features)
                    base_k = 3 if len(df_scaled) >= 60 else 2
                    eval_df = evaluate_clustering_algorithms(df_scaled, k=base_k)
                    eval_df.to_csv(cluster_dir / f"{fp.stem}_eval_k{base_k}.csv", index=False, encoding="utf-8-sig")
                    profile_summary = {}
                    for profile in RECOMMENDATION_PROFILES.keys():
                        algo_rec = recommend_clustering_algorithm(eval_df, profile=profile)
                        combo_rec = recommend_k_algorithm_combo(
                            df_scaled,
                            k_values=range(2, 9),
                            fallback_k=base_k,
                            fallback_algorithm=algo_rec.get("recommended_algorithm", "kmeans"),
                            profile=profile,
                        )
                        rec_k = int(combo_rec.get("recommended_k", base_k))
                        rec_algo = combo_rec.get("recommended_algorithm", "kmeans")
                        labeled_df, _, metrics = perform_clustering(
                            df_clean,
                            df_scaled,
                            k=rec_k,
                            algorithm=rec_algo,
                        )
                        labeled_df.to_csv(
                            cluster_dir / f"{fp.stem}_{profile}_k{rec_k}_{rec_algo}.csv",
                            index=False,
                            encoding="utf-8-sig",
                        )
                        profile_summary[profile] = {
                            "k": rec_k,
                            "algorithm": rec_algo,
                            "silhouette": float(metrics.get("silhouette", np.nan)),
                            "calinski_harabasz": float(metrics.get("calinski_harabasz", np.nan)),
                            "davies_bouldin": float(metrics.get("davies_bouldin", np.nan)),
                        }
                    (cluster_dir / f"{fp.stem}_profile_summary.json").write_text(
                        json.dumps(profile_summary, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    item["cluster_export"] = "ok"
                    item["cluster_profile"] = "balanced"
                    item["cluster_k"] = profile_summary["balanced"]["k"]
                    item["cluster_algorithm"] = profile_summary["balanced"]["algorithm"]
                else:
                    item["cluster_export"] = "skip: 有效样本不足"
            else:
                item["cluster_export"] = "skip: 数值特征不足"
        except Exception as e:
            item["cluster_export"] = f"fail: {e}"

        try:
            target, features = choose_regression_columns(df)
            if target and len(features) >= 3:
                analyzer = GameExperienceAnalyzer(df.copy())
                reg = analyzer.regression_analysis(features, target, missing_strategy="median")
                reg_df = reg["results_df"]
                reg_df.to_csv(reg_dir / f"{fp.stem}_regression.csv", index=False, encoding="utf-8-sig")
                summary = {
                    "target": target,
                    "features": features,
                    "sample_size": int(reg["sample_size"]),
                    "alpha": float(reg["alpha"]) if pd.notna(reg["alpha"]) else None,
                    "r_squared": float(reg["final_model"].rsquared),
                    "adj_r_squared": float(reg["final_model"].rsquared_adj),
                }
                (reg_dir / f"{fp.stem}_regression_summary.json").write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                item["regression_export"] = "ok"
            else:
                item["regression_export"] = "skip: 可用回归字段不足"
        except Exception as e:
            item["regression_export"] = f"fail: {e}"

        file_summaries.append(item)

    summary_df = pd.DataFrame(file_summaries)
    summary_df.to_csv(summary_dir / "example_full_review_summary.csv", index=False, encoding="utf-8-sig")
    summary = {
        "timestamp": ts,
        "output_dir": str(out_dir),
        "script_results": script_results,
        "file_count": len(files),
    }
    (summary_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Full review completed: {out_dir}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
