# 问卷数表工具集 · 代码审阅与潜在问题报告

> 审阅范围：README 中提及的五大核心工具及其依赖的 core/web 模块，逐行审阅后的 debug 与代码质量问题汇总。  
> 审阅日期：2026-03-17

---

## 一、运行 Bug（可能导致崩溃或错误结果）

### 1. 排序题「导出结论表」下载按钮无法生效（Quant / quant_app.py）

**位置**：`survey_tools/web/quant_app.py` 约 892–903 行  

**问题**：在 `if st.button("导出结论表", key="export_ranking_summary_new"):` 内部创建 buffer 并渲染 `st.download_button`。用户点击「导出结论表」后，下一轮运行中该 button 为 False，下载按钮不再渲染，且 buffer 未持久化，导致用户无法在下一轮点击「下载 Excel」。  

**建议**：将导出 buffer 存入 `st.session_state`（如 `export_ranking_buffer` / `export_ranking_name`），在「导出结论表」时写入 session_state；下载按钮在「有 session_state 中的 buffer 时」始终渲染，这样在用户点击下载的下一轮仍能拿到数据。

---

### 2. 游研专家上传新文件后仍使用旧数据（game_analyst.py）

**位置**：`game_analyst.py` 约 411–416 行  

**问题**：仅当 `'df_cleaned' not in st.session_state` 时才会用当前 `uploaded_file` 读入并写入 `st.session_state.df_cleaned`。用户更换文件后，`uploaded_file` 变化，但 `df_cleaned` 已存在，不会更新，后续所有分析仍基于旧文件。  

**建议**：用「文件标识」（如 `(uploaded_file.name, uploaded_file.size)` 或 `uploaded_file.file_id`）做版本判断；当检测到与 session 中保存的标识不一致时，清除 `df_cleaned` 并重新读入，或直接在本轮用当前 `uploaded_file` 覆盖 `df_cleaned`。

---

### 3. IPA 结果全被 dropna 后空 DataFrame 导致异常（satisfaction_app.py）

**位置**：`survey_tools/web/satisfaction_app.py` 约 65–74 行  

**问题**：`res_df = pd.DataFrame(results).dropna(subset=["满意度评分", "对整体的影响力"])` 可能得到空 DataFrame（例如所有细项或目标列为常数、相关性为 NaN）。后续 `res_df["满意度评分"].mean()`、`res_df["对整体的影响力"].mean()` 以及 `px.scatter(res_df, ...)` 在空表上可能产生 NaN 或报错。  

**建议**：在绘图与计算均值前增加 `if res_df.empty:` 分支，展示「无有效数据」提示并提前 return，避免后续使用空 DataFrame。

---

### 4. 满意度回归缺失策略回退后未清空分组列（satisfaction_app.py）

**位置**：`survey_tools/web/satisfaction_app.py` 约 339–352 行  

**问题**：当选择「按分组均值/中位数填补」但未找到可用分组列时，代码将 `missing_strategy = "mean"`，但未显式设置 `missing_group_col = None`。若之前选过分组列，`missing_group_col` 仍可能保留，传入 `regression_analysis(..., missing_group_col=...)` 时，core 可能仍按分组逻辑处理。  

**建议**：在 `st.warning("未找到可用分组列...")` 且 `missing_strategy = "mean"` 的分支中显式设置 `missing_group_col = None`。

---

## 二、逻辑断层 / 功能缺失

### 5. 多选透视表「总计」列在多选分支中可能用错分母（quant_app.py）

**位置**：`survey_tools/web/quant_app.py` 约 196–206 行（多选分支）  

**说明**：多选下 `total_sample_size = group_sizes.sum()` 为各分组「组样本数」之和；`total_ratio = total_mentions / total_sample_size` 按「总提及人次/总人数」算整体提及率。若业务上多选「总计」需与单选一致（即「总人数」为所有分组人数之和），当前逻辑一致；若存在「按题有效人数」等不同口径，需在文档或注释中明确，避免与报表其他部分口径不一致。

---

### 6. 聚类联合推荐 recommended_k 类型（cluster_app.py）

**位置**：`survey_tools/web/cluster_app.py` 约 359 行  

**问题**：`rec_k = int(global_rec.get("recommended_k", k_final))` 若 `recommended_k` 为浮点或来自 JSON 的字符串，在部分环境下 `int()` 可能抛错。  

**建议**：使用安全转换，例如 `int(float(global_rec.get("recommended_k", k_final)))` 或 try/except 兜底为 `k_final`。

---

### 7. 文本分析工具 CSV 编码（问卷文本分析工具 v1.py）

**位置**：`问卷文本分析工具 v1.py` 约 458 行  

**问题**：`df = pd.read_csv(uploaded_file)` 未指定 encoding，中文等非 UTF-8 的 CSV 易报错。Quant 入口已使用 `encoding="gbk"` 回退。  

