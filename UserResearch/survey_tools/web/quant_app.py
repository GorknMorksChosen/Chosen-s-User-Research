import io
import datetime
import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st
from survey_tools.utils.io import (
    read_table_auto,
    load_sav,
    apply_sav_labels,
    ExportBundle,
    export_xlsx,
)
from survey_tools.utils.wjx_header import normalize_wjx_headers
from survey_tools.core.quant import (
    calculate_rating_metrics,
    run_group_difference_test,
    process_ranking_data,
    run_within_group_multi_choice,
    run_within_group_matrix_rating,
    make_safe_sheet_name,
)
from survey_tools.core.question_type import (
    get_prefix,
    detect_column_type,
    get_option_label,
    count_mentions,
    is_companion_text_column,
    stem_text_suggests_nps,
)
from survey_tools.core.effect_size import interpret_effect_size
from survey_tools.core.quant import build_question_specs, run_quant_cross_engine
from survey_tools.web.outline_upload import (
    OUTLINE_CAPTION,
    OUTLINE_PLATFORM_OPTIONS,
    outline_raw_to_quant_type_map,
    parse_uploaded_outline_file,
)


def init_session_state():
    if "df" not in st.session_state:
        st.session_state.df = None
    if "core_segment_col" not in st.session_state:
        st.session_state.core_segment_col = None
    if "analysis_results" not in st.session_state:
        st.session_state.analysis_results = []
    if "quant_summary" not in st.session_state:
        st.session_state.quant_summary = ""
    if "column_type_df" not in st.session_state:
        st.session_state.column_type_df = None
    if "export_ranking_buffer" not in st.session_state:
        st.session_state.export_ranking_buffer = None
    if "export_ranking_name" not in st.session_state:
        st.session_state.export_ranking_name = ""
    if "export_cross_buffer" not in st.session_state:
        st.session_state.export_cross_buffer = None
    if "export_cross_name" not in st.session_state:
        st.session_state.export_cross_name = ""
    if "debug_log_enabled" not in st.session_state:
        st.session_state.debug_log_enabled = False
    if "debug_log_lines" not in st.session_state:
        st.session_state.debug_log_lines = []
    if "combined_group_recipes" not in st.session_state:
        # [{"name": str, "cols": [str, ...]}]
        st.session_state.combined_group_recipes = []
    if "outline_q_num_to_type" not in st.session_state:
        st.session_state.outline_q_num_to_type = None  # 可选大纲解析后的题号→题型映射


def debug_log(message: str) -> None:
    if not st.session_state.get("debug_log_enabled", False):
        return
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.debug_log_lines.append(f"[{timestamp}] {message}")


def apply_combined_group_recipes(df: pd.DataFrame) -> pd.DataFrame:
    """根据 session_state 中记录的组合分组配方，在每次 rerun 时重建组合分组列。"""
    recipes = st.session_state.get("combined_group_recipes") or []
    if not recipes:
        return df
    out = df.copy()
    for r in recipes:
        try:
            name = (r or {}).get("name")
            cols = (r or {}).get("cols") or []
            if not name or not cols:
                continue
            missing = [c for c in cols if c not in out.columns]
            if missing:
                debug_log(f"组合分组配方跳过（缺列）: {name} | missing={missing[:10]}")
                continue
            out[name] = out[cols].astype(str).apply(
                lambda row: " | ".join(f"{c}={v}" for c, v in zip(cols, row.tolist())),
                axis=1,
            )
        except Exception as e:
            debug_log(f"组合分组配方重建失败: {r} | error={repr(e)}")
    return out

def load_data(uploaded_file, sheet_name=0):
    if isinstance(uploaded_file, pd.ExcelFile):
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
    else:
        df = read_table_auto(uploaded_file, sheet_name=sheet_name)
    df.columns = [str(c).strip() for c in df.columns]
    return df

def analyze_single_choice(df, core_segment_col, question_col):
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
            records.append(
                {
                    "题目": question_col,
                    "核心分组": seg_value,
                    "选项": str(option),
                    "频次": int(count),
                    "行百分比": float(ratio),
                    "组样本数": int(total),
                }
            )
    if not records:
        return pd.DataFrame(
            columns=["题目", "核心分组", "选项", "频次", "行百分比", "组样本数"]
        )
    return pd.DataFrame(records)

def analyze_multi_choice(df, core_segment_col, prefix, option_cols):
    records = []
    grouped = df.groupby(core_segment_col, dropna=True)
    for seg_value, group in grouped:
        # 修改：多选题分母应为“该题有效作答人数”，而非分组总人数
        # 逻辑：题组内任意一项不为NaN即视为参与了该题（处理跳题逻辑）
        # 注意：如果未选中是0，0不是NaN，会被计入分母（正确，因为该用户看到了题只是没选）
        # 如果未选中是NaN（且该用户未选任何项），则会被排除（正确，视为Skip或Missing）
        subset = group[option_cols]
        valid_n = len(subset.dropna(how='all'))
        
        total = valid_n
        if total == 0:
            continue
        for col in option_cols:
            mentions = count_mentions(group[col])
            ratio = mentions / total if total > 0 else 0
            option_label = get_option_label(col)
            records.append(
                {
                    "题目": prefix,
                    "核心分组": seg_value,
                    "选项": option_label,
                    "提及人数": int(mentions),
                    "提及率": float(ratio),
                    "组样本数": int(total),
                }
            )
    if not records:
        return pd.DataFrame(
            columns=["题目", "核心分组", "选项", "提及人数", "提及率", "组样本数"]
        )
    return pd.DataFrame(records)

