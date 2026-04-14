# 全量审查结论与 To-Do（2026-04-14）

> 适用场景：个人项目（主要依赖 AI coding）。  
> 文档目的：把本次全量审查的结论、风险和下一步任务收敛为“可直接执行”的清单。

---

## 1. 本次审查范围

- 统计与算法核心：`survey_tools/core/quant.py`、`survey_tools/core/advanced_modeling.py`、`survey_tools/core/effect_size.py`、`survey_tools/core/playtest_pipeline.py`
- Web 与状态管理：`survey_tools/web/quant_app.py`、`survey_tools/web/satisfaction_app.py`、`survey_tools/web/pipeline_app.py`、`survey_tools/web/cluster_app.py`
- 工程与质量保障：`tests/`、`requirements.txt`、`requirements.lock.txt`、`tests/verify_dependency_matrix.py`、`README.md`
- 运行验证：执行 `python tests/run_quality_matrix.py`，结果 `10/10` 通过

---

## 2. 总体结论（先给你一句话）

项目当前“可运行性”和“已有回归覆盖”整体不错，但仍有三类高优先级问题：

1. **统计口径存在不一致风险**（尤其多选显著性的校正口径）
2. **异常处理存在静默失败风险**（看起来成功，实际部分结果缺失）
3. **依赖锁定闭环未完成**（`requirements` / `lock` / `matrix` 不一致）

---

## 3. 风险清单（按严重程度）

## P0（优先修）

### P0-1 多选显著性口径不一致
- **现象**：`overall` 层面使用了 FDR 校正，但 `cells` 级逐格显著性仍可能基于未校正 p 值；导出文案又写“已 FDR 校正”。
- **影响**：可能放大假阳性，报告解释和实际计算不完全一致。
- **建议**：统一 `overall` 与 `cells` 的校正策略，或在导出明确区分“校正后 / 未校正”。

### P0-2 流水线静默失败风险
- **现象**：部分核心步骤异常被吞后，流程仍可继续导出并提示完成。
- **影响**：用户容易把“不完整结果”当成“完整报告”使用。
- **建议**：增加结果完整性契约（如 `is_complete`、`errors`、`warnings`），UI 按状态显示“完成 / 部分完成 / 失败”。

### P0-3 依赖闭环不一致
- **现象**：`requirements.txt` 包含 `pyreadstat`、`python-dotenv`、`click`，但 `requirements.lock.txt` 与 `verify_dependency_matrix.py` 未对齐覆盖。
- **影响**：可能出现“依赖检查通过，但新环境运行缺包”。
- **建议**：同步三处依赖来源，保证单一事实源。

---

## P1（高价值优化）

### P1-1 core 与 web 边界渗透
- **现象**：core 模块中存在 Streamlit 直接调用。
- **影响**：降低可复用性，增加后续重构成本。
- **建议**：core 仅返回数据与 warning；UI 展示放到 web 层。

### P1-2 回归显著性判定口径可再严谨
- **现象**：部分结论判定使用了四舍五入后的 p 值。
- **影响**：阈值附近可能误判显著性。
- **建议**：判定使用 raw p，展示层再格式化。

### P1-3 效应量标签与检验类型可能混淆
- **现象**：前端显示“效应量(η²)”但实际可能是 Cohen’s d（依检验而定）。
- **影响**：解释阈值与业务解读可能偏差。
- **建议**：返回 `effect_size_metric` 字段，前端动态显示对应标签。

### P1-4 组内 pairwise 多重比较控制不足
- **现象**：部分组内事后比较直接解释 raw p。
- **影响**：比较次数多时，I 类错误膨胀。
- **建议**：组内 pairwise 增加 Holm/FDR 校正并输出校正后结果。

### P1-5 Streamlit 状态对象偏大
- **现象**：`st.session_state` 长驻较多 DataFrame/导出字节/中间结果。
- **影响**：内存压力增大、文件切换后状态污染风险增加。
- **建议**：按文件签名切换时清理衍生状态；大对象按需生成或分层缓存。

---

## P2（技术债/中期）

### P2-1 web/core 双轨重复实现
- **现象**：历史函数与新 core 引擎并存。
- **影响**：长期存在口径漂移与维护重复。
- **建议**：逐步收敛到 core 单一事实源。

### P2-2 配置文档与仓库实物不完全一致
- **现象**：README 有 `.env.example` 使用说明，但仓库未检出对应模板文件。
- **影响**：新环境初始化成本上升，AI 执行步骤易卡住。
- **建议**：补 `.env.example` 并确保 `.gitignore` 白名单允许提交模板。

---

## 4. To-Do 清单（按执行顺序）

> 说明：以下任务按“你 + AI”执行设计，不需要负责人字段。  
> 推荐每完成 1 个任务就让 AI 跑一次最小回归，避免堆改后难排错。

## 第 1 组（本周，先做）

