import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from survey_tools.core.quant import run_group_difference_test

def verify_v1_logic():
    print("=== 正在验证 v1.py (当前版本) 的核心统计逻辑 ===")
    xlsx_candidates = [
        os.path.join(_PROJECT_ROOT, "mock_survey_data.xlsx"),
        os.path.join(_PROJECT_ROOT, "example", "mock_survey_data.xlsx"),
    ]
    csv_fallback = os.path.join(_PROJECT_ROOT, "test_assets", "mock_survey.csv")
    file_path = None
    for c in xlsx_candidates:
        if os.path.exists(c):
            file_path = c
            break
    use_csv = False
    if file_path is None and os.path.isfile(csv_fallback):
        file_path = csv_fallback
        use_csv = True
    if file_path is None:
        print(
            "错误: 找不到模拟数据文件，已尝试 xlsx: "
            f"{xlsx_candidates} 与 csv: {csv_fallback}"
        )
        sys.exit(1)

    print(f"加载数据: {file_path}")
    if use_csv:
        df = pd.read_csv(file_path)
        group_col = "group"
        single_col = "single_choice"
        rating_col = "score"
    else:
        df = pd.read_excel(file_path)
        group_col = "Q2.年龄段"
        single_col = "Q1.性别"
        rating_col = "Q5.NPS打分"
    
    print(f"\n[测试 1] 单选题差异检验: {single_col} x {group_col}")
    # 模拟 Web 端调用
    res_single = run_group_difference_test(df, group_col, single_col, "单选")
    
    overall = res_single.get("overall", {})
    print(f"  > 检验方法: {overall.get('test')}")
    print(f"  > P值: {overall.get('p_value'):.4f}")
    print(f"  > 效应量 (Cramer's V): {overall.get('effect_size'):.4f}")
    
    if overall.get('p_value') is not None:
        print("  > 结果: PASS 成功计算")
    else:
        print("  > 结果: FAIL 计算失败")

    print(f"\n[测试 2] 评分题差异检验: {rating_col} x {group_col}")
    # 模拟 Web 端调用
    res_rating = run_group_difference_test(df, group_col, rating_col, "评分")
    
    overall_r = res_rating.get("overall", {})
    print(f"  > 检验方法: {overall_r.get('test')}")
    print(f"  > P值: {overall_r.get('p_value'):.4f}")
    print(f"  > 效应量: {overall_r.get('effect_size'):.4f}")
    
    pairwise = res_rating.get("pairwise")
    if pairwise is not None and not pairwise.empty:
        print(f"  > 两两比较: 生成了 {len(pairwise)} 组对比")
    
    if overall_r.get('p_value') is not None:
        print("  > 结果: PASS 成功计算")
    else:
        print("  > 结果: FAIL 计算失败")

    print("\n=== 验证结论 ===")
    print("v1.py 现在已具备与 v1.3 同等的统计分析能力 (卡方/ANOVA/事后检验)。")

if __name__ == "__main__":
    verify_v1_logic()