**建议**：与 Quant 一致，先尝试默认编码，捕获 `UnicodeDecodeError` 后用 `encoding="gbk"` 重试。

---

### 8. 满意度超级应用 CSV 编码（satisfaction_app.py）

**位置**：`survey_tools/web/satisfaction_app.py` 约 357 行  

**问题**：`df = pd.read_csv(uploaded_file)` 同样未做编码回退。  

**建议**：与 Quant/文本工具统一，增加 gbk 回退逻辑。

---

## 三、兼容性 / 可维护性

### 9. Streamlit 已废弃 API（game_analyst.py / 问卷文本分析工具 v1.py）

**位置**：  
- `game_analyst.py`：`st.experimental_rerun()`（约 408、437、447 行等）  
- `问卷文本分析工具 v1.py`：`st.experimental_rerun()`（约 451 行）  

**问题**：`st.experimental_rerun()` 在新版 Streamlit 中已弃用。  

**建议**：改为 `st.rerun()`，并在兼容的 Streamlit 版本上测试。

---

### 10. 游研专家与 core 双份 GameExperienceAnalyzer（game_analyst.py vs advanced_modeling.py）

**位置**：  
- `game_analyst.py` 内完整定义了一版 `GameExperienceAnalyzer`  
- `survey_tools/core/advanced_modeling.py` 中为另一版  

**问题**：两处实现重复（数据体检、因子、聚类、回归、路径、Kano、SHAP 等），修复或增强时需改两处，易遗漏且易产生行为不一致。  

**建议**：游研专家入口统一改为从 `survey_tools.core.advanced_modeling` 导入 `GameExperienceAnalyzer`，删除 `game_analyst.py` 中的类定义，仅保留 UI 与调用逻辑。

---

### 11. 文本分析工具对 make_safe_sheet_name 的依赖（问卷文本分析工具 v1.py）

**位置**：`问卷文本分析工具 v1.py` 第 20 行 `from survey_core_quant import make_safe_sheet_name`  

**说明**：`survey_core_quant.py` 仅做 `from survey_tools.core.quant import *`，实际实现来自 `survey_tools.core.quant.make_safe_sheet_name`。功能无问题，但多一层根目录模块，不利于长期维护。  

**建议**：改为直接从 `survey_tools.core.quant` 导入 `make_safe_sheet_name`，可考虑逐步弱化或移除 `survey_core_quant` 的转发角色。

---

## 四、健壮性 / 边界情况

### 12. quant.py 中 run_question_analysis 的 mode="between" 多选入参（core/quant.py）【已完成】

**位置**：`survey_tools/core/quant.py` 约 805–812 行  

**说明**：`run_question_analysis(..., mode="between")` 在 `question_type == "多选"` 时仍要求 `value_col is not None`；而多选在调用处通常传入 `value_cols`（列表）。若上层误传 `value_col` 为单列或 None，可能直接落到 `return {"overall": None, "pairwise": None}`。当前 quant_app 多选走 `run_group_difference_test(df, core_segment_col, cols, "多选")`，未走 `run_question_analysis`，故暂无运行时问题，但 API 设计上「多选 + between」应对列表形式的 value_cols 做支持或明确文档说明，避免后续误用。  

**修复**：已在 `run_question_analysis` 的 `mode=="between"` 分支中增加对 `question_type=="多选"` 且 `value_cols` 非空的处理，将 `value_cols` 传入 `run_group_difference_test`；并保留单选/评分下对 `value_col` 的原有逻辑。

---

### 13. 路径分析 estimates 列名兼容（game_analyst.py）

**位置**：`game_analyst.py` 约 658–661、674–678 行  

**说明**：代码同时兼容 `Estimate`/`estimate`、`P-value`/`p-value`/`pval` 等列名，已做 try/except，逻辑合理。若 semopy 升级后列名再次变化，可考虑集中到工具函数中做列名归一化，便于维护。

---

### 14. 分群结果与原始 df 的索引对齐（satisfaction_app / game_analyst）

**说明**：satisfaction_app 与 game_analyst 中，将 `df_clustered['玩家分群']` 赋给 `analyzer.data['玩家分群']` 或 `df['玩家分群']` 时，依赖 pandas 的索引对齐。`df_clustered` 来自 `analysis_df.dropna()`，索引为 `df` 的子集，未出现在 `df_clustered` 中的行会得到 NaN。行为符合「仅对有效样本打标签」的预期，无需改逻辑；仅需在文档或注释中说明「未参与聚类的样本其玩家分群为空」，避免误读。

---

## 五、已修复项建议（可立即落地）

以下为建议优先修改的代码级修复（已在报告中给出位置与思路）：

