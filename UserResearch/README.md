# 问卷数表分析工具集 (Survey Analysis Toolkit)

> **当前版本：2026.03 P2-4（第四阶段）**
> 
> 本项目整合了问卷数据处理、统计建模与文本分析的核心工具，旨在提供一站式的问卷分析解决方案。
>
> **当前核心工具模块总数 = 5**。历史文档中的旧称已统一替换为模块化命名。

## 环境准备

首次使用或将项目发给他人时，按以下步骤完成环境初始化：

**1. 创建并激活虚拟环境**
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

**2. 安装依赖**
```bash
pip install -r requirements.txt
```

**3. 配置环境变量（可选，仅在需要 AI 功能时）**

复制模板并填入真实 API Key：
```bash
copy .env.example .env   # Windows
cp .env.example .env     # macOS / Linux
```
然后编辑 `.env`，将 `OPENAI_API_KEY=sk-...` 替换为真实值。若不使用 AI 命名等功能，可跳过此步。

> 提示：`.env` 文件不应提交到版本控制，模板 `.env.example` 已列出所有可配置项。

---

## 快速启动

### 方式一：统一启动菜单（推荐）
直接运行根目录下的启动脚本，通过数字菜单选择工具（支持多选，如 `1,3,5` 一次性多开）：
```bash
python web_tools_launcher.py
```

### 方式二：单独启动指定工具
```bash
streamlit run satisfaction_engine.py
```

---

## 核心工具体系（当前唯一有效口径）

经过架构重构，当前项目统一为五大核心引擎：

| 序号 | 工具名称 | 入口脚本 | 定位 |
| :--- | :--- | :--- | :--- |
| 1 | 问卷定量交叉分析 (Quant Engine) | `quant_analysis_engine.py` | 高频交叉分析与显著性检验 |
| 2 | 满意度与体验建模 (Standard) | `satisfaction_engine.py` | IPA + 回归驱动的标准诊断 |
| 3 | 全链路归因分析 (Advanced) | `game_analyst.py` | 因子/分群/路径/非线性归因 |
| 4 | 玩家分群分析 (Advanced) | `聚类.py` | 多算法分群 + 推荐策略 + 可视化画像 |
| 5 | 问卷文本分析引擎 (Text Engine) | `问卷文本分析工具 v1.py` | 开放题语义分析与结构化导出 |

### 模块一：问卷定量交叉分析 (Quant Engine)
*   **入口脚本**：`quant_analysis_engine.py`
*   **核心功能**：
    *   **自动交叉制表**：智能识别单选、多选、评分、矩阵等题型，生成带显著性差异检验的标准报表。
    *   **题型识别**：自动解析题干中的 `【单选】`、`[多选]` 等标记，并支持人工微调。
    *   **📈 统计检验全家桶**：内置卡方检验、Fisher 精确检验、ANOVA、Kruskal-Wallis、Tukey HSD 等算法。
    *   **可视化增强**：生成堆叠条形图，并在报表中通过箭头 (`▲/▼`) 和色阶展示显著性差异。
    *   **容错机制**：自动屏蔽 `Type_` 等无关列，且在选错题目时自动跳过并提示，防止程序崩溃。
*   **适用场景**：日常问卷基础数据处理、快速生成带统计检验的 Cross-tab 报表。
*   **近期关键修复（2026-03-18 第一轮）**：忽略列在新增组合分组列后保持不被重置；`.sav` 应用变量标签导致单选/评分不含 Q 题号时仍能按 UI 勾选列统计；生成组合分组列后核心分组不再回退 `None`；结果按题号 Q1/Q2/Q3… 排序。
*   **全盘 Review 修复（2026-03-18 第二轮）**：对全项目做系统性 review，产出 `docs/REVIEW_2026-03-18.md`（含 9 高风险/12 中风险/14 低优先级条目），并在同轮全部修复。核心修复包括：排序题 Top1/Top2 率分母错误、P 值/效应量列死代码激活、0/1 多选列误判评分、IPA 四象限标签负值倒置、ExcelFile 对象传入必然崩溃、SAV 标签列名碰撞、聚类行数对齐校验；质量矩阵三个脚本假阳性修复；共 27 处修改，`tests/auto_verify_v1.py` 全部断言通过。详见 `docs/DEV_LOG.md` 和 `docs/REVIEW_2026-03-18.md`。
*   **可选问卷大纲（2026-03-20）**：Web 定量页（`survey_tools/web/quant_app.py`）支持上传 `.docx` / `.txt` 大纲；**「大纲来源」** 下拉选择「问卷星」或「腾讯问卷」决定解析规则（与扩展名解耦）。成功解析后覆盖题型识别；不上传则仍为题干关键词自动识别 + 题型微调。解析实现与 Pipeline 共用 `survey_tools/utils/outline_parser.py`，详见 `docs/DEV_LOG.md`。

