# 方向 A（文本分析接入 Pipeline）实施稿 v1

## 1. 目标与边界

- 目标
  - 将当前 `问卷文本分析工具 v1.py` 的核心文本能力接入 `run_playtest_pipeline.py`
  - Pipeline 报告最后新增 `文本洞察（自动）` Sheet（含词云数据）
  - Web `pipeline_app.py` 增加文本分析开关与基础参数（后续可做）

- 边界（第一期）
  - 先做确定性文本分析（jieba + 关键词统计 + 分组提及率 + 示例原话）
  - 不强制依赖 LLM；LLM 放第二期，作为可选增强，失败可降级

## 2. 架构设计（1:1 体验优先）

### 2.1 模块拆分（新增，不破坏原工具）

- 新增：`survey_tools/core/text_pipeline.py`
- 保留：`问卷文本分析工具 v1.py` 原页面交互不变，只把内部计算调用到 core

### 2.2 调用关系

1. Pipeline 调用 `run_text_pipeline(...)`
2. 返回 `text_result`（结构化结果）
3. `_export_results(...)` 增加最后一个 Sheet：`文本洞察（自动）`

## 3. 核心接口定义（建议）

```python
def run_text_pipeline(
    df: pd.DataFrame,
    *,
    target_cols: list[str] | None = None,
    segment_col: str | None = None,
    top_n: int = 20,
    min_text_len: int = 4,
    max_quotes_per_keyword: int = 3,
    stopwords_path: str | None = None,
    custom_keywords: list[str] | None = None,
) -> dict:
    """
    返回结构化文本分析结果，供 Pipeline 导出和 Web 展示复用。
    """
```

### 返回结构（建议固定 schema）

```json
{
  "meta": {
    "target_cols": ["Q17开放题", "Q23建议"],
    "segment_col": "玩家类型",
    "total_rows": 120,
    "valid_text_rows": 96
  },
  "keyword_freq": [
    {"keyword": "卡顿", "mention_users": 42, "mention_rate": 0.438, "weight": 42},
    {"keyword": "掉帧", "mention_users": 33, "mention_rate": 0.344, "weight": 33}
  ],
  "keyword_by_segment": [
    {"segment": "重度", "keyword": "卡顿", "mention_users": 20, "group_size": 40, "mention_rate": 0.50, "delta_vs_overall": 0.062},
    {"segment": "轻度", "keyword": "卡顿", "mention_users": 8, "group_size": 30, "mention_rate": 0.267, "delta_vs_overall": -0.171}
  ],
  "evidence_quotes": [
    {"keyword": "卡顿", "quote": "打 boss 时明显卡顿", "sample_id": "A12", "segment": "重度"},
    {"keyword": "掉帧", "quote": "切场景会掉帧", "sample_id": "B07", "segment": "中度"}
  ],
  "warnings": [
    "自动排除了 18 列 Unnamed 列",
    "文本有效样本偏少（<15）"
  ]
}
```

## 4. 文本列识别策略（针对问卷星结构）

默认自动识别规则（可手工覆盖）：

- 排除列名命中：
  - `Unnamed:*`
  - 时间/IP/来源/编号/总分等元数据列
- 保留候选列条件：
  - 非空文本比例 > 10%
  - 文本平均长度 >= `min_text_len`
  - 纯数字/纯符号占比低于阈值
- 若用户明确传 `target_cols`，则以用户配置优先

## 5. Pipeline 接入点设计（不改现有口径）

在 `run_playtest_pipeline.py` 中新增“文本阶段”：

- 位置：满意度建模后、导出前
- 行为：
  - 执行 `text_result = run_text_pipeline(...)`
  - 失败不影响主流程：记录 warning，继续导出定量结果
- 导出：
  - `_export_results(..., text_result=text_result)`（新增可选参数）
  - 追加 `文本洞察（自动）` Sheet

## 6. Excel Sheet 设计（`文本洞察（自动）`）

按块写入，便于业务看：

- A 区：`关键词总榜`
  - 字段：关键词 / 提及人数 / 提及率 / 权重
- B 区：`分组差异`
  - 字段：分组 / 关键词 / 提及人数 / 组样本数 / 提及率 / 相对总体偏差
- C 区：`证据原话`
  - 字段：关键词 / 原话 / 分组 / 样本ID
- D 区：`词云数据`
  - 字段：keyword / weight（给前端或后续可视化直接用）

## 7. Web 端体验对齐建议（`pipeline_app.py` 后续）

在“高级配置”增加（默认折叠）：

- `启用文本分析`（默认开）
- `文本目标列`（多选，默认自动识别）
- `关键词 TopN`（默认 20）
- `最小有效字数`（默认 4）

说明文案建议：

- 文本分析默认不会调用外部 LLM，仅做关键词统计与分组洞察，确保稳定可复现。

## 8. 第二期（LLM 增强）设计

新增可选函数：

```python
def summarize_text_with_llm(
    text_result: dict,
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
    timeout_sec: int = 45,
    max_retries: int = 2,
) -> dict
```

输出：

- `summary_overview`
- `key_highlights`
- `core_pain_points`
- `actions`

策略：

- 失败降级：仅不产出 AI 总结，不影响 Excel 主体

## 9. 风险清单与防护

- 风险：`Unnamed` 噪声列污染关键词
  - 防护：自动排除 + 手工覆盖
- 风险：文本样本过少导致伪洞察
  - 防护：阈值预警 + 弱化结论文案
- 风险：LLM 不稳定/成本不可控（第二期）
  - 防护：默认关闭 + 超时/重试/预算上限 + 降级

## 10. 验收标准（DoD）

- Pipeline 跑完后稳定产出 `文本洞察（自动）` Sheet
- 未配置 LLM 也能完成全部流程
- 同一输入重复跑，关键词统计结果一致
- 文本工具原页面主要体验保持一致（1:1）

