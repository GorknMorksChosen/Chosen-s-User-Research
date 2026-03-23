# 放置所有导入语句
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog
import pandas as pd
import os
import threading
import gc
import re
import numpy as np
import json
from itertools import combinations
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from scipy.stats import normaltest, levene, kruskal, f_oneway
from scikit_posthocs import posthoc_dunn
from scipy.stats import fisher_exact
from collections import defaultdict
from pathlib import Path
from openpyxl.utils import get_column_letter
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.anova import AnovaRM
from scipy.stats import ttest_rel, wilcoxon, friedmanchisquare
from survey_tools.core.quant import (
    calculate_cramers_v,
    calculate_eta_squared_anova,
    calculate_eta_squared_kruskal,
    calculate_rank_biserial_correlation,
    calculate_paired_rank_biserial_correlation,
    calculate_cohens_g_mcnemar,
    calculate_cohens_d_paired,
    calculate_cohens_d,
    advanced_split,
    extract_qnum,
    extract_option,
    get_question_stem,
    clean_question_stem,
)
from survey_tools.core.question_type import infer_type_from_columns, parse_columns_for_questions


# ========== 新增：手动标记题型对话框 ==========
class TypeMarkerDialog:
    """一个用于手动标记问卷题目类型的对话框"""
    def __init__(self, parent, columns):
        self.top = tk.Toplevel(parent)
        self.top.title("手动标记问卷题型")
        self.top.geometry("700x500")
        self.top.grab_set() # 模态对话框

        self.result = None
        self.comboboxes = {}
        self.question_info = parse_columns_for_questions(columns)
        self.inferred_types = {
            q_num: infer_type_from_columns(info)
            for q_num, info in self.question_info.items()
        }

        # --- UI Elements ---
        # Scrolled Frame
        main_frame = ttk.Frame(self.top)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Header
        ttk.Label(self.scrollable_frame, text="题号", font=("Helvetica", 10, "bold")).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Label(self.scrollable_frame, text="题干 (自动提取)", font=("Helvetica", 10, "bold")).grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(self.scrollable_frame, text="请选择题型", font=("Helvetica", 10, "bold")).grid(row=0, column=2, padx=5, pady=5, sticky="w")
        
        # Populate with questions
        q_types = ['请选择...', '单选题', '多选题', '评分题', '矩阵单选题', '矩阵评分题', '填空题', '忽略']
        
        for i, (q_num, info) in enumerate(sorted(self.question_info.items())):
            row_num = i + 1
            ttk.Label(self.scrollable_frame, text=f"Q{q_num}").grid(row=row_num, column=0, padx=5, pady=2, sticky="w")
            
            stem_label = ttk.Label(self.scrollable_frame, text=info['stem'], wraplength=400, justify="left")
            stem_label.grid(row=row_num, column=1, padx=5, pady=2, sticky="w")
            
            combo = ttk.Combobox(self.scrollable_frame, values=q_types, state="readonly")
            combo.grid(row=row_num, column=2, padx=5, pady=2, sticky="ew")

            # 如果从题目文本中已经能大致看出题型（例如列名含有【单选】/【多选】等），
            # 则在对话框中自动预选对应题型，用户仍然可以手动修改。
            inferred_display_type = self.inferred_types.get(q_num)
            if inferred_display_type in q_types:
                combo.set(inferred_display_type)
            else:
                combo.set('请选择...')
            self.comboboxes[q_num] = combo

        # Buttons
        button_frame = ttk.Frame(self.top)
        button_frame.pack(fill="x", pady=10)
        
        ttk.Button(button_frame, text="确认并继续", command=self.on_confirm).pack(side="right", padx=10)
        ttk.Button(button_frame, text="取消", command=self.on_cancel).pack(side="right")

    def _infer_type_from_columns(self, info):
        return infer_type_from_columns(info)

    def _parse_columns_for_questions(self, columns):
        return parse_columns_for_questions(columns)

    def on_confirm(self):
        self.result = {'单选': [], '多选': [], '评分': [], '矩阵评分': [], '矩阵单选': [], '填空': []}
        type_mapping_dialog = {
            '单选题': '单选', '多选题': '多选', '评分题': '评分',
            '矩阵评分题': '矩阵评分', '矩阵单选题': '矩阵单选', '填空题': '填空'
        }
        
        for q_num, combo in self.comboboxes.items():
            selected_type_display = combo.get()
            if selected_type_display in ['请选择...', '忽略']:
                continue
            
            internal_type = type_mapping_dialog.get(selected_type_display)
            if internal_type:
                self.result[internal_type].append(q_num)
        
        unselected_questions = [q for q, c in self.comboboxes.items() if c.get() == '请选择...']
        if unselected_questions:
            if not messagebox.askyesno("确认", f"以下题目未选择题型，将被忽略，是否继续？\n{unselected_questions}"):
                return

        print("--- 用户手动标记的题型 ---")
        for q_type, q_nums in self.result.items():
            if q_nums:
                print(f"{q_type}: {sorted(q_nums)}")
        print("--------------------------")
        
        self.top.destroy()

    def on_cancel(self):
        self.result = None
        self.top.destroy()
# ========== 新增：自定义分群对话框 ==========
class CustomSegmentDialog:
    def __init__(self, parent, file_path, sheet_name=0):
        self.top = tk.Toplevel(parent)
        self.top.title("自定义用户分群 (设置条件)")
        self.top.geometry("750x450")
        self.top.grab_set()

        self.result_segments = {}  # 格式: { '用户群1': [('列名', '值'), ...] }
        self.file_path = file_path
        self.sheet_name = sheet_name

        try:
            # 读取数据以获取列名和选项 (只读前1000行加速，或者全读)
            self.df_sample = pd.read_excel(file_path, sheet_name=sheet_name)
            self.df_sample.columns = [str(c).replace('\xa0','').strip() for c in self.df_sample.columns]
            self.columns = self.df_sample.columns.tolist()
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败: {e}")
            self.top.destroy()
            return

        self._build_ui()

    def _build_ui(self):
        # 左侧：已创建的用户群列表
        left_frame = ttk.LabelFrame(self.top, text="已创建的用户群")
        left_frame.pack(side="left", fill="y", padx=10, pady=10)

        self.segment_listbox = tk.Listbox(left_frame, width=25)
        self.segment_listbox.pack(fill="both", expand=True, padx=5, pady=5)

        btn_del = ttk.Button(left_frame, text="删除选中群组", command=self.delete_segment)
        btn_del.pack(pady=5)

        # 右侧：新建分群条件区域
        right_frame = ttk.LabelFrame(self.top, text="新建用户群 (多条件为 '且' 关系)")
        right_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        name_frame = ttk.Frame(right_frame)
        name_frame.pack(fill="x", pady=10)
        ttk.Label(name_frame, text="1. 命名群组:").pack(side="left", padx=5)
        self.seg_name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=self.seg_name_var, width=25).pack(side="left")

        ttk.Label(right_frame, text="2. 设置条件:").pack(anchor="w", padx=5)
        self.conditions_frame = ttk.Frame(right_frame)
        self.conditions_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.condition_rows = []

        btn_add_cond = ttk.Button(right_frame, text="+ 添加一个条件", command=self.add_condition_row)
        btn_add_cond.pack(pady=5)

        self.add_condition_row() # 默认给一行空条件

        btn_save_seg = ttk.Button(right_frame, text="保存当前用户群", command=self.save_segment)
        btn_save_seg.pack(pady=15)

        # 底部：确认返回
        bottom_frame = ttk.Frame(self.top)
        bottom_frame.pack(side="bottom", fill="x", pady=5)
        ttk.Button(bottom_frame, text="确认并返回分析主界面", command=self.on_confirm).pack()

    def add_condition_row(self):
        row_frame = ttk.Frame(self.conditions_frame)
        row_frame.pack(fill="x", pady=2)

        ttk.Label(row_frame, text="如果:").pack(side="left")
        col_combo = ttk.Combobox(row_frame, values=self.columns, state="readonly", width=25)
        col_combo.pack(side="left", padx=5)

        ttk.Label(row_frame, text="=").pack(side="left")
        val_combo = ttk.Combobox(row_frame, state="readonly", width=15)
        val_combo.pack(side="left", padx=5)

        # 当列名被选择时，动态更新对应的选项值
        def on_col_select(event, c_cb=col_combo, v_cb=val_combo):
            selected_col = c_cb.get()
            if selected_col in self.df_sample.columns:
                unique_vals = self.df_sample[selected_col].dropna().astype(str).unique().tolist()
                v_cb['values'] = sorted(unique_vals)
                v_cb.set('')

        col_combo.bind("<<ComboboxSelected>>", on_col_select)
        self.condition_rows.append((col_combo, val_combo, row_frame))

    def save_segment(self):
        seg_name = self.seg_name_var.get().strip()
        if not seg_name:
            messagebox.showwarning("提示", "请为用户群命名！")
            return
        
        conditions = []
        for col_cb, val_cb, _ in self.condition_rows:
            col, val = col_cb.get(), val_cb.get()
            if col and val:
                conditions.append((col, val))
        
        if not conditions:
            messagebox.showwarning("提示", "请至少设置一个有效的判定条件！")
            return

        self.result_segments[seg_name] = conditions
        self.update_listbox()
        
        # 清空输入流，方便录入下一个
        self.seg_name_var.set("")
        for _, _, f in self.condition_rows:
            f.destroy()
        self.condition_rows = []
        self.add_condition_row()

    def delete_segment(self):
        sel = self.segment_listbox.curselection()
        if sel:
            seg_name = self.segment_listbox.get(sel[0])
            del self.result_segments[seg_name]
            self.update_listbox()

    def update_listbox(self):
        self.segment_listbox.delete(0, tk.END)
        for seg in self.result_segments:
            self.segment_listbox.insert(tk.END, seg)

    def on_confirm(self):
        self.top.destroy()


# ========== 放置所有全局常量和辅助函数 ==========.
EFFECT_SIZE_THRESHOLDS = {
    "Cramer's V": {'small': 0.10, 'medium': 0.30, 'large': 0.50, 'max_val': 1.0},
    "Eta-squared": {'small': 0.01, 'medium': 0.06, 'large': 0.14, 'max_val': 1.0},
    "Cohen's d": {'small': 0.20, 'medium': 0.50, 'large': 0.80, 'max_val': 1.5},
    "Rank-biserial correlation": {'small': 0.10, 'medium': 0.30, 'large': 0.50, 'max_val': 1.0},
    "Relative Difference in Proportions": {'small': 0.10, 'medium': 0.30, 'large': 0.50, 'max_val': 1.0},
    "Cohen's g": {'small': 0.10, 'medium': 0.30, 'large': 0.50, 'max_val': 1.0} # 新增 Cohen's g 的阈值
}

EFFECT_SIZE_INTERPRETATION = """
效应量与方向解读说明：
- 效应量（Effect Size）是衡量效应大小的指标，它量化了变量之间的关联强度或组间差异的大小，补充了P值的不足。
  通常，效应量越大，单元格背景绿色越深，表示差异或关联越强；效应量越小，颜色越接近白色。
- 显著性星号(***, **, *)分别表示 p < 0.001, p < 0.01, p < 0.05。
- 方向箭头 (▲, ▼) 表示显著差异的方向：
  ▲ 表示 行项目 的值（均值/比例）显著高于 列项目 的值。
  ▼ 表示 行项目 的值（均值/比例）显著低于 列项目 的值。
"""

def get_direction_arrow(val1, val2):
    """根据两个值的比较返回方向箭头。val1对应行，val2对应列。"""
    if pd.isna(val1) or pd.isna(val2) or val1 == val2:
        return ''
    if val1 > val2:
        return '▲'
    else: # val1 < val2
        return '▼'

def generate_global_between_group_explanation():
    """生成组间分析的全局说明文本"""
    explanation = [
        "【组间显著性差异分析方法说明】",
        "本页展示了不同用户分类之间在各个问题上的回答是否存在统计上的显著差异。",
        "根据问题类型，采用的统计方法和效应量指标如下：",
        "",
        "1. 分类问题 (如：单选题、多选题的每个选项、矩阵单选题的每个选项):",
        "   - 总体检验: 卡方检验 (Chi-square Test)。",
        "   - 两两比较: 当总体检验显著时，进行卡方检验或费舍尔精确检验 (Fisher's Exact Test)。",
        "   - 效应量: 克莱姆V (Cramer's V)，衡量变量间的关联强度。",
        "     - 解读标准: 小效应(≥{EFFECT_SIZE_THRESHOLDS['Cramer\'s V']['small']}), 中等效应(≥{EFFECT_SIZE_THRESHOLDS['Cramer\'s V']['medium']}), 大效应(≥{EFFECT_SIZE_THRESHOLDS['Cramer\'s V']['large']})",
        "",
        "2. 评分问题 (如：评分题、矩阵评分题):",
        "   - 总体检验: 方差分析 (ANOVA) 或 Kruskal-Wallis H检验。选择取决于数据是否满足正态性与方差齐性假设。",
        "   - 两两比较: Tukey HSD 检验 (对应ANOVA) 或 Dunn 检验 (对应Kruskal-Wallis)。",
        "   - 效应量: 科恩d (Cohen's d) 或 秩双列相关 (Rank-biserial correlation)。",
        "     - Cohen's d 解读: 小效应(≥{EFFECT_SIZE_THRESHOLDS['Cohen\'s d']['small']}), 中等效应(≥{EFFECT_SIZE_THRESHOLDS['Cohen\'s d']['medium']}), 大效应(≥{EFFECT_SIZE_THRESHOLDS['Cohen\'s d']['large']})",
        "     - Rank-biserial 解读: 小效应(≥{EFFECT_SIZE_THRESHOLDS['Rank-biserial correlation']['small']}), 中等效应(≥{EFFECT_SIZE_THRESHOLDS['Rank-biserial correlation']['medium']}), 大效应(≥{EFFECT_SIZE_THRESHOLDS['Rank-biserial correlation']['large']})",
    ]
    return "\n".join(explanation)

def generate_global_within_group_explanation():
    """生成组内分析的全局说明文本"""
    explanation = [
        "【组内显著性差异分析方法说明】",
        "本页展示了在同一个用户分类内部，不同选项或子项之间的选择是否存在统计上的显著差异。",
        "根据问题类型，采用的统计方法和效应量指标如下：",
        "",
        "1. 单选题 (选项间比较):",
        "   - 比较方法: 成对二项式检验 (Pairwise Binomial Test)，检验两个选项的选择人数比例是否有差异。",
        "   - 效应量: 选项间相对差异比例 (Relative Difference in Proportions)。",
        "     - 解读标准: 小效应(≥{EFFECT_SIZE_THRESHOLDS['Relative Difference in Proportions']['small']}), 中等效应(≥{EFFECT_SIZE_THRESHOLDS['Relative Difference in Proportions']['medium']}), 大效应(≥{EFFECT_SIZE_THRESHOLDS['Relative Difference in Proportions']['large']})",
        "",
        "2. 多选题 / 矩阵单选题 (选项间比较):",
        "   - 比较方法: McNemar 检验，用于检验配对名义数据的边际同质性，适合“是否选择”这类配对数据。",
        "   - 效应量: 科恩g (Cohen's g)。",
        "     - 解读标准: 小效应(≥{EFFECT_SIZE_THRESHOLDS['Cohen\'s g']['small']}), 中等效应(≥{EFFECT_SIZE_THRESHOLDS['Cohen\'s g']['medium']}), 大效应(≥{EFFECT_SIZE_THRESHOLDS['Cohen\'s g']['large']})",
        "",
        "3. 矩阵评分题 (子项间比较):",
        "   - 总体检验: 重复测量方差分析 (Repeated Measures ANOVA) 或 Friedman 检验。",
        "   - 两两比较: 配对t检验 (Paired t-test) 或 Wilcoxon符号秩检验 (Wilcoxon Signed-Rank Test)。",
        "   - 效应量: 科恩d (Cohen's d) 或 秩双列相关 (Rank-biserial correlation)。(效应量解读标准同组间分析)",
    ]
    return "\n".join(explanation)


def get_green_gradient_color(value, es_type_str):
    if pd.isna(value):
        return '#FFFFFF'
    value = abs(value)
    if value == 0:
        return '#FFFFFF'
    thresholds_info = EFFECT_SIZE_THRESHOLDS.get(es_type_str)
    if not thresholds_info:
        return '#FFFFFF'
    max_val_for_scaling = thresholds_info['max_val']
    normalized_value = min(value / max_val_for_scaling, 1.0)
    r = int(255 * (1 - normalized_value * 0.8))
    g = int(255 * (1 - normalized_value * 0.1))
    b = int(255 * (1 - normalized_value * 0.8))
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return f'#{r:02x}{g:02x}{b:02x}'

    if not name.strip():
        return "未命名子项"
    name = name.replace('：', ':')
    illegal_chars = r'[\\/*?:\[\]\']'
    cleaned = re.sub(illegal_chars, '-', name)
    cleaned = cleaned.strip("'")
    cleaned = cleaned[:31].strip()
    return cleaned if cleaned else "未命名子项"

def clean_sheet_name(name):
    """
    清理Excel Sheet名称，使其符合规范：
    1. 移除非法字符 ( : \ / ? * [ ] )
    2. 截断长度至31个字符
    """
    if not name:
        return "Sheet"
    
    # 移除 Excel 非法字符
    illegal_chars = r'[:\\/?*\[\]]'
    name = re.sub(illegal_chars, '_', str(name))
    
    # 截断到 31 个字符 (Excel 限制)
    return name[:31]

def get_question_stem(original_df, question_number):
    """
    根据新的格式 'Q<num>.<stem>...' 提取题干
    """
    q_num_str = str(question_number)
    
    # 查找所有与该题号相关的列
    q_cols = [c for c in original_df.columns if str(c).strip().startswith(f'Q{q_num_str}.')]
    
    if not q_cols:
        # 后备方案，兼容旧格式
        pattern = re.compile(
            rf'^({re.escape(str(question_number))}[、.])|(Q{re.escape(str(question_number))}\b)|(问题{re.escape(str(question_number))})')
        q_cols = [col for col in original_df.columns if pattern.search(str(col))]
        if q_cols:
            return max(q_cols, key=len)
        return f"Q{question_number}. 问题（未匹配到题干）"

    # 从新格式的列中提取最长的题干作为代表
    longest_stem = ""
    for col in q_cols:
        # ******** 代码修改处 (3/6) ********
        # 使用新的切分逻辑
        stem_part, _ = advanced_split(col)
        # ******** 代码修改结束 ********
        current_stem = stem_part.replace(f'Q{q_num_str}.', '', 1).strip()
        if len(current_stem) > len(longest_stem):
            longest_stem = current_stem
            
    return f"Q{q_num_str}.{longest_stem}" if longest_stem else f"Q{q_num_str}. 问题（未匹配到题干）"


def clean_question_stem(question_stem):
    """清理题干，移除题号前缀和括号内容"""
    # 移除 'Qx.' 前缀
    cleaned_stem = re.sub(r'^Q\d+\.', '', question_stem).strip()
    # 移除其他可能的旧格式前缀
    cleaned_stem = re.sub(r'^\d+[、.]', '', cleaned_stem).strip()
    # 清理括号和特殊字符
    cleaned_stem = re.sub(r'\[.*?\]', '', cleaned_stem)
    cleaned_stem = re.sub(r'（.*?）', '', cleaned_stem)
    cleaned_stem = cleaned_stem.replace('：', '').strip()
    return cleaned_stem

