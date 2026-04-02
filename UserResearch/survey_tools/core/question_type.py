import re
from collections import defaultdict

import pandas as pd

from survey_tools.core.quant import advanced_split, extract_qnum


def get_prefix(col_name):
    """提取列名中冒号之前的题干前缀部分（用于多选题分组识别）。

    Args:
        col_name: str，问卷列名，如 "Q4. 偏好类型：RPG"。

    Returns:
        str，冒号前的前缀；无冒号时返回完整列名。
    """
    s = str(col_name).strip()
    if "：" in s:
        return s.split("：", 1)[0].strip()
    if ":" in s:
        return s.split(":", 1)[0].strip()
    return s


def detect_column_type(col_name, series, prefix, multi_prefixes):
    """自动推断列的题型，遵循多选优先、0/1 不视为评分的判断优先级。

    判断优先级（高→低）：排序题 → 多选前缀匹配 → 纯 0/1 二分列（→单选）
    → 数值范围在 [0,10] 且唯一值 ≤11 → 题干像 NPS 则 NPS，否则评分 → 默认单选。

    Args:
        col_name: str，列名。
        series: pd.Series，该列的原始数据。
        prefix: str，该列的题干前缀（由 get_prefix 提取）。
        multi_prefixes: set or list，已识别的多选题前缀集合。

    Returns:
        str，题型标签：'排序' / '多选' / '评分' / '单选'。
    """
    name = str(col_name)
    s = series
    if "排序" in name:
        return "排序"
    # 多选前缀优先检查，避免 0/1 编码多选列被误判为「评分」
    if prefix in multi_prefixes:
        return "多选"
    numeric = pd.api.types.is_numeric_dtype(s)
    if numeric:
        ser = pd.to_numeric(s, errors="coerce")
        uniq = ser.dropna().unique()
        if len(uniq) > 0:
            vmin = float(pd.Series(uniq).min())
            vmax = float(pd.Series(uniq).max())
            # 纯 0/1 二分编码列不视为评分（常见于多选 0/1 矩阵）
            if set(float(x) for x in uniq).issubset({0.0, 1.0}):
                return "单选"
            if len(uniq) <= 11 and 0 <= vmin and vmax <= 10:
                if stem_text_suggests_nps(name):
                    return "NPS"
                return "评分"
    return "单选"


def get_option_label(col_name):
    """提取列名中冒号之后的选项标签文本。

    Args:
        col_name: str，问卷列名，如 "Q4. 偏好类型：RPG"。

    Returns:
        str，冒号后的选项文本；无冒号或选项为空时返回完整列名。
    """
    s = str(col_name).strip()
    # 问卷星多选常见：题干里含“限选N个…）(首个选项)”；
    # 优先提取最后一段选项括号，避免把“限选提示”带入选项文本。
    if re.search(r"(?:限选|最多选|最多可选)\s*\d+\s*(?:个|项)", s):
        m_tail_opt = re.search(r"[)）]\s*[（(]\s*(.+?)\s*[)）]\s*$", s)
        if m_tail_opt and m_tail_opt.group(1).strip():
            label = m_tail_opt.group(1).strip()
            if not re.fullmatch(r"[\s_＿()（）:：-]+", label):
                return label
    if "：" in s:
        parts = s.split("：", 1)
        if len(parts) > 1 and parts[1].strip():
            label = parts[1].strip()
            return "" if re.fullmatch(r"[\s_＿()（）:：-]+", label) else label
    if ":" in s:
        parts = s.split(":", 1)
        if len(parts) > 1 and parts[1].strip():
            label = parts[1].strip()
            return "" if re.fullmatch(r"[\s_＿()（）:：-]+", label) else label
    # 问卷星常见无冒号多选子列：`5(选项...)` / `5 (选项...)` / `Q5. ...?(选项...)`
    # 1) 优先提取问号后的最后一段括号内容
    m_q_paren = re.search(r"[?？]\s*[（(]\s*(.+?)\s*[)）]\s*$", s)
    if m_q_paren and m_q_paren.group(1).strip():
        label = m_q_paren.group(1).strip()
        return "" if re.fullmatch(r"[\s_＿()（）:：-]+", label) else label

    # 2) 去掉题号前缀（如 `5.` / `5、` / `5(` / `Q5.`）
    cleaned = re.sub(r"^\s*Q?\d+\s*[、.。)\]）]?\s*", "", s).strip()
    cleaned = re.sub(r"^\s*\d+\s*[（(]\s*", "", cleaned).strip()

    # 3) 若整体被括号包裹，去壳后返回
    m_wrap = re.match(r"^[（(]\s*(.+?)\s*[)）]\s*$", cleaned)
    if m_wrap and m_wrap.group(1).strip():
        label = m_wrap.group(1).strip()
        return "" if re.fullmatch(r"[\s_＿()（）:：-]+", label) else label

    label = cleaned if cleaned else s
    return "" if re.fullmatch(r"[\s_＿()（）:：-]+", label) else label


