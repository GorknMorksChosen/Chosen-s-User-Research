# 项目开发变更日志 (Development Log)

本文档用于记录项目的重要变更、修复和优化记录，以防止对话记录丢失导致的信息遗漏。

**阅读约定**：README 与 DEV_LOG 共同构成项目「前情提要、后续计划及完成情况」的入口；对话重开或新人接手时，通过 README + 本 DEV_LOG 即可理解项目全貌。重要 .md 文档在 README 中有说明与映射（见 README「文档与迭代可见性」小节）。

---

## 📅 2026-03-30（最新）

### Pipeline 与文本工具输入口径对齐（分组防误判 / 多选识别 / 题级选择）

**涉及文件**：
- `scripts/run_playtest_pipeline.py`
- `survey_tools/web/pipeline_app.py`
- `survey_tools/core/quant.py`
- `survey_tools/core/question_type.py`
- `问卷文本分析工具 v1.py`
- `README.md`
- `docs/PLAYTEST_PIPELINE.md`

**变更内容**：

- **Pipeline 分组防误判**：
  - `_resolve_segment_col` 自动识别分组列时，新增“跳过题目列（可提取题号）”规则，避免把问卷题目/选项列误识别为分组列。
  - `pipeline_app` 高级配置新增「总体（不分组）」选项；当用户手动选择题目列作为分组列时，运行前自动回退到总体并给出 warning。

- **问卷星多选题识别修复**：
  - `extract_qnum` 新增对 `N(子项)` / `N（子项）` 的题号识别，修复同题多选子列因题号未识别被拆成单选的问题（典型如 Q11/Q16/Q19/Q22/Q25/Q28/Q31）。
  - 新增 `_warn_mixed_types_within_question` 运行时一致性告警：同题出现多种题型时打印详细提示，重点标记“多选 + 单选”高风险组合。

- **多选导出文案修复**：
  - `get_option_label` 增强无冒号列名清洗：支持从 `?()/？（）` 末尾括号提取选项，并去除 `5.` / `5(` / `Q5.` 等题号前缀，修复导出中“5 (xxx)”前缀残留。

- **文本工具输入体验与其他工具对齐**：
  - 接入大纲上传与来源选择（问卷星/腾讯），加载数据后同步构建题型映射。
  - 新增「按题选择（同题多列自动归并）」：在文本工具中可按题而非按列选择输入，多选题子列自动归并为同一道题。
  - 选择器增加题型标签显示，支持“目标列仅显示开放文本题”筛选；背景列默认排除元数据，减少误选噪声。

**验证结果**：
- `python -m py_compile scripts/run_playtest_pipeline.py` -> 通过
- `python -m py_compile survey_tools/web/pipeline_app.py` -> 通过
- `python -m py_compile survey_tools/core/quant.py` -> 通过
- `python -m py_compile survey_tools/core/question_type.py` -> 通过
- `python -m py_compile "问卷文本分析工具 v1.py"` -> 通过
- 针对用户样本复核：Q11/Q16/Q19/Q22/Q25/Q28/Q31 已统一识别为多选，不再出现同题“多选+单选”混拆。

### 依赖安全热修复（Dependabot 高危告警）

**涉及文件**：
- `requirements.txt`
- `requirements.lock.txt`
- `tests/verify_dependency_matrix.py`
- `docs/DEPENDENCY_MATRIX.md`

**变更内容**：
- 升级 `langchain-core` 到已修复区间版本：
  - `requirements.txt`：`langchain-core>=1.2.22,<1.3`
  - `requirements.lock.txt`：`langchain-core==1.2.22`
- 同步更新依赖矩阵校验下限与文档，保证质量矩阵和文档口径一致。

**目标**：
- 消除 GitHub Dependabot 对 `langchain-core==1.2.17` 的高危告警（GHSA-qh6h-p6c9-ff54）。

---

## 📅 2026-03-27（最新）

### 全量 Workspace Review（代码+测试+文档对齐）与发布前同步

**涉及文件**：
- `survey_tools/core/pipeline_report_blocks.py`
- `survey_tools/core/survey_metadata_columns.py`
- `scripts/run_playtest_pipeline.py`
- `survey_tools/web/quant_app.py`
- `tests/test_quant_core_pytest.py`
- `README.md`
- `docs/PROJECT_PLAN_V2_20260323.md`
- `docs/DEV_LOG.md`

**本轮审阅范围**：
- 对本轮已修改/新增核心代码做逐文件审阅，重点覆盖：  
  - Quant 与 Pipeline 导出口径复用是否一致；  
  - 元数据列忽略规则是否已从“脚本内联”收敛为共享模块；  
  - NPS/T2B/均值与显著性导出逻辑是否存在明显回归风险；  
  - Web 端题型重建与 Pipeline 自动识别口径是否对齐。

**验证结果（可复现命令）**：
- `python -m pytest UserResearch/tests/test_quant_core_pytest.py -q` -> `6 passed`
- `python UserResearch/tests/run_quality_matrix.py` -> `10/10 通过`

**结论**：
- 本轮改动在当前测试矩阵下未发现阻断发布的问题；  
- Quant 与 Pipeline 在导出主链路上已完成“同版式复用”收敛；  
- 元数据列忽略规则已形成单一事实源（`survey_tools/core/survey_metadata_columns.py`），降低后续口径漂移风险。

**遗留风险（非阻断）**：
- 在 Windows PowerShell 环境下，质量矩阵中文日志仍可能出现编码显示异常（乱码），当前不影响脚本通过/失败判定，但会影响可读性；建议后续在测试入口统一控制台编码输出策略。

---

## 📅 2026-03-25（最新）

### Quant 导出对齐 Playtest：报告块抽离 + 同版式 Excel 下载

**涉及文件**：
- `survey_tools/core/pipeline_report_blocks.py`（新增：`extract_option_value`、`simple_pivot`、`build_question_block`，从 `run_playtest_pipeline` 抽出）
- `scripts/run_playtest_pipeline.py`（改为 import 上述函数；`_export_results` 支持 `excel_bytes_io` 内存写出、`summary_profile=quant` 样本概况文案；新增 `export_quant_cross_analysis_xlsx_bytes` 供 Web）
- `survey_tools/web/quant_app.py`（主按钮「导出 Playtest 同版式 Excel」；可选每题独立 Sheet；保留「简易透视」纯表导出）

**变更内容**：
- 非矩阵题导出块与 Pipeline 共用 `build_question_block`（含本题平均分、样本量行、T2B/NPS 等）。
- 矩阵题仍走原 `_export_results` 内 2D 表与条件格式（与 CLI 一致）。
- 定量工具样本概况 Sheet 含「分析方式：手动选择分析列（题型可微调）」等字段，与 Playtest 区分。
- 需从 `UserResearch/` 目录启动 streamlit，否则 `scripts.run_playtest_pipeline` 可能无法导入。

### Quant / Pipeline：元数据列自动识别为「忽略」（与 Pipeline 同规则）

**涉及文件**：
- `survey_tools/core/survey_metadata_columns.py`（新增：`METADATA_IGNORE_KEYWORDS`、`is_metadata_column`）
- `survey_tools/web/quant_app.py`（题型重建时列名命中元数据则 `final_type=忽略`，优先于题号推断与大纲覆盖；题型微调仍可改）
- `scripts/run_playtest_pipeline.py`（原 `_FORCE_IGNORE_KEYWORDS` 内联逻辑改为调用 `is_metadata_column`）
- `tests/test_quant_core_pytest.py`（`test_metadata_column_keywords_align_with_pipeline`）

**变更内容**：
- 序号、答卷时间、所用时间、IP、总分、答卷编号、逻辑/跳转等（子串匹配，列名归一化与 Pipeline 一致）在**定量工具自动识别**中默认为「忽略」，避免与 Playtest 行为不一致。
- **产品口径**：非强制锁定；用户可在「题型微调」中改回其他题型。

### Quant：问卷大纲与题型重建（手动覆盖 / 解析失败 / 题号对齐）

**涉及文件**：
- `survey_tools/web/quant_app.py`

**变更内容**：
- 大纲解析**成功**：强制重建题型表，并设置 `outline_skip_manual_merge`，本轮**不合并**旧 `column_type_df` 中的「题型」，避免手动微调挡住大纲；成功文案旁说明可在「题型微调」中再改。
- 大纲解析**失败**（`ValueError` / 其它异常）：清空 `outline_q_num_to_type`，并将 `column_type_df = None`，避免静默沿用「误以为仍带大纲」的旧表。
- 用户**移除大纲文件**：清空映射并 `column_type_df = None`，重建以去掉大纲覆盖（仍保留列变化时的常规手动合并逻辑）。
- 重建后若存在大纲映射：对比大纲题号与数据列 `extract_qnum` 题号，对「仅在大纲中 / 仅在数据中」的题号给出 `st.info` / `st.caption` 提示。
- 解析成功但 `outline_raw_to_quant_type_map` 为空时 `st.warning`，便于发现格式或平台选错。

### Quant：NPS 题型（自动识别 + 手动微调 + 引擎贯通）

**涉及文件**：
- `survey_tools/core/question_type.py`（题干启发式 `stem_text_suggests_nps`、`infer_type_from_columns` 返回 `NPS题`、`detect_column_type` 支持 `NPS`）
- `survey_tools/core/quant.py`（`QuestionSpec` / `build_question_specs` / `run_quant_cross_engine` 支持 `NPS`；统计检验仍走「评分」口径）
- `survey_tools/utils/outline_parser.py`（`outline_to_q_num_type`：大纲 NPS 题映射为 `NPS`）
- `survey_tools/web/quant_app.py`（题型微调选项含「NPS」；交叉与高级评分 Tab 含 NPS）
- `scripts/run_playtest_pipeline.py`（`column_type_map` 含 `NPS` 时与 Quant 一致参与交叉与回归特征）
- `tests/test_quant_core_pytest.py`（`NPS` 规格单测）

**变更内容**：
- 定量工具中与 Pipeline 对齐：题干含 NPS/推荐意愿等且数值为 0–10 量表时，自动识别为 **NPS**（非「评分」）；题型微调中可手动改为 **NPS**。
- 交叉引擎对 `NPS` 的检验方法与评分题相同（Welch / ANOVA / KW），导出与展示中的 **题型** 显示为 `NPS`。

### Playtest Pipeline：Web 大纲上传 + Excel Sheet 选择 + NPS 国际公式落地

**涉及文件**：
- `survey_tools/web/pipeline_app.py`
- `scripts/run_playtest_pipeline.py`
- `docs/PLAYTEST_PIPELINE.md`

**变更内容**：
- **Web 入口增强**：
  - 一键 Pipeline 页面新增「上传问卷大纲（.docx/.txt）」与「大纲来源（问卷星/腾讯）」；
  - 上传 `.xlsx/.xls` 时新增「Sheet 选择」下拉，读取指定 Sheet 进行分析；
  - 大纲解析成功后将结果传入 `run_pipeline(outline=...)`，解析失败自动回退到纯自动识别，不阻断流程。