1. **quant_app**：排序题导出 buffer 存 session_state，下载按钮根据 session_state 渲染。【已完成，见 2026-03-17 DEV_LOG】  
2. **game_analyst**：按文件标识更新 `df_cleaned`，避免换文件仍用旧数据。【已完成】  
3. **satisfaction_app**：IPA 空 `res_df` 时提前提示并 return；缺失策略回退为 mean 时显式 `missing_group_col = None`。【已完成】  
4. **cluster_app**：`rec_k` 用 `int(float(...))` 或 try/except 做安全转换。【已完成】  
5. **问卷文本分析工具 v1 / satisfaction_app**：CSV 读取增加 gbk 回退。【已完成】  
6. **game_analyst / 问卷文本分析工具 v1**：`st.experimental_rerun()` → `st.rerun()`。【已完成】  
7. **quant.py core**：`run_question_analysis` 多选 between 支持 `value_cols`（见问题 12）；评分分支返回 `assumption_checks`（正态/方差齐性→ANOVA/Kruskal 决策），对标 wjxspss。【已完成】

**P0 核对说明（2026-03-17）**：上述 1～7 项已逐项核对当前代码，均已落地（quant_app session_state 排序题导出、game_analyst 文件标识更新 df_cleaned、satisfaction_app 空 res_df 与 missing_group_col、cluster_app recommended_k 安全转换、CSV gbk 回退、st.rerun、quant core value_cols/assumption_checks）。一、二节中其余条目（如多选总计口径、路径分析列名兼容）为说明/文档类，非运行 Bug，无需改代码。

---

## 六、auto_verify_v1 扩展审阅（2026-03-17）

**审阅对象**：`UserResearch/auto_verify_v1.py` 扩展后版本（覆盖 quant core schema 与映射验收相关 core 层用例）。

**覆盖范围**：
- **评分 + 分组**：`overall`（test, stat, p_value, effect_size）、`assumption_checks`（decision, normality_ok, levene_p, reason）；effect_size 数值类型；test 为 ANOVA 或 Kruskal-Wallis。
- **单选 + 分组**：overall 含 test（chi-square/fisher_exact）、stat、p_value、effect_size。
- **多选 + 分组**：overall.test=multi-option，overall 含 p_value、effect_size；`details[].option/p_value/effect_size/test`。
- **run_question_analysis**：多选 between + value_cols 返回 multi-option overall；评分 describe 返回 `describe` DataFrame（列 group, mean, n）。
- **评分事后比较**：当 p_value < 0.05 且存在 pairwise 时，检查 pairwise 含 group1、group2、p_value。

**静态审阅与逻辑推演**：
- 数据源：`test_assets/mock_survey.csv` 或内存 mock，不依赖 input_example，符合约定。
- 各用例独立 try/except，单用例失败不阻断其余；失败列表统一在 main 中输出。
- 评分 pairwise 仅在「有显著且存在 pairwise」时断言列名，避免 mock 随机性导致误报。
- 未发现逻辑错误或遗漏的异常路径。

**建议**：失败报告若包含 `cols`/`type` 等键，可在 main 中一并打印，便于排查（当前已打印 `keys`）。

---

## 七、审阅范围清单

| 模块/入口 | 审阅状态 | 备注 |
|-----------|----------|------|
| 问卷定量分析工具 v1.py | 已审阅 | 入口仅调用 quant_app |
| survey_tools/web/quant_app.py | 已审阅 | 见问题 1、5 |
| survey_tools/core/quant.py | 已审阅 | 见问题 12 |
| survey_tools/core/question_type.py | 已审阅 | 未发现 bug |
| survey_tools/core/effect_size.py | 已审阅 | 未发现 bug |
| 超级应用_满意度与体验建模.py | 已审阅 | 入口仅调用 satisfaction_app |
| survey_tools/web/satisfaction_app.py | 已审阅 | 见问题 3、4、8 |
| survey_tools/core/advanced_modeling.py | 已审阅 | 与 game_analyst 重复实现见问题 10 |
| game_analyst.py | 已审阅 | 见问题 2、9、10、13 |
| 聚类.py | 已审阅 | 入口仅调用 cluster_app |
| survey_tools/web/cluster_app.py | 已审阅 | 见问题 6 |
| survey_tools/core/clustering.py | 已审阅 | 未发现 bug |
| 问卷文本分析工具 v1.py | 已审阅 | 见问题 7、9、11 |
| survey_tools/core/missing_strategy.py | 已审阅 | 未发现 bug |
| survey_tools/core/factor_compat.py | 已审阅 | 未发现 bug |
| web_tools_launcher.py | 已审阅 | 未发现 bug |
| UserResearch/auto_verify_v1.py | 已审阅 | 扩展后覆盖 quant core schema、映射验收相关 core 用例；见第六节 |

---

*本报告仅基于当前代码静态审阅与逻辑推演，实际运行与边界情况建议在本地/测试环境做一次完整回归验证。*
