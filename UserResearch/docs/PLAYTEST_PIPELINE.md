# Playtest 自动化分析流水线（CLI）

本文档说明 Playtest 流水线的用途、命令行参数、输出约定及维护要求。**实现代码**位于 `survey_tools/core/playtest_pipeline.py`；**CLI 薄入口**为 `scripts/run_playtest_pipeline.py`。

---

## 文档定位与维护约定（开发 / AI 必读）

以下约定用于避免「代码已改、文档仍旧」：

1. **官方说明成对物**  
   - 本文件：`UserResearch/docs/PLAYTEST_PIPELINE.md`  
   - 核心模块 docstring：`UserResearch/survey_tools/core/playtest_pipeline.py` 文件最顶部的 `"""..."""`  
   二者应表述一致；参数与行为以代码为准（CLI 入口脚本仅含路径引导与 UTF-8 控制台设置）。

2. **每次更新 Pipeline 后必须同步**  
   若改动涉及下列任一类，**须同时**更新本 Markdown **与** 脚本 docstring（并在 `docs/DEV_LOG.md` 追加一条变更记录，便于审计）：  
   - 新增、删除、重命名或修改默认值的 **CLI 参数**（`@click.option`）  
   - **步骤顺序**、数据目录约定、导出 Sheet 结构、显著性检验等行为  
   - **对外可见的统计口径**（如检验方法、阈值、小样本规则）

3. **权威校验方式**  
   若对参数是否一致有疑问，以当前环境下的命令为准：  
   ```bash
   cd UserResearch
   python scripts/run_playtest_pipeline.py --help
   ```  
   将 `--help` 与本文档对照，不一致则以 `--help` 为准并修正文档。

4. **README 中的索引**  
   项目级入口说明见 `UserResearch/README.md` 中「Playtest 自动化流水线」小节；该小节应保持**简短**，详细内容以本文件为主，避免重复粘贴大段参数表。

---

## 运行前提

- **工作目录**：请在 `UserResearch/` 下执行（保证 `survey_tools` 包与相对路径 `data/raw`、`data/processed` 可用）。
- **数据**：默认从 `--data-dir`（默认 `data/raw`）读取**修改时间最新**的一份 `.sav` / `.csv` / `.xlsx`。

---

## 功能概览

1. 读取原始问卷 → 自动识别题型（可结合 `.sav` meta、问卷大纲）。  
2. 按分组列做交叉/频率分析；无合适分组列时使用「总体」虚拟列。  
3. 尝试满意度多元回归（需识别到满意度类目标列且评分特征≥2；`GameExperienceAnalyzer` 内有效行 &lt; 10 仍会失败）。  
4. 导出多 Sheet Excel 报告。  
5. （可选）对可解析数值分值的单选/评分题做组间均值 **Welch 独立样本 t 检验**，在汇总表中为显著组别均值标红（见下文）。
6. 对识别为 NPS 的题目（题干含 `NPS/净推荐/推荐意愿/recommend` 且选项可解析为 `0-10`），在汇总表追加：Promoter/Passive/Detractor 占比与 **NPS = %Promoter - %Detractor**（其中 Promoter=9-10，Passive=7-8，Detractor=0-6）。

### 近期口径补丁（2026-03-30）

- **分组列防误判**：自动推断分组列时，题目列（可提取题号）不再参与候选，避免把题目/选项列误当分组列。
- **Web 强制总体模式**：`pipeline_app` 新增「总体（不分组）」；若用户误选题目列作为分组列，运行前自动回退总体并提示。
- **问卷星多选列兼容**：题号提取新增 `N(子项)` / `N（子项）` 格式，修复多选子列被拆成单选的问题。
- **运行时一致性告警**：同题出现混合题型会打印 warning，重点提示“多选 + 单选”高风险组合。

### 满意度回归与样本量分档（总样本量 `N = len(df)`）