- **CLI 参数增强**：
  - 新增 `--sheet-name`（支持索引或名称），用于 Excel 指定 Sheet 读取；
  - `--help` 与文档参数表同步更新。
- **NPS 统计口径升级（国际公式）**：
  - 对符合 NPS 条件的题目，按 **Promoter(9-10) / Passive(7-8) / Detractor(0-6)** 分档；
  - 输出 **`NPS = %Promoter - %Detractor`**；
  - NPS 题不再输出「本题平均分」，避免与 NPS 口径混淆；
  - 增强中文题干识别（如“推荐 + 意愿/可能/多大”）。

**验证结果**：
- `python scripts/run_playtest_pipeline.py --help` 通过，`--sheet-name` 已生效。
- 用户实测样例（Boss 跑测问卷）完成验证：  
  - 数据：`349836741_按分数_【代号SUN-0209跑测】boss战斗问卷_18_18.xlsx`  
  - 大纲：`【代号SUN-0209跑测】boss战斗问卷.docx`  
  - 产物：`20260324_Playtest自动化分析报告 (3).xlsx`  
  - 结论：第 3 题按 NPS 口径输出，不再显示平均分。

### Web：问卷大纲上传逻辑抽离（Quant / Pipeline 共用）

**涉及文件**：
- `survey_tools/web/outline_upload.py`（新增）
- `survey_tools/web/quant_app.py`
- `survey_tools/web/pipeline_app.py`

**变更内容**：
- 将「大纲说明文案、平台选项、UploadedFile 解析（`getvalue` + `seek`）」收敛到 `outline_upload`，避免 Quant 与 Playtest Pipeline 两套实现分叉；
- 明确产品口径：**仅**在需要题型/选项对齐的入口复用大纲能力，**不**向其他工具全站铺开。

**验证结果**：
- `python -c "from survey_tools.web.outline_upload import parse_uploaded_outline_file"` 导入通过。

---

## 📅 2026-03-23

### P0-A 首批落地 + 最小 pytest 门禁

**涉及文件**：
- `survey_tools/core/quant.py`
- `survey_tools/web/quant_app.py`
- `game_analyst.py`
- `tool_registry.py`
- `tests/test_quant_core_pytest.py`（新增）
- `README.md`

**变更内容**：
- **A1（矩阵评分路由）**：`run_quant_cross_engine` 中矩阵评分子项改为按“评分”检验，不再误走“单选”路径。
- **A2（小样本策略）**：评分题 `k>2` 分支中，小样本不再默认正态通过；`3<=n<8` 改用 Shapiro，`n<3` 按不满足正态处理，避免误入参数法。
- **A3（多选提及编码）**：统一 `_to_binary_mention` 规则，显式纳入 `0.0`，并采用“数值>0为提及、文本词表兜底”逻辑。
- **A4（alpha 三层统一）**：
  - Quant Web 增加显著性阈值输入（`quant_sig_alpha`）；
  - 统计调用、页面提示、导出 `P值` 星号统一使用同一 `alpha`。
- **B1 先行收口**：`game_analyst.py` UI 侧改为优先复用 `survey_tools.core.advanced_modeling.GameExperienceAnalyzer`（本地旧类改名为 `LegacyGameExperienceAnalyzer` 作为过渡）。
- **C1 对齐修复**：`tool_registry.py` 中不存在的 Quant CLI 入口改为 `None`；`game_analyst` 的 `core_fn` 指向 core 单一事实源。
- **D1 落地**：新增 `tests/test_quant_core_pytest.py`，覆盖单选/多选/评分小样本/矩阵评分路由 4 个关键分支。

**验证结果**：
- `python -m pytest UserResearch/tests/test_quant_core_pytest.py -q` -> `4 passed`
- `python UserResearch/tests/auto_verify_v1.py` -> 通过
- `python UserResearch/tests/verify_no_legacy_quant_engine_import.py` -> PASS

---

### 项目计划 V2 发布（可信度优先）

**涉及文件**：
- `docs/PROJECT_PLAN_V2_20260323.md`（新建）
- `README.md`（工程维护/审阅小节新增计划文档入口）

**变更内容**：
- 新增“项目计划 V2”文档，明确 4 周执行路线：  
  - W1：可信度止血（统计口径、架构边界、文档口径）  
  - W2：工程化收口（pytest、Pydantic 边界校验、依赖闭环、CI）  
  - W3：业务放大 I（历史基线库 + A/B 跨期对比）  
  - W4：业务放大 II（老板视角看板 + 一键 3 页汇报稿）
- 文档包含：按天甘特图、每阶段 DoD、风险预案（高/中/低）及复盘节奏。
- 该计划用于“阶段重排”（可信度优先），不替代既有 P0/P1/P2 历史记录。

---

### 项目计划 V2 更新（任务路线图版）+ 轻量治理口径

**涉及文件**：
- `docs/PROJECT_PLAN_V2_20260323.md`
- `README.md`

**变更内容**：
- 将 `PROJECT_PLAN_V2_20260323.md` 从“按周/按天甘特图”改为“任务路线图驱动”：
  - 以 P0/P1/P2 优先级任务清单为主视图；
  - 每个任务包明确目标、DoD、验收证据与风险预案；
  - 增加统一验收框架与任务状态模板，便于直接跟踪执行。
- README 同步更新计划文档描述，明确其为“任务路线图版”。
- 新增当前协作口径：采用“每周最小文档更新机制”作为默认治理方式：
  - 每周更新 `README.md`（能力口径/风险/下一步）；
  - 每周更新 `docs/DEV_LOG.md`（变更/验证/未完成）；
  - 治理原则：**没有验证结果，不标记完成**。

---

### 项目计划 V2 二次微调（补齐深水区风险）

**涉及文件**：
- `docs/PROJECT_PLAN_V2_20260323.md`
- `README.md`

**变更内容**：
- 根据复盘意见对计划做“非推翻式优化”，新增与重排以下关键项：
  - **P1-C 性能与内存治理（新增且必做）**：覆盖高风险内存路径排查、流式导出/下载改造、大样本性能基线；
  - **E1 边界化约束**：Pydantic 仅用于配置与输入边界，不做全盘重构；
  - **F0 前置任务（新增）**：先设计动态 Schema 演进模型，再建设历史基线库；
  - **G4（新增）**：文本分析接入 Pipeline，替换 placeholder，并要求失败可降级不阻断主流程。
- 执行约束增加：未完成 P1-C 前，不上线新增重型分析功能。

---

### 项目计划 V2 三次微调（工程化进阶版）

**涉及文件**：
- `docs/PROJECT_PLAN_V2_20260323.md`
- `README.md`

**变更内容**：
- 吸收进阶建议后，计划文档做以下增强：
  - 升级计划定位与路线图表述（Masterpiece 导向、现代工程化导向）；
  - `P1-B` 升级为“深度数据契约与强类型重构”（Pydantic V2 + typing + 静态检查收敛）；
  - 新增 `P1-D`“混沌测试与故事化 Mock 引擎”任务包（含十万级压测与脏数据注入要求）；
  - `P2-A` 增加游戏上下文元数据要求（版本号、测试节点、核心改动说明）；
  - `五、执行机制` 重写为 Craftsmanship 导向（提交自检与阶段复盘标准）。
- README 对计划摘要同步为进阶版任务项，确保入口口径一致。

---

## 📅 2026-03-20（最新）

### Playtest：显著性检验统一收口 quant + Excel 视觉增强

**涉及文件**：
- `survey_tools/core/quant.py`（评分题 `k=2` 强制 Welch t；`k>2` ANOVA/KW；单/多选卡方；新增 `pipeline_summary` 标准输出）
- `scripts/run_playtest_pipeline.py`（删除脚本内 `_compute_significance_map`；直接消费 `stats.pipeline_summary`；显著格用 `number_format` 显示 `*` 且保持数值类型；高低方向浅绿/浅红；矩阵评分均值区 `ColorScaleRule` 红黄绿热力图；底部图例说明）
- `docs/PLAYTEST_PIPELINE.md`（显著性说明更新为 quant 统一引擎口径）

---

### Playtest：满意度回归样本分档与导出免责

**涉及文件**：
- `scripts/run_playtest_pipeline.py`（`_MIN_N_REGRESSION_SKIP=15` / `_MIN_N_REGRESSION_FULL=50`；`n<15` 不跑回归；`15<=n<50` 返回 `is_low_sample_warning=True` + `low_sample_n`；`_export_results` 对「满意度回归结果」Sheet：`is_low_sample_warning` 时 A1 合并免责红字、表区浅灰底）
- `docs/PLAYTEST_PIPELINE.md`（满意度分档与导出说明）

---

### Playtest Pipeline 官方文档与维护约定

**涉及文件**：
- `docs/PLAYTEST_PIPELINE.md`（新建：CLI 参数表、显著性检验说明、**维护约定**：更新 Pipeline/CLI 时须同步本文档 + `scripts/run_playtest_pipeline.py` 模块 docstring + 可选本 DEV_LOG 留痕）
- `scripts/run_playtest_pipeline.py`（模块 docstring 与上述文档对齐）
- `README.md`（索引指向 `PLAYTEST_PIPELINE.md`）

**约定**：后续任何对 Playtest 流水线入口、参数或对外统计口径的改动，均按 `PLAYTEST_PIPELINE.md` 首节「文档定位与维护约定」执行。

---

### 问卷大纲解析抽离 + Quant Web「大纲来源」下拉

**涉及文件**：
- `survey_tools/utils/outline_parser.py`（新建 / 持续演进）
- `scripts/run_playtest_pipeline.py`（大纲解析改为调用 `outline_parser`，删除内联 docx/txt 解析大段代码）
- `survey_tools/web/quant_app.py`（可选大纲上传交互）

#### 变更内容

**1. `outline_parser` 模块职责**

- `parse_outline_docx` / `parse_outline_txt`：问卷星 .docx、腾讯 .txt（及腾讯内容保存为 .docx 时的纯文本抽取后解析）。
- `docx_bytes_to_plain_text`：从 docx 二进制抽取去标签纯文本，供腾讯规则解析复用。
- `parse_outline_txt` 支持 `str` 入参（已解码正文）。
- `parse_outline_for_platform(data, filename, platform)`：`platform` 为 `wjx` | `tencent`，由调用方显式指定解析管线；**问卷星 + .txt** 不支持（`ValueError`，Web 端以 `st.warning` 展示）。
- `outline_to_q_num_type`：大纲 → 题号→题型短格式映射，供题型表初始化覆盖（与 Pipeline `_auto_classify_columns` 大纲覆盖口径一致）。

**2. Quant Web（`quant_app`）体验**

