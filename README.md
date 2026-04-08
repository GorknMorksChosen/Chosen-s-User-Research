# 问卷数表分析工具集 (Survey Analysis Toolkit)

> **当前版本：2026.03 P2-4（第四阶段）**
> 
> 本项目整合了问卷数据处理、统计建模与文本分析的核心工具，旨在提供一站式的问卷分析解决方案。
>
> **统一 Web 工具入口以 `UserResearch/tool_registry.py` 为唯一口径（当前注册 6 项，其 `entry` 字段即下文「Web 入口脚本」列）。** 历史文档中的旧称已统一替换为模块化命名。

### 项目定位与需求约定（可单独贴入需求文档）

本项目面向**日常工作用问卷数据分析**（结构化 + 非结构化），理想情况下覆盖 [腾讯问卷](https://wj.qq.com/)、[问卷星](https://www.wjx.cn/)、[SPSSAU](https://spssau.com/) 的统计与 AI 分析能力。

- **统计与 AI 功能可执行清单**：以 `UserResearch/wjxspss.docx`（《SPSSAU 问卷/量表数据分析方法与应用》）为参考整理，正文已提取为 **`UserResearch/docs/wjxspss_extracted.txt`** 保留供检索；可执行清单见 **`UserResearch/docs/功能可执行清单_参考wjxspss.md`**，涵盖：数据探索与格式、问卷数据清理、差异关系（t 检验/方差分析/卡方/非参数）、相关与回归（相关/线性回归/Logistic）、问卷专属（单选多选/信度效度/验证性因子/路径/结构方程/中介与调节）、聚类与文本分析等。
- **输入**：支持 `.csv`、`.sav`、`.xlsx`；格式以 `UserResearch/input_example` 下示例为准。
- **`.sav` 支持**：若实现 .sav 读取，须依赖 **pyreadstat**（或项目指定的同功能库），并在 **README 与依赖文件（如 requirements.txt）** 中注明。
- **导出 .xlsx**：默认每次分析生成**一个工作簿、多张 sheet**（如描述统计、交叉表、回归结果等）；并**允许用户勾选要导出的内容后再打包成多 sheet**。

### 文档与迭代可见性（前情提要 · 计划 · 完成情况）

**README 与 DEV_LOG 为本项目「前情提要、后续计划及完成情况」的入口**，对话重开或新人接手时优先阅读二者即可理解项目全貌。

- **前情提要**：见上文「项目定位与需求约定」、`.cursor/rules/project-standards.mdc`（技术栈、统计标准、数据处理基本原则、输入/输出约定）。
- **后续计划与完成情况**：见 **`UserResearch/docs/DEV_LOG.md`**（按日期记录的变更、修复、P0/P1/P2 执行状态）及本 README「版本优化与迭代计划」小节。

**需求 / 验收 / 计划类文档（均在 `UserResearch/` 下）与 README·DEV_LOG 的映射：**

| 文档 | 用途 |
|------|------|
| `UserResearch/docs/功能可执行清单_参考wjxspss.md` | 统计与 AI 功能可执行清单（参考 wjxspss），与需求约定对齐 |
| `UserResearch/docs/core_modules_wjxspss_mapping.md` | 清单六大类与核心模块的对应关系（已实现/部分实现/未实现） |
| `UserResearch/docs/core_modules_wjxspss_acceptance_matrix.md` | 可验收条目的逐条映射与验收方式、验收状态（待验收/通过/不通过） |
| `UserResearch/docs/task_list_wjxspss_mapping_acceptance.md` | 阶段 A/B/C 任务定义与执行记录（规则补充→对应表→映射验收） |
| `UserResearch/docs/下一步_to-do_项目主管.md` | 当前下一步 to-do（执行验收、问题清单、符合度检查、Backlog、P2 延续等） |
| `UserResearch/docs/验收问题清单_20260317.md` | 16 条验收执行后的问题记录（含质量矩阵 2 失败原因、人工验收不通过项填写说明） |
| `UserResearch/docs/需求与规则符合度检查_20260317.md` | 输入/.sav/导出约定与当前实现的符合度结论（符合/部分符合/不符合） |
| `UserResearch/docs/AI_Agent_人工验收上下文.md` | 供 AI agent（如 Open Claw）完成 18 条人工验收的上下文：项目与任务、工作目录与入口、测试数据、18 条检查点、需更新的文档、能力假设 |
| `UserResearch/docs/双机维护说明.md` | 在两台电脑间用 Git 同步、统一环境与工作目录的维护与迭代说明 |
| `UserResearch/tests/auto_verify_v1.py` | 核心 schema 自动化验收脚本（使用 test_assets 或 mock，断言 p_value/effect_size/assumption_checks） |
| `UserResearch/test_assets/` | 脱敏小样本（如 mock_survey.csv），供自动化验收与 CI/双机复现，不依赖 input_example |
| `UserResearch/docs/Backlog_短期优先级_20260317.md` | 短期可排期缺口清单（优先级 + 建议落点），由清单/对应表/需求约定汇总 |
| `UserResearch/docs/设计_sav变量与值标签可选应用.md` | .sav 变量/值标签可选应用的实现方案（io 层、各工具入口、默认策略、兼容 CSV/Excel），供 P1 排期与实现参考 |

新增或重要 .md 文档应在 README 或 DEV_LOG 中补充说明与映射，以保持「仅读 README + DEV_LOG 即可看懂前情与计划」的约定（见 `.cursor/rules/project-standards.mdc`）。

## 快速启动

### 方式一：统一启动菜单（推荐）
在 **`UserResearch/`** 下运行启动脚本，通过数字菜单选择工具（支持多选，如 `1,3,5` 一次性多开）：
```bash
cd UserResearch
python web_tools_launcher.py
```

### 方式二：单独启动指定工具（与 `tool_registry.py` 的 `entry` 一致）

在 **`UserResearch/`** 下直接指定脚本与端口（端口须与注册表一致，避免冲突），例如：

```bash
cd UserResearch
streamlit run survey_tools/web/quant_app.py --server.port 8501
```

根目录下的 `quant_analysis_engine.py`、`satisfaction_engine.py`、`聚类.py` 等为**薄包装**，内部调用 `survey_tools/web/*_app.py`，与上式等价；日常仍推荐 **`python web_tools_launcher.py`** 选择工具。

---

## 安全与本地访问（威胁模型简述）

- **Streamlit 默认无登录鉴权**：本仓库中的 Web 工具按本地分析场景设计，页面与上传数据**不对访客做身份校验**。仅在 `localhost` 本机访问时，风险主要限于本机用户与本地文件。
- **局域网 / 远程访问**：若将 Streamlit 绑定到 `0.0.0.0` 或经端口转发、内网穿透对外暴露，**等同把分析能力与数据暴露给能访问该端口的任何人**。请在防火墙与网络策略中显式评估，生产或敏感数据场景应另行加反向代理、VPN、认证或专用部署方案。
- **API Key 与 `.env`**：请勿将 `.env`、密钥或令牌提交到版本库；在团队规范中约定**不入库、不截图外传**；在共享或公用机器上，浏览器 Session 可能残留，**登出/清除站点数据**无法替代「不在共享环境长期存放密钥」的治理。

---

## 核心工具体系（当前唯一有效口径）

经过架构重构，**Web 入口脚本**以 `UserResearch/tool_registry.py` 中各工具的 **`entry`** 字段为准（下表与之对齐）。根目录部分 `*_engine.py` / `聚类.py` 仅为兼容旧习惯的薄包装。

| 序号 | 工具名称 | Web 入口脚本（`entry`） | 定位 |
| :--- | :--- | :--- | :--- |
| 1 | 问卷定量交叉分析 (Quant Engine) | `survey_tools/web/quant_app.py` | 高频交叉分析与显著性检验 |
| 2 | 满意度与体验建模 (Standard) | `survey_tools/web/satisfaction_app.py` | IPA + 回归驱动的标准诊断 |
| 3 | 全链路归因分析 (Advanced) | `game_analyst.py` | 因子/分群/路径/非线性归因 |
| 4 | 玩家分群分析 (Advanced) | `survey_tools/web/cluster_app.py` | 多算法分群 + 推荐策略 + 可视化画像 |
| 5 | 问卷文本分析引擎 (Text Engine) | `问卷文本分析工具 v1.py` | 开放题语义分析与结构化导出 |
| 6 | 一键 Playtest 流水线 | `survey_tools/web/pipeline_app.py` | 题型识别、交叉、满意度建模与报告导出 |

> **2026-04-02**：启动菜单 **2**（满意度与体验建模）与 **3**（全链路归因）均已支持左侧边栏 **「一键整合导出」**，将已计算的数据表汇总为**单个多 Sheet Excel**（图表仍在页面查看）。二者定位差异与使用建议见 **`UserResearch/README.md`**（「工具 2 与工具 3」对照表及模块二、三说明）。

### 模块一：问卷定量交叉分析 (Quant Engine)
*   **入口脚本**：`survey_tools/web/quant_app.py`（根目录 `quant_analysis_engine.py` 为薄包装，等价）
*   **核心功能**：
    *   **自动交叉制表**：智能识别单选、多选、评分、矩阵等题型，生成带显著性差异检验的标准报表。
    *   **题型识别**：自动解析题干中的 `【单选】`、`[多选]` 等标记，并支持人工微调。
    *   **统计检验**：内置卡方检验、Fisher 精确检验、ANOVA、Kruskal-Wallis、Tukey HSD 等算法。
    *   **可视化增强**：生成堆叠条形图，并在报表中通过箭头 (`▲/▼`) 和色阶展示显著性差异。
    *   **容错机制**：自动屏蔽 `Type_` 等无关列，且在选错题目时自动跳过并提示，防止程序崩溃。
*   **适用场景**：日常问卷基础数据处理、快速生成带统计检验的 Cross-tab 报表。
*   **[NEW | 2026-04-08]** 导出题型标注与题型微调对齐：在 Quant 中手动调整题型后，即使未重新点击「开始交叉分析」，导出 Excel 标题也按当前题型表同步（单选/评分/NPS 保守覆盖），主下载与简易透视导出口径一致。详见 `UserResearch/docs/DEV_LOG.md`。

### 模块二：满意度与体验建模 (Standard)
*   **入口脚本**：`survey_tools/web/satisfaction_app.py`（根目录 `satisfaction_engine.py` 为薄包装，等价）
*   **核心功能**：
    1.  **基础洞察 (IPA)**：基于满意度表现与重要性（相关系数）的四象限分析，快速识别拖累项。
    2.  **核心诊断 (Regression)**：自动化多元回归分析，包含信度检验、VIF 共线性诊断及改进优先级排序。
*   **适用场景**：快速驱动力分析、基础归因诊断。

### 模块三：全链路归因分析 (Advanced) **[NEW]**
*   **入口脚本**：`game_analyst.py`
*   **定位**：面向深度游戏体验研究的全链路分析工具。
*   **核心模块**：
    *   **数据体检**：自动检测直线勾选、作答过快、离群值等异常样本。
    *   **因子与聚类**：内置因子分析降维与 K-Means 玩家分群。
    *   **路径分析 (SEM)**：支持构建复杂的结构方程模型，验证多层级因果假设。
    *   **Kano 与 SHAP**：集成非线性特征重要性分析。
*   **适用场景**：复杂的游戏体验模型构建、精细化玩家分群研究、学术级归因分析。

### 模块四：玩家分群分析 (Advanced) **[NEW]**
*   **入口脚本**：`survey_tools/web/cluster_app.py`（根目录 `聚类.py` 为薄包装，等价）
*   **核心功能**：
    *   **数据清洗**：自动检测跳题导致的缺失值，支持“剔除 / 均值填充 / 中位数填充”策略切换。
    *   **降维分析**：内置因子分析 (Factor Analysis) 提取潜在维度，提升聚类稳定性。
    *   **K 值选择**：并排展示手肘法 (Elbow) 与轮廓系数 (Silhouette)，辅助决策最佳 K 值。
    *   **算法推荐**：支持“算法推荐”“K+算法联合推荐”，并可一键采用。
    *   **推荐模板**：支持 `balanced / stability_first / discrimination_first` 三种推荐模板。
    *   **综合可视化面板**：PCA 散点图、人群画像雷达图、特征热力图一站式呈现。
    *   **AI 辅助命名**：接入 LLM 自动生成人群画像名称。
*   **适用场景**：精细化用户分群、Persona 构建、潜在特征挖掘。

### 模块五：问卷文本分析引擎 (Text Engine)
*   **入口脚本**：`问卷文本分析工具 v1.py`
*   **核心功能**：
    *   调用 LLM (OpenAI/LangChain) 对开放式文本进行语义理解。
    *   支持关键词提取、情感倾向分析、自动化编码。
    *   **[NEW]** 支持 Excel 多 Sheet 选择，不再局限于读取第一个 Sheet。
    *   **[NEW]** 支持请求重试与指数退避、失败批次重放及调用统计，提升限流/抖动场景稳定性。
    *   **[NEW]** 导出链路改为流式写入并采用“准备导出→下载”模式，降低大样本导出内存峰值。
*   **适用场景**：处理大量开放式问卷文本，挖掘非结构化数据中的洞察。

### 模块六：一键 Playtest 流水线
*   **入口脚本**：`survey_tools/web/pipeline_app.py`
*   **说明**：与统一启动菜单第 6 项一致；CLI 入口见 `tool_registry.py` 中 `cli` 字段（`scripts/run_playtest_pipeline.py`）。详细行为与参数说明见 **`UserResearch/docs/PLAYTEST_PIPELINE.md`**。

---

## 桌面端辅助工具

除了 Web 版工具外，项目还保留了部分基于 Tkinter 的本地 GUI 工具（已升级支持多 Sheet 选择）：

| 工具名称 | 脚本文件 | 功能简介 |
| :--- | :--- | :--- |
| **问卷数表工作台** | `UserResearch/archive/问卷数表分析工具 v1.3.py` | 旧版 Tkinter GUI（已归档；日常请用 Web 版 Quant）。 |

---

## 项目架构说明

本次重构引入了模块化设计，核心代码位于 `survey_tools/` 包中：

```text
问卷数表/
├── README.md                         # 本文件（仓库总览）
└── UserResearch/                     # 日常工作目录（cd 到此再运行工具）
    ├── survey_tools/                 # [核心包] core / utils / web
    ├── docs/                         # DEV_LOG、Playtest 流水线说明（PLAYTEST_PIPELINE.md）等
    ├── tests/                        # run_quality_matrix、verify_*
    ├── archive/                      # 已替代的历史脚本与实验脚本
    ├── scripts/                      # CLI（run_playtest_pipeline 说明见 docs/PLAYTEST_PIPELINE.md）
    ├── tool_registry.py              # Web 工具元数据（entry / port，与 README 口径一致）
    ├── web_tools_launcher.py         # 统一启动菜单（读取 tool_registry）
    └── … 根目录薄包装与 Streamlit 入口（以 tool_registry 为准）
```

---

## 版本优化与迭代计划（2026-03-13）

基于本轮对五大核心工具的逐项复审，版本优化优先级已统一为：
**统计正确性 > 兼容性稳定 > 缺失值策略 > 安全与稳健性 > 性能扩展**。

### P0：立即修复（1-2 个迭代）
- **Quant 统计正确性收敛**：
  - 修复 `survey_tools/core/quant.py` 中多选检验分支可达性与返回结构一致性问题。
  - 校准“统计计算结果 / 导出表格 / 页面展示”三者一致，避免同题多口径。
- **兼容性策略统一**：
  - 收敛 `FactorAnalyzer + scikit-learn` 兼容处理为单一方案，减少多处补丁并行维护。
- **异常返回协议标准化**：
  - 统一核心统计函数在空样本、小样本、异常输入下的返回结构，降低静默失败概率。

### P1：短期优化（2-4 个迭代）
- **缺失值策略升级**：
  - 将当前以均值填充为主的流程升级为策略化配置（如剔除/均值/中位数/分组插补），并补充风险提示。
- **文本引擎稳健性增强**：
  - 增加请求重试与退避机制、批次失败重放能力，提升大批量分析稳定性。
- **导出链路内存优化**：
  - 优化大样本 Excel/结果拼接链路，降低一次性构建大表带来的内存峰值。

### P2：中期演进（季度级）
- **分析管线统一化**：
  - 继续收敛 `web` 与 `core` 双轨重复实现，形成更清晰的模块边界。
- **质量保障体系补齐**：
  - 建立最小可用测试矩阵（统计回归、兼容性、导出一致性）并推进依赖版本锁定。
- **分群能力扩展**：
  - 在保持 KMeans 主链路稳定前提下，逐步扩展多算法与稳定性评估能力。

### 当前执行状态（2026-03-13）
- **P0 已完成**：
  - Quant 多选检验分支可达性与结果映射一致性修复完成。
  - `FactorAnalyzer + scikit-learn` 兼容策略已统一为单一方案（`survey_tools/core/factor_compat.py`）。
  - 核心统计函数异常返回协议已标准化（空样本/小样本/异常输入）。
- **P1 已完成**：
  - 缺失值策略已配置化落地（drop / mean / median / group_mean / group_median），并同步到标准版与高级版回归链路。
  - 文本引擎已支持重试退避、失败批次重放、调用统计可观测输出。
  - 文本引擎导出链路已做内存优化（流式写入 + 准备导出缓存机制）。
- **当前阶段**：进入 **P2 中期演进**（分析管线统一化 / 测试矩阵与依赖锁定 / 分群能力扩展）。
- **P2-2 进展**：
  - 已新增统一质量矩阵入口 `UserResearch/tests/run_quality_matrix.py`，串联统计迁移、v1 逻辑与 P2 基线验证三类脚本扩展。
  - `verify_current_v1_logic.py` 已支持根目录与 `example/` 双路径样本回退，减少环境路径耦合。
- **P2-3 进展**：
  - 已新增依赖锁定文件 `requirements.lock.txt` 与兼容区间版 `requirements.txt`。
  - 已新增依赖矩阵校验脚本 `UserResearch/tests/verify_dependency_matrix.py` 与文档 `UserResearch/docs/DEPENDENCY_MATRIX.md`。
- **P2-4 进展**：
  - 分群核心已支持 `kmeans / gmm / agglomerative` 多算法执行，并输出稳定性指标（Silhouette / Calinski-Harabasz / Davies-Bouldin）。
  - 分群 Web 端已支持多算法评估表与算法切换执行，默认仍为 KMeans。
  - 已新增算法推荐规则与“一键采用推荐算法”交互，支持在业务侧快速落地推荐方案。
  - 已新增 K+算法联合推荐与“一键采用推荐K+算法”能力，支持自动生成分群配置并快速应用。
  - 已新增推荐模板（`balanced / stability_first / discrimination_first`），支持按业务目标切换推荐口径。
  - 已新增 `verify_p24_clustering.py`，覆盖 `example/` 新增样本的分群验证。
- **2026-03-30 热修复（Pipeline + Text Engine 输入对齐）**：
  - **Playtest Pipeline（分组列防误判）**：自动分组识别时不再从题目列中挑选分组字段；Web 端新增「总体（不分组）」显式选项，且当用户误选题目列为分组列时自动回退总体并提示。
  - **Playtest Pipeline（问卷星多选列兼容）**：修复 `31(子项)` 等列名题号提取失败导致的“同题多选子列被拆成单选”问题；新增同题混合题型运行时告警（重点提示“多选+单选”高风险）。
  - **Playtest 导出选项文案清洗**：修复多选导出中 `5 (选项...)` 这类题号前缀残留，统一输出纯选项文本。
  - **文本分析工具（输入体验对齐）**：接入问卷大纲解析（问卷星/腾讯）与统一题型识别；新增「按题选择（同题多列自动归并）」与题型标签化选择器，使多选题在输入层按“题”而非“子列”呈现。

### 当前重点风险（已从“修复项”切换为“演进项”）
- `web` 与 `core` 仍存在双轨重复实现，维护成本较高。
- 自动化回归覆盖面已显著扩展，仍需逐步补齐更多业务边界场景。
- 依赖版本尚未系统锁定，跨环境仍有潜在漂移风险。
- 分群算法已支持模板化推荐，后续需补充模板治理与版本化策略。

### 全量代码审阅与修复 (2026-03-17)
- 对 README 中五大核心工具及其依赖的 core/web 模块进行了逐行审阅，产出 **`UserResearch/docs/CODE_REVIEW_DEBUG_REPORT.md`**（运行 Bug、逻辑断层、兼容性、健壮性等分类汇总）。
- **已落地修复**：排序题导出下载按钮（Quant）、全链路归因工具换文件仍用旧数据、IPA 空表报错与缺失策略回退未清空分组列（满意度应用）、CSV 编码回退（满意度应用与文本工具）、聚类推荐 K 类型安全转换、弃用 API `st.experimental_rerun()` → `st.rerun()`。
- 详细问题列表与未改动的建议（如双份 GameExperienceAnalyzer 收口）见 `UserResearch/docs/CODE_REVIEW_DEBUG_REPORT.md`；变更记录见 `UserResearch/docs/DEV_LOG.md`。

> 说明：详细复审背景与每项风险依据已同步记录于 `UserResearch/docs/DEV_LOG.md`，用于后续版本实现追踪。

---

## 历史脚本与兼容性说明

以下脚本已被合并至 `satisfaction_engine.py`，仅作为**历史备份**保留，**不再建议直接使用**：

*   `UserResearch/archive/multi_regression_v1.1.py`（历史备份；已并入满意度建模“核心诊断”模块）
*   `relation_analysis.py`（已并入满意度建模“基础洞察”模块）
*   `app_satisfaction_driver.py`（旧版尝试，已废弃）

---

## 工程维护 / 审阅

建议在日常改动后运行以下命令做最小回归：

```bash
cd UserResearch
python tests/run_quality_matrix.py
```

该入口默认串联 `tests/` 下各脚本（依赖矩阵、迁移对比、v1 逻辑、`auto_verify_v1`、回归/聚类/IO 子项、`verify_p2_baseline`、`verify_p24_clustering` 等）。

全量代码审阅结论与潜在问题清单见 **`UserResearch/docs/CODE_REVIEW_DEBUG_REPORT.md`**（2026-03-17 审阅产出）。

---

### example 全链路审阅导出（P2-4）

使用 `example/` 全量样本执行项目级审阅并导出结果：

```bash
cd UserResearch
python tests/run_example_full_review.py
```

默认输出目录：
- `review_outputs/<时间戳>/logs`：质量矩阵与子脚本日志
- `review_outputs/<时间戳>/text_exports`：文本引擎导出工作簿
- `review_outputs/<时间戳>/cluster_exports`：分群评估、推荐与分群结果
- `review_outputs/<时间戳>/regression_exports`：回归分析结果与摘要
- `review_outputs/<时间戳>/summary`：全样本审阅汇总

版本管理说明：
- `UserResearch/docs/PROJECT_CODE_REVIEW.md` 为项目级审阅主文档，纳入版本管理并随阶段里程碑同步更新。

---

## 依赖锁定与兼容矩阵（P2-3）

推荐在可复现环境中使用锁定版本安装：

```bash
cd UserResearch
pip install -r requirements.lock.txt
```

安装后运行依赖矩阵校验：

```bash
cd UserResearch
python tests/verify_dependency_matrix.py
```

矩阵详情见 `UserResearch/docs/DEPENDENCY_MATRIX.md`。

---

## 依赖安装

请确保已安装 `UserResearch/requirements.txt` 中的依赖库：

```bash
cd UserResearch
pip install -r requirements.txt
```

若需支持 **.sav（SPSS）** 数据读取，须依赖 **pyreadstat**，已在 `UserResearch/requirements.txt` 及 README「项目定位与需求约定」中注明。