def extract_effect_size_from_sig_string(sig_string):
    if not isinstance(sig_string, str) or not sig_string.strip():
        return np.nan
    match = re.search(r'\(([-+]?\d*\.?\d+)\)', sig_string)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return np.nan
    return np.nan

def get_es_type_string_for_coloring(q_type, post_hoc_test_type):
    if q_type in ['单选']:
        if post_hoc_test_type == 'Binomial Test':
            return "Relative Difference in Proportions"
        else:
            return "Cramer's V"
    elif q_type in ['多选', '矩阵单选']:
        if post_hoc_test_type == 'McNemar Test':
            return "Cohen's g"
        else:
            return "Cramer's V"
    elif q_type in ['评分', '矩阵评分']:
        if post_hoc_test_type == 'ANOVA':
            return "Cohen's d"
        elif post_hoc_test_type == 'Kruskal-Wallis':
            return "Rank-biserial correlation"
        elif post_hoc_test_type == 'Repeated Measures ANOVA':
            return "Cohen's d"
        elif post_hoc_test_type == 'Friedman':
            return "Rank-biserial correlation"
    return None

def get_test_and_es_interpretation_strings(q_type, post_hoc_overall_test_type):
    overall_test_display_name = ""
    pairwise_test_display_name = ""
    es_type_display_name = ""
    es_thresholds = {}

    if q_type == '单选':
        if post_hoc_overall_test_type == 'Binomial Test':
            overall_test_display_name = "成对二项式检验 (Pairwise Binomial Test)"
            pairwise_test_display_name = "成对二项式检验 (Pairwise Binomial Test)"
            es_type_display_name = "选项间相对差异比例 (Relative Difference in Proportions)"
            es_thresholds = EFFECT_SIZE_THRESHOLDS.get("Relative Difference in Proportions", {})
        else:
            overall_test_display_name = "卡方检验 (Chi-square test)"
            pairwise_test_display_name = "卡方检验 (Chi-square test) 或 费舍尔精确检验 (Fisher's Exact Test)"
            es_type_display_name = "Cramer's V"
            es_thresholds = EFFECT_SIZE_THRESHOLDS.get("Cramer's V", {})
    elif q_type in ['多选', '矩阵单选']:
        if post_hoc_overall_test_type == 'McNemar Test':
            overall_test_display_name = "McNemar 检验"
            pairwise_test_display_name = "McNemar 检验"
            es_type_display_name = "Cohen's g"
            es_thresholds = EFFECT_SIZE_THRESHOLDS.get("Cohen's g", {})
        else:
            overall_test_display_name = "卡方检验 (Chi-square test)"
            pairwise_test_display_name = "卡方检验 (Chi-square test) 或 费舍尔精确检验 (Fisher's Exact Test)"
            es_type_display_name = "Cramer's V"
            es_thresholds = EFFECT_SIZE_THRESHOLDS.get("Cramer's V", {})
    elif q_type in ['评分', '矩阵评分']:
        if post_hoc_overall_test_type == 'ANOVA':
            overall_test_display_name = "方差分析 (ANOVA)"
            pairwise_test_display_name = "Tukey HSD 检验"
            es_type_display_name = "Cohen's d"
            es_thresholds = EFFECT_SIZE_THRESHOLDS.get("Cohen's d", {})
        elif post_hoc_overall_test_type == 'Kruskal-Wallis':
            overall_test_display_name = "Kruskal-Wallis H 检验"
            pairwise_test_display_name = "Dunn 检验"
            es_type_display_name = "Rank-biserial correlation"
            es_thresholds = EFFECT_SIZE_THRESHOLDS.get("Rank-biserial correlation", {})
        elif post_hoc_overall_test_type == 'Repeated Measures ANOVA':
            overall_test_display_name = "重复测量方差分析 (Repeated Measures ANOVA)"
            pairwise_test_display_name = "配对 T 检验 (Paired t-test)"
            es_type_display_name = "Cohen's d"
            es_thresholds = EFFECT_SIZE_THRESHOLDS.get("Cohen's d", {})
        elif post_hoc_overall_test_type == 'Friedman':
            overall_test_display_name = "Friedman 检验"
            pairwise_test_display_name = "Wilcoxon 符号秩检验 (Wilcoxon Signed-Rank Test)"
            es_type_display_name = "Rank-biserial correlation"
            es_thresholds = EFFECT_SIZE_THRESHOLDS.get("Rank-biserial correlation", {})

    interpretation_lines = []
    if es_thresholds:
        interpretation_lines.append(f"- 小效应: ≥ {es_thresholds.get('small', 'N/A')}")
        interpretation_lines.append(f"- 中等效应: ≥ {es_thresholds.get('medium', 'N/A')}")
        interpretation_lines.append(f"- 大效应: ≥ {es_thresholds.get('large', 'N/A')}")
        if es_type_display_name in ["Cramer's V", "Rank-biserial correlation", "Relative Difference in Proportions", "Cohen's g"]:
            interpretation_lines.append(f"(取值范围通常在 0 到 1 之间，Rank-biserial correlation 为 -1 到 1，Cohen's d 和 Relative Difference in Proportions 取绝对值)")
        elif es_type_display_name == "Cohen's d":
            interpretation_lines.append(f"(取绝对值判断大小，无理论上限)")
    interpretation_lines.append("显著性星号(***, **, *)表示 p < 0.001, p < 0.01, p < 0.05。")
    return overall_test_display_name, pairwise_test_display_name, es_type_display_name, "\n".join(interpretation_lines)


def remove_duplicate_matrix_columns(df, matrix_modules):
    """此函数在新格式下可能不再需要，但保留以防万一"""
    keep_cols = []
    seen_base_q_subitem = set()
    for col in df.columns:
        match = re.match(r'^Q(\d+)\.(.+?)(?::(.+))?$', str(col))
        if match:
            q_num_str, stem, sub_item = match.groups()
            if sub_item and int(q_num_str) in matrix_modules:
                unique_key = (q_num_str, sub_item.strip())
                if unique_key not in seen_base_q_subitem:
                    seen_base_q_subitem.add(unique_key)
                    keep_cols.append(col)
                else: # 是重复的矩阵列
                    print(f"Skipping duplicate matrix column: {col}")
            else:
                keep_cols.append(col)
        else:
            keep_cols.append(col)
    return df[keep_cols]


def convert_matrix_single_questions(df, matrix_single_modules):
    """
    根据新格式 'Q<num>.<stem>:<sub_item>' 转换矩阵单选题。
    新格式下，单元格的值就是选项，所以此函数主要负责重命名列。
    """
    print(f"开始处理矩阵单选题（新格式），共{len(matrix_single_modules)}个: {matrix_single_modules}")
    converted_data = pd.DataFrame(index=df.index)
    
    for q_num in matrix_single_modules:
        q_num_str = str(q_num)
        # 查找所有属于这个矩阵题的列 (格式: Qx. ... : ...)
        cols_for_q = [c for c in df.columns if str(c).startswith(f'Q{q_num_str}.') and ':' in str(c)]
        
        print(f"处理题号 {q_num_str} 的矩阵单选题，找到 {len(cols_for_q)} 个子项列。")

        for col_original in cols_for_q:
            # 提取子项名称
            try:
                # ******** 代码修改处 (4/6) ********
                _, sub_item = advanced_split(col_original)
                sub_item = sub_item.strip()
                # ******** 代码修改结束 ********
                if sub_item:
                    # 创建新列名
                    new_col_name = f"矩阵单_{q_num_str}_{sub_item.replace(' ', '_').replace('：', '')}"
                    # 直接复制数据，因为值已经是选项了
                    converted_data[new_col_name] = pd.to_numeric(df[col_original], errors='coerce')
                    print(f"  转换: '{col_original}' -> '{new_col_name}'")
            except IndexError:
                print(f"  警告: 无法从 '{col_original}' 中解析子项，已跳过。")

    print(f"矩阵单选题处理完成，创建了 {len(converted_data.columns)} 个新列。")
    return converted_data

def add_corrected_pvalues(df, group_col=None):
    df = df.copy()
    if group_col is None:
        pvals = df['P值'].fillna(1).values
        valid_pvals = np.where(np.isnan(pvals), 1.0, pvals)
        if len(valid_pvals) > 0:
            reject, pvals_corrected, _, _ = multipletests(valid_pvals, method='fdr_bh')
            df['校正后P值'] = pvals_corrected
        else:
            df['校正后P值'] = np.nan
    else:
        df['校正后P值'] = np.nan
        df_sorted = df.sort_values(by=group_col).reset_index(drop=False)
        for group_val, group_df in df_sorted.groupby(group_col, observed=True):
            pvals_group = group_df['P值'].values
            valid_pvals = np.where(np.isnan(pvals_group), 1.0, pvals_group)
            if len(valid_pvals) > 0 and not np.all(np.isnan(pvals_group)):
                _, corrected, _, _ = multipletests(valid_pvals, method='fdr_bh')
                df_sorted.loc[group_df.index, '校正后P值'] = corrected
            else:
                df_sorted.loc[group_df.index, '校正后P值'] = np.nan
        df = df_sorted.set_index('index').reindex(df.index)
    def get_significance(p):
        if pd.isna(p): return ''
        elif p < 0.001: return '***'
        elif p < 0.01: return '**'
        elif p < 0.05: return '*'
        else: return ''
    df['校正显著性'] = df['校正后P值'].apply(get_significance)
    return df


def convert_matrix_rating_questions(df, matrix_rating_modules):
    """
    根据新格式 'Q<num>.<stem>:<sub_item>' 转换矩阵评分题。
    新格式下，单元格的值就是分数，所以此函数主要负责重命名列。
    """
    print(f"开始处理矩阵评分题（新格式），共{len(matrix_rating_modules)}个: {matrix_rating_modules}")
    converted_data = pd.DataFrame(index=df.index)
    
    for q_num in matrix_rating_modules:
        q_num_str = str(q_num)
        # 查找所有属于这个矩阵题的列 (格式: Qx. ... : ...)
        cols_for_q = [c for c in df.columns if str(c).startswith(f'Q{q_num_str}.') and ':' in str(c)]
        
        print(f"处理题号 {q_num_str} 的矩阵评分题，找到 {len(cols_for_q)} 个子项列。")

        for col_original in cols_for_q:
            # 提取子项名称
            try:
                # ******** 代码修改处 (5/6) ********
                _, sub_item = advanced_split(col_original)
                sub_item = sub_item.strip()
                # ******** 代码修改结束 ********
                if sub_item:
                    # 创建新列名
                    new_col_name = f"矩阵评分_{q_num_str}_{sub_item.replace(' ', '_').replace('：', '')}"
                    # 直接复制数据，因为值已经是分数了
                    converted_data[new_col_name] = pd.to_numeric(df[col_original], errors='coerce')
                    print(f"  转换: '{col_original}' -> '{new_col_name}'")
            except IndexError:
                print(f"  警告: 无法从 '{col_original}' 中解析子项，已跳过。")
    
    print(f"矩阵评分题处理完成，创建了 {len(converted_data.columns)} 个新列。")
    return converted_data