### 模块二：满意度与体验建模 (Standard)
*   **入口脚本**：`satisfaction_engine.py`
*   **核心功能**：
    1.  **基础洞察 (IPA)**：基于满意度表现与重要性（相关系数）的四象限分析，快速识别拖累项。
    2.  **核心诊断 (Regression)**：自动化多元回归分析，包含信度检验、VIF 共线性诊断及改进优先级排序。
*   **适用场景**：快速驱动力分析、基础归因诊断。

### 模块三：全链路归因分析 (Advanced) **[NEW]**
*   **入口脚本**：`game_analyst.py`
*   **定位**：新一代旗舰级分析工具，专为深度游戏体验研究打造。
*   **核心模块**：
    *   **数据体检**：自动检测直线勾选、作答过快、离群值等异常样本。
    *   **因子与聚类**：内置因子分析降维与 K-Means 玩家分群。
    *   **路径分析 (SEM)**：支持构建复杂的结构方程模型，验证多层级因果假设。
    *   **Kano 与 SHAP**：集成非线性特征重要性分析。
*   **适用场景**：复杂的游戏体验模型构建、精细化玩家分群研究、学术级归因分析。

### 模块四：玩家分群分析 (Advanced) **[NEW]**
*   **入口脚本**：`聚类.py` (调用 `survey_tools.web.cluster_app`)
*   **核心功能**：
    *   **数据清洗**：自动检测跳题导致的缺失值，支持“剔除 / 均值填充 / 中位数填充”策略切换。
    *   **因子降维**：内置因子分析 (Factor Analysis) 提取潜在维度，提升聚类稳定性。
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

---

## 🖥️ 桌面端辅助工具

除了 Web 版工具外，项目还保留了部分基于 Tkinter 的本地 GUI 工具（已升级支持多 Sheet 选择）：

| 工具名称 | 脚本文件 | 功能简介 |
| :--- | :--- | :--- |
| **问卷数表工作台** | `archive/问卷数表分析工具 v1.3.py` | 旧版 Tkinter GUI（已归档；日常请优先使用 Web 版 Quant Engine / `survey_tools/web/quant_app.py`）。 |

---

## 📂 项目架构说明

本次重构引入了模块化设计，核心代码位于 `survey_tools/` 包中：