- 数据加载后，折叠区「问卷大纲（可选）」：上传 `.docx` / `.txt`，**右侧「大纲来源」** 选择「问卷星」或「腾讯问卷」，决定调用哪套解析器（**不再按扩展名自动推断平台**）。
- 解析成功则写入 `outline_q_num_to_type` 并 `column_type_df = None` 强制重建题型表；未上传大纲时行为不变（`infer_type_from_columns` + 题型微调）。
- 上传时使用 `seek(0)` + `getvalue()` 避免 Streamlit 重复 rerun 导致流读空。

**3. Pipeline CLI**

- `_dispatch_parse_outline` 仍按扩展名 `.txt` → 腾讯、否则 → 问卷星（与「自动发现 data/raw 大纲」习惯一致）；**未**新增 `--outline-platform`（可后续排期）。

**4. 与「Pipeline / Web 统一性」相关的产品结论（记录备查）**

- **强制忽略列**（答卷时间、答卷编号等）：按产品决策 **不** 在 `question_type` 与 Quant Web 间共享常量；**仅** Pipeline 内保留 `_FORCE_IGNORE_KEYWORDS`。
- 核心交叉分析已收敛到 `quant.build_question_specs` + `quant.run_quant_cross_engine`（`quant_v13_engine` 仅兼容转发层）；大纲题型覆盖逻辑在 Pipeline 与 Web 侧与 `outline_to_q_num_type` / `_auto_classify_columns` 对齐。

---

## 📅 2026-03-17

### Pipeline v0.1 → v0.2：5 项增强（A/B/C/D/E）

**涉及文件**:
- `scripts/run_playtest_pipeline.py`（全量更新 v0.1→v0.2）

#### 变更内容

**[A] .sav 格式警告**：加载 `.sav` 文件时自动打印格式提示，说明多选题识别依赖变量标签、建议优先使用 `.xlsx`。

**[B] `.sav` meta 辅助题型识别**：新增 `_enhance_with_sav_meta()` 函数。通过 `pyreadstat.read_sav` 获取原始 meta 对象，利用：
- 原始变量名后缀剥离分组（如 `Q5_1/Q5_2/Q5_3 → 前缀 Q5`），若 2+ 个 0/1 二分列共享同一前缀，识别为多选题
- `meta.variable_measure == 'scale'` → 修正被误判为单选的数值列为评分

**[C] `--segment-col` 参数**：CLI 新增 `--segment-col TEXT` 参数，支持子串模糊匹配（不需要输入完整列名）；优先级高于自动关键词识别。运行示例：
```bash
python scripts/run_playtest_pipeline.py --segment-col "玩家类型"
```

**[D] Sheet 数量控制**：`_export_results` 改为按 Q 题号分组（同一道题的多子项合并为一个 Sheet）；独立题 Sheet 上限 `_MAX_INDIVIDUAL_SHEETS = 60`，超出部分仅出现在「交叉分析（汇总）」Sheet。

**[E] 「总体」fallback 分组**：无自然分组列时，不再跳过交叉分析，而是自动生成 `_总体_` 虚拟列（值恒为 "总体"），输出全量频率分布报告。

**附加修复**：
- Windows PowerShell GBK 编码兼容：在脚本顶部强制 `sys.stdout/stderr` 使用 UTF-8，解决 `⚠`/`✗`/`✅` 字符引发的 `UnicodeEncodeError`
- 报告文件被 Excel 占用时自动追加序号（如 `_2.xlsx`），避免 `PermissionError`

#### 测试结果
- `.xlsx` 文件（42 样本，105 列）：总体 fallback 正常，输出 57 个 Sheet（汇总 + 55 道题），N<50 回归跳过
- `--help` 显示 `--segment-col` 参数文档

---

### 新增：Playtest 自动化分析流水线 MVP

**涉及文件**:
- `scripts/run_playtest_pipeline.py`（新建）

#### 本轮工作内容

基于前序对 `survey_tools/utils/io.py` 的增量重构（`load_survey_data` + `get_latest_local_data`），实现了第一个端到端的 CLI 自动化分析流水线，贯彻 MVP 原则。

**流水线步骤**：

1. **数据装载**：调用 `get_latest_local_data('data/raw')` 自动找到最新文件，再用 `load_survey_data()` 读取并清洗表头，打印样本量。
2. **自动题型识别**：先通过 `parse_columns_for_questions` + `infer_type_from_columns` 做关键词分组推断（高精度），无法匹配时回退到 `detect_column_type` 逐列推断。
3. **定量交叉分析**：通过关键词（组别/分组/类型/经验等）自动寻找分组列，调用 `build_question_specs` + `run_quant_cross_engine` 完成全量交叉；结果按题号全局排序。
4. **满意度回归建模**：加入 N < 50 防护：样本量不足时主动跳过并打印提示；正常时调用 `GameExperienceAnalyzer.regression_analysis()`，自动寻找满意度/NPS类目标列。
5. **文本分析占位**：`_run_text_analysis_placeholder()` 空函数，注释标记 TODO，等待后续从 `text_app.py` 提取 core 模块后接入。
6. **汇总导出**：使用 `ExportBundle` + `export_xlsx`，导出格式：`YYYYMMDD_Playtest自动化分析报告.xlsx`，包含「样本概况」「交叉分析（汇总）」每题独立 Sheet + 「满意度回归结果」。

**CLI 用法（在 UserResearch/ 目录下执行）**：

```bash
# 默认读取 data/raw/，输出到 data/processed/
python scripts/run_playtest_pipeline.py

# 指定目录
python scripts/run_playtest_pipeline.py --data-dir data/raw --output-dir data/processed

# 查看帮助
python scripts/run_playtest_pipeline.py --help
```

**设计决策**：
- 使用 `click` 构建 CLI 入口，与 `project-standards.mdc` 中"CLI 入口"规范对齐。
- 所有步骤独立 try-except：单步骤失败不阻断整体流水线，仅打印警告。
- 内嵌 `sys.path` 修正，确保从项目根目录下各子目录运行脚本时不报 ModuleNotFoundError。
- 自动识别的分组列和满意度列均使用关键词匹配 + 数据验证（唯一值数量、数值型比例），减少误判。

---

## 📅 2026-03-19

### 代码质量补全：顶层规范落地 + 全量 Docstring 补全

**涉及文件**:
- `requirements.txt`
- `survey_tools/core/quant.py`（21 个函数）
- `survey_tools/core/question_type.py`（7 个函数）
- `survey_tools/core/clustering.py`（10 个函数）
- `survey_tools/core/quant_v13_engine.py`（2 个函数）
- `survey_tools/core/advanced_modeling.py`（3 个方法）
- `survey_tools/core/missing_strategy.py`（1 个函数）
- `survey_tools/core/factor_compat.py`（3 个函数）
- `survey_tools/core/effect_size.py`（1 个函数）
- `survey_tools/core/stats_simulation.py`（5 个函数）

#### 本轮工作内容

**1. 修复阻塞性依赖缺失（requirements.txt）**

- 追加 `python-dotenv>=1.0.0,<2.0`：`survey_tools/config.py` 的 `load_dotenv()` 依赖，缺失会导致 `.env` 文件静默不加载。
- 追加 `click>=8.1.0,<9.0`：`tool_registry.py` 已声明 CLI 路径，规范要求的 CLI 入口依赖该库。

**2. 补全 survey_tools/core/ 全量 Docstring（由 10% 合规率提升至接近 100%）**

上轮顶层规范制定后，评估发现 59 个公开函数中仅 6 个（10%）完全符合「中文首行 + Google Style Args/Returns」规范。本轮逐一补全：

| 文件 | 操作 | 数量 |
|---|---|---|
| `quant.py` | 新增完整 docstring | 21 个函数 |
| `question_type.py` | 新增完整 docstring | 7 个函数 |
| `clustering.py` | 英文首行→中文 + 补全缺失 docstring | 10 个函数 |
| `quant_v13_engine.py` | 补全 Args/Returns 块 | 2 个函数 |
| `advanced_modeling.py` | 补全 Args/Returns 块 | 3 个方法 |
| `missing_strategy.py` | 新增完整 docstring | 1 个函数 |
| `factor_compat.py` | 新增完整 docstring | 3 个函数 |
| `effect_size.py` | 新增完整 docstring | 1 个函数 |
| `stats_simulation.py` | 英文首行→中文 + 补全 | 5 个函数 |

**3. 背景：上一轮（项目顶层规范补全，同日）**

在此之前完成了架构层规范落地，包括：
- 更新 `.cursor/rules/project-standards.mdc`（双份同步），新增产品阶段声明、配置外部化、环境管理、Core 函数接口、工具注册表、Docstring 规范、CLI 规范等章节；
- 创建 `survey_tools/config.py`（统一配置模块）；
- 创建 `.env.example`、`.python-version`；
- 创建 `tool_registry.py`（5 个工具的统一元数据注册表）；
- 重构 `web_tools_launcher.py` 改为从注册表读取；
- 更新 `README.md` 新增「环境准备」章节。

---

## 📅 2026-03-17

### 1. 文档与迭代可见性约定 + wjxspss 规则与核心模块映射验收（阶段 A/B/C）
**涉及文件**: `README.md`, `UserResearch/DEV_LOG.md`, `.cursor/rules/project-standards.mdc`, `UserResearch/功能可执行清单_参考wjxspss.md`, `UserResearch/docs/core_modules_wjxspss_mapping.md`, `UserResearch/docs/core_modules_wjxspss_acceptance_matrix.md`, `UserResearch/docs/task_list_wjxspss_mapping_acceptance.md`, `UserResearch/下一步_to-do_项目主管.md`

- **项目规则补充**：README 与 DEV_LOG 须保持可读性，使任何人（含对话重开后）能通过二者理解**前情提要、后续计划及完成情况**；重要 .md 文档（需求/清单/验收/计划类）须在 README 或 DEV_LOG 中有**说明与映射**。已写入 `.cursor/rules/project-standards.mdc`。

- **README 更新**：新增「文档与迭代可见性（前情提要 · 计划 · 完成情况）」小节，明确 README + DEV_LOG 为入口，并列出 `UserResearch/` 下需求与验收相关文档的映射表（功能可执行清单、对应表、映射验收表、任务列表、下一步 to-do）。

- **阶段 A（wjxspss 规则补充）**：从 wjxspss 正文归纳「数据处理基本原则」四条，写入 `project-standards.mdc`；`.cursorrules` 补充引用。详见 `task_list_wjxspss_mapping_acceptance.md` 阶段 A 执行记录。

- **阶段 B（目录-核心模块对应表）**：以功能可执行清单六大类为口径，逐条标出核心模块中已实现/部分实现/未实现，产出 `core_modules_wjxspss_mapping.md`。可验收范围与未实现项已汇总于该文档。