# ========== ExcelMergerApp 类定义 ==========
class ExcelMergerApp:
    def __init__(self, master):
        self.master = master
        master.title("Excel文件合并工具")
        master.minsize(600, 250)
        master.resizable(True, True)

        self.file1_path_var = tk.StringVar()
        self.file2_path_var = tk.StringVar()
        self.merge_col1_var = tk.StringVar()
        self.merge_col2_var = tk.StringVar()

        self.actual_file1_path = None
        self.actual_file2_path = None
        self.sheet1 = 0
        self.sheet2 = 0

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="10")
        main_frame.pack(expand=True, fill="both")

        frame1 = ttk.LabelFrame(main_frame, text="文件 1 (左表)")
        frame1.pack(padx=10, pady=5, fill="x", expand=True)

        ttk.Label(frame1, text="文件路径:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(frame1, textvariable=self.file1_path_var, state="readonly").grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(frame1, text="浏览...", command=lambda: self.browse_file(1)).grid(row=0, column=2, padx=5, pady=5, sticky="e")

        ttk.Label(frame1, text="选择合并列:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.dropdown1 = ttk.Combobox(frame1, textvariable=self.merge_col1_var, state="readonly")
        self.dropdown1.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.dropdown1.bind("<<ComboboxSelected>>", self.on_dropdown_select)

        frame1.grid_columnconfigure(1, weight=1)

        frame2 = ttk.LabelFrame(main_frame, text="文件 2 (右表)")
        frame2.pack(padx=10, pady=5, fill="x", expand=True)

        ttk.Label(frame2, text="文件路径:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(frame2, textvariable=self.file2_path_var, state="readonly").grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(frame2, text="浏览...", command=lambda: self.browse_file(2)).grid(row=0, column=2, padx=5, pady=5, sticky="e")

        ttk.Label(frame2, text="选择合并列:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.dropdown2 = ttk.Combobox(frame2, textvariable=self.merge_col2_var, state="readonly")
        self.dropdown2.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.dropdown2['values'] = []
        self.dropdown2.bind("<<ComboboxSelected>>", self.on_dropdown_select)

        frame2.grid_columnconfigure(1, weight=1)

        action_frame = ttk.Frame(main_frame)
        action_frame.pack(pady=10)

        self.merge_button = ttk.Button(action_frame, text="合并文件", command=self.start_merge_thread)
        self.merge_button.pack(side="left", padx=10)

        self.status_label = ttk.Label(main_frame, text="", foreground="blue")
        self.status_label.pack(pady=5, fill="x", expand=True)

        self.progress_bar = ttk.Progressbar(main_frame, orient="horizontal", mode="indeterminate")
        self.progress_bar.pack(pady=5, fill="x", expand=True)

    def on_dropdown_select(self, event):
        pass

    def browse_file(self, file_num):
        file_path = filedialog.askopenfilename(
            title="选择Excel文件",
            filetypes=[("Excel files", "*.xlsx *.xls")]
        )
        if file_path:
            try:
                try:
                    xls = pd.ExcelFile(file_path)
                    sheet_names = xls.sheet_names
                    if len(sheet_names) > 1:
                        sheet = ask_sheet_gui(sheet_names, self.master)
                        if not sheet: sheet = sheet_names[0]
                    else:
                        sheet = sheet_names[0]
                    df_header = pd.read_excel(xls, sheet_name=sheet, nrows=0)
                except Exception:
                    sheet = 0
                    df_header = pd.read_excel(file_path, nrows=0)
                
                columns = df_header.columns.tolist()
                if file_num == 1:
                    self.sheet1 = sheet
                    self.file1_path_var.set(os.path.basename(file_path))
                    self.actual_file1_path = file_path
                    self.dropdown1['values'] = columns
                    self.merge_col1_var.set("")
                else:
                    self.sheet2 = sheet
                    self.file2_path_var.set(os.path.basename(file_path))
                    self.actual_file2_path = file_path
                    self.dropdown2['values'] = columns
                    self.merge_col2_var.set("")
                self.status_label.config(text=f"文件 {file_num} 列名加载成功: {os.path.basename(file_path)}", foreground="green")
            except Exception as e:
                messagebox.showerror("错误", f"读取文件列名失败: {e}\n请确保文件是有效的Excel文件。")
                self.status_label.config(text=f"文件 {file_num} 加载失败", foreground="red")
                if file_num == 1:
                    self.file1_path_var.set("")
                    self.actual_file1_path = None
                    self.dropdown1['values'] = []
                    self.merge_col1_var.set("")
                else:
                    self.file2_path_var.set("")
                    self.actual_file2_path = None
                    self.dropdown2['values'] = []
                    self.merge_col2_var.set("")

    def start_merge_thread(self):
        file1 = self.actual_file1_path
        file2 = self.actual_file2_path
        col1 = self.merge_col1_var.get()
        col2 = self.merge_col2_var.get()

        if not all([file1, file2, col1, col2]):
            messagebox.showwarning("警告", "请选择两个文件并指定合并列！")
            return

        output_file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            title="保存合并结果为..."
        )

        if not output_file_path:
            self.status_label.config(text="保存操作已取消。", foreground="orange")
            return

        self.merge_button.config(state="disabled")
        self.status_label.config(text="正在加载和合并文件，请稍候...", foreground="blue")
        self.progress_bar.start()
        
        s1 = self.sheet1 if hasattr(self, 'sheet1') else 0
        s2 = self.sheet2 if hasattr(self, 'sheet2') else 0

        merge_thread = threading.Thread(target=self._run_merge_in_thread,
                                        args=(file1, file2, col1, col2, output_file_path, s1, s2))
        merge_thread.start()

    def _run_merge_in_thread(self, file1, file2, col1, col2, output_file_path, sheet1=0, sheet2=0):
        try:
            original_df1 = pd.read_excel(file1, sheet_name=sheet1, dtype={col1: str})
            original_df2 = pd.read_excel(file2, sheet_name=sheet2, dtype={col2: str})

            if col1 not in original_df1.columns:
                raise KeyError(f"'{col1}' 列不存在于文件1中。")
            if col2 not in original_df2.columns:
                raise KeyError(f"'{col2}' 列不存在于文件2中。")

            df1_indexed = original_df1.set_index(col1).copy()
            df2_indexed = original_df2.set_index(col2).copy()

            final_merged_df = pd.merge(df1_indexed, df2_indexed,
                                       left_index=True, right_index=True,
                                       how='inner',
                                       suffixes=('_左表', '_右表')).reset_index()

            set_keys_df1 = set(original_df1[col1].dropna())
            set_keys_df2 = set(original_df2[col2].dropna())
            common_keys = set_keys_df1.intersection(set_keys_df2)

            df1_unmatched = original_df1[~original_df1[col1].isin(common_keys)].copy()
            df2_unmatched = original_df2[~original_df2[col2].isin(common_keys)].copy()

            with pd.ExcelWriter(output_file_path, engine='xlsxwriter') as writer:
                if not final_merged_df.empty:
                    final_merged_df.to_excel(writer, sheet_name='合并结果', index=False)
                else:
                    pd.DataFrame([{"提示": "没有匹配的数据"}]).to_excel(writer, sheet_name='合并结果', index=False, header=False)
                if not df1_unmatched.empty:
                    df1_unmatched.to_excel(writer, sheet_name='左表未匹配数据', index=False)
                else:
                    pd.DataFrame([{"提示": "左表没有未匹配的数据"}]).to_excel(writer, sheet_name='左表未匹配数据', index=False, header=False)
                if not df2_unmatched.empty:
                    df2_unmatched.to_excel(writer, sheet_name='右表未匹配数据', index=False)
                else:
                    pd.DataFrame([{"提示": "右表没有未匹配的数据"}]).to_excel(writer, sheet_name='右表未匹配数据', index=False, header=False)

            self.master.after(0, self._on_merge_complete, True, output_file_path, None)

        except KeyError as e:
            self.master.after(0, self._on_merge_complete, False, None, f"合并列错误: {e}")
        except Exception as e:
            self.master.after(0, self._on_merge_complete, False, None, f"合并过程中发生错误: {e}\n请检查文件是否损坏或格式是否正确。")
        finally:
            gc.collect()

    def _on_merge_complete(self, success, output_file_path, error_message):
        self.merge_button.config(state="normal")
        self.progress_bar.stop()
        self.progress_bar['value'] = 0

        if success:
            self.status_label.config(text=f"文件合并成功！结果保存至：{os.path.basename(output_file_path)}", foreground="green")
            messagebox.showinfo("成功", "文件合并完成！")
        else:
            self.status_label.config(text="合并失败。", foreground="red")
            messagebox.showerror("错误", f"文件合并失败: {error_message}")


def ask_sheet_gui(sheet_names, parent=None):
    """弹出对话框让用户选择工作表"""
    if not sheet_names:
        return None
    if len(sheet_names) == 1:
        return sheet_names[0]
    
    selection = [sheet_names[0]] 
    
    win = tk.Toplevel(parent) if parent else tk.Tk()
    win.title("选择工作表")
    win.geometry("300x150")
    win.grab_set() # 模态
    
    # 居中
    win.update_idletasks()
    width = win.winfo_width()
    height = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    y = (win.winfo_screenheight() // 2) - (height // 2)
    win.geometry(f'{300}x{150}+{x}+{y}')
    
    tk.Label(win, text="检测到多个工作表，请选择：").pack(pady=15)
    
    combo = ttk.Combobox(win, values=sheet_names, state="readonly")
    combo.set(sheet_names[0])
    combo.pack(pady=5, padx=20, fill="x")
    
    def on_ok():
        selection[0] = combo.get()
        win.destroy()
        
    def on_cancel():
        selection[0] = None
        win.destroy()

    btn_frame = tk.Frame(win)
    btn_frame.pack(pady=15)
    ttk.Button(btn_frame, text="确定", command=on_ok).pack(side="left", padx=10)
    ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side="right", padx=10)
    
    win.protocol("WM_DELETE_WINDOW", on_cancel)
    if parent:
        parent.wait_window(win)
    else:
        win.mainloop()
    
    return selection[0]


# ========== SurveyProcessorApp 类定义 (交叉分析功能) ==========
# ========== SurveyProcessorApp 类定义 (交叉分析功能) ==========
class SurveyProcessorApp:
    def __init__(self, master):
        self.master = master
        master.title("问卷数据分析工具")
        # ******** 代码修改处：增加窗口高度以容纳新控件 ********
        master.minsize(650, 400) 
        master.resizable(True, True)

        self.file_path = tk.StringVar()
        self.selected_sheet_name = None
        self.player_type_col = tk.StringVar()
        self.min_duration_var = tk.IntVar(value=60)
        # ******** 代码修改处：新增变量以绑定复选框状态 ********
        self.run_stats_test_var = tk.BooleanVar(value=True)
        
        self.df = None
        self.QUESTION_TYPES = None # 用于存储手动标记的题型

        self.color_formats_cache = {}
        self.sorted_question_options = {}

        main_frame = ttk.Frame(self.master, padding="10")
        main_frame.pack(expand=True, fill="both")

        tk.Label(main_frame, text="选择问卷文件:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.file_entry = tk.Entry(main_frame, textvariable=self.file_path, state="readonly")
        self.file_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.file_button = tk.Button(main_frame, text="浏览...", command=self.browse_file)
        self.file_button.grid(row=0, column=2, padx=5, pady=5, sticky="e")

        # 初始化自定义分群字典
        self.custom_segments = {}

        tk.Label(main_frame, text="选择玩家类型列:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.player_type_combobox = ttk.Combobox(main_frame, textvariable=self.player_type_col, state="readonly")
        self.player_type_combobox.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        # 新增自定义分群按钮
        self.btn_custom_seg = tk.Button(main_frame, text="或：自定义分群", command=self.launch_custom_segments, state="disabled")
        self.btn_custom_seg.grid(row=1, column=2, padx=5, pady=5, sticky="e")

        tk.Label(main_frame, text="最低完成时间 (秒):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.min_duration_entry = tk.Entry(main_frame, textvariable=self.min_duration_var, width=10)
        self.min_duration_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        # ******** 代码修改处：新增复选框控件 ********
        self.run_stats_checkbutton = tk.Checkbutton(main_frame, text="生成统计检验结果 (若不勾选，则不输出显著性差异分析页)", variable=self.run_stats_test_var)
        self.run_stats_checkbutton.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="w")
        
        # ******** 代码修改处：调整后续控件的行号 ********
        self.type_marker_button = tk.Button(main_frame, text="手动标记题型", command=self.launch_type_marker, state="disabled")
        self.type_marker_button.grid(row=4, column=0, columnspan=3, pady=10)

        self.process_button = tk.Button(main_frame, text="开始分析", command=self.start_analysis_thread, state="disabled")
        self.process_button.grid(row=5, column=0, columnspan=3, pady=5)

        self.status_label = ttk.Label(main_frame, text="请先选择文件，然后标记题型", foreground="blue")
        self.status_label.grid(row=6, column=0, columnspan=3, pady=5, sticky="ew")

        self.progress_bar = ttk.Progressbar(main_frame, orient="horizontal", mode="indeterminate")
        self.progress_bar.grid(row=7, column=0, columnspan=3, pady=5, sticky="ew")

        main_frame.grid_columnconfigure(1, weight=1)

    def browse_file(self):
        f_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if f_path:
            self.file_path.set(f_path)
            self.load_columns_for_player_type(f_path)
            self.status_label.config(text=f"文件加载成功: {os.path.basename(f_path)}. 请标记题型。", foreground="green")
            self.type_marker_button.config(state="normal")
            self.process_button.config(state="disabled") # 重新选择文件后禁用分析按钮
            self.btn_custom_seg.config(state="normal")

    def launch_type_marker(self):
        if not self.file_path.get():
            messagebox.showwarning("警告", "请先选择一个文件。")
            return

        try:
            sheet = self.selected_sheet_name if self.selected_sheet_name is not None else 0
            df_header = pd.read_excel(self.file_path.get(), sheet_name=sheet, nrows=0)
            columns = df_header.columns.tolist()
        except Exception as e:
            messagebox.showerror("文件读取错误", f"无法读取文件列名: {e}")
            return

        dialog = TypeMarkerDialog(self.master, columns)
        self.master.wait_window(dialog.top)

        if dialog.result:
            self.QUESTION_TYPES = dialog.result
            self.status_label.config(text="题型标记完成，可以开始分析。", foreground="green")
            self.process_button.config(state="normal")
        else:
            self.QUESTION_TYPES = None
            self.status_label.config(text="题型标记已取消。", foreground="orange")
            self.process_button.config(state="disabled")

    def launch_custom_segments(self):
        f_path = self.file_path.get()
        if not f_path:
            return

        sheet = self.selected_sheet_name if self.selected_sheet_name is not None else 0
        dialog = CustomSegmentDialog(self.master, f_path, sheet_name=sheet)
        self.master.wait_window(dialog.top)

        # 当用户完成了自定义条件的设置后
        if dialog.result_segments:
            self.custom_segments = dialog.result_segments
            current_vals = list(self.player_type_combobox['values'])
            if "[自定义分群]" not in current_vals:
                current_vals.insert(0, "[自定义分群]")
                self.player_type_combobox['values'] = current_vals

            # 自动帮用户选上
            self.player_type_col.set("[自定义分群]")
            self.status_label.config(text=f"已成功设置 {len(self.custom_segments)} 个自定义用户群", foreground="green")

    def load_columns_for_player_type(self, file_path):
        try:
            try:
                xls = pd.ExcelFile(file_path)
                sheet_names = xls.sheet_names
                if len(sheet_names) > 1:
                    self.selected_sheet_name = ask_sheet_gui(sheet_names, self.master)
                    if not self.selected_sheet_name:
                         self.selected_sheet_name = sheet_names[0] # Fallback to first if cancelled
                else:
                    self.selected_sheet_name = sheet_names[0]
                temp_df = pd.read_excel(xls, sheet_name=self.selected_sheet_name, nrows=0)
            except Exception:
                self.selected_sheet_name = 0
                temp_df = pd.read_excel(file_path, nrows=0)
                
            cleaned_columns = [str(col).replace('\xa0','').strip() for col in temp_df.columns]
            self.player_type_combobox['values'] = cleaned_columns
            if '玩家类型' in cleaned_columns:
                self.player_type_col.set('玩家类型')
            elif cleaned_columns:
                self.player_type_col.set(cleaned_columns[0])
        except Exception as e:
            messagebox.showerror("文件读取错误", f"无法读取文件或其列名: {e}")
            self.player_type_combobox['values'] = []
            self.player_type_col.set("")
            self.status_label.config(text="文件列名加载失败", foreground="red")


    def start_analysis_thread(self):
        input_file = self.file_path.get()
        player_col = self.player_type_col.get()
        min_dur = self.min_duration_var.get()
        # ******** 代码修改处：获取复选框的状态 ********
        run_stats = self.run_stats_test_var.get()

        if not input_file or not player_col:
            messagebox.showwarning("输入错误", "请选择文件和玩家类型列。")
            return
        if self.QUESTION_TYPES is None:
            messagebox.showwarning("输入错误", "请先点击'手动标记题型'按钮完成题型指定。")
            return
        if not isinstance(min_dur, int) or min_dur < 0:
            messagebox.showwarning("输入错误", "最低完成时间必须为非负整数。")
            return

        output_file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            title="选择保存分析结果的位置和文件名"
        )

        if not output_file_path:
            self.status_label.config(text="分析结果保存已取消。", foreground="orange")
            return

        self.process_button.config(state="disabled")
        self.type_marker_button.config(state="disabled")
        self.status_label.config(text="正在加载和分析数据，请稍候...", foreground="blue")
        self.progress_bar.start()

        sheet = self.selected_sheet_name if self.selected_sheet_name is not None else 0
        # ******** 代码修改处：将复选框状态传递给后台线程 ********
        analysis_thread = threading.Thread(target=self._run_analysis_in_thread,
                                           args=(input_file, player_col, min_dur, self.QUESTION_TYPES, output_file_path, run_stats, sheet))
        analysis_thread.start()

    # ******** 代码修改处：_run_analysis_in_thread 接收新参数 ********
    def _run_analysis_in_thread(self, input_file, player_col, min_dur, question_types, output_file_path, run_stats, sheet_name=0):
        try:
            df = pd.read_excel(input_file, sheet_name=sheet_name, header=0)
            df.columns = [str(col).replace('\xa0','').strip() for col in df.columns]
            # ******** 新增代码：注入自定义分群数据处理逻辑 ********
            if player_col == "[自定义分群]" and hasattr(self, 'custom_segments') and self.custom_segments:
                print("--- 正在根据自定义规则给用户打标签 ---")
                df['[自定义分群]'] = np.nan
                for seg_name, conditions in self.custom_segments.items():
                    mask = pd.Series(True, index=df.index)
                    for col_name, val in conditions:
                        if col_name in df.columns:
                            # 严格转换为字符型匹配，防止 Excel 数字/文本混淆
                            mask = mask & (df[col_name].astype(str).str.strip() == str(val).strip())
                    
                    df.loc[mask, '[自定义分群]'] = seg_name
                
                # 剔除掉没有命中任何一个分群规则的用户
                df = df.dropna(subset=['[自定义分群]'])
                if df.empty:
                    raise ValueError("根据您自定义的分群条件，没有匹配到任何真实数据，请检查条件设置是否有冲突。")
            # ******** 新增代码结束 ********

            # ******** 代码修改处：将复选框状态传递给主分析函数 ********
            self.process_survey_data(df, player_col, min_dur, question_types, output_file_path, run_stats)

            self.master.after(0, self._on_analysis_complete, True, output_file_path, None)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.master.after(0, self._on_analysis_complete, False, None, str(e))
        finally:
            if 'df' in locals() and locals()['df'] is not None:
                del locals()['df']
            gc.collect()

    def _on_analysis_complete(self, success, output_file_path, error_message):
        self.process_button.config(state="normal")
        self.type_marker_button.config(state="normal")
        self.progress_bar.stop()
        self.progress_bar['value'] = 0

        if success:
            self.status_label.config(text=f"数据分析完成，结果已保存到 '{os.path.basename(output_file_path)}'。", foreground="green")
            messagebox.showinfo("分析完成", f"数据分析已完成，结果已保存到 '{output_file_path}'。")
        else:
            self.status_label.config(text=f"数据分析失败: {error_message}", foreground="red")
            messagebox.showerror("分析失败", f"数据分析过程中发生错误: {error_message}")


    # ******** 代码修改处：process_survey_data 接收新参数 run_statistical_tests ********
    def process_survey_data(self, df_input, player_type_column_name, min_duration_value, question_types_dict, output_excel_path, run_statistical_tests):
        df = df_input.copy()
        original_df = df_input.copy()
        
        if run_statistical_tests:
            print("--- 统计检验已启用 ---")
        else:
            print("--- 统计检验已禁用，将跳过所有显著性检验计算 ---")

        _original_player_type_col_name = player_type_column_name

        if player_type_column_name not in df.columns:
            raise ValueError(f"选定的玩家类型列 '{player_type_column_name}' 不存在于数据中。")

        if player_type_column_name != '玩家类型':
            df = df.rename(columns={player_type_column_name: '玩家类型'})
        player_type_column_name = '玩家类型'

        df[player_type_column_name] = df[player_type_column_name].astype(str)

        if df.columns.duplicated().any():
            duplicate_cols = df.columns[df.columns.duplicated()].tolist()
            if player_type_column_name in duplicate_cols:
                raise ValueError(f"致命错误：分组列 '{player_type_column_name}' 存在重复。")
            else:
                print(f"警告：数据处理后发现非关键重复列名：{duplicate_cols}。")

        # ------------------- 代码修改处: 使用传入的 question_types_dict -------------------
        # 删除了旧的动态题型识别逻辑
        QUESTION_TYPES = question_types_dict
        
        # 确保玩家类型列本身不被当作问题来分析
        player_col_qnum_str = extract_qnum(_original_player_type_col_name)
        if player_col_qnum_str:
            player_col_qnum_int = int(player_col_qnum_str)
            for q_type_list in QUESTION_TYPES.values():
                if player_col_qnum_int in q_type_list:
                    q_type_list.remove(player_col_qnum_int)
                    print(f"Removed player type column (original name: '{_original_player_type_col_name}', qnum: {player_col_qnum_int}) from question types to avoid analyzing it as a question.")
        # ---------------------------------------------------------------------------------

        # 处理“答题时长（秒）”列
        has_duration_col = '答题时长（秒）' in df.columns
        if has_duration_col:
            # 正常按时长过滤
            df['答题时长（秒）'] = pd.to_numeric(df['答题时长（秒）'], errors='coerce')
            df = df.dropna(subset=['答题时长（秒）'])

            original_total = len(df)
            print(f"\n原始问卷总数: {original_total}份")

            pre_filter = len(df)
            df = df[df['答题时长（秒）'] >= min_duration_value]
            removed = pre_filter - len(df)
            print(f"[1/2]填答时间不足已过滤: {removed}份 剩余: {len(df)}份 "
                  f"有效占比: {(len(df)/pre_filter)*100:.2f}%")
            filter1 = len(df)
        else:
            # 没有这一列时，给出友好提示，允许用户选择“忽略并继续”
            msg = (
                "未找到'答题时长（秒）'列，无法按答题时长进行过滤。\n\n"
                "如果问卷数据本身就没有时长信息，可以选择忽略时长过滤并继续分析。\n\n"
                "是否忽略时长过滤，直接继续分析？\n\n"
                "（是：不按时长过滤；否：中止本次分析）"
            )
            user_choice = messagebox.askyesno("缺少答题时长列", msg)
            if not user_choice:
                raise ValueError("用户取消分析：未找到'答题时长（秒）'列，且选择不忽略该字段。")

            print("\n提示：未找到'答题时长（秒）'列，本次分析已跳过按时长过滤步骤。")
            original_total = len(df)
            pre_filter = len(df)
            filter1 = len(df)

        df = df.dropna(subset=[player_type_column_name])
        removed = filter1 - len(df)
        print(f"[1/2]未分类用户已过滤: {removed}份 剩余: {len(df)}份 "
              f"有效占比: {(len(df)/pre_filter)*100:.2f}%")

        pre_filter = len(df)
        age_cols = df.columns[df.columns.str.contains(r'年龄是?[?？]?$')].tolist()
        occupation_cols = df.columns[df.columns.str.contains(r'职业是?[?？]?$')].tolist()

        if len(age_cols) == 1 and len(occupation_cols) == 1:
            age_col = age_cols[0]
            occupation_col = occupation_cols[0]

            def is_valid(row):
                age = str(row[age_col]).strip()
                occupation = str(row[occupation_col]).strip()
                if age in ['', 'nan', 'None'] or occupation in ['', 'nan', 'None']:
                    return False
                student_occupations = {'1.0', '2.0', '3.0'}
                worker_occupation = {'4.0'}
                if occupation in student_occupations:
                    return age == '1.0'
                elif occupation == '4.0':
                    return age in {'2.0', '3.0', '4.0'}
                else:
                    return True

            mask = df.apply(is_valid, axis=1)
            removed = pre_filter - sum(mask)

            if removed == 0:
                print("\n[逻辑诊断] 年龄职业筛选未生效")
            else:
                df = df[mask]
                print(f"[2/2]年龄职业不匹配已过滤: {removed}份 剩余: {len(df)}份 "
                      f"有效占比: {(len(df)/original_total)*100:.2f}%")
        else:
            print(f"警告：年龄列数量={len(age_cols)}，职业列数量={len(occupation_cols)}，请检查列名")

        print("\n--- Converting Matrix Questions for Analysis ---")
        matrix_single_modules = QUESTION_TYPES.get('矩阵单选', [])
        matrix_rating_modules = QUESTION_TYPES.get('矩阵评分', [])

        if matrix_single_modules:
            converted_matrix_single = convert_matrix_single_questions(df, matrix_single_modules)
            df = pd.concat([df, converted_matrix_single], axis=1)
            print(f"Converted {len(converted_matrix_single.columns)} matrix single-choice columns.")

        if matrix_rating_modules:
            converted_matrix_rating = convert_matrix_rating_questions(df, matrix_rating_modules)
            df = pd.concat([df, converted_matrix_rating], axis=1)
            print(f"Converted {len(converted_matrix_rating.columns)} matrix rating columns.")

        output_dir = os.path.dirname(output_excel_path)
        cleaned_data_output_path = os.path.join(output_dir, "清洗后数据.xlsx")
        df.to_excel(cleaned_data_output_path, index=False, engine='openpyxl')
        print(f"清洗数据已保存 -> {cleaned_data_output_path}")

        all_player_types = sorted(df[player_type_column_name].unique())
        within_sig_matrix_sheets_to_combine = []
        self.sorted_question_options = {}

        results = {}
        fill_sheets = {}
        overall_significance_summary_list = []
        sig_matrix_sheets_to_combine = []
        n_counts_per_question = {}

        print("\n--- Pre-populating Master Option/Sub-item Lists from Original Data ---")
        for q_type, q_nums in QUESTION_TYPES.items():
            for q_num in q_nums:
                q_num_str = str(q_num)
                if q_type == '单选':
                    # 先按“新格式”匹配 (Q<num>.题干)
                    q_cols = [c for c in original_df.columns if str(c).startswith(f'Q{q_num_str}.') and ':' not in str(c)]
                    # 如果新格式没匹配到，再退回到基于 extract_qnum 的“宽松匹配”
                    if not q_cols:
                        q_cols = [c for c in original_df.columns
                                  if extract_qnum(str(c)) == q_num_str and ':' not in str(c)]
                    if q_cols:
                        base_col = q_cols[0]
                        all_options = original_df[base_col].dropna().unique().tolist()
                        self.sorted_question_options[('单选', q_num)] = sorted(all_options, key=lambda x: str(x))
                elif q_type == '多选':
                    # 新格式：Q<num>.题干:选项
                    q_cols = [c for c in original_df.columns if str(c).startswith(f'Q{q_num_str}.') and ':' in str(c)]
                    if q_cols:
                        ordered_options = [extract_option(c, q_num_str) for c in q_cols]
                        self.sorted_question_options[('多选', q_num)] = list(dict.fromkeys(ordered_options))  # 保留顺序去重
                    else:
                        # 兼容旧格式 / 下划线格式：Q<num>_1, Q<num>_2, ...
                        fallback_cols = [c for c in original_df.columns if extract_qnum(str(c)) == q_num_str]
                        if fallback_cols:
                            def _fallback_option_name(col_name: str) -> str:
                                col_str = str(col_name).strip()
                                # 去掉题号前缀及连接符，类似前面题干里的处理
                                name = re.sub(rf'^\s*Q{q_num_str}[\s._\-、，:：]*', '', col_str).strip()
                                return name or col_str

                            ordered_options = [_fallback_option_name(c) for c in fallback_cols]
                            self.sorted_question_options[('多选', q_num)] = list(dict.fromkeys(ordered_options))
                elif q_type == '矩阵评分' or q_type == '矩阵单选':
                    matrix_cols = [c for c in original_df.columns if str(c).startswith(f'Q{q_num_str}.') and ':' in str(c)]
                    all_sub_items = {extract_option(c, q_num_str) for c in matrix_cols}
                    self.sorted_question_options[(q_type, q_num)] = sorted(list(all_sub_items))

        # 单选题分析
        for q in QUESTION_TYPES.get("单选", []):
            q_num_str = str(q)
            # 先尝试新格式 (Q<num>.题干)
            q_cols = [c for c in df.columns if str(c).startswith(f'Q{q_num_str}.') and ':' not in str(c)]
            # 再兼容旧格式 / 下划线格式 (Q<num>、Q<num>_1 等)
            if not q_cols:
                q_cols = [c for c in df.columns
                          if extract_qnum(str(c)) == q_num_str and ':' not in str(c)]
            
            if not q_cols:
                print(f"警告：单选题{q}未找到匹配格式 'Q{q}.题干' 的列，已跳过。")
                continue
            
            # 假设每个单选题只有一个主列
            col = q_cols[0]
            print(f"为单选题{q}选择的列: {col}")

            if not q_cols: continue
            valid = df[[col, player_type_column_name]].dropna(subset=[col, player_type_column_name])
            n_counts = valid[player_type_column_name].value_counts()
            n_counts_per_question[f"单选题_{q}_二维透视"] = n_counts
            grouped = valid.groupby([player_type_column_name, col], observed=True).size().reset_index(name='选择人数')
            totals = valid.groupby(player_type_column_name, observed=True).size().reset_index(name='总人数')
            merged = grouped.merge(totals, on=player_type_column_name)
            merged['选择人数占比'] = (merged['选择人数'] / merged['总人数']).round(3)
            res = merged.rename(columns={col: '选项内容'})[['玩家类型', '选项内容', '选择人数', '选择人数占比']]
            pivot_df = res.pivot_table(index='选项内容', columns=player_type_column_name, values='选择人数占比', aggfunc='first', fill_value=0).reset_index().rename_axis(None, axis=1)
            col_name = valid[col].name
            total_counts = valid[col].value_counts().reset_index(name='人数').rename(columns={col_name: '选项内容'})
            total_percent = valid[col].value_counts(normalize=True).reset_index(name='总计').rename(columns={col_name: '选项内容'})
            total_ratio = total_counts.merge(total_percent, on='选项内容')
            pivot_df = pivot_df.merge(total_ratio[['选项内容','人数','总计']], on='选项内容', how='outer')
            for p_type in all_player_types:
                if p_type not in pivot_df.columns:
                    pivot_df[p_type] = 0.0
            core_columns = ['选项内容']
            tail_columns = ['总计', '人数']
            pivot_df = pivot_df[core_columns + all_player_types + tail_columns]
            numeric_cols_to_fill = [c for c in pivot_df.columns if c != '选项内容']
            pivot_df[numeric_cols_to_fill] = pivot_df[numeric_cols_to_fill].fillna(0)
            
            # ******** 代码修改处：根据复选框状态决定是否执行检验 ********
            if run_statistical_tests:
                test_result = pd.DataFrame()
                overall_p = np.nan
                overall_test_type = ''
                overall_effect_size = np.nan
                sig_pair_str = '无'
                crosstab_for_overall = pd.crosstab(valid[col], valid[player_type_column_name])
                if crosstab_for_overall.empty or crosstab_for_overall.shape[0] < 2 or crosstab_for_overall.shape[1] < 2:
                    test_result = pd.DataFrame({'错误信息': [f"数据不足，无法对单选题 {q} 进行显著性检验。"], '各组样本量': [str(dict(valid[player_type_column_name].value_counts()))]})
                else:
                    try:
                        chi2, p, dof, expected = stats.chi2_contingency(crosstab_for_overall)[:4]
                        overall_p = p
                        overall_test_type = '卡方检验'
                        overall_effect_size = calculate_cramers_v(crosstab_for_overall)
                        test_result = pd.DataFrame({'题号': [q], '检验类型': ['卡方检验'], '统计量': [chi2], 'p值': [p], '自由度': [dof], '效应量': [overall_effect_size]})
                        if p < 0.05:
                            posthoc_res = []
                            player_types_test = valid[player_type_column_name].unique()
                            player_types_test.sort()
                            pairs = list(combinations(player_types_test, 2))
                            for g1, g2 in pairs:
                                subset = valid[valid[player_type_column_name].isin([g1, g2])]
                                sub_crosstab = pd.crosstab(subset[col], subset[player_type_column_name])
                                if not sub_crosstab.empty and sub_crosstab.shape[0] > 1 and sub_crosstab.shape[1] > 1:
                                    try:
                                        if sub_crosstab.shape == (2,2):
                                            _, p_val_pair = fisher_exact(sub_crosstab)
                                        else:
                                            _, p_val_pair, _, _ = stats.chi2_contingency(sub_crosstab)
                                        cramer_v_val = calculate_cramers_v(sub_crosstab)
                                        posthoc_res.append({'组别1':g1, '组别2':g2, '原始p值':p_val_pair, '效应量': cramer_v_val})
                                    except Exception as e_inner:
                                        print(f"WARNING: Single choice {q} pairwise chi2/fisher for {g1} vs {g2} failed: {e_inner}")
                                        posthoc_res.append({'组别1':g1, '组别2':g2, '原始p值':np.nan, '效应量': np.nan})
                                else:
                                    posthoc_res.append({'组别1':g1, '组别2':g2, '原始p值':np.nan, '效应量': np.nan})
                            df_post = pd.DataFrame(posthoc_res)
                            if not df_post.empty:
                                valid_p_values = df_post['原始p值'].dropna()
                                if not valid_p_values.empty:
                                    reject, pvals_corrected_fdr, _, _ = multipletests(valid_p_values, method='fdr_bh')
                                    df_post['校正后p值'] = np.nan
                                    df_post.loc[df_post['原始p值'].notna(), '校正后p值'] = pvals_corrected_fdr
                                else:
                                    df_post['校正后p值'] = np.nan
                                df_post['显著性'] = ''
                                for i in range(len(df_post)):
                                    p_corrected = df_post.loc[i, '校正后p值']
                                    effect_size = df_post.loc[i, '效应量']
                                    sig_str = ''
                                    if pd.notna(p_corrected):
                                        if p_corrected < 0.001: sig_str = '***'
                                        elif p_corrected < 0.01: sig_str = '**'
                                        elif p_corrected < 0.05: sig_str = '*'
                                    if sig_str:
                                        df_post.loc[i, '显著性'] = f"{sig_str} ({effect_size:.2f})"
                                    else:
                                        df_post.loc[i, '显著性'] = sig_str
                                test_result = pd.concat([test_result, df_post])
                    except Exception as e:
                        print(f"WARNING: Overall chi2 test for Single choice {q} failed: {e}")
                        test_result = pd.DataFrame({'错误信息': [f"总检验失败: {e}"], '各组样本量': [str(dict(valid[player_type_column_name].value_counts()))]})
                
                results[f"检验结果_单选_{q}"] = test_result
                
                sig_matrix = pd.DataFrame('', index=all_player_types, columns=all_player_types)
                if not test_result.empty and '组别1' in test_result.columns and '组别2' in test_result.columns:
                    pairwise_results = test_result[test_result['组别1'].notna()]
                    if not pairwise_results.empty:
                        for _, row in pairwise_results.iterrows():
                            g1, g2 = row['组别1'], row['组别2']
                            sig = row['显著性'] if isinstance(row['显著性'], str) and row['显著性'] else ''
                            if g1 in sig_matrix.index and g2 in sig_matrix.columns:
                                sig_matrix.loc[g1, g2] = sig
                            if g2 in sig_matrix.index and g1 in sig_matrix.columns:
                                sig_matrix.loc[g2, g1] = sig
                if len(all_player_types) >= 2:
                    sig_matrix.index.name = f"{player_type_column_name}_Group1"
                    sig_matrix.columns.name = f"{player_type_column_name}_Group2"
                    sig_matrix_sheets_to_combine.append({'name': f"显著性表_单选_{q}", 'data': sig_matrix, 'q_type': '单选', 'main_q_for_sort': q, 'sub_q_for_sort': '', 'option_part': '', 'display_title': clean_question_stem(get_question_stem(original_df, q)) + f" (单选 - 组间显著性差异)", 'post_hoc_test_type': overall_test_type if pd.notna(overall_test_type) else 'Chi2/Fisher'})

                if not test_result.empty and '显著性' in test_result.columns and '组别1' in test_result.columns:
                    significant_pairs_df = test_result[test_result['显著性'].astype(str).str.startswith('*', na=False) & test_result['组别1'].notna()]
                    sig_pair_str = '; '.join([f"{row['组别1']} vs {row['组别2']}{row['显著性']}" for _, row in significant_pairs_df.iterrows()]) if not significant_pairs_df.empty else '无'
                else:
                    sig_pair_str = '无'
            else: # 如果不执行检验
                overall_p, overall_test_type, overall_effect_size, sig_pair_str = np.nan, '已跳过', np.nan, '已跳过'
            
            # 无论是否检验，都保留透视表
            results[f"单选题_{q}_二维透视"] = pivot_df

            overall_significance_summary_list.append({'题号': q, '题干': clean_question_stem(get_question_stem(original_df, q)), '题型': '单选', '总检验类型': overall_test_type, '总检验p值': overall_p, '总检验显著性': (lambda p: '***' if p < 0.001 else ('**' if p < 0.01 else ('*' if p < 0.05 else '')))(overall_p) if pd.notna(overall_p) else '' if overall_test_type != '已跳过' else '已跳过', '总检验效应量': overall_effect_size if pd.notna(overall_effect_size) else np.nan, '显著差异组对': sig_pair_str})

            # ========== 代码修改处 开始 (为单选题添加填空项处理) ==========
            # 新格式下，填空项可能是独立的 "填空题"，也可能是在单选题选项中。此逻辑保持不变。
            fill_cols = [c for c in df.columns if extract_qnum(c) == str(q) and "填空项" in c and df[c].dtype == 'object']
            if fill_cols:
                fill_res_list = []
                for fill_col in fill_cols:
                    option_match = re.search(r'（(.*?)）', fill_col)
                    option = option_match.group(1).strip() if option_match else '其他'

                    # 提取玩家类型和答案
                    temp_data = df[[player_type_column_name, fill_col]].copy()
                    temp_data.rename(columns={fill_col: '答案内容'}, inplace=True)
                    temp_data['答案内容'] = temp_data['答案内容'].astype(str).str.strip()

                    # 过滤空答案
                    filtered_data = temp_data[~temp_data['答案内容'].isin(['', 'nan'])].copy()

                    if not filtered_data.empty:
                        filtered_data['题目选项'] = option
                        final_temp_df = filtered_data[[player_type_column_name, '题目选项', '答案内容']]
                        fill_res_list.append(final_temp_df)

                if fill_res_list:
                    fill_res = pd.concat(fill_res_list, ignore_index=True)
                    fill_sheets[f"填空项_单选_{q}"] = fill_res
            # ========== 代码修改处 结束 ==========

        # 评分题分析
        for q in QUESTION_TYPES.get("评分", []):
            q_num_str = str(q)
            q_cols = [c for c in df.columns if str(c).startswith(f'Q{q_num_str}.') and ':' not in str(c)]
            q_cols = [c for c in q_cols if pd.api.types.is_numeric_dtype(df[c])]

            if q_cols:
                col = q_cols[0]
            else:
                print(f"警告：评分题{q}未找到有效数值列（格式 Q{q}.题干），已跳过。")
                continue

            required_columns = [player_type_column_name, col]
            valid = df[required_columns].dropna(subset=[col])
            valid[col] = pd.to_numeric(valid[col], errors='coerce')
            valid = valid.dropna(subset=[col])
            valid = valid[valid[col] != 0]
            valid = valid.dropna(subset=[player_type_column_name])
            if valid[col].empty:
                print(f"警告：评分题{q}无有效数据，跳过处理")
                continue
            n_counts = valid[player_type_column_name].value_counts()
            n_counts_per_question[f"评分题_{q}_二维表"] = n_counts
            col_cleaned = col.strip().replace('\xa0', '').replace('\u200b', '')
            count_matrix = valid.groupby([player_type_column_name, col_cleaned], observed=True).size().unstack(fill_value=0)
            count_matrix.columns = pd.to_numeric(count_matrix.columns)
            count_matrix = count_matrix.sort_index(axis=1)
            total_counts = count_matrix.sum(axis=1)
            dist_pct = count_matrix.div(total_counts, axis=0)
            avg_srs = valid.groupby(player_type_column_name, observed=True)[col_cleaned].mean()
            result_list = []
            for player_type in count_matrix.index:
                for score in count_matrix.columns:
                    result_list.append({'玩家类型': player_type, '评分项': str(score), '值': dist_pct.loc[player_type, score]})
                result_list.append({'玩家类型': player_type, '评分项': '平均分', '值': avg_srs[player_type]})
            result_df = pd.DataFrame(result_list)
            pivot_df = result_df.pivot_table(index='评分项', columns='玩家类型', values='值', aggfunc='first', fill_value=0).reset_index()
            pivot_df['排序键'] = pivot_df['评分项'].apply(lambda x: int(x) if x.isdigit() else float('inf'))
            pivot_df = pivot_df.sort_values('排序键').drop('排序键', axis=1)
            pivot_df.reset_index(drop=True, inplace=True)
            valid_col = valid[col_cleaned]
            score_counts_num = valid_col.value_counts().sort_index().reset_index()
            score_counts_num.columns = ['评分项', '人数']
            score_counts_pct = valid_col.value_counts(normalize=True).sort_index().reset_index()
            score_counts_pct.columns = ['评分项', '总计']
            score_counts_num['评分项'] = score_counts_num['评分项'].astype(str)
            score_counts_pct['评分项'] = score_counts_pct['评分项'].astype(str)
            score_counts = score_counts_num.merge(score_counts_pct, on='评分项')
            avg_total = pd.DataFrame({'评分项': ['平均分'], '人数': valid_col.count(), '总计': valid_col.mean()})
            total_dist = pd.concat([score_counts, avg_total], ignore_index=True)
            pivot_df = pivot_df.merge(total_dist, on='评分项', how='left')
            for p_type in all_player_types:
                if p_type not in pivot_df.columns:
                    pivot_df[p_type] = 0.0
            pivot_df = pivot_df[['评分项'] + all_player_types + ['总计', '人数']]
            pivot_df = pivot_df.fillna(0)
            pivot_df.replace([np.inf, -np.inf], 0, inplace=True)
            pivot_df.iloc[:, 1:] = pivot_df.iloc[:, 1:].apply(pd.to_numeric)
            
            # ******** 代码修改处：根据复选框状态决定是否执行检验 ********
            if run_statistical_tests:
                test_res = pd.DataFrame()
                overall_p = np.nan
                overall_test_type = ''
                overall_effect_size = np.nan
                sig_pair_str = '无'
                if len(valid[player_type_column_name].unique()) > 1:
                    groups = valid[player_type_column_name].unique()
                    group_data = [valid[valid[player_type_column_name] == g][col_cleaned].dropna() for g in groups]
                    group_sizes = [len(g) for g in group_data]
                    min_size = min(group_sizes)
                    filtered_groups = [g for g in group_data if len(g) >= 2]
                    if len(filtered_groups) < 2:
                        test_res = pd.DataFrame({'错误信息': [f"数据不足，无法对评分题 {q} 进行显著性检验（至少需要两个组各2个样本）。"], '各组样本量': [str(dict(valid[player_type_column_name].value_counts()))]})
                    else:
                        try:
                            normality = []
                            for g in filtered_groups:
                                if len(g) >= 8:
                                    _, p_norm = normaltest(g)
                                    normality.append(p_norm > 0.05)
                                else:
                                    normality.append(True)
                            if len(filtered_groups) >= 2 and all(len(g) >= 2 for g in filtered_groups):
                                _, levene_p = levene(*filtered_groups)
                            else:
                                levene_p = 1.0
                            if all(normality) and levene_p > 0.05 and min_size >= 3:
                                f_val, p_val = f_oneway(*filtered_groups)
                                overall_test_type = 'ANOVA'
                                overall_p = p_val
                                overall_effect_size = calculate_eta_squared_anova(filtered_groups)
                            else:
                                if len(filtered_groups) >= 2 and min_size >= 3:
                                    h_val, p_val = kruskal(*filtered_groups)
                                    overall_test_type = 'Kruskal-Wallis'
                                    overall_p = p_val
                                    overall_effect_size = calculate_eta_squared_kruskal(h_val, len(filtered_groups), sum(len(g) for g in filtered_groups))
                                else:
                                    raise ValueError(f"样本量不足：最小组样本数={min_size}（需要≥3）")
                            test_res = pd.DataFrame({'题号': [q], '检验类型': [overall_test_type], '统计量': [round(f_val if overall_test_type=='ANOVA' else h_val, 4)], 'p值': [overall_p], '效应量': [overall_effect_size]})
                            if overall_p < 0.05 and min_size >= 3:
                                posthoc_df = pd.DataFrame()
                                if overall_test_type == 'ANOVA':
                                    tukey = pairwise_tukeyhsd(endog=valid[col_cleaned], groups=valid[player_type_column_name], alpha=0.05)
                                    tukey_df = pd.DataFrame(tukey._results_table.data[1:], columns=['组别1','组别2','均值差','p值','下限','上限','拒绝'])
                                    tukey_df['校正后p值'] = tukey_df['p值'].astype(float)
                                    posthoc_df = tukey_df
                                else:
                                    dunn_res_df = posthoc_dunn(valid, val_col=col_cleaned, group_col=player_type_column_name, p_adjust='fdr_bh').stack().reset_index()
                                    dunn_res_df.columns = ['组别1','组别2','校正后p值']

                                posthoc_df['校正后p值'] = posthoc_df['校正后p值'].apply(lambda x: max(0, min(1, float(x))))
                                posthoc_df['显著性'] = ''
                                for i, row in posthoc_df.iterrows():
                                    p_corrected = row['校正后p值']
                                    g1, g2 = row['组别1'], row['组别2']
                                    data1 = valid[valid[player_type_column_name] == g1][col_cleaned].dropna()
                                    data2 = valid[valid[player_type_column_name] == g2][col_cleaned].dropna()
                                    effect_size = np.nan
                                    if overall_test_type == 'ANOVA':
                                        if len(data1) > 1 and len(data2) > 1:
                                            effect_size = calculate_cohens_d(data1, data2)
                                    else:
                                        if len(data1) > 0 and len(data2) > 0:
                                            effect_size = calculate_rank_biserial_correlation(data1, data2)
                                    posthoc_df.loc[i, '效应量'] = effect_size
                                    sig_str = ''
                                    if pd.notna(p_corrected):
                                        if p_corrected < 0.001: sig_str = '***'
                                        elif p_corrected < 0.01: sig_str = '**'
                                        elif p_corrected < 0.05: sig_str = '*'

                                    if sig_str:
                                        direction_arrow = get_direction_arrow(np.mean(data1), np.mean(data2))
                                        posthoc_df.loc[i, '显著性'] = f"{direction_arrow} {sig_str} ({effect_size:.2f})"
                                    else:
                                        posthoc_df.loc[i, '显著性'] = ''
                                test_res = pd.concat([test_res, posthoc_df])

                            if not test_res.empty and '显著性' in test_res.columns and '组别1' in test_res.columns:
                                significant_pairs_df = test_res[test_res['显著性'].astype(str).str.contains(r'\*', na=False) & test_res['组别1'].notna()]
                                sig_pair_str = '; '.join([f"{row['组别1']} vs {row['组别2']}{row['显著性']}" for _, row in significant_pairs_df.iterrows()]) if not significant_pairs_df.empty else '无'
                        except Exception as e:
                            print(f"评分题{q}统计检验失败: {str(e)}")
                            test_res = pd.DataFrame({'错误信息': [f"检验失败: {str(e)}"], '各组样本量': [str(dict(valid[player_type_column_name].value_counts()))]})
                
                results[f"检验结果_评分_{q}"] = test_res

                sig_matrix = pd.DataFrame('', index=all_player_types, columns=all_player_types)
                if not test_res.empty and '组别1' in test_res.columns and '组别2' in test_res.columns:
                    pairwise_results = test_res[test_res['组别1'].notna()]
                    if not pairwise_results.empty:
                        for _, row in pairwise_results.iterrows():
                            g1, g2 = row['组别1'], row['组别2']
                            sig = row['显著性'] if isinstance(row['显著性'], str) and row['显著性'] else ''
                            if g1 in sig_matrix.index and g2 in sig_matrix.columns:
                                sig_matrix.loc[g1, g2] = sig
                            if g2 in sig_matrix.index and g1 in sig_matrix.columns:
                                if '▲' in sig: inv_sig = sig.replace('▲', '▼')
                                elif '▼' in sig: inv_sig = sig.replace('▼', '▲')
                                else: inv_sig = sig
                                sig_matrix.loc[g2, g1] = inv_sig
                if len(all_player_types) >= 2:
                    sig_matrix.index.name = f"{player_type_column_name}_Group1"
                    sig_matrix.columns.name = f"{player_type_column_name}_Group2"
                    sig_matrix_sheets_to_combine.append({'name': f"显著性表_评分_{q}", 'data': sig_matrix, 'q_type': '评分', 'main_q_for_sort': q, 'sub_q_for_sort': '', 'option_part': '', 'display_title': clean_question_stem(get_question_stem(original_df, q)) + f" (评分 - 组间显著性差异)", 'post_hoc_test_type': overall_test_type})
            else: # 如果不执行检验
                overall_p, overall_test_type, overall_effect_size, sig_pair_str = np.nan, '已跳过', np.nan, '已跳过'
            
            results[f"评分题_{q}_二维表"] = pivot_df
            overall_significance_summary_list.append({'题号': q, '题干': clean_question_stem(get_question_stem(original_df, q)), '题型': '评分', '总检验类型': overall_test_type, '总检验p值': overall_p, '总检验显著性': (lambda p: '***' if p < 0.001 else ('**' if p < 0.01 else ('*' if p < 0.05 else '')))(overall_p) if pd.notna(overall_p) else '' if overall_test_type != '已跳过' else '已跳过', '总检验效应量': overall_effect_size if pd.notna(overall_effect_size) else np.nan, '显著差异组对': sig_pair_str})


        # 多选题分析
        for q in QUESTION_TYPES.get("多选", []):
            q_num_str = str(q)
            # 新格式：Q<num>.题干:选项
            q_cols = [c for c in df.columns if str(c).startswith(f'Q{q_num_str}.') and ':' in str(c)]
            if not q_cols:
                # 兼容旧格式 / 下划线格式：所有题号为 q 的列都视为选项列
                q_cols = [c for c in df.columns if extract_qnum(str(c)) == q_num_str]
            
            option_order = self.sorted_question_options.get(('多选', q), [])

            # 根据列名和 option_order 建立“选项 -> 列名”的映射
            option_to_col = {}
            for c in q_cols:
                col_str = str(c).strip()
                if ':' in col_str:
                    opt_name = extract_option(col_str, q_num_str)
                else:
                    # 下划线等旧格式，从列名中去掉题号前缀得到选项名
                    opt_name = re.sub(rf'^\s*Q{q_num_str}[\s._\-、，:：]*', '', col_str).strip() or col_str
                option_to_col[opt_name] = c

            if not option_order or not option_to_col:
                print(f"警告：多选题{q}无有效选项列，跳过处理")
                continue

            analysis_df = df[[player_type_column_name] + list(option_to_col.values())].copy()
            for col in option_to_col.values():
                analysis_df[col] = pd.to_numeric(analysis_df[col], errors='coerce').fillna(0)
            valid_mask = analysis_df[list(option_to_col.values())].sum(axis=1) > 0
            analysis_df = analysis_df[valid_mask]

            if analysis_df.empty:
                print(f"警告：多选题{q}无有效回答，跳过处理")
                continue

            n_counts = analysis_df[player_type_column_name].value_counts()
            n_counts_per_question[f"多选题_{q}_分类型"] = n_counts
            total_valid = analysis_df.shape[0]
            melted = analysis_df.melt(id_vars=player_type_column_name, value_vars=list(option_to_col.values()), var_name='选项内容', value_name='是否选择').query('是否选择 > 0')
            melted['选项内容'] = melted['选项内容'].apply(lambda x: next((opt for opt, col_name in option_to_col.items() if col_name == x), x))
            type_counts = analysis_df[player_type_column_name].value_counts()
            grouped = melted.groupby([player_type_column_name, '选项内容'], observed=True).size().reset_index(name='_tmp')
            grouped['分类型占比'] = grouped.apply(lambda x: round(x['_tmp'] / type_counts.get(x[player_type_column_name], 1), 4), axis=1)
            total_ratio = melted['选项内容'].value_counts().reset_index(name='人数')
            total_ratio['总计'] = (total_ratio['人数'] / total_valid).round(4)
            total_ratio = total_ratio[total_ratio['选项内容'].isin(option_order)]
            pivot_table = grouped.pivot_table(index='选项内容', columns=player_type_column_name, values='分类型占比', fill_value=0).reset_index()
            final_table = pivot_table.merge(total_ratio[['选项内容', '人数', '总计']], on='选项内容', how='outer')
            final_table['选项内容'] = pd.Categorical(final_table['选项内容'], categories=option_order, ordered=True)
            final_table = final_table.sort_values('选项内容').reset_index(drop=True)
            for p_type in all_player_types:
                if p_type not in final_table.columns:
                    final_table[p_type] = 0.0
            core_columns = ['选项内容']
            tail_columns = ['总计', '人数']
            final_table = final_table[core_columns + all_player_types + tail_columns]
            numeric_cols_to_fill = [c for c in final_table.columns if c != '选项内容']
            final_table[numeric_cols_to_fill] = final_table[numeric_cols_to_fill].fillna(0)
            results[f"多选题_{q}_分类型"] = final_table

            # ******** 代码修改处：根据复选框状态决定是否执行检验 ********
            if run_statistical_tests:
                all_test_results = []
                overall_sig_multi_choice = 'No'
                sig_pair_str_multi_choice = []
                for option in option_order:
                    option_str = str(option).strip() if pd.notnull(option) else ""
                    col_name_test = option_to_col.get(option_str, None)
                    if not col_name_test or col_name_test not in df.columns: continue
                    contingency_table = pd.crosstab(df[player_type_column_name], df[col_name_test])
                    if contingency_table.empty or contingency_table.shape[0] < 2 or contingency_table.shape[1] < 2:
                        all_test_results.append({'题号': q, '选项': option, '原始p值': np.nan, '检验类型': '数据不足', '统计量': np.nan, '理论频数': None, '效应量': np.nan})
                        continue
                    try:
                        chi2, p_chi, dof, expected = stats.chi2_contingency(contingency_table)[:4]
                        p_val = p_chi
                        stat_val = chi2
                        test_type = '卡方检验'
                        option_effect_size = calculate_cramers_v(contingency_table)
                        if contingency_table.shape == (2,2) and contingency_table.min().min() < 5:
                            try:
                                oddsratio, p_fish = fisher_exact(contingency_table)
                                p_val = p_fish
                                stat_val = oddsratio
                                test_type = '费舍尔精确检验'
                                option_effect_size = calculate_cramers_v(contingency_table)
                            except (ValueError, NotImplementedError) as e_fish:
                                print(f"WARNING: Multi-choice {q} option {option} Fisher exact for {e_fish}")
                                pass
                        all_test_results.append({'题号': q, '选项': option, '原始p值': p_val, '检验类型': test_type, '统计量': stat_val, '理论频数': expected, '效应量': option_effect_size})
                    except Exception as e:
                        print(f"题{q}选项{option}检验失败：{str(e)}")
                        all_test_results.append({'题号': q, '选项': option, '原始p值': np.nan, '检验类型': f"错误: {type(e).__name__}", '统计量': np.nan, '理论频数': None, '效应量': np.nan})
                        continue
                test_df = pd.DataFrame(all_test_results)
                # ========== 在这里添加修复代码 ==========
                if '显著性' not in test_df.columns:
                    test_df['显著性'] = ''
                if not test_df.empty and '原始p值' in test_df.columns:
                    pvals_for_correction = test_df['原始p值'].dropna()
                    if not pvals_for_correction.empty:
                        reject, pvals_corrected_fdr, _, _ = multipletests(pvals_for_correction, method='fdr_bh')
                        corrected_idx = 0
                        for i, row_data in enumerate(all_test_results):
                            if pd.notna(row_data['原始p值']):
                                all_test_results[i]['校正后p值'] = pvals_corrected_fdr[corrected_idx]
                                corrected_idx += 1
                            else:
                                all_test_results[i]['校正后p值'] = np.nan
                            sig_str = ''
                            if pd.notna(all_test_results[i]['校正后p值']):
                                if all_test_results[i]['校正后p值'] < 0.001: sig_str = '***'
                                elif all_test_results[i]['校正后p值'] < 0.01: sig_str = '**'
                                elif all_test_results[i]['校正后p值'] < 0.05: sig_str = '*'
                            effect_size_val = all_test_results[i]['效应量']
                            if sig_str:
                                all_test_results[i]['显著性'] = f"{sig_str} ({effect_size_val:.2f})"
                            else:
                                all_test_results[i]['显著性'] = ''
                test_df = pd.DataFrame(all_test_results)
                if '显著性' not in test_df.columns:
                    test_df['显著性'] = ''
                posthoc_data = []
                if not test_df.empty and any(test_df['显著性'].astype(str).str.contains(r'\*', na=False)):
                    for idx, row in test_df.iterrows():
                        if isinstance(row['显著性'], str) and '*' in row['显著性'] and pd.notna(row['选项']):
                            option = row['选项']
                            col_name_posthoc = option_to_col.get(option, None)
                            if not col_name_posthoc: continue
                            counts = df.groupby(player_type_column_name)[col_name_posthoc].agg(['sum', 'count'])
                            counts = counts[counts['count'] > 0]
                            counts['未选择'] = counts['count'] - counts['sum']
                            groups_for_posthoc = counts.index.tolist()
                            groups_for_posthoc.sort()
                            pairs = list(combinations(groups_for_posthoc, 2))
                            for g1, g2 in pairs:
                                k1, n1 = counts.loc[g1, 'sum'], counts.loc[g1, 'count']
                                k2, n2 = counts.loc[g2, 'sum'], counts.loc[g2, 'count']
                                if n1 == 0 or n2 == 0:
                                    posthoc_data.append({'题号': q, '选项': option, '组别1': g1, '组别2': g2, '原始p值': np.nan, '检验类型': '数据不足', '校正后p值': np.nan, '显著性': '', '效应量': np.nan, '方向':''})
                                    continue
                                table = [[k1, n1 - k1], [k2, n2 - k2]]
                                try:
                                    _, p_val_fish_p = fisher_exact(table)
                                    cramer_v_pairwise = calculate_cramers_v(pd.DataFrame(table))
                                    prop1 = k1/n1 if n1 > 0 else 0
                                    prop2 = k2/n2 if n2 > 0 else 0
                                    direction_arrow = get_direction_arrow(prop1, prop2)
                                    posthoc_data.append({'题号': q, '选项': option, '组别1': g1, '组别2': g2, '原始p值': p_val_fish_p, '检验类型': '费舍尔精确检验', '效应量': cramer_v_pairwise, '方向': direction_arrow})
                                except Exception as e_fish:
                                    print(f"WARNING: Multi-choice {q} option {option} Fisher exact for {g1} vs {g2} failed: {e_fish}")
                                    posthoc_data.append({'题号': q, '选项': option, '组别1': g1, '组别2': g2, '原始p值': np.nan, '检验类型': f"错误: {type(e_fish).__name__}", '校正后p值': np.nan, '显著性': '', '效应量': np.nan, '方向': ''})
                if posthoc_data:
                    df_posthoc = pd.DataFrame(posthoc_data)
                    if '原始p值' in df_posthoc.columns:
                        pvals_for_correction_posthoc = df_posthoc['原始p值'].dropna()
                        if not pvals_for_correction_posthoc.empty:
                            reject_posthoc, pvals_corrected_fdr_posthoc, _, _ = multipletests(pvals_for_correction_posthoc, method='fdr_bh')
                            corrected_idx_posthoc = 0
                            for i in range(len(df_posthoc)):
                                if pd.notna(df_posthoc.loc[i, '原始p值']):
                                    df_posthoc.loc[i, '校正后p值'] = pvals_corrected_fdr_posthoc[corrected_idx_posthoc]
                                    corrected_idx_posthoc += 1
                                else:
                                    df_posthoc.loc[i, '校正后p值'] = np.nan
                                sig_str_posthoc = ''
                                if pd.notna(df_posthoc.loc[i, '校正后p值']):
                                    if df_posthoc.loc[i, '校正后p值'] < 0.001: sig_str_posthoc = '***'
                                    elif df_posthoc.loc[i, '校正后p值'] < 0.01: sig_str_posthoc = '**'
                                    elif df_posthoc.loc[i, '校正后p值'] < 0.05: sig_str_posthoc = '*'
                                effect_size_val_posthoc = df_posthoc.loc[i, '效应量']
                                direction = df_posthoc.loc[i, '方向']
                                if sig_str_posthoc:
                                    df_posthoc.loc[i, '显著性'] = f"{direction} {sig_str_posthoc} ({effect_size_val_posthoc:.2f})"
                                else:
                                    df_posthoc.loc[i, '显著性'] = ''
                    test_df = pd.concat([test_df, df_posthoc], ignore_index=True)
                    test_df = test_df.drop_duplicates(subset=['题号', '选项', '组别1', '组别2'], keep='last')
                else:
                    test_df = pd.DataFrame(columns=['题号','选项','检验类型','统计量','原始p值','校正后p值','显著性','组别1','组别2','效应量'])
                results[f"检验结果_多选_{q}"] = test_df

                for opt in option_order:
                    sig_matrix = pd.DataFrame('', index=all_player_types, columns=all_player_types)
                    if not test_df.empty:
                        pairwise_results_for_option = test_df[(test_df['选项'] == opt) & test_df['组别1'].notna()]
                        if not pairwise_results_for_option.empty:
                            for _, row in pairwise_results_for_option.iterrows():
                                g1, g2 = row['组别1'], row['组别2']
                                sig = row['显著性'] if isinstance(row['显著性'], str) and row['显著性'] else ''
                                if g1 in sig_matrix.index and g2 in sig_matrix.columns:
                                    sig_matrix.loc[g1, g2] = sig
                                if g2 in sig_matrix.index and g1 in sig_matrix.columns:
                                    if '▲' in sig: inv_sig = sig.replace('▲', '▼')
                                    elif '▼' in sig: inv_sig = sig.replace('▼', '▲')
                                    else: inv_sig = sig
                                    sig_matrix.loc[g2, g1] = inv_sig

                    if len(all_player_types) >= 2:
                        sig_matrix.index.name = f"{player_type_column_name}_Group1"
                        sig_matrix.columns.name = f"{player_type_column_name}_Group2"
                        sig_matrix_sheets_to_combine.append({
                            'name': f"显著性表_多选_{q}_选项_{clean_sheet_name(str(opt))}", 
                            'data': sig_matrix, 
                            'q_type': '多选', 
                            'main_q_for_sort': q, 
                            'sub_q_for_sort': '', 
                            'option_part': str(opt), 
                            'display_title': clean_question_stem(get_question_stem(original_df, q)) + f" (选项: {str(opt)}) (多选 - 组间显著性差异)", 
                            'post_hoc_test_type': 'Chi2/Fisher'
                        })

                if not test_df.empty and '显著性' in test_df.columns:
                    significant_pairwise_results = test_df[test_df['显著性'].astype(str).str.contains(r'\*', na=False) & test_df['组别1'].notna()]
                    if not significant_pairwise_results.empty:
                        overall_sig_multi_choice = 'Yes'
                        for opt, group_df in significant_pairwise_results.groupby('选项'):
                            # sig_pair_str_multi_choice.append(f"选项{opt}: {'; '.join([f'{r_p['组别1']} vs {r_p['组别2']}{r_p['显著性']}' for _, r_p in group_df.iterrows() if r_p['显著性']])}")
                            # 修复方案3：拆分逻辑，先构建内部列表
                            inner_list = [f"{r_p['组别1']} vs {r_p['组别2']}{r_p['显著性']}" for _, r_p in group_df.iterrows() if r_p['显著性']]
                            sig_pair_str_multi_choice.append(f"选项{opt}: {'; '.join(inner_list)}")
            else: # 如果不执行检验
                overall_sig_multi_choice = '已跳过'
                sig_pair_str_multi_choice = ['已跳过']


            overall_significance_summary_list.append({'题号': q, '题干': clean_question_stem(get_question_stem(original_df, q)), '题型': '多选', '总检验类型': 'Fisher/Chi2 (按选项)' if run_statistical_tests else '已跳过', '总检验p值': np.nan, '总检验显著性': overall_sig_multi_choice, '总检验效应量': np.nan, '显著差异组对': '; '.join(sig_pair_str_multi_choice) if sig_pair_str_multi_choice else '无'})

            # ========== 代码修改处 开始 (修改多选题的填空项处理逻辑) ==========
            # 新格式下，填空项可能是独立的 "填空题"，也可能是在多选题选项中。此逻辑保持不变。
            fill_cols = [c for c in df.columns if extract_qnum(c) == str(q) and "填空项" in c and df[c].dtype == 'object']
            if fill_cols:
                fill_res_list = []
                for fill_col in fill_cols:
                    option_match = re.search(r'（(.*?)）', fill_col)
                    option = option_match.group(1) if option_match else '其他'

                    # 提取玩家类型和答案
                    temp_data = df[[player_type_column_name, fill_col]].copy()
                    temp_data.rename(columns={fill_col: '答案内容'}, inplace=True)
                    temp_data['答案内容'] = temp_data['答案内容'].astype(str).str.strip()

                    # 过滤空答案
                    filtered_data = temp_data[~temp_data['答案内容'].isin(['', 'nan'])].copy()

                    if not filtered_data.empty:
                        filtered_data['题目选项'] = option
                        # 调整列顺序以包含玩家类型
                        final_temp_df = filtered_data[[player_type_column_name, '题目选项', '答案内容']]
                        fill_res_list.append(final_temp_df)

                if fill_res_list:
                    fill_res = pd.concat(fill_res_list, ignore_index=True)
                    # 使用更明确的工作表名称以避免冲突
                    fill_sheets[f"填空项_多选_{q}"] = fill_res
            # ========== 代码修改处 结束 ==========


        # ======================= 新增模块：矩阵评分题分析 (组间) =======================
        for q in QUESTION_TYPES.get("矩阵评分", []):
            sub_item_cols = [c for c in df.columns if c.startswith(f"矩阵评分_{q}_")]
            main_stem = clean_question_stem(get_question_stem(original_df, q))

            for col in sub_item_cols:
                sub_item_name = col.replace(f"矩阵评分_{q}_", "").replace('_', ' ')

                # --- 复用评分题分析逻辑 ---
                required_columns = [player_type_column_name, col]
                valid = df[required_columns].dropna(subset=[col])
                valid[col] = pd.to_numeric(valid[col], errors='coerce')
                valid = valid.dropna(subset=[col])
                valid = valid[valid[col] != 0]
                valid = valid.dropna(subset=[player_type_column_name])

                if valid[col].empty:
                    print(f"警告：矩阵评分题 {q} - 子项 '{sub_item_name}' 无有效数据，跳过处理")
                    continue

                n_counts = valid[player_type_column_name].value_counts()
                n_counts_per_question[f"矩阵评分_{q}_{sub_item_name}_二维表"] = n_counts

                count_matrix = valid.groupby([player_type_column_name, col], observed=True).size().unstack(fill_value=0)
                count_matrix.columns = pd.to_numeric(count_matrix.columns)
                count_matrix = count_matrix.sort_index(axis=1)
                total_counts = count_matrix.sum(axis=1)
                dist_pct = count_matrix.div(total_counts, axis=0)
                avg_srs = valid.groupby(player_type_column_name, observed=True)[col].mean()

                result_list = []
                for player_type in count_matrix.index:
                    for score in count_matrix.columns:
                        result_list.append({'玩家类型': player_type, '评分项': str(score), '值': dist_pct.loc[player_type, score]})
                    result_list.append({'玩家类型': player_type, '评分项': '平均分', '值': avg_srs[player_type]})

                result_df = pd.DataFrame(result_list)
                pivot_df = result_df.pivot_table(index='评分项', columns='玩家类型', values='值', aggfunc='first', fill_value=0).reset_index()
                pivot_df['排序键'] = pivot_df['评分项'].apply(lambda x: int(x) if x.isdigit() else float('inf'))
                pivot_df = pivot_df.sort_values('排序键').drop('排序键', axis=1).reset_index(drop=True)

                valid_col = valid[col]
                score_counts_num = valid_col.value_counts().sort_index().reset_index(); score_counts_num.columns = ['评分项', '人数']
                score_counts_pct = valid_col.value_counts(normalize=True).sort_index().reset_index(); score_counts_pct.columns = ['评分项', '总计']
                score_counts_num['评分项'] = score_counts_num['评分项'].astype(str); score_counts_pct['评分项'] = score_counts_pct['评分项'].astype(str)
                score_counts = score_counts_num.merge(score_counts_pct, on='评分项')
                avg_total = pd.DataFrame({'评分项': ['平均分'], '人数': valid_col.count(), '总计': valid_col.mean()})
                total_dist = pd.concat([score_counts, avg_total], ignore_index=True)

                pivot_df = pivot_df.merge(total_dist, on='评分项', how='left')
                for p_type in all_player_types:
                    if p_type not in pivot_df.columns: pivot_df[p_type] = 0.0
                pivot_df = pivot_df[['评分项'] + all_player_types + ['总计', '人数']].fillna(0)
                pivot_df.replace([np.inf, -np.inf], 0, inplace=True)
                pivot_df.iloc[:, 1:] = pivot_df.iloc[:, 1:].apply(pd.to_numeric)
                results[f"矩阵评分_{q}_{sub_item_name}_二维表"] = pivot_df
                
                # ******** 代码修改处：根据复选框状态决定是否执行检验 ********
                if run_statistical_tests:
                    test_res = pd.DataFrame()
                    overall_p, overall_test_type, overall_effect_size, sig_pair_str = np.nan, '', np.nan, '无'

                    if len(valid[player_type_column_name].unique()) > 1:
                        groups = valid[player_type_column_name].unique()
                        group_data = [valid[valid[player_type_column_name] == g][col].dropna() for g in groups]
                        min_size = min([len(g) for g in group_data])
                        filtered_groups = [g for g in group_data if len(g) >= 2]

                        if len(filtered_groups) < 2:
                            test_res = pd.DataFrame({'错误信息': [f"数据不足，无法对矩阵评分题 {q}-{sub_item_name} 进行显著性检验。"]})
                        else:
                            try:
                                normality = [normaltest(g).pvalue > 0.05 for g in filtered_groups if len(g) >= 8]
                                levene_p = levene(*filtered_groups).pvalue if len(filtered_groups) >= 2 else 1.0

                                if all(normality) and levene_p > 0.05 and min_size >= 3:
                                    f_val, p_val = f_oneway(*filtered_groups)
                                    overall_test_type = 'ANOVA'
                                    overall_p = p_val
                                    overall_effect_size = calculate_eta_squared_anova(filtered_groups)
                                elif len(filtered_groups) >= 2 and min_size >= 3:
                                    h_val, p_val = kruskal(*filtered_groups)
                                    overall_test_type = 'Kruskal-Wallis'
                                    overall_p = p_val
                                    overall_effect_size = calculate_eta_squared_kruskal(h_val, len(filtered_groups), sum(len(g) for g in filtered_groups))
                                else:
                                    raise ValueError(f"样本量不足：最小组样本数={min_size}")

                                test_res = pd.DataFrame({'题号': [f"{q}-{sub_item_name}"], '检验类型': [overall_test_type], '统计量': [round(f_val if overall_test_type=='ANOVA' else h_val, 4)], 'p值': [overall_p], '效应量': [overall_effect_size]})

                                if overall_p < 0.05:
                                    posthoc_df = pd.DataFrame()
                                    if overall_test_type == 'ANOVA':
                                        tukey = pairwise_tukeyhsd(endog=valid[col], groups=valid[player_type_column_name], alpha=0.05)
                                        posthoc_df = pd.DataFrame(tukey._results_table.data[1:], columns=['组别1','组别2','均值差','p值','下限','上限','拒绝'])
                                        posthoc_df['校正后p值'] = posthoc_df['p值'].astype(float)
                                    else:
                                        posthoc_df = posthoc_dunn(valid, val_col=col, group_col=player_type_column_name, p_adjust='fdr_bh').stack().reset_index()
                                        posthoc_df.columns = ['组别1','组别2','校正后p值']

                                    posthoc_df['显著性'] = ''
                                    for i, row in posthoc_df.iterrows():
                                        g1, g2 = row['组别1'], row['组别2']
                                        data1, data2 = valid[valid[player_type_column_name] == g1][col], valid[valid[player_type_column_name] == g2][col]
                                        effect_size = calculate_cohens_d(data1, data2) if overall_test_type == 'ANOVA' else calculate_rank_biserial_correlation(data1, data2)
                                        p_corrected = row['校正后p值']
                                        sig_str = ('***' if p_corrected < 0.001 else '**' if p_corrected < 0.01 else '*' if p_corrected < 0.05 else '')
                                        if sig_str:
                                            direction_arrow = get_direction_arrow(np.mean(data1), np.mean(data2))
                                            posthoc_df.loc[i, '显著性'] = f"{direction_arrow} {sig_str} ({effect_size:.2f})"
                                    test_res = pd.concat([test_res, posthoc_df])

                            except Exception as e:
                                test_res = pd.DataFrame({'错误信息': [f"检验失败: {e}"]})

                    results[f"检验结果_矩阵评分_{q}_{sub_item_name}"] = test_res

                    sig_matrix = pd.DataFrame('', index=all_player_types, columns=all_player_types)
                    if not test_res.empty and '组别1' in test_res.columns:
                        pairwise_results = test_res[test_res['组别1'].notna()]
                        for _, row in pairwise_results.iterrows():
                            g1, g2, sig = row['组别1'], row['组别2'], row.get('显著性', '')
                            if g1 in sig_matrix.index and g2 in sig_matrix.columns:
                                sig_matrix.loc[g1, g2] = sig
                            if g2 in sig_matrix.index and g1 in sig_matrix.columns:
                                inv_sig = sig.replace('▲', '▼') if '▲' in sig else sig.replace('▼', '▲') if '▼' in sig else sig
                                sig_matrix.loc[g2, g1] = inv_sig

                    if len(all_player_types) >= 2:
                        sig_matrix.index.name = f"{player_type_column_name}_Group1"; sig_matrix.columns.name = f"{player_type_column_name}_Group2"
                        sig_matrix_sheets_to_combine.append({'name': f"显著性表_矩阵评分_{q}_{sub_item_name}", 'data': sig_matrix, 'q_type': '评分', 'main_q_for_sort': q, 'sub_q_for_sort': sub_item_name, 'option_part': '', 'display_title': main_stem + f" - {sub_item_name} (矩阵评分 - 组间显著性差异)", 'post_hoc_test_type': overall_test_type})

        # ======================= 新增模块：矩阵单选题分析 (组间) =======================
        for q in QUESTION_TYPES.get("矩阵单选", []):
            sub_item_cols = [c for c in df.columns if c.startswith(f"矩阵单_{q}_")]
            main_stem = clean_question_stem(get_question_stem(original_df, q))

            for col in sub_item_cols:
                sub_item_name = col.replace(f"矩阵单_{q}_", "").replace('_', ' ')

                # --- 复用评分题分析逻辑 (因为矩阵单选被转换成了评分) ---
                required_columns = [player_type_column_name, col]
                valid = df[required_columns].dropna(subset=[col])
                valid[col] = pd.to_numeric(valid[col], errors='coerce')
                valid = valid.dropna(subset=[col])
                valid = valid.dropna(subset=[player_type_column_name])

                if valid[col].empty:
                    print(f"警告：矩阵单选题 {q} - 子项 '{sub_item_name}' 无有效数据，跳过处理")
                    continue

                n_counts = valid[player_type_column_name].value_counts()
                n_counts_per_question[f"矩阵单选_{q}_{sub_item_name}_二维表"] = n_counts

                count_matrix = valid.groupby([player_type_column_name, col], observed=True).size().unstack(fill_value=0)
                count_matrix.columns = pd.to_numeric(count_matrix.columns)
                count_matrix = count_matrix.sort_index(axis=1)
                total_counts = count_matrix.sum(axis=1)
                dist_pct = count_matrix.div(total_counts, axis=0)
                avg_srs = valid.groupby(player_type_column_name, observed=True)[col].mean()

                result_list = []
                for player_type in count_matrix.index:
                    for score in count_matrix.columns:
                        result_list.append({'玩家类型': player_type, '评分项': str(score), '值': dist_pct.loc[player_type, score]})
                    result_list.append({'玩家类型': player_type, '评分项': '平均分', '值': avg_srs[player_type]})

                result_df = pd.DataFrame(result_list)
                pivot_df = result_df.pivot_table(index='评分项', columns='玩家类型', values='值', aggfunc='first', fill_value=0).reset_index()
                pivot_df['排序键'] = pivot_df['评分项'].apply(lambda x: int(x) if x.isdigit() else float('inf'))
                pivot_df = pivot_df.sort_values('排序键').drop('排序键', axis=1).reset_index(drop=True)

                valid_col = valid[col]
                score_counts_num = valid_col.value_counts().sort_index().reset_index(); score_counts_num.columns = ['评分项', '人数']
                score_counts_pct = valid_col.value_counts(normalize=True).sort_index().reset_index(); score_counts_pct.columns = ['评分项', '总计']
                score_counts_num['评分项'] = score_counts_num['评分项'].astype(str); score_counts_pct['评分项'] = score_counts_pct['评分项'].astype(str)
                score_counts = score_counts_num.merge(score_counts_pct, on='评分项')
                avg_total = pd.DataFrame({'评分项': ['平均分'], '人数': valid_col.count(), '总计': valid_col.mean()})
                total_dist = pd.concat([score_counts, avg_total], ignore_index=True)

                pivot_df = pivot_df.merge(total_dist, on='评分项', how='left')
                for p_type in all_player_types:
                    if p_type not in pivot_df.columns: pivot_df[p_type] = 0.0
                pivot_df = pivot_df[['评分项'] + all_player_types + ['总计', '人数']].fillna(0)
                pivot_df.replace([np.inf, -np.inf], 0, inplace=True)
                pivot_df.iloc[:, 1:] = pivot_df.iloc[:, 1:].apply(pd.to_numeric)
                results[f"矩阵单选_{q}_{sub_item_name}_二维表"] = pivot_df

                # ******** 代码修改处：根据复选框状态决定是否执行检验 ********
                if run_statistical_tests:
                    test_res = pd.DataFrame()
                    overall_p, overall_test_type, overall_effect_size, sig_pair_str = np.nan, '', np.nan, '无'

                    if len(valid[player_type_column_name].unique()) > 1:
                        groups = valid[player_type_column_name].unique()
                        group_data = [valid[valid[player_type_column_name] == g][col].dropna() for g in groups]
                        min_size = min([len(g) for g in group_data]) if group_data else 0
                        filtered_groups = [g for g in group_data if len(g) >= 2]

                        if len(filtered_groups) < 2:
                            test_res = pd.DataFrame({'错误信息': [f"数据不足，无法对矩阵单选题 {q}-{sub_item_name} 进行显著性检验。"]})
                        else:
                            try:
                                h_val, p_val = kruskal(*filtered_groups)
                                overall_test_type = 'Kruskal-Wallis'
                                overall_p = p_val
                                overall_effect_size = calculate_eta_squared_kruskal(h_val, len(filtered_groups), sum(len(g) for g in filtered_groups))
                                test_res = pd.DataFrame({'题号': [f"{q}-{sub_item_name}"], '检验类型': [overall_test_type], '统计量': [round(h_val, 4)], 'p值': [overall_p], '效应量': [overall_effect_size]})

                                if overall_p < 0.05:
                                    posthoc_df = posthoc_dunn(valid, val_col=col, group_col=player_type_column_name, p_adjust='fdr_bh').stack().reset_index()
                                    posthoc_df.columns = ['组别1','组别2','校正后p值']

                                    posthoc_df['显著性'] = ''
                                    for i, row in posthoc_df.iterrows():
                                        g1, g2 = row['组别1'], row['组别2']
                                        data1, data2 = valid[valid[player_type_column_name] == g1][col], valid[valid[player_type_column_name] == g2][col]
                                        effect_size = calculate_rank_biserial_correlation(data1, data2)
                                        p_corrected = row['校正后p值']
                                        sig_str = ('***' if p_corrected < 0.001 else '**' if p_corrected < 0.01 else '*' if p_corrected < 0.05 else '')
                                        if sig_str:
                                            direction_arrow = get_direction_arrow(np.mean(data1), np.mean(data2))
                                            posthoc_df.loc[i, '显著性'] = f"{direction_arrow} {sig_str} ({effect_size:.2f})"
                                    test_res = pd.concat([test_res, posthoc_df])

                            except Exception as e:
                                test_res = pd.DataFrame({'错误信息': [f"检验失败: {e}"]})

                    results[f"检验结果_矩阵单选_{q}_{sub_item_name}"] = test_res

                    sig_matrix = pd.DataFrame('', index=all_player_types, columns=all_player_types)
                    if not test_res.empty and '组别1' in test_res.columns:
                        pairwise_results = test_res[test_res['组别1'].notna()]
                        for _, row in pairwise_results.iterrows():
                            g1, g2, sig = row['组别1'], row['组别2'], row.get('显著性', '')
                            if g1 in sig_matrix.index and g2 in sig_matrix.columns:
                                sig_matrix.loc[g1, g2] = sig
                            if g2 in sig_matrix.index and g1 in sig_matrix.columns:
                                inv_sig = sig.replace('▲', '▼') if '▲' in sig else sig.replace('▼', '▲') if '▼' in sig else sig
                                sig_matrix.loc[g2, g1] = inv_sig

                    if len(all_player_types) >= 2:
                        sig_matrix.index.name = f"{player_type_column_name}_Group1"; sig_matrix.columns.name = f"{player_type_column_name}_Group2"
                        sig_matrix_sheets_to_combine.append({'name': f"显著性表_矩阵单选_{q}_{sub_item_name}", 'data': sig_matrix, 'q_type': '评分', 'main_q_for_sort': q, 'sub_q_for_sort': sub_item_name, 'option_part': '', 'display_title': main_stem + f" - {sub_item_name} (矩阵单选 - 组间显著性差异)", 'post_hoc_test_type': overall_test_type})

        results.update(fill_sheets)

        # Fill-in-the-blank questions
        for q in QUESTION_TYPES.get("填空", []):
            q_num_str = str(q)
            q_cols = [c for c in df.columns if str(c).startswith(f'Q{q_num_str}.') and ':' not in str(c)]
            if not q_cols:
                continue
            
            analysis_df = df[[player_type_column_name] + q_cols].copy()
            cleaned = (analysis_df.pipe(lambda d: d[pd.notna(d[player_type_column_name])]).melt(id_vars=[player_type_column_name], value_vars=q_cols, var_name='问题项', value_name='答案内容').assign(答案内容=lambda x: x['答案内容'].fillna('').astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()).loc[lambda d: d['答案内容'].str.len() > 0].dropna(how='any'))
            final_dfs = []
            for type_name, group in cleaned.groupby(player_type_column_name, observed=True):
                type_res = (group.reset_index(drop=True).assign(序号=lambda x: x.index + 1, 玩家类型=lambda x: x[player_type_column_name].fillna('INVALID')).query("玩家类型 != 'INVALID'")[['玩家类型',  '答案内容']])
                final_dfs.append(type_res)
            if final_dfs:
                final_output = pd.concat(final_dfs, ignore_index=True)
                assert not final_output.isna().any().any(), "结果中存在NaN值"
                results[f"填空题_{q}_分类型"] = final_output
            else:
                results[f"填空题_{q}_分类型"] = pd.DataFrame(columns=['玩家类型',  '答案内容'])
            overall_significance_summary_list.append({'题号': q, '题干': clean_question_stem(get_question_stem(original_df, q)), '题型': '填空', '总检验类型': '不适用', '总检验p值': np.nan, '总检验显著性': '不适用', '总检验效应量': np.nan, '显著差异组对': '不适用'})


        # --- Within-Group Difference Analysis ---
        # ******** 代码修改处：根据复选框状态决定是否执行整个组内分析模块 ********
        if run_statistical_tests:
            print("\n--- Starting Within-Group Difference Analysis ---")
            unique_player_types = df[player_type_column_name].unique()
            for p_type in unique_player_types:
                player_subset_df = df[df[player_type_column_name] == p_type].copy()
                if player_subset_df.empty:
                    print(f"Skipping within-group analysis for '{p_type}' due to empty subset.")
                    continue

                print(f"Analyzing within-group differences for Player Type: '{p_type}'")

                # 1. Single Choice (单选) - Within Group
                for q_num in QUESTION_TYPES.get("单选", []):
                    q_num_str = str(q_num)
                    q_cols = [c for c in df.columns if str(c).startswith(f'Q{q_num_str}.') and ':' not in str(c)]
                    if not q_cols: continue
                    col_name = q_cols[0] 

                    if col_name not in player_subset_df.columns: continue

                    option_counts_series = player_subset_df[col_name].value_counts().dropna()

                    ordered_options_raw = self.sorted_question_options.get(('单选', q_num), [])
                    if not ordered_options_raw: 
                        print(f"  FATAL: Master option list for single-choice Q{q_num} was not pre-populated. Skipping within-group analysis for this question.")
                        continue

                    ordered_options = [opt for opt in ordered_options_raw if '填空项' not in str(opt)]
                    num_options = len(ordered_options)

                    if num_options < 2:
                        continue

                    pairwise_test_results = []
                    for i in range(num_options):
                        for j in range(i + 1, num_options):
                            opt_i = ordered_options[i]
                            opt_j = ordered_options[j]
                            count_i = option_counts_series.get(opt_i, 0)
                            count_j = option_counts_series.get(opt_j, 0)
                            total_for_pair = count_i + count_j
                            if total_for_pair > 0:
                                p_val = stats.binomtest(min(count_i, count_j), total_for_pair, p=0.5, alternative='two-sided').pvalue
                                effect_size = abs(count_i - count_j) / total_for_pair
                                direction_arrow = get_direction_arrow(count_i, count_j)
                                pairwise_test_results.append({'opt1': opt_i, 'opt2': opt_j, 'raw_p': p_val, 'effect_size': effect_size, 'direction': direction_arrow})
                            else:
                                pairwise_test_results.append({'opt1': opt_i, 'opt2': opt_j, 'raw_p': np.nan, 'effect_size': np.nan, 'direction': ''})
                    df_pairwise_results = pd.DataFrame(pairwise_test_results)
                    if not df_pairwise_results.empty and 'raw_p' in df_pairwise_results.columns and df_pairwise_results['raw_p'].notna().any():
                        valid_p_values = df_pairwise_results['raw_p'].dropna().values
                        reject, pvals_corrected_fdr, _, _ = multipletests(valid_p_values, method='fdr_bh')
                        df_pairwise_results['corrected_p'] = np.nan
                        df_pairwise_results.loc[df_pairwise_results['raw_p'].notna(), 'corrected_p'] = pvals_corrected_fdr
                    else:
                        df_pairwise_results['corrected_p'] = np.nan
                    within_sig_matrix = pd.DataFrame('', index=ordered_options, columns=ordered_options)
                    for _, row in df_pairwise_results.iterrows():
                        opt_i, opt_j, corrected_p_val, effect_size, direction = row['opt1'], row['opt2'], row['corrected_p'], row['effect_size'], row['direction']
                        sig_str = ''
                        if pd.notna(corrected_p_val):
                            if corrected_p_val < 0.001: sig_str = '***'
                            elif corrected_p_val < 0.01: sig_str = '**'
                            elif corrected_p_val < 0.05: sig_str = '*'

                        cell_value = ''
                        if sig_str:
                            cell_value = f"{direction} {sig_str} ({effect_size:.2f})"

                        within_sig_matrix.loc[opt_i, opt_j] = cell_value
                        if '▲' in cell_value: inv_cell = cell_value.replace('▲', '▼')
                        elif '▼' in cell_value: inv_cell = cell_value.replace('▼', '▲')
                        else: inv_cell = cell_value
                        within_sig_matrix.loc[opt_j, opt_i] = inv_cell
                    within_sig_matrix.index.name = "选项1"
                    within_sig_matrix.columns.name = "选项2"
                    within_sig_matrix_sheets_to_combine.append({'name': f"组内显著性_{p_type}_单选_Q{q_num}", 'data': within_sig_matrix, 'q_type': '单选', 'player_type_display': p_type, 'main_q_for_sort': q_num, 'sub_q_for_sort': '', 'option_part': '', 'display_title': f"玩家类型: {p_type} - {clean_question_stem(get_question_stem(original_df, q_num))} (单选 - 组内显著性差异)", 'overall_test_type': 'Binomial Test'})

                # 2. Multiple Choice (多选) - Within Group
                for q_num in QUESTION_TYPES.get("多选", []):
                    q_num_str = str(q_num)
                    q_cols_multi = [c for c in df.columns if str(c).startswith(f'Q{q_num_str}.') and ':' in str(c)]
                    existing_cols_in_subset = [col for col in q_cols_multi if col in player_subset_df.columns]
                    if not existing_cols_in_subset: continue
                    options_map_multi = {extract_option(col, q_num_str): col for col in existing_cols_in_subset}

                    ordered_options_raw = self.sorted_question_options.get(('多选', q_num), [])
                    if not ordered_options_raw:
                        print(f"  FATAL: Master option list for multi-choice Q{q_num} was not pre-populated. Skipping within-group analysis for this question.")
                        continue

                    ordered_options = [opt for opt in ordered_options_raw if '填空项' not in str(opt)]
                    num_options = len(ordered_options)
                    if num_options < 2:
                        continue

                    pairwise_test_results_multi = []
                    for i in range(num_options):
                        for j in range(i + 1, num_options):
                            opt_i, opt_j = ordered_options[i], ordered_options[j]
                            col_i, col_j = options_map_multi.get(opt_i), options_map_multi.get(opt_j)

                            if col_i is None or col_j is None:
                                pairwise_test_results_multi.append({'opt1': opt_i, 'opt2': opt_j, 'raw_p': np.nan, 'effect_size': np.nan, 'direction': ''})
                                continue

                            temp_df = player_subset_df[[col_i, col_j]].copy()
                            temp_df[col_i] = pd.to_numeric(temp_df[col_i], errors='coerce').fillna(0).astype(int)
                            temp_df[col_j] = pd.to_numeric(temp_df[col_j], errors='coerce').fillna(0).astype(int)

                            try:
                                # ========== 代码修正处 开始 ==========
                                table_initial = pd.crosstab(temp_df[col_i], temp_df[col_j])
                                
                                # 获取不一致对 (b, c) 和一致对 (a, d) 的计数值
                                # b = (选i, 未选j), c = (未选i, 选j)
                                # a = (选i, 选j), d = (未选i, 未选j)
                                b_val = table_initial.get(0, {}).get(1, 0) # crosstab.loc[1, 0]
                                c_val = table_initial.get(1, {}).get(0, 0) # crosstab.loc[0, 1]
                                yes_yes = table_initial.get(1, {}).get(1, 0) # crosstab.loc[1, 1]
                                no_no = table_initial.get(0, {}).get(0, 0) # crosstab.loc[0, 0]

                                discordant_pairs = b_val + c_val
                                
                                p_val = np.nan
                                effect_size = np.nan

                                if discordant_pairs > 0:
                                    # 修正: 按照 [[n00, n01], [n10, n11]] 的标准格式构建列联表
                                    # n00=no_no, n01=c_val, n10=b_val, n11=yes_yes
                                    correct_table_for_mcnemar = np.array([[no_no, c_val], [b_val, yes_yes]])
                                    
                                    # 根据样本量选择精确检验或卡方近似检验
                                    test_exact = discordant_pairs < 25
                                    mcnemar_result = mcnemar(correct_table_for_mcnemar, exact=test_exact)
                                    p_val = mcnemar_result.pvalue
                                    
                                    # 使用辅助函数计算效应量，更稳健
                                    effect_size = calculate_cohens_g_mcnemar(correct_table_for_mcnemar)
                                else:
                                    # 如果没有不一致对，则p值为1，无差异
                                    p_val = 1.0
                                    effect_size = 0.0
                                # ========== 代码修正处 结束 ==========

                                count_i = temp_df[col_i].sum()
                                count_j = temp_df[col_j].sum()
                                direction_arrow = get_direction_arrow(count_i, count_j)
                                pairwise_test_results_multi.append({'opt1': opt_i, 'opt2': opt_j, 'raw_p': p_val, 'effect_size': effect_size, 'direction': direction_arrow})

                            except Exception as e:
                                print(f"WARNING: McNemar test for multi-choice Q{q_num} options '{opt_i}' vs '{opt_j}' for '{p_type}' failed: {e}")
                                pairwise_test_results_multi.append({'opt1': opt_i, 'opt2': opt_j, 'raw_p': np.nan, 'effect_size': np.nan, 'direction': ''})

                    df_pairwise_results_multi = pd.DataFrame(pairwise_test_results_multi)
                    if not df_pairwise_results_multi.empty and 'raw_p' in df_pairwise_results_multi.columns and df_pairwise_results_multi['raw_p'].notna().any():
                        valid_p_values = df_pairwise_results_multi['raw_p'].dropna().values
                        reject, pvals_corrected_fdr, _, _ = multipletests(valid_p_values, method='fdr_bh')
                        df_pairwise_results_multi['corrected_p'] = np.nan
                        df_pairwise_results_multi.loc[df_pairwise_results_multi['raw_p'].notna(), 'corrected_p'] = pvals_corrected_fdr
                    else:
                        df_pairwise_results_multi['corrected_p'] = np.nan

                    within_sig_matrix_multi = pd.DataFrame('', index=ordered_options, columns=ordered_options)
                    for _, row in df_pairwise_results_multi.iterrows():
                        opt_i, opt_j, corrected_p_val, effect_size, direction = row['opt1'], row['opt2'], row['corrected_p'], row['effect_size'], row['direction']
                        sig_str = ''
                        if pd.notna(corrected_p_val):
                            if corrected_p_val < 0.001: sig_str = '***'
                            elif corrected_p_val < 0.01: sig_str = '**'
                            elif corrected_p_val < 0.05: sig_str = '*'

                        cell_value = ''
                        if sig_str:
                            cell_value = f"{direction} {sig_str} ({effect_size:.2f})"

                        within_sig_matrix_multi.loc[opt_i, opt_j] = cell_value
                        if '▲' in cell_value: inv_cell = cell_value.replace('▲', '▼')
                        elif '▼' in cell_value: inv_cell = cell_value.replace('▼', '▲')
                        else: inv_cell = cell_value
                        within_sig_matrix_multi.loc[opt_j, opt_i] = inv_cell
                    within_sig_matrix_multi.index.name = "选项1"
                    within_sig_matrix_multi.columns.name = "选项2"
                    within_sig_matrix_sheets_to_combine.append({'name': f"组内显著性_{p_type}_多选_Q{q_num}", 'data': within_sig_matrix_multi, 'q_type': '多选', 'player_type_display': p_type, 'main_q_for_sort': q_num, 'sub_q_for_sort': '', 'option_part': '', 'display_title': f"玩家类型: {p_type} - {clean_question_stem(get_question_stem(original_df, q_num))} (多选 - 组内显著性差异)", 'overall_test_type': 'McNemar Test'})

                # 4. Matrix Rating (矩阵评分) - Within Group
                for q_num in QUESTION_TYPES.get("矩阵评分", []):
                    ordered_options = self.sorted_question_options.get(('矩阵评分', q_num), [])
                    if not ordered_options:
                        print(f"  FATAL: Master sub-item list for matrix rating Q{q_num} was not pre-populated. Skipping.")
                        continue

                    rating_data_for_test = {}
                    for sub_name in ordered_options:
                        converted_col_name = f"矩阵评分_{q_num}_{sub_name.replace(' ', '_').replace('：', '')}"
                        if converted_col_name in player_subset_df.columns:
                            data_points = player_subset_df[converted_col_name].dropna()
                            data_points = pd.to_numeric(data_points, errors='coerce').dropna()
                            rating_data_for_test[sub_name] = data_points.tolist()
                        else:
                            rating_data_for_test[sub_name] = []

                    if len(ordered_options) < 2:
                        continue

                    within_sig_matrix_rating = pd.DataFrame('', index=ordered_options, columns=ordered_options)
                    overall_test_type_within = 'N/A'

                    valid_options_for_test = [opt for opt, data in rating_data_for_test.items() if len(data) >= 3]
                    if len(valid_options_for_test) < 2:
                        print(f"  Q{q_num} (矩阵评分) for '{p_type}': Less than 2 sub-items with sufficient data for testing.")
                    else:
                        try:
                            valid_rm_cols = [f"矩阵评分_{q_num}_{s.replace(' ', '_').replace('：', '')}" for s in valid_options_for_test]
                            valid_subset_df_for_rm = player_subset_df[valid_rm_cols].dropna()

                            if not valid_subset_df_for_rm.empty and len(valid_subset_df_for_rm) >= 3:
                                p_val_overall = np.nan
                                try:
                                    h_val, p_val_overall = friedmanchisquare(*[valid_subset_df_for_rm[c] for c in valid_rm_cols])
                                    overall_test_type_within = 'Friedman'
                                except Exception as e:
                                    print(f"Friedman test failed for Q{q_num}, {p_type}: {e}")

                                if p_val_overall < 0.05:
                                    pairwise_results_list = []
                                    pairs = list(combinations(valid_options_for_test, 2))
                                    for sub1_name, sub2_name in pairs:
                                        data1 = valid_subset_df_for_rm[f"矩阵评分_{q_num}_{sub1_name.replace(' ', '_').replace('：', '')}"]
                                        data2 = valid_subset_df_for_rm[f"矩阵评分_{q_num}_{sub2_name.replace(' ', '_').replace('：', '')}"]
                                        p_val_pairwise, effect_size_pairwise = np.nan, np.nan

                                        if len(data1) < 2: continue

                                        try:
                                            stat_wilcoxon, p_val_pairwise = wilcoxon(data1, data2, nan_policy='omit', zero_method='wilcox')
                                            effect_size_pairwise = calculate_paired_rank_biserial_correlation(data1, data2)
                                            direction_arrow = get_direction_arrow(np.mean(data1), np.mean(data2))
                                        except ValueError: 
                                            direction_arrow = ''
                                            pass
                                        pairwise_results_list.append({'sub_item1': sub1_name, 'sub_item2': sub2_name, 'raw_p': p_val_pairwise, 'effect_size': effect_size_pairwise, 'direction': direction_arrow})

                                    df_pairwise = pd.DataFrame(pairwise_results_list)
                                    if not df_pairwise.empty and 'raw_p' in df_pairwise.columns and df_pairwise['raw_p'].notna().any():
                                        valid_p_values = df_pairwise['raw_p'].dropna().values
                                        reject, pvals_corrected_fdr, _, _ = multipletests(valid_p_values, method='fdr_bh')
                                        df_pairwise['corrected_p'] = np.nan
                                        df_pairwise.loc[df_pairwise['raw_p'].notna(), 'corrected_p'] = pvals_corrected_fdr
                                    else:
                                        df_pairwise['corrected_p'] = np.nan

                                    for _, row in df_pairwise.iterrows():
                                        sub1_name, sub2_name, corrected_p_val, effect_size, direction = row['sub_item1'], row['sub_item2'], row['corrected_p'], row['effect_size'], row['direction']
                                        sig_str = ''
                                        if pd.notna(corrected_p_val):
                                            if corrected_p_val < 0.001: sig_str = '***'
                                            elif corrected_p_val < 0.01: sig_str = '**'
                                            elif corrected_p_val < 0.05: sig_str = '*'

                                        cell_value = ''
                                        if sig_str:
                                            cell_value = f"{direction} {sig_str} ({effect_size:.2f})"

                                        within_sig_matrix_rating.loc[sub1_name, sub2_name] = cell_value
                                        if '▲' in cell_value: inv_cell = cell_value.replace('▲', '▼')
                                        elif '▼' in cell_value: inv_cell = cell_value.replace('▼', '▲')
                                        else: inv_cell = cell_value
                                        within_sig_matrix_rating.loc[sub2_name, sub1_name] = inv_cell
                        except Exception as e:
                            print(f"  Q{q_num} (矩阵评分) for '{p_type}': Error during within-group significance test: {e}")

                    within_sig_matrix_rating.index.name = "子项1"
                    within_sig_matrix_rating.columns.name = "子项2"
                    within_sig_matrix_sheets_to_combine.append({'name': f"组内显著性_{p_type}_矩阵评分_Q{q_num}", 'data': within_sig_matrix_rating, 'q_type': '评分', 'player_type_display': p_type, 'main_q_for_sort': q_num, 'sub_q_for_sort': '', 'option_part': '', 'display_title': f"玩家类型: {p_type} - {clean_question_stem(get_question_stem(original_df, q_num))} (矩阵评分 - 组内显著性差异)", 'overall_test_type': overall_test_type_within})

                # 5. Matrix Single Choice (矩阵单选) - Within Group
                for q_num in QUESTION_TYPES.get("矩阵单选", []):
                    q_num_str = str(q_num)
                    # 因为矩阵单选题也被转换成了数值型，所以这里的组内比较实际上是比较不同子项的均值
                    # 这与矩阵评分题的组内比较逻辑完全相同
                    ordered_sub_items = self.sorted_question_options.get(('矩阵单选', q_num), [])
                    if not ordered_sub_items:
                        print(f"  FATAL: Master sub-item list for matrix single Q{q_num} was not pre-populated. Skipping.")
                        continue

                    if len(ordered_sub_items) < 2:
                        continue

                    # --- 复用矩阵评分题的组内比较逻辑 ---
                    within_sig_matrix_ms = pd.DataFrame('', index=ordered_sub_items, columns=ordered_sub_items)
                    overall_test_type_within_ms = 'N/A'

                    valid_sub_items_for_test = [sub for sub in ordered_sub_items if f"矩阵单_{q_num}_{sub.replace(' ', '_').replace('：', '')}" in player_subset_df.columns and len(player_subset_df[f"矩阵单_{q_num}_{sub.replace(' ', '_').replace('：', '')}"].dropna()) >= 3]

                    if len(valid_sub_items_for_test) >= 2:
                        try:
                            valid_rm_cols_ms = [f"矩阵单_{q_num}_{s.replace(' ', '_').replace('：', '')}" for s in valid_sub_items_for_test]
                            valid_subset_df_for_rm_ms = player_subset_df[valid_rm_cols_ms].dropna()

                            if not valid_subset_df_for_rm_ms.empty and len(valid_subset_df_for_rm_ms) >= 3:
                                p_val_overall_ms = np.nan
                                try:
                                    h_val_ms, p_val_overall_ms = friedmanchisquare(*[valid_subset_df_for_rm_ms[c] for c in valid_rm_cols_ms])
                                    overall_test_type_within_ms = 'Friedman'
                                except Exception as e:
                                    print(f"Friedman test failed for Matrix Single Q{q_num}, {p_type}: {e}")

                                if p_val_overall_ms < 0.05:
                                    pairwise_results_list_ms = []
                                    pairs_ms = list(combinations(valid_sub_items_for_test, 2))
                                    for sub1, sub2 in pairs_ms:
                                        data1 = valid_subset_df_for_rm_ms[f"矩阵单_{q_num}_{sub1.replace(' ', '_').replace('：', '')}"]
                                        data2 = valid_subset_df_for_rm_ms[f"矩阵单_{q_num}_{sub2.replace(' ', '_').replace('：', '')}"]
                                        if len(data1) < 2: continue
                                        
                                        try:
                                            _, p_val_pairwise_ms = wilcoxon(data1, data2, nan_policy='omit')
                                            effect_size_ms = calculate_paired_rank_biserial_correlation(data1, data2)
                                            direction_arrow_ms = get_direction_arrow(np.mean(data1), np.mean(data2))
                                            pairwise_results_list_ms.append({'sub1': sub1, 'sub2': sub2, 'raw_p': p_val_pairwise_ms, 'effect_size': effect_size_ms, 'direction': direction_arrow_ms})
                                        except ValueError:
                                            pass
                                    
                                    df_pairwise_ms = pd.DataFrame(pairwise_results_list_ms)
                                    if not df_pairwise_ms.empty and df_pairwise_ms['raw_p'].notna().any():
                                        valid_p_values_ms = df_pairwise_ms['raw_p'].dropna().values
                                        _, pvals_corrected_ms, _, _ = multipletests(valid_p_values_ms, method='fdr_bh')
                                        df_pairwise_ms.loc[df_pairwise_ms['raw_p'].notna(), 'corrected_p'] = pvals_corrected_ms
                                    
                                    for _, row in df_pairwise_ms.iterrows():
                                        sub1, sub2, p_corr, es, direction = row['sub1'], row['sub2'], row.get('corrected_p', np.nan), row['effect_size'], row['direction']
                                        sig_str = ('***' if p_corr < 0.001 else '**' if p_corr < 0.01 else '*' if p_corr < 0.05 else '')
                                        if sig_str:
                                            cell_val = f"{direction} {sig_str} ({es:.2f})"
                                            within_sig_matrix_ms.loc[sub1, sub2] = cell_val
                                            inv_cell_val = cell_val.replace('▲', '▼') if '▲' in cell_val else cell_val.replace('▼', '▲')
                                            within_sig_matrix_ms.loc[sub2, sub1] = inv_cell_val
                        except Exception as e:
                            print(f"  Q{q_num} (矩阵单选) for '{p_type}': Error during within-group significance test: {e}")

                    within_sig_matrix_ms.index.name = "子项1"
                    within_sig_matrix_ms.columns.name = "子项2"
                    within_sig_matrix_sheets_to_combine.append({'name': f"组内显著性_{p_type}_矩阵单选_Q{q_num}", 'data': within_sig_matrix_ms, 'q_type': '评分', # Treat as rating for coloring
                                                             'player_type_display': p_type, 'main_q_for_sort': q_num, 'sub_q_for_sort': '', 'option_part': '',
                                                             'display_title': f"玩家类型: {p_type} - {clean_question_stem(get_question_stem(original_df, q_num))} (矩阵单选 - 组内显著性差异)",
                                                             'overall_test_type': overall_test_type_within_ms})

        # ========== Results Export ==========
        if results or within_sig_matrix_sheets_to_combine:
            with pd.ExcelWriter(
                output_excel_path,
                engine='xlsxwriter',
                engine_kwargs={'options': {'nan_inf_to_errors': True}}
            ) as writer:
                header_format = writer.book.add_format({'num_format': '@', 'bold': True, 'align': 'center', 'valign': 'vcenter'})
                first_col_format = writer.book.add_format({'num_format': '@', 'bold': True, 'align': 'left', 'valign': 'vcenter'}) # 新增：第一列左对齐格式
                percent_format = writer.book.add_format({'num_format': '0.0%'})
                number_format = writer.book.add_format({'num_format': '0.00'})
                integer_format = writer.book.add_format({'num_format': '0'})

                # ====== Consolidated Survey Data Table ('整合总表') ======
                pattern_data_summary = re.compile(r"^(?P<type>多选题|单选题|评分题|矩阵评分|矩阵单选)_(?P<main_q>\d+)(?:[_-](?P<sub_q>.+?))?(_二维表|_二维透视|_分类型)?$", flags=re.IGNORECASE)
                valid_sheets_data_summary = []
                for name, df_res in results.items():
                    match = pattern_data_summary.match(str(name))
                    if match:
                        try:
                            main_q = int(match.group('main_q'))
                            sub_q = match.group('sub_q') or ''
                            q_type_str = match.group('type').replace('题','')
                            valid_sheets_data_summary.append((main_q, sub_q, q_type_str, name, df_res))
                        except (ValueError, AttributeError) as e:
                            print(f"× 无法解析工作表名称 (数据汇总): {name}, 错误: {e}")

                if valid_sheets_data_summary:
                    summary_sheet_data_summary = writer.book.add_worksheet("整合总表")
                    writer.sheets["整合总表"] = summary_sheet_data_summary
                    player_type_counts = df[player_type_column_name].value_counts().sort_index()
                    current_row = 0
                    summary_sheet_data_summary.write(current_row, 0, "各组有效样本人数：", first_col_format)
                    current_row += 1
                    for group, count in player_type_counts.items():
                        summary_sheet_data_summary.write(current_row, 0, f"  {group}: {count}人", None)
                        current_row += 1
                    current_row += 2
                    sorted_sheets_data_summary = sorted(valid_sheets_data_summary, key=lambda x: (x[0], x[1]))
                    current_main_q = None
                    for idx, (main_q, sub_q, q_type, name, df_res) in enumerate(sorted_sheets_data_summary):
                        str_columns = df_res.columns.astype(str)
                        filter_cond = ~str_columns.str.contains('选择人数|排序键', flags=re.IGNORECASE, na=False)
                        clean_data = df_res.loc[:, filter_cond].copy() # 使用 .copy() 避免 SettingWithCopyWarning
                        if clean_data.empty: continue

                        # ========== TGI 计算开始 ==========
                        if '总计' in clean_data.columns and not clean_data.empty:
                            player_type_cols_in_table = [pt for pt in all_player_types if pt in clean_data.columns]
                            
                            for player_type in player_type_cols_in_table:
                                tgi_col_name = f'{player_type}_TGI'
                                # 使用 np.where 进行矢量化安全除法
                                clean_data[tgi_col_name] = np.where(
                                    clean_data['总计'] > 0,
                                    (clean_data[player_type] / clean_data['总计']) * 100,
                                    0  # 当总体占比为0时，TGI设为0
                                )
                        # ========== TGI 计算结束 ==========

                        if main_q != current_main_q:
                            current_row += 1
                            current_main_q = main_q
                        stem = get_question_stem(original_df, main_q)
                        cleaned_stem_for_display = clean_question_stem(stem)
                        # ******** 代码修改处：在题干前添加题号 ********
                        title_text = f"Q{main_q}.{cleaned_stem_for_display}—{sub_q}" if q_type in ['矩阵评分', '矩阵单选'] and sub_q else f"Q{main_q}.{cleaned_stem_for_display}"
                        # ******** 代码修改结束 ********
                        summary_sheet_data_summary.write(current_row, 0, title_text, first_col_format)
                        current_row += 1

                        header_cols = clean_data.columns.tolist()
                        for col_idx, col in enumerate(header_cols):
                            summary_sheet_data_summary.write(current_row, col_idx, str(col), header_format)
                        current_row += 1
                        for df_row_idx, row in clean_data.iterrows():
                            excel_row = current_row + df_row_idx
                            original_label = str(row.iloc[0])
                            for col_idx, col in enumerate(header_cols):
                                cell_value = row[col]
                                fmt = None
                                # ========== 此处是核心修改点 ==========
                                if col_idx == 0:
                                    # 删除了从 original_label 中提取括号内内容的逻辑
                                    cell_value = original_label
                                    fmt = first_col_format
                                elif str(col).endswith('_TGI'):
                                    fmt = integer_format
                                    cell_value = int(round(cell_value, 0)) if pd.notna(cell_value) else ''
                                elif col == '人数':
                                    fmt = integer_format
                                    cell_value = int(cell_value) if pd.notna(cell_value) else ''
                                else:
                                    if '平均分' in original_label or q_type in ['评分', '矩阵评分', '矩阵单选']:
                                        fmt = number_format
                                    elif isinstance(cell_value, float) and cell_value <= 1 and cell_value >= 0:
                                        fmt = percent_format
                                    else:
                                        fmt = number_format if isinstance(cell_value, (int, float)) else None
                                summary_sheet_data_summary.write(excel_row, col_idx, cell_value, fmt)
                        current_row += len(clean_data)
                        n_counts = n_counts_per_question.get(name)
                        if n_counts is not None:
                            n_row_excel = current_row
                            summary_sheet_data_summary.write(n_row_excel, 0, "N (人数)", first_col_format)
                            total_n = n_counts.sum()
                            for col_idx, col_name in enumerate(header_cols):
                                if col_idx == 0: continue
                                if col_name in all_player_types:
                                    count = n_counts.get(col_name, 0)
                                    summary_sheet_data_summary.write(n_row_excel, col_idx, int(count), integer_format)
                                elif col_name == '人数':
                                    summary_sheet_data_summary.write(n_row_excel, col_idx, int(total_n), integer_format)
                                elif col_name == '总计':
                                    summary_sheet_data_summary.write(n_row_excel, col_idx, "", None)
                                # TGI列在N(人数)行留空，此逻辑已隐式处理
                            current_row += 1
                        current_row += 1
                    summary_sheet_data_summary.set_column(0, 0, 25)
                    # 动态调整列宽
                    if 'header_cols' in locals():
                        summary_sheet_data_summary.set_column(1, len(header_cols), 12)

                # ====== Write Between-Group Significance Tables ======
                # ******** 代码修改处：此部分仅在 sig_matrix_sheets_to_combine 列表不为空时执行（即勾选了统计检验）********
                sorted_sig_matrices = sorted(sig_matrix_sheets_to_combine, key=lambda x: (x['main_q_for_sort'], x['sub_q_for_sort'], x['option_part']))
                if sorted_sig_matrices:
                    combined_sig_sheet = writer.book.add_worksheet("组间显著性差异分析")
                    writer.sheets["组间显著性差异分析"] = combined_sig_sheet
                    current_sig_row = 0

                    global_explanation = generate_global_between_group_explanation()
                    for line in global_explanation.split('\n'):
                        combined_sig_sheet.write(current_sig_row, 0, line)
                        current_sig_row += 1
                    current_sig_row += 1 

                    for line in EFFECT_SIZE_INTERPRETATION.split('\n'):
                        combined_sig_sheet.write(current_sig_row, 0, line)
                        current_sig_row += 1
                    current_sig_row += 2

                    for item in sorted_sig_matrices:
                        combined_sig_sheet.write(current_sig_row, 0, item['display_title'], first_col_format)
                        current_sig_row += 1

                        data = item['data'].copy()
                        data.columns = data.columns.astype(str)
                        for col_idx, col_name in enumerate(data.columns):
                            combined_sig_sheet.write(current_sig_row, col_idx + 1, col_name, first_col_format)
                        combined_sig_sheet.write(current_sig_row, 0, str(data.index.name), first_col_format)
                        current_sig_row += 1
                        for df_row_idx, (idx_val, row_series) in enumerate(data.iterrows()):
                            combined_sig_sheet.write(current_sig_row + df_row_idx, 0, str(idx_val), first_col_format)
                            for col_idx, cell_value in enumerate(row_series):
                                if col_idx > df_row_idx:
                                    effect_size_numeric_value = extract_effect_size_from_sig_string(cell_value)
                                    es_type_for_color = get_es_type_string_for_coloring(item['q_type'], item.get('post_hoc_test_type'))
                                    cell_color_hex = get_green_gradient_color(effect_size_numeric_value, es_type_for_color)
                                    if cell_color_hex not in self.color_formats_cache:
                                        new_format = writer.book.add_format({'bg_color': cell_color_hex})
                                        self.color_formats_cache[cell_color_hex] = new_format
                                    selected_format = self.color_formats_cache[cell_color_hex]
                                    combined_sig_sheet.write(current_sig_row + df_row_idx, col_idx + 1, cell_value, selected_format)
                                elif col_idx == df_row_idx:
                                    combined_sig_sheet.write(current_sig_row + df_row_idx, col_idx + 1, '-', None)
                                else:
                                    combined_sig_sheet.write(current_sig_row + df_row_idx, col_idx + 1, '', None)
                        current_sig_row += len(data) + 2
                    if sorted_sig_matrices:
                        max_cols_all_tables = max(len(item['data'].columns) for item in sorted_sig_matrices) + 1
                        combined_sig_sheet.set_column(0, 0, 25)
                        combined_sig_sheet.set_column(1, max_cols_all_tables, 18)

                # ====== Write Within-Group Significance Tables ======
                # ******** 代码修改处：此部分仅在 within_sig_matrix_sheets_to_combine 列表不为空时执行（即勾选了统计检验）********
                sorted_within_sig_matrices = sorted(within_sig_matrix_sheets_to_combine, key=lambda x: (x['main_q_for_sort'], x['player_type_display'], x['sub_q_for_sort'], x['option_part']))
                if sorted_within_sig_matrices:
                    combined_within_sig_sheet = writer.book.add_worksheet("组内显著性差异分析")
                    writer.sheets["组内显著性差异分析"] = combined_within_sig_sheet
                    current_within_sig_row = 0

                    global_explanation_within = generate_global_within_group_explanation()
                    for line in global_explanation_within.split('\n'):
                        combined_within_sig_sheet.write(current_within_sig_row, 0, line)
                        current_within_sig_row += 1
                    current_within_sig_row += 1

                    for line in EFFECT_SIZE_INTERPRETATION.split('\n'):
                        combined_within_sig_sheet.write(current_within_sig_row, 0, line)
                        current_within_sig_row += 1
                    current_within_sig_row += 2

                    for item in sorted_within_sig_matrices:
                        combined_within_sig_sheet.write(current_within_sig_row, 0, item['display_title'], first_col_format)
                        current_within_sig_row += 1

                        data = item['data'].copy()
                        data.columns = data.columns.astype(str)
                        for col_idx, col_name in enumerate(data.columns):
                            combined_within_sig_sheet.write(current_within_sig_row, col_idx + 1, col_name, first_col_format)
                        combined_within_sig_sheet.write(current_within_sig_row, 0, str(data.index.name), first_col_format)
                        current_within_sig_row += 1
                        for df_row_idx, (idx_val, row_series) in enumerate(data.iterrows()):
                            combined_within_sig_sheet.write(current_within_sig_row + df_row_idx, 0, str(idx_val), first_col_format)
                            for col_idx, cell_value in enumerate(row_series):
                                if col_idx > df_row_idx:
                                    effect_size_numeric_value = extract_effect_size_from_sig_string(cell_value)
                                    es_type_for_color = get_es_type_string_for_coloring(item['q_type'], item.get('overall_test_type'))
                                    cell_color_hex = get_green_gradient_color(effect_size_numeric_value, es_type_for_color) if cell_value.strip() else '#FFFFFF'
                                    if cell_color_hex not in self.color_formats_cache:
                                        new_format = writer.book.add_format({'bg_color': cell_color_hex})
                                        self.color_formats_cache[cell_color_hex] = new_format
                                    selected_format = self.color_formats_cache[cell_color_hex]
                                    combined_within_sig_sheet.write(current_within_sig_row + df_row_idx, col_idx + 1, cell_value, selected_format)
                                elif col_idx == df_row_idx:
                                    combined_within_sig_sheet.write(current_within_sig_row + df_row_idx, col_idx + 1, '-', None)
                                else:
                                    combined_within_sig_sheet.write(current_within_sig_row + df_row_idx, col_idx + 1, '', None)
                        current_within_sig_row += len(data) + 2
                    if sorted_within_sig_matrices:
                        max_cols_all_tables_within = max(len(item['data'].columns) for item in sorted_within_sig_matrices) + 1
                        combined_within_sig_sheet.set_column(0, 0, 25)
                        combined_within_sig_sheet.set_column(1, max_cols_all_tables_within, 18)

                # ====== Write Fill-in-the-blank sheets ======
                # # ******** 代码修改处：仅写入非检验结果的分析表 ********
                # analysis_sheets = {k: v for k, v in results.items() if not k.startswith('检验结果_')}
                # for name, data in analysis_sheets.items():
                #     clean_sheet_name_str = clean_sheet_name(name)
                #     data.to_excel(writer, sheet_name=clean_sheet_name_str, index=False)
                #     worksheet = writer.sheets[clean_sheet_name_str]
                #     if "填空" in name:
                #         worksheet.set_column('A:A', 15)
                #         worksheet.set_column('B:B', 40)
                # ====== Write Fill-in-the-blank sheets ======
                # ******** 代码修改处：仅写入题目为“填空”的非检验结果分析表 ********
                analysis_sheets = {
                    k: v for k, v in results.items()
                    if (not k.startswith('检验结果_')) and ('填空' in k)
                }
                for name, data in analysis_sheets.items():
                    clean_sheet_name_str = clean_sheet_name(name)
                    data.to_excel(writer, sheet_name=clean_sheet_name_str, index=False)
                    worksheet = writer.sheets[clean_sheet_name_str]
                    worksheet.set_column('A:A', 15)
                    worksheet.set_column('B:B', 40)
            print(f"分析完成，结果已保存 -> {output_excel_path}")
        else:
            print("警告：未生成任何分析结果，请检查数据格式或过滤条件")

# ========== 新增的主应用程序类 ==========
class CombinedApp:
    def __init__(self, master):
        self.master = master
        master.title("问卷处理工具")
        master.geometry("300x130") # 调整高度
        master.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="20")
        main_frame.pack(expand=True, fill="both")
        merge_button = ttk.Button(main_frame, text="合并问卷", command=self.launch_excel_merger)
        merge_button.pack(pady=5, fill="x")
        analyze_button = ttk.Button(main_frame, text="交叉分析", command=self.launch_survey_processor)
        analyze_button.pack(pady=5, fill="x")
        # ******** 代码修改处：移除了“回归分析”按钮 ********

    def launch_excel_merger(self):
        new_window = tk.Toplevel(self.master)
        new_window.title("Excel文件合并工具")
        ExcelMergerApp(new_window)

    def launch_survey_processor(self):
        new_window = tk.Toplevel(self.master)
        new_window.title("问卷交叉分析工具")
        SurveyProcessorApp(new_window)

    # ******** 代码修改处：移除了 launch_regression_analysis 函数 ********


# ========== 全局唯一的程序启动入口 ==========
if __name__ == "__main__":
    root = tk.Tk()
    app = CombinedApp(root)
    root.mainloop()