def count_mentions(series):
    """统计多选题列中有效提及（被选中）的样本数量。

    针对两种常见编码方式：数值型 0/1（>0 视为提及）和文本型（过滤空值/否/未选等）。

    Args:
        series: pd.Series，多选题单列数据。

    Returns:
        int，有效提及数量；series 为 None 时返回 0。
    """
    if series is None:
        return 0
    # 多选题的“提及”计数：常见两种编码
    # - 数值型 0/1：仅 >0 视为提及（0 为未选）
    # - 文本型：过滤掉明确的“未选/否/0/空”等
    if pd.api.types.is_numeric_dtype(series):
        s = pd.to_numeric(series, errors="coerce")
        return int((s.fillna(0) > 0).sum())
    invalid_raw = {
        "",
        "0",
        "0.0",
        "否",
        "未选",
        "nan",
        "none",
        "无",
        "na",
        "n/a",
    }
    invalid_lower = {s.lower() for s in invalid_raw}
    ser = series.astype(str).str.strip()
    is_null = series.isna()
    mask_valid = ~is_null & ~ser.str.lower().isin(invalid_lower)
    return int(mask_valid.sum())


def stem_text_suggests_nps(text: str) -> bool:
    """题干/列名拼接文本是否像 NPS（0–10 推荐意愿），与 Pipeline 口径对齐（启发式）。"""
    t = str(text).replace(" ", "").lower()
    nps_keys = ("nps", "净推荐", "推荐意愿", "推荐可能性", "推荐概率", "recommend")
    if any(k in t for k in nps_keys):
        return True
    if "推荐" in t and any(k in t for k in ("意愿", "可能", "多大")):
        return True
    return False


def infer_type_from_columns(info):
    """通过列名关键词推断该题目的题型（多选/矩阵/评分/填空/单选）。

    将题目所有列名拼接后做关键词匹配，优先级：矩阵 > 多选 > NPS > 填空 > 单选 > 评分。

    Args:
        info: dict，含键 "all_cols"（list[str]），该题目下所有列名的列表。

    Returns:
        str or None，题型字符串如 "多选题"/"矩阵评分题"/"NPS题"/"单选题" 等；无匹配时返回 None。
    """
    cols = info.get("all_cols", [])
    if not cols:
        return None
    joined = "｜".join(str(c) for c in cols)
    text = joined.replace(" ", "")
    if "矩阵单选" in text or "【矩阵单选" in text:
        return "矩阵单选题"
    if "矩阵评分" in text or "【矩阵评分" in text:
        return "矩阵评分题"
    if "【多选题" in text or "【多选】" in text or "多选题" in text or "（多选）" in text or "(多选)" in text or "[多选]" in text:
        return "多选题"
    if "多选" in text and ("限选" in text or "最多选" in text):
        return "多选题"
    # 兼容问卷星“多选”常见但未显式包含“多选”关键词的写法：
    # 例如：「……（限选3个，如果多于3个，请选择您最不满意的点）(选项A …),」
    # 这类列在旧逻辑中可能无法命中多选推断，随后被数值启发式误判为「评分」。
    if re.search(r"(?:限选|最多选|最多可选)\s*\d+\s*(?:个|项)", text):
        return "多选题"
    if stem_text_suggests_nps(joined):
        return "NPS题"
    if "开放题" in text or "（开放题）" in text or "【开放题】" in text:
        return "填空题"
    if "【单选】" in text or "【单选题" in text or "单选题" in text or "（单选）" in text or "(单选)" in text or "[单选]" in text:
        return "单选题"
    if "【评分】" in text or "评分题" in text or "打分题" in text or "[评分]" in text:
        return "评分题"
    return None