```text
UserResearch/  （工作目录）
├── survey_tools/                    # [核心包]
│   ├── core/                        # 核心算法层
│   │   ├── quant.py                 # 定量统计核心
│   │   ├── advanced_modeling.py     # 回归/因子/聚类/路径
│   │   ├── clustering.py            # 分群多算法与推荐策略
│   │   └── ...
│   ├── utils/                       # 通用工具
│   │   ├── io.py                    # 读表 / 导出 / 本地最新数据
│   │   ├── outline_parser.py        # 问卷大纲解析（问卷星/腾讯；Pipeline 与 Web Quant 共用）
│   │   └── ...
│   └── web/                         # Web 应用层
│       ├── quant_app.py
│       ├── satisfaction_app.py
│       ├── cluster_app.py
│       └── ...
├── docs/                            # 设计说明、DEV_LOG、Playtest 流水线说明等
├── tests/                           # 质量矩阵与 verify_* 回归脚本
├── archive/                         # 已替代的历史脚本与一次性实验脚本
├── scripts/
│   └── run_playtest_pipeline.py     # [CLI] Playtest 自动化分析流水线（可选 --outline，大纲解析同上）
├── quant_analysis_engine.py           # [入口] Quant Engine
├── satisfaction_engine.py             # [入口] Standard
├── game_analyst.py                  # [入口] Flagship 归因
├── 聚类.py                           # [入口] Flagship 分群
├── 问卷文本分析工具 v1.py             # [入口] Text Engine
├── web_tools_launcher.py            # [入口] 统一控制台启动菜单
└── tool_registry.py                 # 工具元数据（启动菜单读取）
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
  - 缺失值策略已配置化落地（drop / mean / median / group_mean / group_median），并同步到标准版与旗舰版回归链路。
  - 文本引擎已支持重试退避、失败批次重放、调用统计可观测输出。
  - 文本引擎导出链路已做内存优化（流式写入 + 准备导出缓存机制）。
- **当前阶段**：进入 **P2 中期演进**（分析管线统一化 / 测试矩阵与依赖锁定 / 分群能力扩展）。
- **P2-2 进展**：
  - 已新增统一质量矩阵入口 `tests/run_quality_matrix.py`，串联统计迁移、v1 逻辑与 P2 基线验证三类脚本。
  - `tests/verify_current_v1_logic.py` 已支持根目录 / `example/` / `test_assets/mock_survey.csv` 样本回退，减少环境路径耦合。
- **P2-3 进展**：
  - 已新增依赖锁定文件 `requirements.lock.txt` 与兼容区间版 `requirements.txt`。
  - 已新增依赖矩阵校验脚本 `tests/verify_dependency_matrix.py` 与文档 `docs/DEPENDENCY_MATRIX.md`。
- **P2-4 进展**：
  - 分群核心已支持 `kmeans / gmm / agglomerative` 多算法执行，并输出稳定性指标（Silhouette / Calinski-Harabasz / Davies-Bouldin）。
  - 分群 Web 端已支持多算法评估表与算法切换执行，默认仍为 KMeans。
  - 已新增算法推荐规则与“一键采用推荐算法”交互，支持在业务侧快速落地推荐方案。
  - 已新增 K+算法联合推荐与“一键采用推荐K+算法”能力，支持自动生成分群配置并快速应用。
  - 已新增推荐模板（`balanced / stability_first / discrimination_first`），支持按业务目标切换推荐口径。
  - 已新增 `tests/verify_p24_clustering.py`，覆盖 `example/` 新增样本的分群验证。

### 当前重点风险（已从“修复项”切换为“演进项”）
- `web` 与 `core` 仍存在双轨重复实现，维护成本较高。
- 自动化回归覆盖面已显著扩展，仍需逐步补齐更多业务边界场景。
- 依赖版本尚未系统锁定，跨环境仍有潜在漂移风险。
- 分群算法已支持模板化推荐，后续需补充模板治理与版本化策略。

### 全量代码审阅与修复 (2026-03-17)
- 对 README 中五大核心工具及其依赖的 core/web 模块进行了逐行审阅，产出 **`docs/CODE_REVIEW_DEBUG_REPORT.md`**（运行 Bug、逻辑断层、兼容性、健壮性等分类汇总）。
- **已落地修复**：排序题导出下载按钮（Quant）、游研专家换文件仍用旧数据、IPA 空表报错与缺失策略回退未清空分组列（满意度应用）、CSV 编码回退（满意度应用与文本工具）、聚类推荐 K 类型安全转换、弃用 API `st.experimental_rerun()` → `st.rerun()`。
- 详细问题列表与未改动的建议（如双份 GameExperienceAnalyzer 收口）见 `docs/CODE_REVIEW_DEBUG_REPORT.md`；变更记录见 `docs/DEV_LOG.md`。

> 说明：详细复审背景与每项风险依据已同步记录于 `docs/DEV_LOG.md`，用于后续版本实现追踪。

---

## ⚠️ 历史脚本与兼容性说明

以下脚本已被合并至 `satisfaction_engine.py`，仅作为**历史备份**保留，**不再建议直接使用**：

*   🚫 `archive/multi_regression_v1.1.py`（历史备份；已并入超级应用“核心诊断”模块）
*   🚫 `relation_analysis.py`（已并入超级应用“基础洞察”模块）
*   🚫 `app_satisfaction_driver.py`（旧版尝试，已废弃）

---

## 🧰 工程维护 / 审阅

设计/方案文档（排期与实现）：`docs/设计_问卷星表头规范化.md`、`docs/设计_sav变量与值标签可选应用.md`；任务优先级见 `docs/Backlog_短期优先级_20260317.md`。  
最新执行计划（可信度优先，任务路线图版，含优先级任务清单/DoD/风险预案）见：`docs/PROJECT_PLAN_V2_20260323.md`。  
2026-03-23 微调：已将“性能与内存治理（P1-C）”“深度数据契约与强类型重构（P1-B）”“混沌测试与故事化 Mock 引擎（P1-D）”“带游戏上下文元数据的基线库（P2-A）”“文本分析接入 Pipeline（G4）”纳入同一执行路线。

**轻量治理约定（当前执行）**：以“低维护成本 + 高可追溯”为目标，默认采用每周最小文档更新机制：  
- 每周更新 `README.md`：当前能力口径、关键风险、下一步重点；  
- 每周更新 `docs/DEV_LOG.md`：本周变更、验证结果、未完成事项；  
- 原则：**没有验证结果的改动，不标记为完成**。

**Playtest 自动化流水线（CLI）**：在 `UserResearch/` 下执行 `python scripts/run_playtest_pipeline.py`，自动读取 `data/raw/` 最新数据表，完成题型识别、交叉分析、可选满意度回归与多 Sheet 导出；可通过 `--outline` 指定大纲，或自动发现目录内最新 `.docx`/`.txt`；支持 `--sig-test` / `--no-sig-test` 与 `--sig-alpha` 控制组间均值显著性检验。**完整参数表、维护约定与统计说明见 [`docs/PLAYTEST_PIPELINE.md`](docs/PLAYTEST_PIPELINE.md)**（更新 Pipeline 或 CLI 时须同步该文档与脚本顶部 docstring，并可在 `docs/DEV_LOG.md` 留痕）。大纲解析实现位于 `survey_tools/utils/outline_parser.py`（Web 定量工具上传大纲时通过「大纲来源」选择问卷星/腾讯规则；CLI 仍按扩展名 `.txt`→腾讯、否则→问卷星 分派）。

建议在日常改动后运行以下命令做最小回归：

```bash
python tests/run_quality_matrix.py
```

该入口默认串联 `tests/` 下：
- `verify_dependency_matrix.py`（依赖版本兼容性校验）
- `test_migration.py`（统计迁移一致性）
- `verify_current_v1_logic.py`（v1 核心统计逻辑可用性）
- `auto_verify_v1.py`（核心 schema 断言）
- `verify_standard_regression_core.py` / `verify_clustering_recommendation_core.py` / `verify_text_ingestion_io.py`
- `verify_p2_baseline.py`（P2 基线：缺失值策略矩阵 + 文本导出构建）
- `verify_p24_clustering.py`（P2-4：多算法分群验证）

全量代码审阅结论与潜在问题清单见 **`docs/CODE_REVIEW_DEBUG_REPORT.md`**（2026-03-17 审阅产出）。

---

### 🧪 example 全链路审阅导出（P2-4）

使用 `example/` 全量样本执行项目级审阅并导出结果：

```bash
python tests/run_example_full_review.py
```

默认输出目录：
- `review_outputs/<时间戳>/logs`：质量矩阵与子脚本日志
- `review_outputs/<时间戳>/text_exports`：文本引擎导出工作簿
- `review_outputs/<时间戳>/cluster_exports`：分群评估、推荐与分群结果
- `review_outputs/<时间戳>/regression_exports`：回归分析结果与摘要
- `review_outputs/<时间戳>/summary`：全样本审阅汇总

版本管理说明：
- `docs/PROJECT_CODE_REVIEW.md` 为项目级审阅主文档，纳入版本管理并随阶段里程碑同步更新。

---

## 🔒 依赖锁定与兼容矩阵（P2-3）

推荐在可复现环境中使用锁定版本安装：

```bash
pip install -r requirements.lock.txt
```

安装后运行依赖矩阵校验：

```bash
python tests/verify_dependency_matrix.py
```

矩阵详情见 `docs/DEPENDENCY_MATRIX.md`。

---

## 📦 依赖安装

请确保已安装 `requirements.txt` 中的依赖库：

```bash
pip install -r requirements.txt
```
