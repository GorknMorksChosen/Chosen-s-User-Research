import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from survey_tools.core.clustering import (
    RECOMMENDATION_PROFILES,
    clean_data,
    preprocess_features,
    evaluate_clustering_algorithms,
    recommend_clustering_algorithm,
    recommend_k_algorithm_combo,
    perform_clustering,
)


def pick_numeric_features(df: pd.DataFrame):
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    valid = [c for c in numeric_cols if pd.to_numeric(df[c], errors="coerce").notna().sum() >= 20]
    return valid[:8]


def load_first_sheet(path: str):
    xls = pd.ExcelFile(path)
    return pd.read_excel(xls, sheet_name=xls.sheet_names[0])


def run_file(path: str):
    df = load_first_sheet(path)
    feature_cols = pick_numeric_features(df)
    if len(feature_cols) < 3:
        return {"file": os.path.basename(path), "status": "skip", "reason": "数值特征不足"}
    df_clean = clean_data(df, feature_cols, method="median")
    if len(df_clean) < 30:
        return {"file": os.path.basename(path), "status": "skip", "reason": "有效样本不足"}
    df_scaled, _ = preprocess_features(df_clean, feature_cols)
    k = 3 if len(df_scaled) >= 60 else 2
    eval_df = evaluate_clustering_algorithms(df_scaled, k=k)
    if not (eval_df["status"] == "ok").any():
        raise RuntimeError(f"多算法评估全部失败: {path}")
    profile_algos = {}
    for profile in RECOMMENDATION_PROFILES.keys():
        recommendation = recommend_clustering_algorithm(eval_df, profile=profile)
        rec_by_profile = recommendation.get("recommended_algorithm")
        if rec_by_profile not in ["kmeans", "gmm", "agglomerative"]:
            raise RuntimeError(f"推荐算法异常: {path} | profile={profile}")
        profile_algos[profile] = rec_by_profile
    recommendation = recommend_clustering_algorithm(eval_df, profile="balanced")
    rec_algo = recommendation.get("recommended_algorithm")
    if rec_algo not in ["kmeans", "gmm", "agglomerative"]:
        raise RuntimeError(f"推荐算法异常: {path}")
    combo_profile_map = {}
    for profile in RECOMMENDATION_PROFILES.keys():
        combo_rec = recommend_k_algorithm_combo(
            df_scaled,
            k_values=range(2, 6),
            fallback_k=k,
            fallback_algorithm=profile_algos[profile],
            profile=profile,
        )
        rec_combo_algo_by_profile = combo_rec.get("recommended_algorithm")
        rec_k_by_profile = int(combo_rec.get("recommended_k", k))
        if rec_combo_algo_by_profile not in ["kmeans", "gmm", "agglomerative"]:
            raise RuntimeError(f"联合推荐算法异常: {path} | profile={profile}")
        if rec_k_by_profile < 2 or rec_k_by_profile > 8:
            raise RuntimeError(f"联合推荐K异常: {path} | profile={profile}")
        combo_profile_map[profile] = (rec_k_by_profile, rec_combo_algo_by_profile)
    combo_rec = recommend_k_algorithm_combo(
        df_scaled,
        k_values=range(2, 9),
        fallback_k=k,
        fallback_algorithm=rec_algo,
        profile="balanced",
    )
    rec_k = int(combo_rec.get("recommended_k", k))
    rec_combo_algo = combo_rec.get("recommended_algorithm")
    if rec_combo_algo not in ["kmeans", "gmm", "agglomerative"]:
        raise RuntimeError(f"联合推荐算法异常: {path}")
    if rec_k < 2 or rec_k > 8:
        raise RuntimeError(f"联合推荐K异常: {path}")
    labeled_df_combo, profiles_combo, metrics_combo = perform_clustering(
        df_clean,
        df_scaled,
        k=rec_k,
        algorithm=rec_combo_algo,
    )
    if "Cluster" not in labeled_df_combo.columns or profiles_combo.empty:
        raise RuntimeError(f"联合推荐执行失败: {path}")
    if metrics_combo.get("algorithm") != rec_combo_algo:
        raise RuntimeError(f"联合推荐指标异常: {path}")
    for algo in ["kmeans", "gmm", "agglomerative"]:
        labeled_df, profiles, metrics = perform_clustering(
            df_clean,
            df_scaled,
            k=k,
            algorithm=algo,
        )
        if "Cluster" not in labeled_df.columns:
            raise RuntimeError(f"{algo} 未输出 Cluster 列: {path}")
        if profiles.empty:
            raise RuntimeError(f"{algo} 画像为空: {path}")
        if metrics.get("algorithm") != algo:
            raise RuntimeError(f"{algo} 指标算法标识异常: {path}")
    return {
        "file": os.path.basename(path),
        "status": "ok",
        "features": len(feature_cols),
        "samples": len(df_clean),
        "k": k,
        "recommended": rec_algo,
        "recommended_k": rec_k,
        "recommended_combo_algo": rec_combo_algo,
        "profile_algos": profile_algos,
        "profile_combos": combo_profile_map,
    }


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
        print("P2-4 clustering skipped: 未找到 example/ 或 test_assets/ 下的 .xlsx。")
        sys.exit(0)
    oks = 0
    skips = 0
    for fp in sorted(files):
        result = run_file(fp)
        if result["status"] == "ok":
            oks += 1
            print(
                f"[OK] {result['file']} | features={result['features']} | "
                f"samples={result['samples']} | k={result['k']} | recommended={result['recommended']} | "
                f"recommended_combo=({result['recommended_k']}, {result['recommended_combo_algo']}) | "
                f"profile_algos={result['profile_algos']} | profile_combos={result['profile_combos']}"
            )
        else:
            skips += 1
            print(f"[SKIP] {result['file']} | reason={result['reason']}")
    if oks == 0:
        raise RuntimeError("没有可通过的样本文件，无法完成P2-4聚类验证。")
    print(f"P2-4 clustering verification passed. ok={oks}, skip={skips}, total={len(files)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"P2-4 clustering verification failed: {e}")
        sys.exit(1)