### TODO-01：统一多选显著性校正口径（P0）
- **目标**：`overall` 与 `cells` 显著性口径一致。
- **建议改动点**：`survey_tools/core/quant.py`、`survey_tools/core/playtest_pipeline.py`
- **实现细化（结合本轮 review 与 Gemini 建议）**：
  - `cells` 级两比例比较加入“小样本降级策略”（不要仅替换为 `proportions_ztest`）：
    - 样本满足近似条件时走 z 检验；
    - 小样本/稀疏场景回退到更稳健路径（如 2x2 Fisher）。
  - 单选 `>2x2` 且稀疏期望频数场景，返回结构化警告字段（如 `warning_sparse_data`、`expected_lt5_ratio`）。
  - `cells` 的显著性判定补充多重比较校正（或在导出中明确标注“未校正”），避免与 `overall` 的 FDR 口径冲突。
- **验收标准**：
  - 导出文案与真实计算一致
  - 同一题目的显著标记不再“overall 与 cells 打架”

### TODO-02：给流水线加“完整性契约”（P0）
- **目标**：避免“部分失败仍显示成功”。
- **建议改动点**：`survey_tools/core/playtest_pipeline.py`、`survey_tools/web/pipeline_app.py`
- **验收标准**：
  - 返回结构有 `is_complete/errors/warnings`
  - UI 按状态正确显示完成级别

### TODO-03：依赖闭环三文件对齐（P0）
- **目标**：`requirements.txt`、`requirements.lock.txt`、`tests/verify_dependency_matrix.py` 完全一致。
- **验收标准**：
  - `python tests/verify_dependency_matrix.py` 通过
  - 新环境按 lock 安装后 `.sav`、`.env`、CLI 相关能力可用

---

## 第 2 组（1-2 个迭代）

### TODO-04：清理 core 中 UI 依赖（P1）
- **目标**：core 不直接依赖 Streamlit。
- **建议改动点**：`survey_tools/core/advanced_modeling.py`
- **验收标准**：
  - core 返回结构化 warning
  - web 层负责 warning 展示

### TODO-05：显著性判定改用 raw p（P1）
- **目标**：统计结论严格基于原始 p 值判断。
- **建议改动点**：`survey_tools/core/advanced_modeling.py`
- **验收标准**：
  - 阈值附近样例（如 0.049x / 0.050x）判定正确

### TODO-06：效应量标签动态化（P1）
- **目标**：展示层标签与检验方法一致（例如 d / η²）。
- **建议改动点**：`survey_tools/core/quant.py`、`survey_tools/web/quant_app.py`
- **验收标准**：
  - 导出、页面、日志三处标签一致

### TODO-07：组内 pairwise 增加多重比较校正（P1）
- **目标**：组内比较结果更稳健。
- **建议改动点**：`survey_tools/core/quant.py`
- **验收标准**：
  - 输出包含校正后 p 值
  - 显著判定优先使用校正后口径

### TODO-08：session_state 生命周期治理（P1）
- **目标**：降低内存和状态污染风险。
- **建议改动点**：`survey_tools/web/quant_app.py`、`survey_tools/web/satisfaction_app.py`、`survey_tools/web/pipeline_app.py`
- **验收标准**：
  - 文件切换后衍生状态清理
  - 大对象缓存有明确生命周期

---

## 第 3 组（中期优化）

### TODO-09：收敛双轨重复逻辑（P2）
- **目标**：web 不重复实现核心统计逻辑。
- **验收标准**：
  - 同类能力仅保留 core 入口
  - 历史函数标注 deprecated 并规划删除路径

### TODO-10：补齐配置模板与文档一致性（P2）
- **目标**：新机器初始化可一步完成。
- **验收标准**：
  - 仓库有 `.env.example`
  - README 步骤可直接执行无卡点

### TODO-11：排序题分类阈值动态化（P2）
- **目标**：避免 `classify_ranking_demand` 对固定分值阈值（如 3.5/3.0）的硬编码依赖。
- **建议改动点**：`survey_tools/core/quant.py`（`classify_ranking_demand`、`process_ranking_data`）
- **验收标准**：
  - 阈值可随题目分值上限或选项数动态变化（例如基于 `max_possible_score`）
  - 5 选项与 10 选项排序题在同类偏好结构下，分类结果口径一致、可解释

---

## 5. 建议最小测试集（后续可直接让 AI 新增）

1. 多选 `cells` 显著性与 FDR 口径一致性测试  
2. 回归显著性判定（raw p vs round p）边界测试  
3. 效应量指标标签映射测试（d / η²）  
4. 流水线“部分失败”状态传播测试（`is_complete/errors`）  
5. session_state 文件切换清理测试（防旧状态污染）
6. 小样本比例检验降级与稀疏警告测试（z-test/Fisher 分支 + `warning_sparse_data` 字段）

---

## 6. 建议你给 AI 的执行方式（实用版）

你可以每次只给 AI 一条任务，减少失控概率。推荐模板：

- **模板 A（单任务）**：  
  “请只实现 TODO-01，不要改其他功能。改完后运行 `python tests/run_quality_matrix.py`，并把新增/修改的测试结果告诉我。”

- **模板 B（带验收）**：  
  “请实现 TODO-02，并新增最小测试覆盖异常分支。若无法一次完成，请先提交不改变行为的重构，再提交功能改动。”

- **模板 C（防超改）**：  
  “只允许修改这几个文件：`<文件列表>`。不要动 UI 文案，不要改 README，不要改无关模块。”

---

## 7. 维护约定

- 每完成一个 TODO，在 `docs/DEV_LOG.md` 记录：改了什么、怎么验证、还有什么没做。
- 原则：**没有验证结果，不标记完成**。

