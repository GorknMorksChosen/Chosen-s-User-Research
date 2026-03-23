from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from scripts.run_playtest_pipeline import run_pipeline
from survey_tools.utils.io import load_survey_data


def _load_uploaded_df(uploaded_file) -> pd.DataFrame:
    df = load_survey_data(uploaded_file)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def main() -> None:
    st.set_page_config(page_title="一键 Playtest 流水线", layout="wide")
    st.title("一键 Playtest 流水线")
    st.caption("上传问卷文件，一键完成题型识别、交叉分析与满意度建模。")

    uploaded_file = st.file_uploader(
        "上传问卷文件（.sav / .csv / .xlsx）",
        type=["sav", "csv", "xlsx"],
    )

    df: Optional[pd.DataFrame] = None
    load_error: Optional[Exception] = None
    if uploaded_file is not None:
        try:
            df = _load_uploaded_df(uploaded_file)
            st.info(f"已加载数据：样本量 {len(df)}，列数 {len(df.columns)}")
        except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as exc:
            load_error = exc
            st.error(f"文件格式或编码解析失败：{exc}")
            st.info("请确认上传的是有效的 .sav/.csv/.xlsx 文件，且编码/内容未损坏。")
        except Exception as exc:  # pragma: no cover
            load_error = exc
            st.error("读取文件时发生系统异常，请稍后重试或联系维护同事。")
            st.exception(exc)

    with st.expander("高级配置", expanded=True):
        segment_options = ["自动推断"]
        if df is not None:
            segment_options += [str(c) for c in df.columns]
        segment_choice = st.selectbox("交叉分组列", options=segment_options, index=0)
        per_question_sheets = st.toggle("每题独立生成 Sheet", value=False)
        sig_test = st.toggle("启用显著性检验", value=True)
        sig_alpha = st.number_input(
            "显著性阈值 alpha",
            min_value=0.001,
            max_value=0.2,
            value=0.05,
            step=0.001,
            format="%.3f",
            disabled=not sig_test,
        )
        st.caption("提示：关闭显著性检验后，仅输出描述统计结果，不执行显著性打标与差异标记。")

    run_clicked = st.button(
        "▶️ 开始一键分析",
        type="primary",
        use_container_width=True,
        disabled=(uploaded_file is None or load_error is not None),
    )

    if not run_clicked:
        return

    if df is None:
        st.warning("请先上传有效数据文件。")
        return

    output_dir = str(Path("data") / "processed")
    segment_col = None if segment_choice == "自动推断" else segment_choice

    try:
        with st.status("正在执行 Playtest 流水线...", expanded=True) as status:
            st.write("题型识别中...")
            run_res = run_pipeline(
                df=df,
                output_dir=output_dir,
                segment_col=segment_col,
                per_question_sheets=per_question_sheets,
                sig_test=sig_test,
                sig_alpha=float(sig_alpha),
            )
            st.write("题型识别完毕")
            st.write("交叉分析完毕")
            st.write("回归建模完成")
            st.write("报告导出完成")
            status.update(label="流水线执行完成", state="complete", expanded=False)

        output_file = Path(run_res["output_file"])
        st.success("分析完成，报告已生成。")
        with output_file.open("rb") as f:
            st.download_button(
                "下载 Excel 报告",
                data=f,
                file_name=output_file.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    except Exception as exc:
        st.error(f"流水线执行失败：{exc}")


if __name__ == "__main__":
    main()
