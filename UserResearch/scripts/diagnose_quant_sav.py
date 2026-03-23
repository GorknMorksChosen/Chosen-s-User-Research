# -*- coding: utf-8 -*-
"""
诊断 Quant 交叉分析「全部 100%」问题：加载 .sav，检查核心分组列取值与一次交叉结果。
用法: python scripts/diagnose_quant_sav.py [path_to.sav]
若未传路径，则尝试 input_example/问卷星导出_角色战斗定位-0225.sav
"""
import sys
from pathlib import Path

# 项目根
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from survey_tools.utils.io import load_sav, apply_sav_labels
from survey_tools.utils.wjx_header import normalize_wjx_headers

def analyze_single_choice_local(df, core_segment_col, question_col):
    """与 quant_app.analyze_single_choice 一致，便于脚本内复现。"""
    records = []
    grouped = df.groupby(core_segment_col, dropna=True)
    for seg_value, group in grouped:
        total = len(group)
        if total == 0:
            continue
        vc = group[question_col].value_counts(dropna=True)
        for option, count in vc.items():
            if pd.isna(option):
                continue
            ratio = count / total if total > 0 else 0
            records.append({
                "题目": question_col,
                "核心分组": seg_value,
                "选项": str(option),
                "频次": int(count),
                "行百分比": float(ratio),
                "组样本数": int(total),
            })
    if not records:
        return pd.DataFrame(columns=["题目", "核心分组", "选项", "频次", "行百分比", "组样本数"])
    return pd.DataFrame(records)


def main():
    if len(sys.argv) >= 2:
        sav_path = Path(sys.argv[1])
    else:
        sav_path = ROOT / "input_example" / "问卷星导出_角色战斗定位-0225.sav"
    if not sav_path.exists():
        print(f"文件不存在: {sav_path}")
        print("用法: python scripts/diagnose_quant_sav.py <path_to.sav>")
        return 1

    print(f"加载: {sav_path}")
    df, variable_labels, value_labels = load_sav(str(sav_path))
    print(f"行数={len(df)}, 列数={len(df.columns)}")

    # 与 Quant 一致：应用变量标签
    if variable_labels:
        df = apply_sav_labels(
            df,
            variable_labels=variable_labels,
            value_labels=None,
            apply_variable_labels=True,
            apply_value_labels=False,
        )
    df, _ = normalize_wjx_headers(df)
    columns = df.columns.tolist()

    # 找可能的「核心分组」列（含 玩家分类 / Type）
    seg_candidates = [c for c in columns if "玩家分类" in str(c) or "Type" in str(c)]
    if not seg_candidates:
        seg_candidates = columns[:5]
    print("\n可能的核心分组列（含「玩家分类」或「Type」）:", seg_candidates[:10])

    for col in seg_candidates[:3]:
        s = df[col]
        n_unique = s.nunique()
        n_total = len(df)
        print(f"\n列: {col[:60]}...")
        print(f"  不同取值数: {n_unique} (总行数 {n_total})")
        if n_total > 0 and n_unique >= max(2, n_total * 0.9):
            print("  >>> 取值过多，相当于每行一个分组，会导致交叉结果全部 100%")
        print("  value_counts (前 10):")
        print(s.value_counts(dropna=False).head(10).to_string())

    # 用第一个候选作为核心分组，选第一列单选题做一次交叉
    core_col = seg_candidates[0] if seg_candidates else columns[0]
    # 选一个看起来像单选题的列（非多选子列）
    q_cols = [c for c in columns if str(c).startswith("Q1.") and ":" not in str(c)]
    if not q_cols:
        q_cols = [c for c in columns if "Q1" in str(c) and ":" not in str(c)]
    question_col = q_cols[0] if q_cols else columns[1]

    print(f"\n试算交叉: 核心分组={core_col[:50]}..., 题目列={question_col[:50]}...")
    table = analyze_single_choice_local(df, core_col, question_col)
    if table.empty:
        print("  结果为空")
    else:
        print("  行数:", len(table))
        print("  行百分比 样例 (前 10):")
        print(table[["核心分组", "选项", "频次", "行百分比", "组样本数"]].head(10).to_string())
        pct = table["行百分比"]
        if (pct >= 0.99).all():
            print("  >>> 所有行百分比均 >= 99%，即「全部 100%」现象；原因是核心分组列取值过多（每行一组）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