- **阶段 C（映射验收表）**：对已实现/部分实现条目建立逐条映射与验收方式，产出 `core_modules_wjxspss_acceptance_matrix.md`（共 16 条可验收项，状态初始为「待验收」）。不修改代码，仅用于人工或回归验收。

- **下一步 to-do**：产出 `UserResearch/下一步_to-do_项目主管.md`，包含立即执行（执行验收表、验收问题清单、需求与规则符合度检查）、短期（修复不通过项、沉淀回归用例、功能缺口 Backlog）、中期（P2 管线统一化、依赖锁定、导出约定落地）及可选项。执行顺序与参考文档已在其中说明。

- **DEV_LOG 本条目**：记录上述文档与规则变更，并再次申明 README + DEV_LOG 为前情与计划入口。

### 2. 执行「一」：16 条验收 + 问题清单 + 需求/规则符合度检查
**涉及文件**: `UserResearch/验收问题清单_20260317.md`（新增）, `UserResearch/需求与规则符合度检查_20260317.md`（新增）, `UserResearch/docs/core_modules_wjxspss_acceptance_matrix.md`, `README.md`

- **质量矩阵**：执行 `run_quality_matrix.py`，结果 3/5 通过（verify_dependency_matrix、test_migration、verify_current_v1_logic），2/5 失败（verify_p2_baseline、verify_p24_clustering 因依赖 `UserResearch/example` 路径不存在或编码问题）。失败原因与 16 条映射验收无一一对应，但影响 P2 基线及 P2-4 聚类自动化回归。
- **16 条映射验收**：需人工在界面逐条执行（运行各 Streamlit 入口、上传 input_example 数据、按检查点查看）。已产出 **`验收问题清单_20260317.md`**，用于记录不通过项及人工验收后的填写说明；映射验收表已补充执行记录与上述两文档引用。
- **需求与规则符合度检查**：已产出 **`需求与规则符合度检查_20260317.md`**。结论摘要：输入 .csv/.xlsx 符合，input_example 符合；**.sav 未接入**（依赖已写、文档已注明）；导出「一工作簿多 sheet」部分符合（满意度/文本等已多 sheet，Quant 主导出为单 sheet）；「用户勾选再打包」未实现。
- README「文档与迭代可见性」映射表已新增上述两文档。
- **AI Agent 人工验收上下文**：新增 `UserResearch/AI_Agent_人工验收上下文.md`，供搭建 AI agent（如 Open Claw）时快速接手人工验收：含项目与任务一句话、工作目录与五剑客入口、测试数据路径、18 条验收一览（条目→工具→检查点）、需更新的文档与动作、前情提要、智能体能力假设。README 映射表已加入该文档。

### 3. 分阶段落地：Core 修复 + 自动化验收 + .sav/导出统一（2026-03-17）
**涉及文件**: `survey_tools/core/quant.py`, `survey_tools/utils/io.py`, `UserResearch/auto_verify_v1.py`, `UserResearch/test_assets/mock_survey.csv`, `CODE_REVIEW_DEBUG_REPORT.md`, `DEV_LOG.md`

- **Phase 1（Core P0）**  
  - **quant.py**：`run_question_analysis` 在 `mode=="between"` 且 `question_type=="多选"` 时支持 `value_cols`（列表），并传入 `run_group_difference_test`，修复报告问题 12。  
  - **quant.py**：评分分支（ANOVA/Kruskal）在返回中增加 `assumption_checks`（normality_ok、levene_p、decision、reason），对标 wjxspss「非正态/方差不齐时自动切换非参数」并在结果中注明。  
  - 报告「五、已修复项」中 1–6 已标记已完成；问题 12 与 assumption_checks 修复已记入报告。

- **Phase 3（自动化验收）**  
  - 新增 **`UserResearch/auto_verify_v1.py`**：使用 `test_assets/mock_survey.csv` 或内存 mock，调用 `run_group_difference_test` / `run_question_analysis`，断言返回含 `p_value`、`effect_size`、评分分支含 `assumption_checks.decision`；多选 between 支持 `value_cols`。断言失败时输出详细失败报告。  
  - 新增 **`UserResearch/test_assets/mock_survey.csv`**：脱敏小样本，供自动化验收与双机/CI 复现，不依赖被 gitignore 的 input_example。

- **Phase 4（.sav 与统一导出协议）**  
  - **survey_tools/utils/io.py**：实现 **`load_sav(path_or_file)`**，使用 pyreadstat 读取 .sav，返回 `(df, variable_labels, value_labels)`，支持路径或文件对象（临时文件兜底）。  
  - **survey_tools/utils/io.py**：定义 **`ExportBundle(workbook_name, sheets)`** 与 **`export_xlsx(bundle, path_or_buffer)`**，统一「单工作簿多 Sheet」写出；各工具后续可将结果组装为 ExportBundle 再调用 export_xlsx，UI 适配可后置。

### 4. 短期：auto_verify_v1 并入质量矩阵 + verify_p2/verify_p24 路径回退
**涉及文件**: `UserResearch/run_quality_matrix.py`, `UserResearch/verify_p2_baseline.py`, `UserResearch/verify_p24_clustering.py`