def pivot_v13_style(df_long, q_type, core_segment_col, option_order=None, stats_res=None, alpha=0.05):
    """Convert long-form analysis results to v1.3 style pivot table.
    option_order: for 多选, list of option labels in questionnaire order; pivot rows will follow this order.
    stats_res: result dict from run_group_difference_test（H3：不再依赖 df._stats 死代码）.
    """
    if df_long.empty:
        return df_long
    
    if q_type in ("单选", "评分", "NPS", "矩阵单选", "矩阵评分"):
        # Rows: 选项, Cols: 核心分组, Value: 行百分比
        pivot = df_long.pivot_table(
            index="选项", 
            columns="核心分组", 
            values="行百分比", 
            aggfunc="first", 
            fill_value=0
        ).reset_index()
        
        # Calculate Totals
        total_counts = df_long.groupby("选项")["频次"].sum()
        total_samples = df_long["频次"].sum()
        total_ratio = total_counts / total_samples if total_samples > 0 else 0
        
        pivot["总计"] = pivot["选项"].map(total_ratio)
        pivot["人数"] = pivot["选项"].map(total_counts)
        
        # Add Stats Info if available
        if stats_res:
            overall = stats_res.get("overall", {})
            p_val = overall.get("p_value")
            eff = overall.get("effect_size")
            test_name = overall.get("test")
            
            # Format P-value
            if p_val is not None and not np.isnan(p_val):
                sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < alpha else ""
                pivot["P值"] = f"{p_val:.3f}{sig}"
            else:
                pivot["P值"] = ""
                
            # Format Effect Size
            if eff is not None and not np.isnan(eff):
                # Keep as float for conditional formatting, format later for display
                pivot["效应量"] = eff
            else:
                pivot["效应量"] = np.nan
                
            pivot["检验方法"] = test_name or ""
            
            # Apply arrows if available
            arrows = stats_res.get("posthoc_arrows", {})
            if arrows:
                # Pivot columns are group names
                # Pivot index is option names (in '选项' column)
                for group_col_name in pivot.columns:
                    if group_col_name in ["选项", "总计", "人数", "P值", "效应量", "检验方法"]:
                        continue
                        
                    def format_with_arrow(val, opt_label):
                        # val is float ratio (e.g. 0.45)
                        if pd.isna(val): return ""
                        
                        arrow = arrows.get((group_col_name, opt_label), "")
                        pct_str = f"{val:.1%}"
                        if arrow:
                            return f"{pct_str} {arrow}"
                        return pct_str
                    
                    # Apply using index to get option label
                    pivot[group_col_name] = [
                        format_with_arrow(pivot.at[i, group_col_name], pivot.at[i, "选项"]) 
                        for i in pivot.index
                    ]

    else: # 多选
        # Rows: 选项, Cols: 核心分组, Value: 提及率
        pivot = df_long.pivot_table(
            index="选项", 
            columns="核心分组", 
            values="提及率", 
            aggfunc="first", 
            fill_value=0
        ).reset_index()
        
        group_sizes = df_long.groupby("核心分组")["组样本数"].first()
        total_sample_size = group_sizes.sum()
        
        total_mentions = df_long.groupby("选项")["提及人数"].sum()
        total_ratio = total_mentions / total_sample_size if total_sample_size > 0 else 0
        
        pivot["总计"] = pivot["选项"].map(total_ratio)
        pivot["人数"] = pivot["选项"].map(total_mentions)

        # 按问卷选项顺序固定行序（v1.3 行为）
        if option_order and len(option_order) > 0:
            present = pivot["选项"].unique().tolist()
            order = [x for x in option_order if x in present] + [x for x in present if x not in option_order]
            pivot["选项"] = pd.Categorical(pivot["选项"], categories=order, ordered=True)
            pivot = pivot.sort_values("选项").reset_index(drop=True)

        # Add Stats for Multi-choice
        # For multi-choice, we might have detailed per-option stats or overall
        if stats_res:
             details = stats_res.get("details", [])
             overall = stats_res.get("overall", {})
             
             # If we have details, map them to options
             if details:
                 p_map = {}
                 eff_map = {}
                 for d in details:
                     lbl = d.get("option_label") or d.get("option")
                     if lbl is None:
                         continue
                     lbl = str(lbl).strip()
                     p_corr = d.get("p_value_corrected")
                     p_map[lbl] = p_corr if pd.notna(p_corr) else d.get("p_value")
                     eff_map[lbl] = d.get("effect_size")

                 def format_p(lbl):
                     val = p_map.get(lbl)
                     if val is not None and not (isinstance(val, float) and np.isnan(val)):
                         sig = "***" if val < 0.001 else "**" if val < 0.01 else "*" if val < alpha else ""
                         return f"{val:.3f}{sig}"
                     return ""
                     
                 def format_eff(lbl):
                     val = eff_map.get(lbl)
                     if val is not None and not np.isnan(val):
                         return val # Keep as float
                     return np.nan

                 pivot["P值"] = pivot["选项"].apply(format_p)
                 pivot["效应量"] = pivot["选项"].apply(format_eff)
                 pivot["检验方法"] = "Chi-square" # Usually per option
             
             elif overall:
                 # Fallback to overall
                 p_val = overall.get("p_value")
                 if p_val is not None and not np.isnan(p_val):
                     sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < alpha else ""
                     pivot["P值"] = f"{p_val:.3f}{sig}"
                 else:
                     pivot["P值"] = ""
                 pivot["效应量"] = overall.get('effect_size', np.nan) # Keep as float
                 pivot["检验方法"] = overall.get("test", "")
        
    return pivot

def build_markdown_summary(analysis_results, core_segment_col):
    lines = []
    lines.append(f"核心分组列：{core_segment_col}")
    for res in analysis_results:
        question = res["题目"]
        q_type = res["题型"]
        df_q = res["数据"]
        if df_q.empty:
            continue
        lines.append(f"\n### 题目：{question}（{q_type}）")
        for seg_value, group in df_q.groupby("核心分组"):
            total = (
                int(group["组样本数"].iloc[0])
                if "组样本数" in group.columns and not group["组样本数"].isna().all()
                else None
            )
            if total is not None:
                lines.append(f"- 分组：{seg_value}（n={total}）")
            else:
                lines.append(f"- 分组：{seg_value}")
            if q_type in ("单选", "评分", "NPS", "矩阵单选", "矩阵评分"):
                group_sorted = group.sort_values("行百分比", ascending=False)
                for _, row in group_sorted.iterrows():
                    pct = row["行百分比"] * 100
                    lines.append(
                        f"  - {row['选项']}: {pct:.1f}% ({int(row['频次'])})"
                    )
            else:
                # 多选
                group_sorted = group.sort_values("提及率", ascending=False)
                for _, row in group_sorted.iterrows():
                    pct = row["提及率"] * 100
                    lines.append(
                        f"  - {row['选项']}: {pct:.1f}% ({int(row['提及人数'])})"
                    )
    return "\n".join(lines)

def build_json_summary(analysis_results, core_segment_col):
    summary = {"core_segment": core_segment_col, "questions": []}
    for res in analysis_results:
        question = res["题目"]
        q_type = res["题型"]
        df_q = res["数据"]
        if df_q.empty:
            continue
        q_entry = {"name": question, "type": q_type, "data": []}
        for _, row in df_q.iterrows():
            item = {
                "segment": row["核心分组"],
                "option": row["选项"],
                "group_size": int(row["组样本数"])
                if "组样本数" in df_q.columns
                else None,
            }
            if q_type in ("单选", "评分", "NPS", "矩阵单选", "矩阵评分"):
                item["count"] = int(row["频次"])
                item["ratio"] = float(row["行百分比"])
            else:
                item["count"] = int(row["提及人数"])
                item["ratio"] = float(row["提及率"])
            q_entry["data"].append(item)
        summary["questions"].append(q_entry)
    import json
    return json.dumps(summary, ensure_ascii=False, indent=2)