| 条件 | 行为 |
|------|------|
| `N < 15` | **不执行**回归；控制台提示「样本量极小，无法进行回归计算」。 |
| `15 <= N < 50` | 满足前置条件时**执行**回归；结果中 `is_low_sample_warning=True`。导出「满意度回归结果」Sheet 时：**第 1 行**为合并单元格免责声明（加粗红字），**回归系数表**（表头+数据）使用浅灰背景表示仅供参考。免责声明中 `{n}` 为 `low_sample_n`（与分档判定一致的总行数）。 |
| `N >= 50` | 正常执行；`is_low_sample_warning=False`；满意度 Sheet 无 A1 免责条、表无浅灰底。 |

说明：核心库对清洗后有效行数仍有下限（&lt;10 会抛错），与上述总行数分档独立；若回归未运行则无「满意度回归结果」Sheet。

---

## CLI 参数一览

| 长参数 | 短说明 | 默认值 |
|--------|--------|--------|
| `--data-dir` | 原始问卷目录 | `data/raw` |
| `--output-dir` | 报告输出目录 | `data/processed` |
| `--segment-col` | 分组列名**子串**模糊匹配；缺省自动识别；找不到则用「总体」 | 无 |
| `--force-overall` | 强制按「总体」单一分组输出，跳过自动分组列识别；与 `--segment-col` 同时存在时本项优先 | 关闭 |
| `--sheet-name` | Excel 读取的 Sheet（支持索引如 `0`，或名称如 `Sheet1`）；仅对 `.xlsx/.xls` 生效 | 无（默认第 0 张） |
| `--per-question-sheets` | 除汇总外，为每题单独建 Sheet（上限 60） | 关闭 |
| `--outline` | 问卷大纲路径（`.docx` 问卷星 / `.txt` 腾讯）；不指定则在 `data-dir` 下自动找最新 `.docx` 或 `.txt` | 无 |
| `--sig-test` / `--no-sig-test` | 是否启用 quant 统一显著性检验并在 Excel 打标（`*` + 颜色） | 开启（`--sig-test`） |
| `--sig-alpha` | 显著性阈值 α，`p < α` 视为显著；须在 `(0,1)`，否则回退 `0.05` | `0.05` |

**查看完整帮助（与实现同步）：**

```bash
python scripts/run_playtest_pipeline.py --help
```

示例：

```bash
python scripts/run_playtest_pipeline.py --sheet-name 0
python scripts/run_playtest_pipeline.py --sheet-name "Sheet1"
```

---

## 显著性检验（`--sig-test` 开启时）

- **统一引擎**：由 `survey_tools/core/quant.py` 的 `run_group_difference_test` 输出标准统计结构。  
- **评分题**：`k=2` 使用 Welch t；`k>2` 使用 ANOVA 或 Kruskal-Wallis（按前提检验自动选择）。  
- **单/多选题**：使用卡方/Fisher（多选逐选项并做 FDR(BH) 校正）。  
- **Excel 打标**：显著单元格保持纯数字，使用 `number_format` 显示星号级别：`* p<0.05`、`** p<0.01`；并按方向显示浅绿（higher）/浅红（lower）提示。  
- **热力图**：矩阵评分的均值区域应用 `ColorScaleRule` 红黄绿三阶色带。  
- **关闭**：`--no-sig-test` 不做显著性打标与颜色标注。

---

## 输出产物

- 文件名形如：`YYYYMMDD_Playtest自动化分析报告.xlsx`（重名占用时会自动加后缀）。  
- 典型 Sheet：`样本概况`、`交叉分析（汇总）`；条件具备时可有 `满意度回归结果`；`--per-question-sheets` 时每题独立 Sheet。  
- 详细列结构与矩阵合并规则以脚本内 `_export_results` 及辅助函数为准。

---

## 相关代码与大纲

- 流水线实现：`survey_tools/core/playtest_pipeline.py`；CLI 入口：`scripts/run_playtest_pipeline.py`  
- 大纲解析：`survey_tools/utils/outline_parser.py`（CLI 按扩展名：`.txt` → 腾讯规则，否则 → 问卷星规则）  
- 变更日志：`docs/DEV_LOG.md`

---

*文档版本与脚本版本应对齐；脚本内标注为 v0.3 时，以脚本为准。*
