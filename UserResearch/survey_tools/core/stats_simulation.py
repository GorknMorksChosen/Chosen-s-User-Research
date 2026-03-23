import pandas as pd
import numpy as np
from scipy import stats
from statsmodels.stats.multitest import multipletests
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

EFFECT_SIZE_THRESHOLDS = {
    "Cramer's V": {'small': 0.10, 'medium': 0.30, 'large': 0.50, 'max_val': 1.0},
    "Eta-squared": {'small': 0.01, 'medium': 0.06, 'large': 0.14, 'max_val': 1.0},
    "Cohen's d": {'small': 0.20, 'medium': 0.50, 'large': 0.80, 'max_val': 1.5},
}

def get_direction_arrow(val1, val2):
    """比较两个数值大小，返回方向指示箭头字符。

    Args:
        val1: float or None，参照行的数值。
        val2: float or None，参照列的数值。

    Returns:
        str，"▲" 表示 val1 > val2，"▼" 表示 val1 < val2，相等或含 NaN 时返回 ""。
    """
    if pd.isna(val1) or pd.isna(val2) or val1 == val2:
        return ''
    if val1 > val2:
        return '▲'
    else: # val1 < val2
        return '▼'

def calculate_cramers_v(confusion_matrix):
    """计算列联表的 Cramér's V 效应量（仿真脚本内置版，含偏差修正）。

    Args:
        confusion_matrix: pd.DataFrame，交叉频数列联表。

    Returns:
        float，修正后的 Cramér's V 值（0~1）。
    """
    chi2 = stats.chi2_contingency(confusion_matrix)[0]
    n = confusion_matrix.sum().sum()
    phi2 = chi2 / n
    r, k = confusion_matrix.shape
    phi2corr = max(0, phi2 - ((k-1)*(r-1))/(n-1))
    rcorr = r - ((r-1)**2)/(n-1)
    kcorr = k - ((k-1)**2)/(n-1)
    return np.sqrt(phi2corr / min((kcorr-1), (rcorr-1)))

def analyze_single_choice_stats(df, group_col, q_col):
    """模拟 v1.3 单选题统计逻辑：卡方检验 + Cramér's V（用于仿真验证）。

    Args:
        df: pd.DataFrame，问卷数据，行为受访者。
        group_col: str，分组列名。
        q_col: str，单选题列名。

    Returns:
        dict，含 question/test/p_value/effect_size/significant 字段。
    """
    # Cross tabulation
    ct = pd.crosstab(df[q_col], df[group_col])
    
    # Chi-square test
    chi2, p, dof, ex = stats.chi2_contingency(ct)
    
    # Effect size
    cramers_v = calculate_cramers_v(ct)
    
    # Result format
    return {
        'question': q_col,
        'test': 'Chi-square',
        'p_value': p,
        'effect_size': cramers_v,
        'significant': p < 0.05
    }

def analyze_rating_stats(df, group_col, q_col):
    """模拟 v1.3 评分题统计逻辑：单因素 ANOVA + Eta-squared（用于仿真验证）。

    Args:
        df: pd.DataFrame，问卷数据，行为受访者。
        group_col: str，分组列名。
        q_col: str，评分题列名（数值型）。

    Returns:
        dict，含 question/test/p_value/effect_size/significant 字段。
    """
    groups = [group[q_col].dropna().values for name, group in df.groupby(group_col)]
    
    # ANOVA
    f_val, p = stats.f_oneway(*groups)
    
    # Eta-squared (simplified)
    # Total Sum of Squares
    all_vals = np.concatenate(groups)
    grand_mean = np.mean(all_vals)
    ss_total = np.sum((all_vals - grand_mean)**2)
    
    # Between Group Sum of Squares
    ss_between = 0
    for group in groups:
        ss_between += len(group) * (np.mean(group) - grand_mean)**2
        
    eta_squared = ss_between / ss_total if ss_total != 0 else 0
    
    return {
        'question': q_col,
        'test': 'ANOVA',
        'p_value': p,
        'effect_size': eta_squared,
        'significant': p < 0.05
    }

def run_simulation(file_path):
    """从 Excel 文件读取数据并运行 v1.3 统计逻辑仿真，打印结果（调试/迁移验证用）。

    Args:
        file_path: str，Excel 文件路径（需包含 Q1.性别、Q2.年龄段、Q5.NPS打分 等列）。

    Returns:
        list[dict]，单选题和评分题的统计结果列表。
    """
    print(f"Loading data from {file_path}...")
    df = pd.read_excel(file_path)
    
    # Define roles
    group_col = 'Q2.年龄段'
    single_col = 'Q1.性别'
    rating_col = 'Q5.NPS打分'
    
    results = []
    
    # Run Stats for Single Choice
    print(f"Running Stats for {single_col} by {group_col}...")
    res_single = analyze_single_choice_stats(df, group_col, single_col)
    results.append(res_single)
    
    # Run Stats for Rating
    print(f"Running Stats for {rating_col} by {group_col}...")
    res_rating = analyze_rating_stats(df, group_col, rating_col)
    results.append(res_rating)
    
    return results

if __name__ == "__main__":
    file_path = 'd:\\SUN用研运营\\Python分析工具\\问卷数表\\mock_survey_data.xlsx'
    results = run_simulation(file_path)
    print("\n--- Simulation Results (v1.3 Logic) ---")
    for r in results:
        sig_mark = "***" if r['p_value'] < 0.001 else "**" if r['p_value'] < 0.01 else "*" if r['p_value'] < 0.05 else ""
        print(f"Question: {r['question']}")
        print(f"  Test: {r['test']}")
        print(f"  P-value: {r['p_value']:.4f} {sig_mark}")
        print(f"  Effect Size: {r['effect_size']:.4f}")
        print("-" * 30)