def _option_base_for_other(col_name: str) -> str:
    """
    取列名中选项部分（题干与选项之间为第一个冒号，取其后内容），并去掉末尾 .8/.9 得到可比较的基名。
    用于判断「其他」相邻两列是否同名。
    """
    s = str(col_name).strip()
    idx = -1
    for sep in (":", "："):
        pos = s.find(sep)
        if pos >= 0 and (idx < 0 or pos < idx):
            idx = pos
    if idx >= 0:
        option = s[idx + 1 :].strip()
    else:
        option = s
    if option.endswith(".9") or option.endswith(".8"):
        option = option[:-2].strip()
    return option


def is_companion_text_column(
    col_name: str,
    ordered_all_cols_in_question: list,
    index_in_question: int | None = None,
) -> bool:
    """判断是否为「其他」选项的附属文本填写列，避免将其计入多选提及率分析。

    仅当满足：与前一列紧挨着，且两列选项基名相同且含「其他」关键词时，
    将后一列视为前一列「其他」附带的文本填写列；其他情况均视为普通多选列。

    Args:
        col_name: str，待判断的列名。
        ordered_all_cols_in_question: list[str]，该题目下所有列名的有序列表。
        index_in_question: int or None，col_name 在列表中的下标；
            存在同名列时必须传入以避免 index() 取到错误位置。

    Returns:
        bool，True 表示该列是附属文本填写列，应被忽略；False 表示正常多选列。
    """
    all_str = [str(x).strip() for x in ordered_all_cols_in_question]
    if index_in_question is not None:
        i = index_in_question
        if i < 0 or i >= len(all_str) or all_str[i] != str(col_name).strip():
            return False
    else:
        try:
            i = all_str.index(str(col_name).strip())
        except ValueError:
            return False
    if i < 1:
        return False
    prev_name = all_str[i - 1]
    base_cur = _option_base_for_other(col_name)
    base_prev = _option_base_for_other(prev_name)
    if base_cur != base_prev:
        return False
    if "其他" not in base_cur:
        return False
    return True


def parse_columns_for_questions(columns):
    """解析 DataFrame 列名列表，按题号分组并提取题干信息。

    从列名中提取题号（extract_qnum）和题干（advanced_split），
    将同一题号的所有列归并，并保留最长的题干文本。

    Args:
        columns: list or Index，问卷 DataFrame 的列名序列。

    Returns:
        defaultdict，键为题号（int），值为 dict：
          - "stem": str，该题最长题干文本。
          - "all_cols": list[str]，该题所有列名列表。
        注意：无法解析题号（非整数）的列会被跳过。
    """
    questions_data = defaultdict(lambda: {"stem": "", "all_cols": []})
    cols_list = list(columns)
    limit_multi_pat = re.compile(r"(?:限选|最多选|最多可选)\s*\d+\s*(?:个|项)")

    for idx, col in enumerate(cols_list):
        col_str = str(col).strip()
        q_num_str = extract_qnum(col_str)
        if not q_num_str:
            # 兼容：问卷星导出里，部分“多选题（限选N个）”的第一列可能不带题号前缀，
            # 但紧挨着后面会出现诸如 `4(选项...)` 这种可解析题号的列。
            # 若当前列含“限选/最多选”，则归并到“后续最近能解析出题号的那一组”。
            if limit_multi_pat.search(col_str):
                next_q_num = None
                for j in range(idx + 1, len(cols_list)):
                    qn = extract_qnum(str(cols_list[j]).strip())
                    if qn:
                        next_q_num = qn
                        break
                if next_q_num:
                    q_num_str = next_q_num
                else:
                    continue
            else:
                continue
        try:
            q_num = int(q_num_str)
        except ValueError:
            continue
        questions_data[q_num]["all_cols"].append(col_str)
        stem_part, _ = advanced_split(col_str)
        stem = re.sub(rf"^\s*Q{q_num_str}[\s._\-、，:：]*", "", stem_part).strip()
        if not stem:
            stem = col_str
        if len(stem) > len(questions_data[q_num]["stem"]):
            questions_data[q_num]["stem"] = stem
    return questions_data