def main():
    init_session_state()

    st.set_page_config(page_title="问卷定量交叉分析工具", layout="wide")
    st.title("问卷定量交叉分析")
    st.markdown("基于 Pandas 的定量交叉分析与分组对比，不依赖 LLM。")

    with st.expander("调试与日志（定位异常用）", expanded=False):
        st.session_state.debug_log_enabled = st.checkbox(
            "开启调试日志（仅记录统计摘要，不记录原始逐行数据）",
            value=st.session_state.debug_log_enabled,
            key="debug_log_enabled_checkbox",
        )
        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("清空日志", key="debug_log_clear"):
                st.session_state.debug_log_lines = []
        with col_b:
            log_text = "\n".join(st.session_state.debug_log_lines)
            st.download_button(
                "下载 log",
                data=log_text.encode("utf-8"),
                file_name="quant_debug.log",
                mime="text/plain",
                key="debug_log_download",
            )
        st.caption("建议：先勾选开启日志，再上传文件并运行一次「全自动交叉分析」，然后下载 log 发我。")

    uploaded_file = st.file_uploader("上传问卷数据文件（Excel / CSV / SAV）", type=["xlsx", "xls", "csv", "sav"])

    if uploaded_file:
        try:
            name = uploaded_file.name.lower()
            if name.endswith(".csv"):
                df = load_data(uploaded_file)
            elif name.endswith(".sav"):
                # 缓存 .sav 解析结果，避免勾选切换时重复 read 导致流耗尽
                # M5: 缓存键加入文件大小，同名不同内容时强制重新读取
                cache_key = f"sav_{uploaded_file.name}_{uploaded_file.size}"
                if (
                    getattr(st.session_state, "sav_cache_key", None) != cache_key
                    or st.session_state.get("sav_df_raw") is None
                ):
                    df, variable_labels, value_labels = load_sav(uploaded_file)
                    st.session_state.sav_cache_key = cache_key
                    st.session_state.sav_df_raw = df
                    st.session_state.sav_variable_labels = variable_labels
                    st.session_state.sav_value_labels = value_labels
                df = st.session_state.sav_df_raw.copy()
                variable_labels = st.session_state.sav_variable_labels
                value_labels = st.session_state.sav_value_labels
                apply_var = st.checkbox(
                    "应用变量标签（用题干作为列名）",
                    value=True,
                    key="sav_apply_variable_labels",
                )
                apply_val = st.checkbox(
                    "应用值标签（用选项文字替换编码）",
                    value=False,
                    key="sav_apply_value_labels",
                )
                if variable_labels or value_labels:
                    df = apply_sav_labels(
                        df,
                        variable_labels=variable_labels or None,
                        value_labels=value_labels or None,
                        apply_variable_labels=apply_var,
                        apply_value_labels=apply_val,
                    )
            else:
                xls = pd.ExcelFile(uploaded_file)
                sheet_names = xls.sheet_names
                if len(sheet_names) > 1:
                    sheet_name = st.selectbox("请选择要分析的工作表 (Sheet)", sheet_names)
                else:
                    sheet_name = sheet_names[0]
                df = load_data(xls, sheet_name=sheet_name)
            df, wjx_modified = normalize_wjx_headers(df)
            if wjx_modified:
                st.info("已自动规范化问卷星表头，便于多选/矩阵题识别。")
            # 重要：每次 rerun 都会重建 df；这里把工具内生成的组合分组列按“配方”自动补回
            df = apply_combined_group_recipes(df)
            st.session_state.df = df
            debug_log(f"已读取文件: {uploaded_file.name} | rows={len(df)} cols={len(df.columns)}")
            st.success(f"成功读取文件：{uploaded_file.name}，共 {len(df)} 行，{len(df.columns)} 列")
        except Exception as e:
            debug_log(f"读取文件失败: {uploaded_file.name if uploaded_file else ''} | error={repr(e)}")
            st.error(f"读取文件失败：{e}")

    df = st.session_state.df

    if df is not None:
        st.subheader("数据预览")
        st.dataframe(df.head(10), use_container_width=True)
        columns = df.columns.tolist()

        # 可选：问卷大纲上传（用于提升题型识别，与 Pipeline 共享解析逻辑）
        with st.expander("问卷大纲（可选，用于提升题型识别）"):
            st.caption(OUTLINE_CAPTION)
            col_out_u, col_out_s = st.columns([2, 1])
            with col_out_u:
                outline_upload = st.file_uploader(
                    "上传大纲文件（.docx / .txt）",
                    type=["docx", "txt"],
                    key="outline_uploader",
                )
            with col_out_s:
                outline_platform_label = st.selectbox(
                    "大纲来源",
                    OUTLINE_PLATFORM_OPTIONS,
                    key="outline_platform_select",
                    help="选择与您导出大纲一致的平台，以使用对应解析规则。",
                )

            if outline_upload:
                try:
                    outline = parse_uploaded_outline_file(
                        outline_upload, outline_platform_label
                    )
                    st.session_state.outline_q_num_to_type = outline_raw_to_quant_type_map(
                        outline
                    )
                    st.session_state.column_type_df = None  # 强制重建题型表以应用大纲
                    st.success(
                        f"已解析大纲：{outline_upload.name}（{outline_platform_label}），"
                        f"共 {len(outline)} 道题"
                    )
                except ValueError as e:
                    st.warning(str(e))
                    st.session_state.outline_q_num_to_type = None
                except Exception as e:
                    st.error(f"大纲解析失败：{e}")
                    st.session_state.outline_q_num_to_type = None
            else:
                if st.session_state.outline_q_num_to_type is not None:
                    st.caption("已清除大纲，将使用自动识别 + 手动调整")
                st.session_state.outline_q_num_to_type = None

        # 自动识别题型 (Logic from question_type.py)
        #
        # 注意：当用户在工具内生成「组合分组列」后，columns 会发生变化。
        # 这里如果直接重建整张题型表，会把用户手动标记（例如「忽略」）全部覆盖掉，
        # 进而导致“已忽略的子列仍被统计”的问题。
        #
        # 因此这里改为：当列集合变化时，**增量合并**新列的自动识别结果，保留旧列的「题型」。
        if (
            st.session_state.column_type_df is None
            or set(st.session_state.column_type_df["列名"]) != set(columns)
        ):
            # 1. Parse questions first to group columns
            from survey_tools.core.question_type import parse_columns_for_questions, infer_type_from_columns
            questions_data = parse_columns_for_questions(columns)
            
            # 2. Infer types for each question group
            q_num_to_type = {}
            for q_num, info in questions_data.items():
                inferred = infer_type_from_columns(info)
                if inferred:
                    q_num_to_type[q_num] = inferred

            # 2b. 大纲覆盖：若有上传大纲，用大纲题型覆盖（与 Pipeline 一致）
            outline_map = st.session_state.get("outline_q_num_to_type")
            if outline_map:
                for q_num, otype in outline_map.items():
                    q_num_to_type[q_num] = otype

            # 3. Map back to individual columns
            from collections import defaultdict
            q_idx_in_question = defaultdict(int)  # 每题内列的下标，用于同名「其他」时区分前后列
            prev_type_df = st.session_state.column_type_df
            prev_type_map = {}
            if prev_type_df is not None and "列名" in prev_type_df.columns and "题型" in prev_type_df.columns:
                try:
                    prev_type_map = dict(zip(prev_type_df["列名"].astype(str), prev_type_df["题型"]))
                except Exception:
                    prev_type_map = {}

            combined_names = {
                (x or {}).get("name")
                for x in (st.session_state.get("combined_group_recipes") or [])
                if isinstance((x or {}).get("name"), str)
            }

            records = []
            for c in columns:
                series = df[c]
                from survey_tools.core.quant import extract_qnum
                q_num_str = extract_qnum(str(c))
                q_num = None
                if q_num_str:
                    try:
                        q_num = int(q_num_str)
                    except ValueError:
                        pass

                all_cols = questions_data.get(q_num, {}).get("all_cols", []) if q_num is not None else []
                idx_in_q = q_idx_in_question[q_num] if q_num is not None else 0
                if q_num is not None:
                    q_idx_in_question[q_num] += 1

                final_type = "单选" # Default fallback

                if q_num is not None and q_num in q_num_to_type:
                    v13_type = q_num_to_type[q_num]
                    # 兼容 infer_type_from_columns 的长格式与 outline 的短格式
                    if v13_type in ("多选题", "多选"): final_type = "多选"
                    elif v13_type in ("单选题", "单选"): final_type = "单选"
                    elif v13_type in ("NPS题", "NPS"): final_type = "NPS"
                    elif v13_type in ("评分题", "评分"): final_type = "评分"
                    elif v13_type in ("矩阵单选题", "矩阵"): final_type = "矩阵"
                    elif v13_type in ("矩阵评分题", "矩阵评分"): final_type = "矩阵"
                    elif v13_type in ("填空题", "忽略"): final_type = "忽略"

                # 附属文本列：仅当与前一列紧挨且同名（或同基名含「其他」）时，后一列标为忽略
                if is_companion_text_column(str(c), [str(x) for x in all_cols], idx_in_q):
                    final_type = "忽略"

                # If still default, try old logic as backup
                if final_type == "单选":
                     c_str = str(c)
                     if (
                         "Type_" in c_str
                         or c_str.strip().lower().startswith("type.")
                         or "其他" in c_str
                         or "填空" in c_str
                         or "建议" in c_str
                     ):
                         final_type = "忽略"
                     elif "排序" in c_str:
                         final_type = "排序"
                     else:
                        # 仅当未从题干推断为「单选题」时，才用数值启发式覆盖为评分
                        from_inferred_single = (
                            q_num is not None
                            and q_num in q_num_to_type
                            and q_num_to_type[q_num] == "单选题"
                        )
                        if not from_inferred_single:
                            numeric = pd.api.types.is_numeric_dtype(series)
                            if numeric:
                                uniq = series.dropna().unique()
                                if len(uniq) > 0:
                                    vmin = float(pd.Series(uniq).min())
                                    vmax = float(pd.Series(uniq).max())
                                    if len(uniq) <= 11 and 0 <= vmin and vmax <= 10:
                                        final_type = (
                                            "NPS"
                                            if stem_text_suggests_nps(c_str)
                                            else "评分"
                                        )

                # 组合分组列是“分析维度列”，默认不参与题目统计，避免污染题目列表
                if str(c) in combined_names:
                    final_type = "忽略"

                # 保留用户之前手动修改过的题型（尤其是「忽略」）
                manual_type = prev_type_map.get(str(c))
                effective_type = manual_type if manual_type else final_type

                records.append({"列名": c, "自动类型": final_type, "题型": effective_type})
            st.session_state.column_type_df = pd.DataFrame(records)
            
        st.subheader("题型微调")
        with st.form("type_editor_form"):
            type_df = st.data_editor(
                st.session_state.column_type_df,
                num_rows="fixed",
                column_config={
                    "题型": st.column_config.SelectboxColumn(
                        "题型",
                        options=["单选", "多选", "评分", "NPS", "矩阵", "排序", "忽略"],
                    )
                },
                hide_index=True,
                key="column_type_editor",
                height=400, # Set a fixed height to avoid layout shift
            )
            submitted = st.form_submit_button("确认并应用修改")
            
        if submitted:
            st.session_state.column_type_df = type_df
            st.success("题型修改已应用！")
            
        # Use the latest type_df (either from session state or form return) for downstream logic
        # But wait, if not submitted, type_df is the one inside the form. 
        # We should rely on session_state for persistence across reruns that are NOT form submissions.
        # Actually, when inside a form, st.data_editor returns the current state of the UI.
        # But changes are not sent to backend until submit.
        
        # To ensure downstream logic always uses the valid confirmed types:
        if submitted:
             current_type_df = type_df
        else:
             current_type_df = st.session_state.column_type_df

        column_type_map = {
            row["列名"]: row["题型"]
            for _, row in current_type_df.iterrows()
            if isinstance(row.get("列名"), str)
        }
        
        with st.expander("高级分组设置：在工具内生成组合分组列"):
            combined_cols = st.multiselect(
                "选择用于组合的新分组列",
                options=columns,
                key="combined_group_cols",
            )
            default_group_name = st.session_state.get("combined_group_name", "组合分组")
            combined_name = st.text_input(
                "新分组列名称",
                value=default_group_name,
                key="combined_group_name_input",
            )
            if st.button("生成组合分组列", key="create_combined_group"):
                if combined_cols and combined_name.strip():
                    name = combined_name.strip()
                    new_series = df[combined_cols].astype(str).apply(
                        lambda r: " | ".join(
                            f"{c}={v}" for c, v in zip(combined_cols, r.tolist())
                        ),
                        axis=1,
                    )
                    st.session_state.df[name] = new_series
                    # 记录配方，保证 rerun/重读文件后仍能重建该列
                    recipes = st.session_state.get("combined_group_recipes") or []
                    if not any((x or {}).get("name") == name for x in recipes):
                        recipes.append({"name": name, "cols": list(combined_cols)})
                        st.session_state.combined_group_recipes = recipes
                        debug_log(f"新增组合分组配方: {name} | cols={list(combined_cols)}")
                    df = st.session_state.df
                    columns = df.columns.tolist()
                    st.session_state.core_segment_col = name
                    # 同步 selectbox 的 widget 状态，否则新增列后选择可能回退为 None
                    st.session_state.core_segment_col_widget = name
                    # 不要对 combined_group_cols 赋值：该 key 已被上面的 multiselect 占用，手动赋值会触发 Streamlit 报错
                    st.session_state.combined_group_name = name
                    st.rerun()
                    
        st.subheader("配置面板")
        with st.expander("🛠️ 交叉分析设置 (点击展开/收起)", expanded=True):
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.markdown("#### 1. 核心分组")
                seg_options = [None] + columns
                current_seg = st.session_state.get("core_segment_col_widget") or st.session_state.get(
                    "core_segment_col"
                )
                try:
                    seg_index = seg_options.index(current_seg) if current_seg in seg_options else 0
                except Exception:
                    seg_index = 0
                core_segment_col = st.selectbox(
                    "🎯 选择核心分组列",
                    options=seg_options,
                    index=seg_index,
                    key="core_segment_col_widget",
                    help="用于交叉分析的维度列，例如：性别、年龄段、玩家类型等。"
                )
                st.session_state.core_segment_col = core_segment_col
                if core_segment_col:
                    try:
                        n_unique = df[core_segment_col].nunique()
                        top_counts = df[core_segment_col].value_counts(dropna=False).head(10).to_dict()
                        debug_log(
                            f"选择核心分组列: {core_segment_col} | unique={n_unique} top10={top_counts}"
                        )
                    except Exception as e:
                        debug_log(f"核心分组列统计失败: {core_segment_col} | error={repr(e)}")

            with col2:
                st.markdown("#### 2. 题目选择")
                # Prepare selection options: Group by question to avoid clutter
                from survey_tools.core.question_type import parse_columns_for_questions
                questions_data = parse_columns_for_questions(columns)
                
                selection_map = {} # label -> [cols]
                display_options = []
                
                # Helper to find type
                def get_col_type(c):
                    if st.session_state.column_type_df is not None:
                        row = st.session_state.column_type_df[st.session_state.column_type_df["列名"] == c]
                        if not row.empty:
                            return row.iloc[0]["题型"]
                    return "未知"

                # 1. Process grouped questions
                processed_cols = set()
                sorted_q_nums = sorted(questions_data.keys())
                for q_num in sorted_q_nums:
                    info = questions_data[q_num]
                    q_cols = info["all_cols"]
                    stem = info["stem"]
                    
                    # Force update types from current_type_df (user edits)
                    # Because questions_data was parsed from columns without user edits
                    types = [get_col_type(c) for c in q_cols]
                    
                    # If all cols in a question are marked as "忽略", skip adding to display options
                    if all(t == "忽略" for t in types):
                        processed_cols.update(q_cols)
                        continue
                    
                    # Heuristic to determine group type based on manual edits
                    # If any col is Multi, treat group as Multi
                    if "多选" in types:
                        label = f"Q{q_num}. {stem} [多选题]"
                        # 仅纳入未被标记为「忽略」的子列
                        selection_map[label] = [c for c in q_cols if get_col_type(c) != "忽略"]
                        display_options.append(label)
                        processed_cols.update(q_cols)
                    elif "矩阵" in types or "矩阵单选" in types or "矩阵评分" in types:
                        # Check if mixed types
                        label = f"Q{q_num}. {stem} [矩阵题]"
                        # 仅纳入未被标记为「忽略」的子列
                        selection_map[label] = [c for c in q_cols if get_col_type(c) != "忽略"]
                        display_options.append(label)
                        processed_cols.update(q_cols)
                    else:
                        # For single columns or groups that are not multi/matrix
                        # Filter out ignored columns within the group if mixed?
                        # Or just add valid ones.
                        valid_cols = [c for c in q_cols if get_col_type(c) != "忽略"]
                        
                        if not valid_cols:
                            processed_cols.update(q_cols)
                            continue
                            
                        # If manually marked as "单选", treat as Single even if it looks like Rating
                        # If manually marked as "评分", treat as Rating
                        
                        # If group has multiple columns but not Multi/Matrix, it might be a split Single choice?
                        # Or just multiple single choice questions sharing same Q num (rare).
                        # Let's treat them individually if not Multi/Matrix.
                        
                        if len(valid_cols) == 1:
                            c = valid_cols[0]
                            t = get_col_type(c)
                            label = f"{c} [{t}]"
                            selection_map[label] = [c]
                            display_options.append(label)
                        else:
                            # Multiple valid cols, but not Multi/Matrix. 
                            # Maybe "排序" or just loose collection.
                            # Treat as group with first col's type
                            t = get_col_type(valid_cols[0])
                            label = f"Q{q_num}. {stem} [{t}组]"
                            selection_map[label] = valid_cols
                            display_options.append(label)
                        
                        processed_cols.update(q_cols)

                remaining_cols = [c for c in columns if c not in processed_cols]
                for c in remaining_cols:
                    t = get_col_type(c)
                    if t == "忽略":
                        continue
                    label = f"{c} [{t}]"
                    selection_map[label] = [c]
                    display_options.append(label)

                analysis_cols_labels = st.multiselect(
                    "📊 选择分析题目 (已自动合并多选/矩阵题)",
                    options=display_options,
                    help="支持多选，系统会自动识别题型并进行相应分析。"
                )
                # M6: 文件切换后 options 变化，已选项不在新 options 里时 Streamlit 静默清空；给用户提示
                if analysis_cols_labels and set(analysis_cols_labels) - set(display_options):
                    st.info("检测到部分已选题目在当前数据中不存在，已自动清除无效选项。请重新确认分析题目选择。")

                analysis_cols = []
                for label in analysis_cols_labels:
                    analysis_cols.extend(selection_map[label])

            st.markdown("---")
            alpha_col, run_col1, run_col2 = st.columns([1, 2, 1])
            with alpha_col:
                sig_alpha = st.number_input(
                    "显著性阈值 alpha",
                    min_value=0.001,
                    max_value=0.2,
                    value=float(st.session_state.get("quant_sig_alpha", 0.05)),
                    step=0.001,
                    format="%.3f",
                    key="quant_sig_alpha",
                    help="统计检验显著性阈值；页面提示、导出星号和检验判定将统一使用该值。",
                )
            with run_col2:
                 run_btn = st.button("开始交叉分析", type="primary", use_container_width=True)
            with run_col1:
                 st.caption(f"点击按钮后，系统将自动进行：交叉制表、卡方检验/ANOVA检验、效应量计算及P值标记（alpha={sig_alpha:.3f}）。")
        
        if run_btn:
            if core_segment_col is None:
                st.warning("请先选择核心分组列。")
            elif not analysis_cols:
                st.warning("请至少选择一列题目进行分析。")
            elif core_segment_col not in df.columns:
                st.error("核心分组列不在当前数据中，请重新选择。")
            else:
                n_unique = df[core_segment_col].nunique()
                n_total = len(df)
                if n_total > 0 and n_unique >= max(2, n_total * 0.9):
                    st.warning(
                        f"核心分组列「{core_segment_col}」有 **{n_unique}** 个不同取值（共 {n_total} 行），"
                        "相当于每行一个分组，交叉结果会全部显示为 100%。"
                        "请选择分类数较少的列（如性别、年龄段、玩家类型）作为核心分组。"
                    )
                debug_log(
                    f"开始全自动交叉分析 | core_segment_col={core_segment_col} | selected_cols={len(analysis_cols)}"
                )
                # v1.3 口径引擎：将当前“列级题型标记”汇总为按题号的 question_types，并交给 engine 统一产出结果
                from survey_tools.core.quant import extract_qnum

                selected_cols_set = set(analysis_cols)
                ignored_cols_set = {c for c, t in column_type_map.items() if t == "忽略"}

                question_types = {
                    "单选": [],
                    "多选": [],
                    "评分": [],
                    "NPS": [],
                    "矩阵单选": [],
                    "矩阵评分": [],
                }
                explicit_single_cols = []
                explicit_rating_cols = []
                explicit_nps_cols = []
                for c in selected_cols_set:
                    if c in ignored_cols_set:
                        continue
                    q_str = extract_qnum(str(c))
                    t = column_type_map.get(c)
                    # 单选/评分/NPS 直接按列统计（不强依赖列名中存在 Q<num>）
                    if t == "单选":
                        explicit_single_cols.append(c)
                    elif t == "评分":
                        explicit_rating_cols.append(c)
                    elif t == "NPS":
                        explicit_nps_cols.append(c)

                    if not q_str:
                        continue
                    try:
                        q_num = int(q_str)
                    except Exception:
                        continue
                    if t == "单选":
                        question_types["单选"].append(q_num)
                    elif t == "多选":
                        question_types["多选"].append(q_num)
                    elif t == "评分":
                        question_types["评分"].append(q_num)
                    elif t == "NPS":
                        question_types["NPS"].append(q_num)
                    elif t == "矩阵":
                        # M2: 同一 q_num 只允许进入一个矩阵类型，避免重复分析
                        already_in_matrix = (
                            q_num in question_types["矩阵评分"]
                            or q_num in question_types["矩阵单选"]
                        )
                        if not already_in_matrix:
                            if pd.api.types.is_numeric_dtype(df[c]):
                                question_types["矩阵评分"].append(q_num)
                            else:
                                question_types["矩阵单选"].append(q_num)

                for k in list(question_types.keys()):
                    question_types[k] = sorted(list(dict.fromkeys(question_types[k])))

                debug_log(f"识别到题型组(v13_engine): { {k: len(v) for k, v in question_types.items()} }")

                question_specs = build_question_specs(df, question_types)
                results = run_quant_cross_engine(
                    df,
                    core_segment_col=core_segment_col,
                    question_specs=question_specs,
                    selected_cols_set=selected_cols_set,
                    ignored_cols_set=ignored_cols_set,
                    explicit_single_cols=explicit_single_cols,
                    explicit_rating_cols=explicit_rating_cols,
                    explicit_nps_cols=explicit_nps_cols,
                    alpha=float(sig_alpha),
                )

                # 结果按题号全局排序：Q1、Q2、Q3...
                # 说明：部分列（尤其是 .sav 应用变量标签后）可能不含 Q<number>，这些会排到最后并保持相对稳定
                def _type_rank(t: str) -> int:
                    order = {
                        "单选": 10,
                        "评分": 20,
                        "NPS": 20,
                        "多选": 30,
                        "矩阵单选": 40,
                        "矩阵评分": 50,
                        "矩阵": 60,
                    }
                    return order.get(str(t), 999)

                def _qnum_sort_key(res: dict):
                    from survey_tools.core.quant import extract_qnum

                    q = res.get("题目")
                    q_str = extract_qnum(str(q)) if q is not None else None
                    q_num = int(q_str) if (q_str and q_str.isdigit()) else 9999
                    return (q_num, _type_rank(res.get("题型")), str(q))

                results = sorted(list(results or []), key=_qnum_sort_key)

                st.session_state.analysis_results = results
                if results:
                    st.success("交叉分析完成。")
                else:
                    st.warning("未生成任何统计结果，请检查选择的题目列和核心分组列。")

    analysis_results = st.session_state.analysis_results

    if analysis_results:
        st.divider()
        st.subheader("题目级交叉统计结果 (仿 v1.3 样式)")
        for res in analysis_results:
            question = res["题目"]
            q_type = res["题型"]
            df_q = res["数据"]
            if df_q.empty:
                continue
            
            st.markdown(f"#### {question}（{q_type}）")
            
            # Use the pivot function to display v1.3 style
            try:
                pivot_df = pivot_v13_style(
                    df_q, q_type, st.session_state.core_segment_col,
                    option_order=res.get("option_order"),
                    stats_res=res.get("stats"),  # H3: 传入真实 stats
                    alpha=float(st.session_state.get("quant_sig_alpha", 0.05)),
                )
                # Formatting for display
                if "总计" in pivot_df.columns:
                    format_dict = {}
                    # Only apply % format to numeric columns
                    if pd.api.types.is_numeric_dtype(pivot_df["总计"]):
                        format_dict["总计"] = "{:.1%}"
                    
                    for col in pivot_df.columns:
                        if col not in ["选项", "人数", "总计", "P值", "效应量", "检验方法"]:
                            # Check if column is numeric before applying format
                            if pd.api.types.is_numeric_dtype(pivot_df[col]):
                                format_dict[col] = "{:.1%}"
                            # If it's object (string), it might contain arrows or formatted strings already
                            # In that case, we don't apply style format
                            
                    st.dataframe(pivot_df.style.format(format_dict), use_container_width=True)
                else:
                    st.dataframe(df_q, use_container_width=True)
            except Exception as e:
                st.error(f"无法展示表格: {e}")
                st.dataframe(df_q, use_container_width=True)

            try:
                if q_type in ("单选", "评分", "NPS", "矩阵单选", "矩阵评分"):
                    fig = px.bar(
                        df_q,
                        x="核心分组",
                        y="行百分比",
                        color="选项",
                        barmode="group",
                        text=df_q["行百分比"].apply(lambda v: f"{v*100:.1f}%"),
                    )
                else:
                    # 多选
                    fig = px.bar(
                        df_q,
                        x="核心分组",
                        y="提及率",
                        color="选项",
                        barmode="group",
                        text=df_q["提及率"].apply(lambda v: f"{v*100:.1f}%"),
                    )
                fig.update_layout(yaxis_tickformat=".0%")
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.caption(f"无法生成图表: {e}")

        st.divider()
        st.subheader("结果导出与量化统计摘要")
        # 构建可导出 sheet：汇总 + 每题一 sheet（一工作簿多 sheet + 用户勾选）
        combined_dfs = []
        per_question_sheets = []  # [(sheet_name, df), ...]
        for idx, res in enumerate(analysis_results, start=1):
            question = res["题目"]
            df_q = res["数据"]
            q_type = res["题型"]
            if df_q.empty:
                continue
            try:
                pivot_df = pivot_v13_style(
                    df_q, q_type, st.session_state.core_segment_col,
                    option_order=res.get("option_order"),
                    stats_res=res.get("stats"),  # H3
                    alpha=float(st.session_state.get("quant_sig_alpha", 0.05)),
                )
            except Exception as e:
                pivot_df = df_q.copy()
            if pivot_df.empty:
                continue
            col0 = pivot_df.columns[0]
            title_df = pd.DataFrame({col0: [f"{question} ({q_type})"]}).reindex(columns=pivot_df.columns)
            empty_df = pd.DataFrame({col0: [""]}).reindex(columns=pivot_df.columns)
            combined_dfs.append(title_df)
            combined_dfs.append(pivot_df)
            combined_dfs.append(empty_df)
            safe_name = make_safe_sheet_name(question, fallback_prefix="Q", index=idx)
            per_question_sheets.append((safe_name, pd.concat([title_df, pivot_df, empty_df], ignore_index=True)))
        summary_df = pd.concat(combined_dfs, ignore_index=True) if combined_dfs else pd.DataFrame({"提示": ["无数据"]})
        exportable = [("交叉分析结果（汇总）", summary_df)] + per_question_sheets
        export_options = [name for name, _ in exportable]
        default_sel = list(export_options)
        selected = st.multiselect(
            "勾选要导出的 sheet（可多选）",
            options=export_options,
            default=default_sel,
            key="quant_export_sheets",
        )
        if st.button("导出所选为 Excel"):
            if not selected:
                st.warning("请至少勾选一个 sheet 再导出。")
            else:
                try:
                    sheets_to_write = [(name, df) for name, df in exportable if name in selected]
                    debug_log(
                        f"导出 Excel | selected={len(selected)} sheets_to_write={len(sheets_to_write)} "
                        f"names={selected[:30]}"
                    )
                    bundle = ExportBundle(workbook_name="问卷定量交叉分析结果", sheets=sheets_to_write)
                    buffer = io.BytesIO()
                    export_xlsx(bundle, buffer)
                    st.session_state.export_cross_buffer = buffer.getvalue()
                    st.session_state.export_cross_name = "问卷定量交叉分析结果.xlsx"
                    st.rerun()
                except Exception as e:
                    debug_log(f"导出 Excel 失败 | error={repr(e)}")
                    st.error(f"导出 Excel 失败: {e}")
        if st.session_state.get("export_cross_buffer") is not None:
            st.download_button(
                label="下载交叉统计结果 Excel",
                data=st.session_state["export_cross_buffer"],
                file_name=st.session_state.get("export_cross_name", "问卷定量交叉分析结果.xlsx"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="quant_export_download",
            )

        format_choice = st.radio(
            "选择量化统计摘要格式",
            options=["Markdown", "JSON"],
            horizontal=True,
        )
        if st.button("生成量化统计摘要"):
            core_segment_col = st.session_state.core_segment_col
            if core_segment_col is None:
                st.warning("请先选择核心分组列并完成一次交叉分析。")
            else:
                if format_choice == "Markdown":
                    summary_text = build_markdown_summary(analysis_results, core_segment_col)
                else:
                    summary_text = build_json_summary(analysis_results, core_segment_col)
                st.session_state.quant_summary = summary_text
        summary_text = st.session_state.quant_summary
        st.text_area(
            "量化统计摘要结果，可复制后用于后续 LLM 定性比对",
            value=summary_text,
            height=300,
        )
        st.divider()
        tab_single, tab_rating, tab_within, tab_ranking = st.tabs(
            ["单选题组间差异检验", "高级统计分析（评分题）", "组内差异分析", "🏆 排序题深度洞察"]
        )
        with tab_single:
            if core_segment_col is None:
                st.info("请先在上方选择核心分组列，并完成一次基础交叉分析。")
            else:
                type_df = st.session_state.column_type_df
                single_cols = (
                    type_df[type_df["题型"] == "单选"]["列名"].tolist()
                    if type_df is not None
                    else []
                )
                if not single_cols:
                    st.info("当前题型标记中尚未设置任何单选题列。请在“题型微调”中将相应列标记为“单选”。")
                else:
                    single_col = st.selectbox(
                        "选择需要进行组间差异检验的单选题列",
                        options=single_cols,
                    )
                    if st.button("运行单选题组间差异检验", key="run_single_choice_test"):
                        test_res = run_group_difference_test(
                            df, core_segment_col, single_col, "单选", alpha=float(sig_alpha)
                        )
                        overall = test_res.get("overall") or {}
                        p_val = overall.get("p_value")
                        effect = overall.get("effect_size")
                        effect_comment = interpret_effect_size("Cramer's V", effect)
                        st.subheader("单选题组间差异总体检验结果")
                        st.write(
                            {
                                "检验类型": overall.get("test"),
                                "统计量": overall.get("stat"),
                                "p值": p_val,
                                "效应量(Cramer's V)": effect,
                                "效应量解释": effect_comment,
                            }
                        )
                        if p_val is not None and pd.notna(p_val) and p_val < sig_alpha:
                            st.error(f"该单选题在不同分组之间存在显著差异（p < {sig_alpha:.3f}）。")
                        else:
                            st.info(f"未检测到该单选题在不同分组之间的显著差异（p ≥ {sig_alpha:.3f}）。")
        with tab_rating:
            if core_segment_col is None:
                st.info("请先在上方选择核心分组列，并完成一次基础交叉分析。")
            else:
                type_df = st.session_state.column_type_df
                rating_cols = (
                    type_df[type_df["题型"].isin(["评分", "NPS"])]["列名"].tolist()
                    if type_df is not None
                    else []
                )
                if not rating_cols:
                    st.info(
                        "当前题型标记中尚未设置任何评分题或 NPS 题。请在「题型微调」中将相应列标记为「评分」或「NPS」。"
                    )
                else:
                    rating_col = st.selectbox(
                        "选择需要进行组间差异检验的评分题列",
                        options=rating_cols,
                    )
                    if st.button("运行评分题组间差异检验", key="run_rating_test"):
                        metrics_df = calculate_rating_metrics(
                            df, rating_col, core_segment_col
                        )
                        st.subheader("评分题基础统计指标")
                        st.dataframe(metrics_df, use_container_width=True)
                        test_res = run_group_difference_test(
                            df, core_segment_col, rating_col, "评分", alpha=float(sig_alpha)
                        )
                        overall = test_res.get("overall") or {}
                        pairwise = test_res.get("pairwise")
                        p_val = overall.get("p_value")
                        st.subheader("组间差异总体检验结果")
                        st.write(
                            {
                                "检验类型": overall.get("test"),
                                "统计量": overall.get("stat"),
                                "p值": p_val,
                                "效应量(η²)": overall.get("effect_size"),
                            }
                        )
                        if p_val is not None and pd.notna(p_val) and p_val < sig_alpha:
                            st.error(f"该评分题在不同分组之间存在显著差异（p < {sig_alpha:.3f}）。")
                        else:
                            st.info(f"未检测到显著的组间差异（p ≥ {sig_alpha:.3f}）。")
                        if isinstance(pairwise, pd.DataFrame) and not pairwise.empty:
                            st.subheader("两两组间差异结果")
                            st.dataframe(pairwise, use_container_width=True)
                            means = (
                                pd.to_numeric(df[rating_col], errors="coerce")
                                .groupby(df[core_segment_col])
                                .mean()
                            )
                            conclusions = []
                            seen_pairs = set()
                            for _, row in pairwise.iterrows():
                                g1 = row.get("group1")
                                g2 = row.get("group2")
                                pv = row.get("p_value")
                                if g1 not in means or g2 not in means:
                                    continue
                                if pv is None or pd.isna(pv) or pv >= sig_alpha:
                                    continue
                                key_pair = tuple(sorted([str(g1), str(g2)]))
                                if key_pair in seen_pairs:
                                    continue
                                seen_pairs.add(key_pair)
                                m1 = means[g1]
                                m2 = means[g2]
                                if pd.isna(m1) or pd.isna(m2):
                                    continue
                                if m1 > m2:
                                    conclusions.append(
                                        f"[{g1}] 在「{rating_col}」上的得分显著高于 [{g2}]"
                                    )
                                elif m2 > m1:
                                    conclusions.append(
                                        f"[{g2}] 在「{rating_col}」上的得分显著高于 [{g1}]"
                                    )
                            if conclusions:
                                st.subheader("一句话结论")
                                st.write("；".join(conclusions[:5]))
                            else:
                                if p_val is not None and pd.notna(p_val) and p_val < sig_alpha:
                                    st.subheader("一句话结论")
                                    st.write(
                                        f"在评分题「{rating_col}」上，不同分组之间整体存在显著差异，但未提取出稳定的两两差异结论。"
                                    )
        with tab_within:
            type_df = st.session_state.column_type_df
            if type_df is None:
                st.info("请先在“题型微调”中完成题型标记，然后再使用组内差异分析。")
            else:
                st.subheader("多选 / 矩阵单选题：组内显著性差异（McNemar）")
                if type_df is not None:
                    multi_like = type_df[
                        type_df["题型"].isin(["多选", "矩阵"])
                    ]["列名"].tolist()
                    prefix_map_multi = {}
                    for c in multi_like:
                        p = get_prefix(c)
                        prefix_map_multi.setdefault(p, []).append(c)
                    multi_prefix_options = [
                        p for p, cols in prefix_map_multi.items() if len(cols) >= 2
                    ]
                else:
                    multi_prefix_options = []
                    prefix_map_multi = {}
                if not multi_prefix_options:
                    st.info(
                        "当前没有检测到可用于组内差异分析的多选/矩阵单选题。请在“题型微调”中将相关列标记为“多选”或“矩阵”。"
                    )
                else:
                    chosen_prefix = st.selectbox(
                        "选择需要进行组内显著性分析的多选/矩阵单选题（按前缀识别）",
                        options=multi_prefix_options,
                    )
                    option_cols = prefix_map_multi.get(chosen_prefix, [])
                    st.write(f"当前题目包含的选项列：{option_cols}")
                    if st.button(
                        "运行多选/矩阵单选题组内显著性分析", key="run_within_multi_choice"
                    ):
                        test_df = run_within_group_multi_choice(df, option_cols)
                        if test_df is None or test_df.empty:
                            st.warning("样本量不足或数据不完整，未能计算组内显著性差异。")
                        else:
                            st.dataframe(test_df, use_container_width=True)
                            sig_pairs = test_df[
                                (test_df["p_value"].notna())
                                & (test_df["p_value"] < sig_alpha)
                            ]
                            if not sig_pairs.empty:
                                st.subheader(f"显著差异选项对（p < {sig_alpha:.3f}）")
                                lines = []
                                for _, row in sig_pairs.iterrows():
                                    lines.append(
                                        f"选项「{row['option1']}」与「{row['option2']}」在被选择的概率上存在显著差异（p={row['p_value']:.3f}，g={row['effect_size_g']:.2f}）。"
                                    )
                                st.write("；".join(lines))
                            else:
                                st.info(f"在该题内部，各选项之间未检测到显著差异（p ≥ {sig_alpha:.3f}）。")

                st.subheader("多选 / 矩阵单选题：组间差异概览（卡方 / Fisher）")
                if type_df is not None:
                    multi_like_between = type_df[
                        type_df["题型"].isin(["多选", "矩阵"])
                    ]["列名"].tolist()
                    prefix_map_multi_between = {}
                    for c in multi_like_between:
                        p = get_prefix(c)
                        prefix_map_multi_between.setdefault(p, []).append(c)
                    multi_prefix_options_between = [
                        p for p, cols in prefix_map_multi_between.items() if len(cols) >= 1
                    ]
                else:
                    multi_prefix_options_between = []
                    prefix_map_multi_between = {}
                if not multi_prefix_options_between:
                    st.info(
                        "当前没有检测到可用于组间差异分析的多选/矩阵单选题。请在“题型微调”中将相关列标记为“多选”或“矩阵”。"
                    )
                else:
                    chosen_prefix_between = st.selectbox(
                        "选择需要进行组间差异分析的多选/矩阵单选题（按前缀识别）",
                        options=multi_prefix_options_between,
                        key="between_multi_prefix",
                    )
                    option_cols_between = prefix_map_multi_between.get(
                        chosen_prefix_between, []
                    )
                    st.write(f"当前题目包含的选项列：{option_cols_between}")

                    if st.button(
                        "运行多选/矩阵单选题组间差异分析", key="run_between_multi_choice"
                    ):
                        if core_segment_col is None:
                            st.warning("请先在上方选择核心分组列。")
                        else:
                            rows = []
                            for col in option_cols_between:
                                tmp = df[[core_segment_col, col]].copy()
                                tmp[col] = tmp[col].apply(
                                    lambda v: "提及"
                                    if (
                                        not pd.isna(v)
                                        and str(v).strip().lower()
                                        not in ("", "0", "0.0", "nan", "none", "na", "n/a", "未选", "否")
                                    )
                                    else "未提及"
                                )
                                # H1: 多选类型需传列表；列已预处理为"提及"/"未提及"，用单选检验更准确
                                res = run_group_difference_test(
                                    tmp, core_segment_col, col, "单选", alpha=float(sig_alpha)
                                )
                                overall = res.get("overall") or {}
                                p_val = overall.get("p_value")
                                eff = overall.get("effect_size")
                                eff_comment = interpret_effect_size("Cramer's V", eff)
                                rows.append(
                                    {
                                        "前缀": chosen_prefix_between,
                                        "选项列": col,
                                        "检验类型": overall.get("test"),
                                        "p值": p_val,
                                        "效应量(Cramer's V)": eff,
                                        "效应量解释": eff_comment,
                                    }
                                )
                            if rows:
                                res_df = pd.DataFrame(rows)
                                st.subheader("多选 / 矩阵单选题：各选项组间差异结果")
                                st.dataframe(res_df, use_container_width=True)
                            else:
                                st.info("未生成任何组间差异结果，请检查数据是否有效。")

                st.subheader("矩阵评分题：组内显著性差异（Friedman + Wilcoxon）")
                matrix_like = (
                    type_df[type_df["题型"] == "矩阵"]["列名"].tolist()
                    if type_df is not None
                    else []
                )
                prefix_map_matrix = {}
                for c in matrix_like:
                    p = get_prefix(c)
                    prefix_map_matrix.setdefault(p, []).append(c)
                matrix_prefix_options = [
                    p for p, cols in prefix_map_matrix.items() if len(cols) >= 2
                ]
                if not matrix_prefix_options:
                    st.info(
                        "当前没有检测到可用于组内差异分析的矩阵评分题。请在“题型微调”中将相关列标记为“矩阵”。"
                    )
                else:
                    chosen_matrix_prefix = st.selectbox(
                        "选择需要进行组内显著性分析的矩阵评分题（按前缀识别）",
                        options=matrix_prefix_options,
                    )
                    value_cols = prefix_map_matrix.get(chosen_matrix_prefix, [])
                    st.write(f"当前矩阵评分题包含的子项列：{value_cols}")
                    if st.button(
                        "运行矩阵评分题组内显著性分析", key="run_within_matrix_rating"
                    ):
                        res = run_within_group_matrix_rating(df, value_cols)
                        overall = res.get("overall") or {}
                        pairwise = res.get("pairwise")
                        st.subheader("总体组内差异检验（Friedman）")
                        st.write(
                            {
                                "检验类型": overall.get("test"),
                                "统计量": overall.get("stat"),
                                "p值": overall.get("p_value"),
                            }
                        )
                        if (
                            overall.get("p_value") is not None
                            and pd.notna(overall.get("p_value"))
                            and overall.get("p_value") < sig_alpha
                        ):
                            st.error(f"该矩阵评分题的各子项之间整体存在显著差异（p < {sig_alpha:.3f}）。")
                        else:
                            st.info(f"未检测到矩阵子项之间显著的总体差异（p ≥ {sig_alpha:.3f}）。")
                        if isinstance(pairwise, pd.DataFrame) and not pairwise.empty:
                            st.subheader("两两子项对比结果（Wilcoxon）")
                            st.dataframe(pairwise, use_container_width=True)
                            sig_pairs = pairwise[
                                (pairwise["p_value"].notna())
                                & (pairwise["p_value"] < sig_alpha)
                            ]
                            if not sig_pairs.empty:
                                st.subheader("一句话结论示例")
                                lines = []
                                for _, row in sig_pairs.iterrows():
                                    lines.append(
                                        f"子项「{row['item1']}」与「{row['item2']}」的评分分布存在显著差异（p={row['p_value']:.3f}，d={row['effect_size_d']:.2f}）。"
                                    )
                                st.write("；".join(lines[:5]))
                            else:
                                if (
                                    overall.get("p_value") is not None
                                    and pd.notna(overall.get("p_value"))
                                    and overall.get("p_value") < sig_alpha
                                ):
                                    st.subheader("一句话结论示例")
                                    st.write(
                                        f"在矩阵评分题「{chosen_matrix_prefix}」中，各子项评分分布整体存在显著差异，但未提取出稳定的两两差异结论。"
                                    )
        with tab_ranking:
            type_df = st.session_state.column_type_df
            ranking_cols = (
                type_df[type_df["题型"] == "排序"]["列名"].tolist()
                if type_df is not None
                else []
            )
            
            # 自动聚合排序题前缀
            prefix_map_ranking = {}
            for c in ranking_cols:
                p = get_prefix(c)
                prefix_map_ranking.setdefault(p, []).append(c)
            
            ranking_prefix_options = [
                p for p, cols in prefix_map_ranking.items() if len(cols) >= 1
            ]
            
            if not ranking_prefix_options:
                st.info("当前题型标记中尚未设置任何排序题列。请在“题型微调”中将相应列标记为“排序”。")
            else:
                st.markdown("### 🏆 排序题深度洞察")
                
                # 1. 选择标签列（用户分组）
                label_default = (
                    core_segment_col if core_segment_col in columns else columns[0]
                )
                label_col = st.selectbox(
                    "1. 选择分析维度（用户标签/分组）",
                    options=columns,
                    index=columns.index(label_default),
                    key="ranking_label_col"
                )
                
                # 2. 选择排序题组（自动聚合）
                chosen_ranking_prefix = st.selectbox(
                    "2. 选择排序题（按前缀聚合）",
                    options=ranking_prefix_options,
                    key="ranking_prefix_select"
                )
                
                rank_cols = prefix_map_ranking.get(chosen_ranking_prefix, [])
                st.info(f"已自动识别该排序题包含 {len(rank_cols)} 个位置列：{', '.join(rank_cols)}")
                
                if st.button("生成深度洞察报告", key="run_ranking_analysis"):
                    rank_result = process_ranking_data(
                        df, label_col, rank_cols
                    )
                    # H4: 将结果存入 session_state，使导出/下载按钮可在下一轮 rerun 中独立渲染
                    st.session_state["ranking_result_cache"] = rank_result
                    st.session_state.pop("export_ranking_buffer", None)

                if st.session_state.get("ranking_result_cache"):
                    rank_result = st.session_state["ranking_result_cache"]
                    long_df = rank_result["long_df"]
                    avg_score = rank_result["avg_score"]
                    top1_rate = rank_result["top1_rate"]
                    top2_rate = rank_result["top2_rate"]
                    summary_df = rank_result.get("summary")
                    
                    # 结果展示
                    if isinstance(summary_df, pd.DataFrame) and not summary_df.empty:
                        st.subheader("1. 综合诊断结论表")
                        
                        def _color_rows(row):
                            label = row.get("需求分类结论", "")
                            if label == "众望所归型":
                                return ["background-color: #e4f7e4; color: black"] * len(row)
                            if label == "小众狂热型":
                                return ["background-color: #ffe9d6; color: black"] * len(row)
                            if label == "安全备胎型":
                                return ["background-color: #e6f3ff; color: black"] * len(row)
                            return ["" for _ in row]
                            
                        styled = summary_df.style.apply(_color_rows, axis=1).format({
                            "加权得分": "{:.2f}",
                            "Top1率": "{:.1f}%",
                            "Top2率": "{:.1f}%"
                        })
                        st.dataframe(styled, use_container_width=True)
                        
                    st.subheader("2. 交互式热力图洞察")
                    
                    if not avg_score.empty:
                        st.markdown("**A. 平均加权得分** (反映整体偏好强度)")
                        mat = avg_score.copy()
                        mat.index = mat.index.astype(str)
                        mat.columns = mat.columns.astype(str)
                        fig_avg = px.imshow(
                            mat,
                            text_auto=".2f",
                            aspect="auto",
                            color_continuous_scale="YlGnBu",
                            labels={"x": "选项", "y": label_col, "color": "得分"},
                        )
                        st.plotly_chart(fig_avg, use_container_width=True)

                    if top1_rate is not None and not top1_rate.empty:
                        st.markdown("**B. Top1 第一提及率** (反映核心死忠粉占比)")
                        mat1 = top1_rate.copy()
                        mat1.index = mat1.index.astype(str)
                        mat1.columns = mat1.columns.astype(str)
                        fig_top1 = px.imshow(
                            mat1,
                            text_auto=".1f",
                            aspect="auto",
                            color_continuous_scale="OrRd",
                            labels={"x": "选项", "y": label_col, "color": "Top1率(%)"},
                        )
                        st.plotly_chart(fig_top1, use_container_width=True)

                    if top2_rate is not None and not top2_rate.empty:
                        st.markdown("**C. Top2 前两名胜出率** (反映更广泛的接受度)")
                        mat2 = top2_rate.copy()
                        mat2.index = mat2.index.astype(str)
                        mat2.columns = mat2.columns.astype(str)
                        fig_top2 = px.imshow(
                            mat2,
                            text_auto=".1f",
                            aspect="auto",
                            color_continuous_scale="Purples",
                            labels={"x": "选项", "y": label_col, "color": "Top2率(%)"},
                        )
                        st.plotly_chart(fig_top2, use_container_width=True)

                    # 导出：将 buffer 存入 session_state，以便下一轮仍能渲染下载按钮
                    if st.button("导出结论表", key="export_ranking_summary_new"):
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                            if not summary_df.empty:
                                summary_df.to_excel(writer, sheet_name="排序题结论", index=False)
                        buffer.seek(0)
                        st.session_state["export_ranking_buffer"] = buffer.getvalue()
                        st.session_state["export_ranking_name"] = "排序题深度洞察报告.xlsx"
                        st.success("已准备导出，请点击下方「下载 Excel」。")
                    if st.session_state.get("export_ranking_buffer") is not None:
                        st.download_button(
                            label="📥 下载 Excel",
                            data=st.session_state["export_ranking_buffer"],
                            file_name=st.session_state.get("export_ranking_name", "排序题深度洞察报告.xlsx"),
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_ranking_export",
                        )

if __name__ == "__main__":
    main()