- **run_quality_matrix.py**：在脚本列表中新增 **auto_verify_v1.py**（核心 schema 验收），顺序在 verify_current_v1_logic 之后、verify_p2_baseline 之前。
- **verify_p2_baseline.py** / **verify_p24_clustering.py**：当 **example/** 目录不存在时，回退到 **test_assets/** 下查找 .xlsx；若仍无可用文件则**跳过验证并正常退出**（exit 0），避免因路径缺失导致质量矩阵整体失败。双机/CI 无 example 时矩阵可 6/6 通过。
- 执行结果：质量矩阵 6/6 通过（含 auto_verify_v1、verify_p2_baseline、verify_p24_clustering）。

### 5. 扩展 auto_verify_v1 + 问题清单审阅更新 + P0 核对（2026-03-17）
**涉及文件**: `UserResearch/auto_verify_v1.py`, `UserResearch/CODE_REVIEW_DEBUG_REPORT.md`

- **auto_verify_v1 扩展**：在现有 mock/test_assets 基础上增加对 quant core 的更多断言与 core 层用例。  
  - 评分+分组：overall 含 test/stat/p_value/effect_size，effect_size 数值类型；assumption_checks 含 decision、normality_ok、levene_p、reason；test 为 ANOVA 或 Kruskal-Wallis。  
  - 单选+分组：overall 含 test（chi-square/fisher_exact）、stat、p_value、effect_size。  
  - 多选+分组：overall.test=multi-option，overall 含 p_value、effect_size；details[0] 含 option、p_value、effect_size、test。  
  - run_question_analysis：多选 between + value_cols 返回 multi-option；评分 describe 返回 describe DataFrame（列 group、mean、n）。  
  - 评分事后比较：当 p&lt;0.05 且存在 pairwise 时，检查 pairwise 含 group1、group2、p_value。  
  - 失败报告增强：打印 keys/cols/type 便于排查。
- **问题清单更新**：对 auto_verify_v1 做静态审阅与逻辑推演，在 **CODE_REVIEW_DEBUG_REPORT.md** 新增「六、auto_verify_v1 扩展审阅」；审阅范围清单新增 `UserResearch/auto_verify_v1.py`。
- **P0 核对**：问题清单「五、已修复项」1～7 已逐项核对当前代码，均已落地；一、二节其余条目为说明/文档类。报告内已补充 P0 核对说明。
- 质量矩阵 6/6 通过（含扩展后的 auto_verify_v1）。

---

## 📅 2026-03-18

### 1. Quant Engine 2.0：忽略项在“新增组合分组列”后被重置，导致仍参与统计
**涉及文件**：`survey_tools/web/quant_app.py`

- **问题**：当用户在工具内生成“组合分组列”后，DataFrame 列集合变化会触发题型表 `column_type_df` 重新构建，导致用户手动标记的「忽略」被覆盖回自动识别结果，进而出现“已忽略的子项仍被统计”的现象。
- **修复**：
  - 列集合变化时，题型表改为**增量合并新列**，并**保留旧列的人工题型**（尤其是「忽略」）。
  - 组合分组列（按配方名命中）默认标记为「忽略」，避免作为题目列进入统计与题目选择列表。

### 2. Quant Engine 2.0：.sav 应用变量标签后，单选/评分可能不含 Q 题号，导致只分析多选
**涉及文件**：`survey_tools/core/quant.py`, `survey_tools/core/quant_v13_engine.py`, `survey_tools/web/quant_app.py`

- **问题**：v1.3 口径引擎对单选/评分默认按题号（Q<number>）回查列；在 `.sav` 勾选“应用变量标签”后，列名可能不再包含可解析的 `Q<number>`，导致 UI 已选中的单选/评分列未进入引擎统计，表现为“只分析多选”。
- **修复**：
  - 在引擎 `run_quant_cross_engine(...)`（兼容别名 `run_v13_like_cross(...)`）中新增 `explicit_single_cols / explicit_rating_cols` 参数：对单选/评分优先按 UI 显式勾选列逐列统计（并去重），不再强依赖列名含 Q 题号。
  - `quant_app.py` 在构建 question_types 时同步收集上述显式列并传入引擎。

### 3. Quant Engine 2.0：生成组合分组列后，核心分组选择新列回退为 None
**涉及文件**：`survey_tools/web/quant_app.py`

- **问题**：核心分组 `selectbox` 使用 widget key `core_segment_col_widget`；生成组合分组列时仅更新 `core_segment_col` 未同步 widget 状态，导致 options 变化后 widget 值非法而回退 `None`。
- **修复**：
  - 生成组合分组列后同步设置 `st.session_state.core_segment_col_widget = <新列名>` 并 `st.rerun()`，保证 UI 状态与业务状态一致。
  - 核心分组默认值读取优先使用 `core_segment_col_widget`，进一步增强 rerun 稳定性。

### 4. Quant Engine 2.0：交叉分析结果展示/导出按题号全局排序（Q1、Q2、Q3…）
**涉及文件**：`survey_tools/web/quant_app.py`

- **问题**：结果列表的顺序随引擎遍历题型而分段（单选一段、多选一段…），不符合“按题号递增”阅读习惯。
- **修复**：在 `analysis_results` 写入 session_state 前，按 `extract_qnum()` 提取题号做全局排序；无法提取题号的条目排到最后并保持稳定顺序。

### 6. 推进下一步 to-do 2/3：验收问题清单 + 需求与规则符合度检查（2026-03-17）
**涉及文件**: `UserResearch/验收问题清单_20260317.md`, `UserResearch/需求与规则符合度检查_20260317.md`

- **2. 验收问题清单**  
  - 更新「一、自动化可执行部分」：质量矩阵由 3/5 改为 **6/6 通过**，补充 auto_verify_v1、verify_p2_baseline、verify_p24_clustering 的当前说明。  
  - 补全「二、16 条映射验收」：为 16 条赋予**编号 M1～M16**，与映射验收表一一对应；新增**不通过项记录表**（编号、清单条目、对应五剑客、现象、可能原因），便于人工验收后直接填表。  
  - 增加「人工验收时建议关注」与「四、与下一步 to-do 的对应」说明。  
- **3. 需求与规则符合度检查**  
  - 刷新「一、输入格式」「二、.sav 支持」：明确各入口（quant_app、satisfaction_app、cluster_app、game_analyst、文本工具）支持 .csv/.xlsx，**未接 .sav**；注明底层 `survey_tools/utils/io.py` 已实现 `load_sav()` 与 `read_table_auto()` 对 .sav 的调度，供后续入口接入。  
  - 建议中补充：.sav 可在入口 file_uploader 增加 sav 类型并调用 `io.load_sav()`；用户勾选再打包可复用 `io.ExportBundle` / `export_xlsx`。  
  - 文档版本说明增加「推进 2/3 时刷新」。

### 7. 推进短期 to-do 4～6：.sav 接入 + 回归用例沉淀 + Backlog（2026-03-17）
**涉及文件**: `survey_tools/utils/io.py`, `survey_tools/web/quant_app.py`, `survey_tools/web/satisfaction_app.py`, `survey_tools/web/cluster_app.py`, `game_analyst.py`, `问卷文本分析工具 v1.py`, `UserResearch/run_quality_matrix.py`, `UserResearch/verify_standard_regression_core.py`, `UserResearch/verify_clustering_recommendation_core.py`, `UserResearch/verify_text_ingestion_io.py`, `UserResearch/Backlog_短期优先级_20260317.md`, `UserResearch/下一步_to-do_项目主管.md`, `README.md`

- **短期 4：修复验收不通过项/关键缺口（优先落地 .sav）**  
  - 五剑客入口统一支持上传 `.sav`：Quant/Standard/聚类/游研专家/Text 的 file_uploader 均加入 `sav`。  
  - 统一读取链路：CSV/Excel/SAV 读取统一走 `survey_tools.utils.io.read_table_auto`（CSV 含 encoding 回退；Excel 支持多 sheet 选择；SAV 通过 pyreadstat 读取）。  
  - 结果：对照需求约定与符合度检查中 “.sav 未接入入口” 的缺口已消除。

- **短期 5：验收用例沉淀为回归用例**  
  - 新增 3 个自动化脚本并并入质量矩阵：  
    - `verify_standard_regression_core.py`：Standard/core 回归分析 schema 断言（results_df 列、alpha/sample_size 等）。  
    - `verify_clustering_recommendation_core.py`：聚类/core 的算法推荐与 K+算法联合推荐回归用例。  
    - `verify_text_ingestion_io.py`：Text 的数据入口已切换为 `read_table_auto`，用 test_assets 覆盖读取路径。  
  - `run_quality_matrix.py` 更新后当前为 **9/9 通过**。

- **短期 6：功能缺口与 Backlog**  
  - 新增 `Backlog_短期优先级_20260317.md`：将“导出勾选打包、多 sheet 导出、偏相关、配对/单样本检验、Logistic”等缺口收敛为可排期任务（含优先级与建议落点）。  
  - `下一步_to-do_项目主管.md` 与 README 文档映射表同步更新该 Backlog 文档引用。

### 8. 中期 9：导出约定落地（2026-03-17）
**涉及文件**: `survey_tools/web/quant_app.py`, `survey_tools/web/satisfaction_app.py`, `survey_tools/utils/io.py`, `UserResearch/需求与规则符合度检查_20260317.md`, `UserResearch/Backlog_短期优先级_20260317.md`, `UserResearch/下一步_to-do_项目主管.md`

- **Quant**  
  - 导出由「单 sheet 多题堆叠」改为**单工作簿多 sheet**：可选「交叉分析结果（汇总）」+ 每题一 sheet（sheet 名经 `make_safe_sheet_name` 处理）。  
  - **用户勾选**：导出前通过 `st.multiselect` 勾选要导出的 sheet，仅将勾选项通过 `ExportBundle` + `export_xlsx` 打包；导出 buffer 存 `session_state`，下载按钮在下一轮仍可用。  
- **Standard（满意度）**  
  - 导出由固定三 sheet 改为**勾选再打包**：用户可勾选「统计诊断汇总」「模型健康度」「自动摘要」，仅将勾选项写入 `ExportBundle` 并 `export_xlsx` 下载。  
- **文档**  
  - `需求与规则符合度检查_20260317.md`：导出维度更新为「部分符合」；Quant/Standard 已一工作簿多 sheet 且支持用户勾选再打包；.sav 结论更新为「符合」。  
  - `Backlog_短期优先级_20260317.md`：P0 两项导出任务移入「已在本轮落地」。  
  - `下一步_to-do_项目主管.md`：中期 9 执行记录见下条。

### 9. 设计文档：.sav 变量与值标签可选应用方案（2026-03-17）
**涉及文件**: `UserResearch/设计_sav变量与值标签可选应用.md`（新增）, `UserResearch/Backlog_短期优先级_20260317.md`, `README.md`

- 新增 **`UserResearch/设计_sav变量与值标签可选应用.md`**：按「读 .sav 时用 load_sav、可选应用变量/值标签」思路写明的实现方案，供后续 P1 排期与实现参考。
- 内容要点：io 层保持 `read_table_auto` 不变，新增 `read_table_auto_with_meta`（.sav 返回 df + variable_labels + value_labels，CSV/Excel 返回 (df, None, None)）、`apply_sav_labels` 纯函数；各工具入口仅在 .sav 且 meta 非空时提供「应用变量标签」「应用值标签」勾选；默认不应用以兼容现有行为；CSV/Excel 不涉及标签。
- Backlog P1 已增加「.sav 变量/值标签可选应用」条目并引用该设计文档；README 文档映射表已增加该设计文档。

### 10. 全量代码审阅与 Debug 修复（五大工具 + core/web）
**涉及文件**: `CODE_REVIEW_DEBUG_REPORT.md`（新增）, `survey_tools/web/quant_app.py`, `survey_tools/web/satisfaction_app.py`, `game_analyst.py`, `survey_tools/web/cluster_app.py`, `问卷文本分析工具 v1.py`, `README.md`, `DEV_LOG.md`

- **审阅范围**:
  - 按 README 定义的五大核心工具及其依赖的 core/web 模块进行逐行审阅，聚焦运行 Bug、功能缺失、逻辑断层、兼容性与健壮性。
  - 产出独立审阅报告 **`CODE_REVIEW_DEBUG_REPORT.md`**，对问题按「运行 Bug / 逻辑断层·功能缺失 / 兼容性·可维护性 / 健壮性·边界」分类，并保留未改动建议（如双份 GameExperienceAnalyzer 收口、文本工具从 core.quant 直导 make_safe_sheet_name 等）。

- **已落地修复**:
  - **Quant (quant_app)**：排序题「导出结论表」下载按钮在下一轮无法使用 → 将导出 buffer 存入 `st.session_state`，下载按钮根据 session 中的 buffer 渲染；并初始化 `export_ranking_buffer` / `export_ranking_name`。
  - **游研专家 (game_analyst)**：上传新文件后仍使用旧数据 → 用 `(name, size)` 作为文件标识，仅在未加载或标识变化时重新读入并更新 `df_cleaned`。
  - **满意度应用 (satisfaction_app)**：IPA 结果全被 dropna 后空 DataFrame 导致后续均值与绘图异常 → 对 `res_df.empty` 做判断并提前提示；缺失策略回退为 mean 时显式设置 `missing_group_col = None`；CSV 读取增加 `encoding="gbk"` 回退。
  - **分群 (cluster_app)**：联合推荐 `recommended_k` 类型可能非整 → 使用 `int(float(...))` 并 try/except 兜底为 `k_final`。
  - **文本工具 (问卷文本分析工具 v1.py)**：CSV 未指定编码易导致中文报错 → 增加 `UnicodeDecodeError` 后 gbk 回退；弃用 API `st.experimental_rerun()` → `st.rerun()`。
  - **游研专家**：弃用 API `st.experimental_rerun()` → `st.rerun()`。

- **文档同步**:
  - README 新增「全量代码审阅与修复 (2026-03-17)」小节，指向 `CODE_REVIEW_DEBUG_REPORT.md` 与本次修复摘要；工程维护/审阅小节补充审阅报告引用。
  - DEV_LOG 本条目记录审阅范围、修复清单与涉及文件。

## 📅 2026-03-13

### 1. 核心工具代码复审结论与版本迭代路线确认
**涉及文件**: `survey_tools/web/quant_app.py`, `survey_tools/core/quant.py`, `survey_tools/web/satisfaction_app.py`, `survey_tools/core/advanced_modeling.py`, `game_analyst.py`, `survey_tools/web/cluster_app.py`, `survey_tools/core/clustering.py`, `问卷文本分析工具 v1.py`, `README.md`, `DEV_LOG.md`

- **本轮复审范围**:
  - 按 README 定义的五个核心引擎逐项复审关键实现，聚焦统计正确性、版本兼容、性能、异常处理与数据安全。
  - 对外部 AI 审查建议逐条交叉核验，形成“立即修复 / 近期优化 / 中期演进”的分层路线。

- **复审确认的高优先级风险**:
  - **统计正确性风险 (Quant Engine)**:
    - `survey_tools/core/quant.py` 中 `run_group_difference_test` 的多选分支存在可达性问题：前置条件已覆盖 `"多选"`，导致后续多选专用分支难以生效。
    - 多选统计展示仍存在“已计算但导出表达不充分”的问题，和既有待办一致。
  - **兼容性策略分裂 (FactorAnalyzer/sklearn)**:
    - `advanced_modeling.py`、`clustering.py`、`game_analyst.py` 对兼容性处理策略不一致，存在维护与排障复杂度上升风险。
  - **缺失值处理策略偏单一**:
    - 回归与聚类主流程仍大量使用均值填充，尽管已有缺失率预警，但在跳题场景下仍可能引入结构性偏差。
  - **LLM 稳健性与隐私风险 (Text Engine / Cluster AI Naming)**:
    - 文本引擎批处理请求 `max_retries=0`，限流或短暂网络波动下鲁棒性不足。
    - API Key 支持输入框与环境变量双通道，但缺少统一的密钥与脱敏治理规范。

- **版本优化路线图（冻结为后续迭代基线）**:
  - **P0（立即修复，目标 1-2 个迭代）**
    - 修复 Quant 多选检验分支可达性与结果映射一致性问题，确保“计算逻辑 = 导出逻辑 = 可视化逻辑”。
    - 统一核心统计函数的最小样本保护与失败返回协议，减少静默失败。
    - 收敛 FactorAnalyzer/sklearn 兼容方案为单一策略，避免多处 monkey patch 并行演化。
  - **P1（短期优化，目标 2-4 个迭代）**
    - 将缺失值处理升级为策略化配置（drop/mean/中位数/分组插补），并在 UI 中明确统计影响提示。
    - 文本引擎增加重试与退避机制、批次失败重放能力、调用失败可观测指标。
    - 对大样本导出链路做内存优化，降低一次性拼接大表的峰值内存压力。
  - **P2（中期演进，目标季度级）**
    - 建立统一分析管线与错误处理规范，减少 `web` 与 `core` 双轨重复实现。
    - 引入最小可用测试矩阵（统计回归、兼容性、导出一致性）与依赖版本锁定策略。
    - 逐步扩展聚类算法可选项与结果稳定性评估面板（在保持 KMeans 主路径稳定前提下演进）。

- **优先级原则（本轮确认）**:
  - 优先顺序为：统计正确性 > 兼容性稳定 > 缺失值策略 > 安全与稳健性 > 性能扩展。
  - 并行计算不是当前最高优先级，需在正确性与稳定性基线达成后推进。

### 2. 路线图执行进度更新（P0/P1 收口）
**涉及文件**: `survey_tools/core/quant.py`, `survey_tools/web/quant_app.py`, `survey_tools/core/factor_compat.py`, `survey_tools/core/advanced_modeling.py`, `survey_tools/core/clustering.py`, `survey_tools/web/satisfaction_app.py`, `survey_tools/web/cluster_app.py`, `game_analyst.py`, `问卷文本分析工具 v1.py`

- **P0 已完成**:
  - Quant 多选检验分支可达性、返回映射与展示口径完成对齐。
  - `FactorAnalyzer + scikit-learn` 兼容处理统一收敛至 `factor_compat.py`，并在 `advanced_modeling / clustering / game_analyst` 全链路接入。
  - 核心异常返回协议完成标准化，小样本/空样本/异常输入下稳定性提升。

- **P1 已完成**:
  - 缺失值策略完成配置化升级：`drop / mean / median / group_mean / group_median`，已落地到标准版与旗舰版回归流程，分群清洗策略扩展至 `median`。
  - 文本引擎完成稳健性增强：重试+指数退避+抖动、失败批次重放、调用统计可观测输出。
  - 文本引擎导出链路完成内存优化：由 `pandas.ExcelWriter` 聚合写入改为 `openpyxl write_only` 流式写入，并改为“准备导出→下载”以避免每次渲染重复构建导出大对象。

- **关键修复点（本轮新增）**:
  - 修复回归 VIF 计算在“已有常量列”场景下的越界问题：`sm.add_constant(..., has_constant="add")`。
  - 修复文本导出缓存失效时机：上传新文件、重置配置、重新分析后自动清空旧导出缓存，避免下载陈旧结果。

### 3. 验证与回归结果（含业务样本）
**验证样本**:
- `example/mock_survey_data.xlsx`
- `example/player_segmentation_result (1).xlsx`
- `example/349829695_按序号_【代号SUN-0209跑测】15人问卷_42_42 (3).xlsx`

**验证结论**:
- 编译检查通过：`python -m compileall survey_tools game_analyst.py`、`python -m compileall 问卷文本分析工具 v1.py`。
- 缺失值策略与回归流程在上述业务样本上可运行，核心/旗舰回归策略链路可用。
- 文本引擎重试机制经模拟限流注入测试通过：可在重试上限内恢复，超上限时按预期失败并回填占位结果。
- 文本引擎导出构建在业务样本上通过，且导出字节结果正常生成。

### 4. 下一阶段（P2）执行入口
- **分析管线统一化**: 收敛 `web` 与 `core` 的重复实现，明确单一真源逻辑。
- **质量保障体系补齐**: 建立最小可用回归矩阵（统计正确性 / 兼容性 / 导出一致性）。
- **依赖版本锁定**: 明确关键依赖版本边界与兼容矩阵。
- **分群能力扩展**: 在维持 KMeans 主路径稳定前提下逐步引入多算法与稳定性评估。

### 5. P2-2 首批落地（质量保障体系）
**涉及文件**: `survey_tools/core/missing_strategy.py`, `survey_tools/core/advanced_modeling.py`, `game_analyst.py`, `verify_current_v1_logic.py`, `verify_p2_baseline.py`, `run_quality_matrix.py`

- **分析管线统一化（增量）**:
  - 将回归缺失值策略实现抽取到 `survey_tools/core/missing_strategy.py`，`advanced_modeling` 与 `game_analyst` 统一复用，减少双轨重复逻辑。

- **最小测试矩阵（落地）**:
  - 新增 `verify_p2_baseline.py`，覆盖 `example/` 全量业务样本上的缺失值策略矩阵回归与文本导出构建检查（可验证样本自动识别，边界样本自动跳过并记录）。
  - 新增 `run_quality_matrix.py` 统一入口，按顺序执行：
    - `verify_dependency_matrix.py`
    - `test_migration.py`
    - `verify_current_v1_logic.py`
    - `verify_p2_baseline.py`

- **可移植性修复**:
  - `verify_current_v1_logic.py` 改为优先读取根目录样本，缺失时自动回退到 `example/mock_survey_data.xlsx`。

- **验证结论**:
  - `python -m compileall survey_tools game_analyst.py verify_p2_baseline.py` 通过。
  - `python verify_p2_baseline.py` 通过。
  - `python test_migration.py` 通过。
  - `python run_quality_matrix.py` 通过。

### 6. P2-3 首批落地（依赖版本锁定与兼容矩阵）
**涉及文件**: `requirements.txt`, `requirements.lock.txt`, `verify_dependency_matrix.py`, `DEPENDENCY_MATRIX.md`, `README.md`

- **依赖锁定策略落地**:
  - `requirements.txt` 升级为区间约束，限制关键库在已验证主版本范围内。
  - 新增 `requirements.lock.txt` 作为精确锁定版本清单，用于复现实验与稳定回归环境。
  - 补充运行时必需依赖声明：`scipy`、`factor-analyzer`、`XlsxWriter`。

- **兼容矩阵落地**:
  - 新增 `verify_dependency_matrix.py`，自动检查当前环境是否落在项目兼容区间内。
  - 新增 `DEPENDENCY_MATRIX.md`，固化 Python 基线、兼容区间、锁定版本与执行命令。
  - `run_quality_matrix.py` 已纳入 `verify_dependency_matrix.py` 作为首个检查步骤。

- **验证结论**:
  - `python verify_dependency_matrix.py` 通过。
  - `python run_quality_matrix.py` 通过。

### 7. P2-4 首批落地（分群能力扩展）
**涉及文件**: `survey_tools/core/clustering.py`, `survey_tools/web/cluster_app.py`, `verify_p24_clustering.py`, `verify_p2_baseline.py`, `run_quality_matrix.py`, `README.md`

- **多算法能力落地**:
  - 分群核心新增多算法执行能力：`kmeans / gmm / agglomerative`。
  - 输出稳定性指标：`silhouette / calinski_harabasz / davies_bouldin`，并补充簇规模均衡度指标。
  - 新增 `evaluate_clustering_algorithms(...)`，支持固定 K 下算法横向比较。

- **Web 端能力扩展**:
  - 分群设置面板新增算法选择项，默认保持 `kmeans` 主路径。
  - 执行区新增“评估多算法（当前K）”结果表，便于业务快速比较算法表现。
  - 聚类结果页新增关键稳定性指标展示，方便画像解释与复盘。

- **验证矩阵扩展**:
  - 新增 `verify_p24_clustering.py`，覆盖 `example/` 新增样本，自动识别可验证文件并执行多算法回归。
  - `verify_p2_baseline.py` 改为扫描 `example/` 全量 `.xlsx`，提升对新增样本的回归覆盖。
  - `run_quality_matrix.py` 已纳入 `verify_p24_clustering.py`。

- **验证结论**:
  - `python verify_p24_clustering.py` 通过（ok=4, skip=4, total=8）。
  - `python verify_p2_baseline.py` 通过（文本导出覆盖 8 份样本）。
  - `python verify_dependency_matrix.py`、`python test_migration.py`、`python verify_current_v1_logic.py` 通过。

### 8. P2-4 第二阶段（推荐策略与一键采用）
**涉及文件**: `survey_tools/core/clustering.py`, `survey_tools/web/cluster_app.py`, `verify_p24_clustering.py`, `README.md`

- **推荐策略落地**:
  - 新增 `recommend_clustering_algorithm(...)`，基于 `silhouette / calinski_harabasz / davies_bouldin / imbalance_ratio` 计算综合评分并给出推荐算法。
  - 对推荐结果增加稳定性护栏：若相对 KMeans 优势不显著，则回退推荐 KMeans。

- **交互能力落地**:
  - 分群页多算法评估结果支持展示 `recommendation_score` 排序结果。
  - 新增“一键采用推荐算法”按钮，自动回填算法选择并触发重跑。

- **验证补强**:
  - `verify_p24_clustering.py` 已纳入推荐逻辑校验，确保推荐算法字段合法且可执行。

- **验证结论**:
  - `python -m compileall survey_tools\core\clustering.py survey_tools\web\cluster_app.py verify_p24_clustering.py` 通过。
  - `python verify_p24_clustering.py` 通过（ok=4, skip=4, total=8）。
  - `python run_quality_matrix.py` 通过（5/5）。

### 9. P2-4 第三阶段（K+算法联合推荐）
**涉及文件**: `survey_tools/core/clustering.py`, `survey_tools/web/cluster_app.py`, `verify_p24_clustering.py`, `README.md`

- **联合推荐策略落地**:
  - 新增 `recommend_k_algorithm_combo(...)`，跨 K 候选与多算法进行联合评分，输出推荐 `K + algorithm`。
  - 联合评分维度包含 `silhouette / calinski_harabasz / davies_bouldin / imbalance_ratio / k复杂度`。
  - 增加相对当前配置的增益护栏，优势不显著时保持当前配置，避免过度切换。

- **交互能力落地**:
  - 分群页新增“智能推荐K+算法”按钮，可一键触发联合评估。
  - 新增“联合推荐结果（K+算法）”展示区，输出推荐理由与候选排序。
  - 新增“一键采用推荐K+算法”按钮，直接回填 `K` 与算法配置。

- **验证补强**:
  - `verify_p24_clustering.py` 增加联合推荐校验，验证推荐 K 合法、推荐算法合法且可执行。

- **验证结论**:
  - `python -m compileall survey_tools\core\clustering.py survey_tools\web\cluster_app.py verify_p24_clustering.py` 通过。
  - `python verify_p24_clustering.py` 通过（ok=4, skip=4, total=8）。
  - `python run_quality_matrix.py` 通过（5/5）。

### 10. P2-4 第四阶段（模板化推荐口径）
**涉及文件**: `survey_tools/core/clustering.py`, `survey_tools/web/cluster_app.py`, `verify_p24_clustering.py`, `README.md`

- **模板能力落地**:
  - 新增推荐模板集合：`balanced / stability_first / discrimination_first`。
  - 推荐逻辑支持 `profile` 参数，算法推荐与 K+算法联合推荐统一按模板权重执行。
  - 新增统一评分函数，减少重复打分逻辑并保证模板行为一致。

- **交互能力落地**:
  - 分群侧边栏新增“推荐口径”模板选择项，支持业务目标快速切换。
  - 推荐结果提示中显示当前模板，便于复盘与跨团队沟通。

- **验证补强**:
  - `verify_p24_clustering.py` 增加多模板回归，校验各模板推荐输出合法且可执行。

- **验证结论**:
  - `python -m compileall survey_tools\core\clustering.py survey_tools\web\cluster_app.py verify_p24_clustering.py` 通过。
  - `python verify_p24_clustering.py` 通过（ok=4, skip=4, total=8）。
  - `python run_quality_matrix.py` 通过（5/5）。

### 11. 文档一致性与全链路导出审阅
**涉及文件**: `README.md`, `DEV_LOG.md`, `run_example_full_review.py`, `PROJECT_CODE_REVIEW.md`

- **文档一致性更新**:
  - README 明确“当前核心工具总数 = 5（五剑客）”，统一历史口径差异。
  - README 增补 `example/` 全链路审阅导出入口与产物目录说明。
  - DEV_LOG 同步修订历史表述中可能引发歧义的“旧口径描述”。
  - 03-16 项目级审阅模型信息已在 `PROJECT_CODE_REVIEW.md` 固化：`GPT-5.3-Codex（Trae IDE）`。

- **全链路审阅导出能力**:
  - 新增 `run_example_full_review.py`，基于 `example/` 样本一键执行质量脚本并导出审阅产物。
  - 产物覆盖日志、文本导出、分群评估与结果、回归分析结果及总览汇总。
  - 新增 `PROJECT_CODE_REVIEW.md`，沉淀本轮项目级代码审阅结论与后续建议。

- **验证结论**:
  - `python run_example_full_review.py` 可执行并生成审阅目录。
  - `python run_quality_matrix.py` 通过（5/5）。

## 📅 2026-03-11

### 1. 玩家智能分群引擎 (Smart Player Segmentation) 发布
**涉及文件**: `survey_tools/web/cluster_app.py`, `survey_tools/core/clustering.py`, `聚类.py`, `web_tools_launcher.py`

- **全新架构 (Super App No.4)**:
  - 彻底重构了原有的 `聚类.py` 桌面工具，将其升级为基于 Streamlit 的 Web 旗舰应用。
  - 实现了从数据清洗、降维、聚类到画像生成、AI 命名的完整业务流。

- **核心功能亮点**:
  - **智能清洗**: 自动检测特征缺失率，若 >10%（跳题风险）则强制弹出高危预警，支持“剔除”或“均值填充”。
  - **降维增强**: 内置 `FactorAnalyzer`，支持先进行因子分析提取潜在维度，再进行聚类，提升稳定性。
  - **寻 K 神器**: 并排展示 **手肘法 (WCSS)** 与 **轮廓系数 (Silhouette)** 图表，辅助决策最佳 K 值。
  - **全景战情室**:
    - **PCA 散点图**: 交互式展示人群分布。
    - **雷达图**: 直观对比各簇特征均值。
    - **热力图**: 宏观查看特征差异。
  - **AI 辅助命名**: 集成 OpenAI/LangChain，一键根据画像特征生成生动的人群名称。
  - **稳健性修复**: 修复了 `factor_analyzer` 与 `sklearn >= 1.6` 的兼容性问题（`check_array` 缺少 `force_all_finite` 参数）。已在所有涉及模块中添加了 Monkey Patch。
  - **题型智能过滤**: `Quant Engine` 新增自动识别逻辑，将 `Type_`（连续因子得分）和 `其他`（开放填空）自动标记为“忽略”，并修复了“忽略”题型仍被纳入分析的 Bug。
  - **Excel 格式修复**: 修复了导出时“效应量”被转为文本导致 Excel 色阶条件格式失效的问题。
  - **题型识别增强**: 扩展了 `question_type.py` 的关键词库，支持识别 `[单选]`、`[多选]` 等英文括号格式；修复了单选题被误判为评分题的优先级问题。
  - **交互体验优化**: 修复了 `Quant Engine` 在遇到数据错误时直接崩溃的问题，改为跳过错误题目并显示警告；修复了手动修改题型后下方列表未实时同步的 Bug。

- **系统集成**:
  - 更新 `web_tools_launcher.py`，将新工具注册为第 4 个菜单项。
  - 更新 `README.md`，确立了当时的工具体系（当前版本已统一为“五剑客”）。

## 📅 2026-03-10

### 1. 问卷定量分析工具 (Quant Engine) 修复与优化
**涉及文件**: `survey_tools/web/quant_app.py`, `survey_tools/core/question_type.py`

- **Excel 多 Sheet 支持**:
  - 为 `load_data` 函数增加了 `sheet_name` 参数。
  - 实现了上传 Excel 文件后自动检测 Sheet 数量，若大于 1 则弹出下拉框供用户选择的逻辑。
  - 修复了 `analyze_single_choice` 等函数中因未正确处理多 Sheet 导致的读取默认 Sheet 问题。

- **题型自动识别逻辑增强**:
  - 更新 `survey_tools/core/question_type.py`，增加了对 `（多选）`、`（单选）`、`限选`、`最多选` 等关键词的识别支持。
  - 修复了部分明确标记为“多选”的题目被错误识别为“评分题”的问题。

- **交叉分析逻辑重构 (对齐 v1.3 版本)**:
  - **题目聚合**: 重写了题目选择逻辑。现在不再列出所有原始列（如 Q1:A, Q1:B），而是自动将属于同一题目的列聚合显示（如 `Q1. 游戏类型 [多选题]`），大幅简化了操作。
  - **分析逻辑**: 
    - 修复了多选题、矩阵单选、矩阵评分题被错误拆解为多个独立单选题进行分析的问题。
    - 现在多选题会正确计算“提及率”（Mention Rate），矩阵题会按子项进行组间/组内差异分析。
  - **展示与导出**:
    - 引入 `pivot_v13_style` 函数，将分析结果转化为标准的透视表格式（行=选项，列=分组，值=百分比，含总计）。
    - 修复了绘图时的 `KeyError: '提及率'` 错误，确保所有题型（单选、评分、矩阵）都能正确调用 `行百分比` 或 `提及率` 进行绘图。

- **交互体验升级**:
  - **题型微调**: 将 `st.data_editor` 封装在 `st.form` 中，实现了批量修改题型后一次性提交，解决了“修改即刷新”导致的页面跳动问题。
  - **摘要生成修复**: 修复了“生成量化统计摘要”时的 `KeyError: '提及率'` 报错，确保所有题型均可正常生成文本摘要。

- **Excel 导出格式对齐 (v1.3)**:
  - 重构导出逻辑，废弃了“一题一Sheet”的模式。
  - 实现了“单 Sheet 聚合导出”，所有题目的交叉分析结果均写入同一个 `交叉分析结果` Sheet 中，按顺序纵向排列，与 v1.3 版本完全一致。

- **Quant Engine 2.0 升级 (对齐 v1.3 核心能力)**:
  - **核心自动化 (Phase 1)**:
    - 移植了 `v1.3` 的统计引擎（包括卡方、Fisher、ANOVA、Tukey HSD 等）。
    - 实现了“一键全自动分析”，点击开始后自动为所有题目运行显著性检验。
  - **报表增强 (Phase 2)**:
    - 升级 Excel 导出，自动在结果表中追加 `P值`（含星号标记）、`效应量` 和 `检验方法` 列。
    - 多选题支持展示每个选项的独立检验结果。
  - **界面紧凑化 (Phase 3)**:
    - 引入 `st.expander` 和 `st.columns` 布局，实现“配置面板”折叠与分栏显示，提升信息密度和操作流畅度。
  - **可视化增强 (Phase 4)**:
    - **方向箭头标记**: 实现了基于标准化残差 (Standardized Residuals) 的事后检验逻辑。当 P<0.05 时，若某选项显著高于期望值则标记 `▲`，显著低于则标记 `▼`，直接追加在百分比数据旁。
    - **条件格式 (Color Scale)**: 利用 `xlsxwriter` 为 Excel 导出表中的“效应量”列添加了 **白->绿** 的三色阶条件格式，效应量越大背景越绿，视觉上快速聚焦重点。

- **工具集架构整顿 (Launcher Integration)**:
  - **Launcher 升级**: 更新 `web_tools_launcher.py`，将 `game_analyst.py` 正式注册为 **“游研专家：全链路归因分析 (Flagship)”**，排位提升至核心分析引擎第 3 位。
  - **文档同步**: 同步更新 `README.md`，确立了以 `game_analyst.py` 为旗舰工具的工具体系（当前版本已统一为“五剑客”），并将其从“历史备份”列表中移除，纠正了此前的分类错误。
  - **角色定义**: 明确了 `game_analyst.py` 与 `satisfaction_engine.py` 的差异：前者侧重全链路深度归因，后者侧重快速标准化分析。

- **游研专家 (Flagship) 深度优化**:
  - **稳健性修复**: 移除了 `FactorAnalyzer` 调用中的高风险 `sklearn` 补丁，改为异常捕获与版本兼容提示，防止环境崩溃。
  - **统计严谨性**: 在多元回归分析前增加了 **“缺失率预警”**，若特征缺失 >10%，警示用户避免均值填充带来的偏差。
  - **性能升级**: 引入 `MiniBatchKMeans`，当样本量 >5000 时自动切换为小批量聚类算法，大幅提升大样本处理速度。

- **Quant Engine (v1) 逻辑修正**:
  - **多选题分母修正**: 修复了多选题（及题组）在计算提及率和进行统计检验时，错误使用总样本量作为分母的问题。
  - **跳题逻辑适配**: 现在分母会自动过滤掉该题全为 NaN（即未作答/跳过）的样本，仅统计“有效参与人数”，确保选择率计算准确。

### 2. 待办事项与已知问题 (Future Roadmap)
- [ ] **多选题详细检验展示**: 虽然数据已计算，但在 Excel 导出中多选题的 P 值展示逻辑仍有优化空间（目前可能仅展示最显著项或需展开）。
- [ ] **自定义分群**: Web 版尚未移植 v1.3 的“自定义分群”弹窗功能，目前只能基于现有列进行分组。

### 3. 其他工具的 Excel 读取优化
**涉及文件**: `survey_tools/web/satisfaction_app.py`, `问卷文本分析工具 v1.py`, `聚类.py`, `问卷数表分析工具 v1.3.py`

- 全面检查并升级了上述工具的 Excel 读取模块。
- **Tkinter 工具**: 为桌面版工具（如 `聚类.py`）添加了弹窗 (`ask_sheet_gui`) 以支持 Sheet 选择。
- **Streamlit 工具**: 为 Web 版工具统一添加了侧边栏或主界面的 Sheet 选择组件。

---

## 📅 2026-03-18（第二轮：全盘 Review 修复 ×27 个 Bug）

### 背景
对项目做全盘 review，产出 `REVIEW_2026-03-18.md`（位于 UserResearch/ 根目录），识别出 9 个高风险 Bug、12 个中风险问题、3 个质量矩阵假阳性、14 个低优先级可维护性问题，并在同一轮对话内全部执行修复。

---

### 高风险 Bug 修复

**H1 · quant_app.py — 多选组间检验传参类型错误**
- `run_group_difference_test(..., col, "多选")` 传字符串，进入"多选"分支必然 `isinstance` 检查失败直接返回空结果。
- 修复：改为 `"单选"` 类型（列已被预处理为"提及"/"未提及"二分），使检验逻辑正常执行。

**H2 · quant.py — 排序题 Top1/Top2 率分母×n_排序位置**
- 分母取 `long_df["label"].value_counts()`，长格式每人贡献 `n_rank_positions` 行，分母被放大，Top1/Top2 率系统性偏低。
- 修复：分母改为 `df.groupby(label_col).size()`（原始受访者人数）。

**H3 · quant_app.py — pivot_v13_style 的 P值/效应量/箭头是死代码**
- `stats_res = getattr(df_long, "_stats", None)` 从未有人设过 `_stats` 属性，永远为 `None`，P值/效应量列永久缺失。
- 修复：定量引擎（现为 `run_quant_cross_engine`，兼容 `run_v13_like_cross`）为每条结果注入 `"stats": run_group_difference_test(...)`；`pivot_v13_style` 增加 `stats_res=None` 参数，调用方传入 `res.get("stats")`。

**H4 · quant_app.py — 排序题导出按钮嵌套在父 button 内**
- "导出结论表"嵌套在 `if st.button("生成深度洞察报告"):` 内，点击导出后 rerun 父 button 不再为 True，导出逻辑未执行，按钮消失。
- 修复：计算结果写入 `session_state["ranking_result_cache"]`，展示/导出/下载均从 session_state 读取，脱离父 button 依赖。

**H5 · io.py — apply_sav_labels 新标签与已有列名碰撞**
- 去重逻辑只在"有标签的列之间"查重，不检查新标签是否与未标记列名重名，碰撞后产生重复列。
- 修复：用 `used_names` 集合初始化为所有未被重命名的列名，后续所有标签均在此集合中去重。

**H6 · io.py — 传入 pd.ExcelFile 必然 ValueError**
- `pd.ExcelFile` 无 `.name` 属性，三个格式分支均跳过，直接 `raise ValueError`，多 Sheet Excel 100% 报错。
- 修复：在格式检测入口前补充 `isinstance(path_or_file, pd.ExcelFile)` 分支，直接调用 `pd.read_excel`。

**H7 · question_type.py — 0/1 多选列被误判为「评分」**
- 数值检测先于多选前缀检测，0/1 编码多选列满足"≤11 unique，范围[0,10]"被判为评分。
- 修复：将 `prefix in multi_prefixes` 检查提前到数值检测之前；并额外补充 `set({0.0, 1.0}).issubset(uniq)` 时归为单选。

**H8 · satisfaction_app.py — IPA 四象限标签在负相关时坐标倒置**
- 标签坐标用 `x_mean * 0.9 / 1.1`，当 `x/y_mean < 0` 时乘以系数方向反转，四个象限标签完全错置。
- 修复：改为基于数据范围的绝对偏移量 `_dx/_dy`，与均值正负无关。

**H9 · cluster_app.py — df_clean 与 df_for_clustering 行数不一致无校验**
- `perform_factor_analysis` 内部若有额外 dropna，输出行数可能少于 `df_clean`，后续 `perform_clustering` index 对齐失败。
- 修复：因子分析后比较行数，不一致时截断 `df_clean` 并给出 UI 警告。

---

### 中风险问题修复

- **M1** `quant_v13_engine.py`：矩阵 `option_order` 改为按列遍历顺序去重，不再用 `sorted()` 破坏问卷原始顺序。
- **M2** `quant_app.py`：同一 `q_num` 只允许进入一种矩阵类型，避免矩阵评分和矩阵单选重复分析。
- **M3** `quant_v13_engine.py`：单选分母改为 `group[q_col].notna().sum()`，排除跳题 NaN，使各选项百分比之和趋近 100%。
- **M4** `quant.py`：多选 `overall.p_value` 优先用 FDR 校正后最小值，与 `sig_count` 口径统一。
- **M5** `quant_app.py`：SAV 缓存键加入文件大小（`uploaded_file.size`），防止同名不同内容读旧数据。
- **M6** `quant_app.py`：文件切换后 multiselect 旧选项被静默清空时，显示信息提示。
- **M7** `satisfaction_app.py`：高缺失率警告后增加 radio 让用户选择「剔除缺失」或「均值填补」，不再无条件 fillna。
- **M8** `satisfaction_app.py`：`dropna()` 后增加最小样本量（10条）保护，样本不足时提前 return。
- **M9** `satisfaction_app.py`：聚类结果写回 `analyzer.data` 改用 `.reindex(analyzer.data.index)`，防止 index 错位。
- **M10** `satisfaction_app.py`：`cluster_option.split()[-1]` 用 try/except 保护，AI 命名后不会崩溃。
- **M11** `game_analyst.py`：`self.data = data.copy()`，防止外部赋值污染原始 df。
- **M12** `question_type.py`：`count_mentions` 中 `mask_valid` 计算改为 `~is_null & ~ser.str.lower().isin(...)`，消除 index 潜在错位。

---

### 质量矩阵假阳性修复

- **QA1** `verify_current_v1_logic.py` / `verify_p2_baseline.py` / `verify_p24_clustering.py`：找不到测试数据时改为 `sys.exit(1)`，质量矩阵不再显示虚假 PASS。
- **QA2** `test_migration.py`：`all_ok=False` 时补充 `sys.exit(1)` 及失败提示。
- **QA3** `auto_verify_v1.py`：
  - mock 数据扩大到 120 条并构造明显组间差异（G1/G2/G3 均值差异 2 分），保证统计显著。
  - 补充排序题用例（`process_ranking_data`），并验证 Top1率 ≤ 100%（H2 回归测试）。
  - pairwise 结构断言移除 `if p < 0.05` 保护，改为无条件检查（若 pairwise 存在）。

---

### 低优先级修复

- **L6** `io.py`：`export_xlsx` Sheet 名截断后用 `used_sheet_names` 集合去重，避免同名导致 openpyxl 报错。
- **L7** `io.py`：CSV `UnicodeDecodeError` 重试前补 `path_or_file.seek(0)`，防止文件指针在末尾导致重试读空。
- **L8** `cluster_app.py`：下载按钮标签从「Excel」改为如实标注「CSV」。
- **L9** `cluster_app.py`：AI 命名回调中裸 `except:` 改为 `except (ValueError, KeyError, TypeError):`。
- **L14** `run_quality_matrix.py`：`subprocess.run` 增加 `timeout=180`，防止脚本死循环挂起质量矩阵。

---

---

## Pipeline v0.3 — 输入输出质量提升（2026-03-19）

### 变更文件
- `scripts/run_playtest_pipeline.py`（完整重写至 v0.3）

### 新增功能

**F1 · 问卷大纲 .docx 导入**
- 新增 `_parse_outline_docx(path)` — 用 `zipfile + re` 解析 Word XML，提取每题的题号、题型、完整选项列表、矩阵子题目列表和跳题逻辑。支持"题目与题型标签跨行"（Word 手动换行）情况。
- 新增 `_get_latest_local_outline(folder)` — 自动发现 `data/raw/` 下最新 `.docx` 文件。
- 新增 `--outline` CLI 参数，可显式指定大纲文件路径；未指定时自动发现。
- 大纲修正题型识别：矩阵单选题 → 矩阵单选，矩阵文本题/填空题 → 忽略，多选题 → 多选。
- 注意：大纲里"单选题"类型不强制覆盖，保留数据驱动识别（避免 1-5 量表题被误标为单选导致回归失效）。

**F2 · 矩阵题子项自动分组**
- 新增 `_infer_matrix_groups(columns)` — 识别问卷星导出格式 `N.题干—子题目` 中的矩阵题列，返回「列名 → 所属矩阵 Q 题号」映射。正确处理后续无题号子项（如 Q16 的`空投事件`、`富集区事件` 等）。

**F3 · 矩阵题 2D 表输出**
- 新增 `_build_matrix_2d_table(group_results, scale_options)` — 将同一矩阵题所有子项合并为 2D 表：行=子题目，列=量表选项，格=`n(X.X%)`。
- 自动将数据整数值（1-5）映射到大纲量表标签（如 "1" → "非常不符合"）。
- 若量表选项含数字前缀（如"1分"），额外计算并输出均值列。

**F4 · 单选/评分题格式改善**
- `_simple_pivot` 新增 `option_list` 参数：
  - 将数据整数值映射到大纲文字标签（数字前缀匹配 + 位置匹配两种策略）。
  - 补全大纲中所有选项，未被选择的选项显示 `n=0, 0.0%` 而非缺失。
  - 按大纲顺序排列选项。
- 新增 `_build_question_block(res, option_list)` — 构建完整格式化 Block，含：
  - 题目标题行
  - 本题平均分行（仅数值选项题，如 1-5 分量表）
  - 透视数据行（选项 | 小计(n) | 总体% | ...）
  - 本题有效填写人次行

**F5 · 矩阵子项全量分析修复**
- 矩阵题子项（含无题号后续子项）加入 `explicit_single_cols`，确保全部参与交叉分析。
- 使用 `continue` 跳过 `question_types` 累积，防止 Q-numbered 第一子项被 question_specs 重复处理。
- `_export_results` 改用 `matrix_q_map` 判断矩阵组，而非依赖 `res["题型"]`（后者因 explicit_single_cols 路径返回"单选"）。

### 关键数字对比（本次跑测大纲数据集）
| 指标 | v0.2 无大纲 | v0.3 有大纲 |
|---|---|---|
| 题型统计 | 单选:86, 评分:19 | 矩阵单选:56, 评分:19, 单选:11, 忽略:19 |
| 交叉分析结果数 | 105 | 86（含全部矩阵子项）|
| 矩阵题 2D 表 | 无（各子项独立单选） | ✅ 有（行=子题，列=量表） |
| 0% 选项显示 | 缺失 | ✅ 补全 |
| 均值行 | 无 | ✅ 有（数值选项题）|
| 有效填写人次行 | 无 | ✅ 有 |

---

> **💡 提示**: 
> 每次进行重大代码修改或功能更新后，建议更新此文档。这样即使 IDE 的对话历史丢失，我们也能通过此文档追溯变更记录。
