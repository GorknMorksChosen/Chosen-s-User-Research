# .sav 变量标签与值标签「可选应用」实现方案

> 目标：读 .sav 时使用 `load_sav` 获取变量标签（variable_labels）与值标签（value_labels），在五剑客界面中**可选**将列名替换为题干、将编码替换为选项文字，且不改变 CSV/Excel 的现有行为。  
> 用途：供排期与实现时参考；与 `Backlog_短期优先级_20260317.md` P1 对应。

---

## 一、目标与范围

- **变量标签**：SPSS 中列名 → 题干/题目说明（如 `Q1` → 「您对游戏画质的满意度」）。应用后界面与导出中的「题目/列名」显示为题干。
- **值标签**：列取值 → 选项文字（如 `1` → 「非常满意」）。应用后交叉表、图表、导出中的「选项」显示为文字而非数字。
- **可选**：用户在上传 .sav 后，可通过勾选「应用变量标签」「应用值标签」决定是否替换；默认建议见下文。
- **兼容**：CSV/Excel 不涉及标签，保持当前「只读 DataFrame」逻辑不变。

---

## 二、数据结构约定

- **io 层** 对 .sav 需返回「数据 + 元数据」：
  - `variable_labels: Dict[str, str]`，键为列名，值为变量标签（题干）。
  - `value_labels: Dict[str, Dict[float, str]]`，键为列名，值为 `{ 编码: 选项文字 }`。
- 对 CSV/Excel：不返回标签，或返回空字典，以便上层统一判断「是否有标签可用」。

---

## 三、io 层（survey_tools/utils/io.py）

### 3.1 保持现有 API

- `load_sav(path_or_file)`：保持不变，返回 `(df, variable_labels, value_labels)`。
- `read_table_auto(...)`：**保持现有行为**，继续仅返回 `pd.DataFrame`（.sav 时内部调用 `load_sav` 只取 df），保证现有五剑客调用方无需修改即可继续工作。

### 3.2 新增：带标签的读取接口

新增函数，仅用于「需要标签」的入口：

```python
def read_table_auto_with_meta(
    path_or_file: Union[str, BinaryIO],
    *,
    sheet_name: Union[int, str, List[int], List[str], None] = 0,
    encoding: Optional[str] = None,
    encoding_fallback: str = "gbk",
) -> Tuple[pd.DataFrame, Optional[Dict[str, str]], Optional[Dict[str, Dict[float, str]]]]:
    """
    与 read_table_auto 相同，但对 .sav 额外返回 (variable_labels, value_labels)。
    对 CSV/Excel 返回 (df, None, None)。
    """
```

- 实现要点：
  - 根据扩展名分支：`.sav` 调用 `load_sav`，返回 `(df, variable_labels, value_labels)`。
  - `.csv` / `.xlsx`：按现有逻辑读 df，返回 `(df, None, None)`。
- 这样各工具入口可**按需**选用 `read_table_auto`（仅要 df）或 `read_table_auto_with_meta`（要 df + 标签），便于渐进式改造。

### 3.3 新增：应用标签的纯函数（推荐放在 io 层）

便于各工具复用，避免在 web 层重复写映射逻辑：

```python
def apply_sav_labels(
    df: pd.DataFrame,
    variable_labels: Optional[Dict[str, str]] = None,
    value_labels: Optional[Dict[str, Dict[float, str]]] = None,
    *,
    apply_variable_labels: bool = True,
    apply_value_labels: bool = True,
) -> pd.DataFrame:
    """
    就地或拷贝后替换列名/取值，返回 DataFrame。
    - 列名：若 variable_labels 中存在且 apply_variable_labels，则列名替换为变量标签（仅当标签非空时）。
    - 取值：若 value_labels 中该列存在且 apply_value_labels，则将该列取值映射为选项文字（保留 NaN）。
    """
```

- 实现要点：
  - 列名：`df.rename(columns={k: v for k, v in variable_labels.items() if v and k in df.columns})`，注意避免重复列名（若多个列映射到同一标签，可加后缀或仅对首个应用）。
  - 取值：按列遍历，若列在 value_labels 中，则 `df[col] = df[col].map(lambda x: value_labels[col].get(x, x) if pd.notna(x) else x)` 或等价逻辑，保留未在字典中的编码为原值。

---

## 四、各工具入口改造要点

以下均为「可选改造」：先接 `read_table_auto_with_meta`，再在**仅当为 .sav 且 meta 非空**时展示「应用变量标签」「应用值标签」勾选项，默认策略见第五节。

| 工具 | 入口/文件 | 改造要点 |
|------|------------|----------|
| Quant | survey_tools/web/quant_app.py | 上传后若为 .sav，调用 `read_table_auto_with_meta`；若有 variable_labels/value_labels，在 sidebar 或导出区增加两个 checkbox，勾选后对当前 `st.session_state.df` 应用 `apply_sav_labels`（可存一份「未应用」的 df 用于重置或对比）。 |
| Standard | survey_tools/web/satisfaction_app.py | 同上：.sav 时用 `read_table_auto_with_meta`，有标签时提供「应用变量标签」「应用值标签」，应用后写回 `st.session_state.df`。 |
| 聚类 | survey_tools/web/cluster_app.py | .sav 时用 `read_table_auto_with_meta`，有标签时可选应用；特征列选择等展示的是列名，应用变量标签后更易读。 |
| 游研专家 | game_analyst.py | 同上：.sav + 带 meta 时提供勾选，应用后更新 `df_cleaned` 或展示用 df。 |
| 文本分析 | 问卷文本分析工具 v1.py | .sav 时用 `read_table_auto_with_meta`，有标签时可选应用；目标列/背景列展示更易读。 |

- **统一约定**：应用标签后，后续分析、导出均基于「已替换后的 df」；不要求同时保留「编码版」与「标签版」两套，除非产品明确需要切换对比。

---

## 五、默认策略与兼容 CSV/Excel

- **CSV/Excel**：  
  - 继续使用 `read_table_auto` 仅取 DataFrame，**不**调用 `read_table_auto_with_meta`，界面**不**出现「应用变量/值标签」选项。  
  - 行为与当前完全一致，无需改动现有调用链。

- **.sav 默认策略（建议）**：  
  - **方案 A（保守）**：默认不应用标签；用户勾选「应用变量标签」「应用值标签」后再应用。兼容性最好，适合先上线。  
  - **方案 B（体验优先）**：默认勾选「应用变量标签」与「应用值标签」，用户可取消。适合 .sav 用户为主、且希望开箱即用题干/选项文字的场景。  
  - 推荐先采用 **方案 A**，在文档或界面提示中说明「.sav 用户可勾选应用标签以显示题干与选项文字」。

- **重复列名/缺失标签**：  
  - 若变量标签为空字符串或缺失，保留原列名。  
  - 若应用变量标签后产生重复列名，可在 io 层 `apply_sav_labels` 中对重复标签加后缀（如 `题干_2`）或仅首列用标签，其余保留原名，避免 pandas 报错。

---

## 六、测试与验收

- **单元/回归**：  
  - 在 `test_assets` 中增加一个最小 .sav（或 pytest 内用 pyreadstat 写临时 .sav），包含变量标签与值标签。  
  - 对 `read_table_auto_with_meta`、`apply_sav_labels` 写断言：应用前后列名与取值符合预期；对 CSV/Excel 调用 `read_table_auto_with_meta` 返回 (df, None, None)。

- **人工验收**：  
  - 上传带标签的 .sav，勾选应用标签后，检查交叉表、导出 Excel、聚类特征名、满意度列名等是否均为题干/选项文字。

---

## 七、排期建议

- **优先级**：P1（体验增强），在 .sav 已支持读取的基础上推进。
- **建议顺序**：  
  1. io 层：实现 `read_table_auto_with_meta`、`apply_sav_labels`，并在 `__all__` 中导出。  
  2. Quant、Standard 各先接一版（.sav 时用 meta + 勾选应用），验证无误后再推广到聚类、游研、文本。  
  3. 文档：在 README 或「输入格式」中注明「.sav 支持可选应用变量/值标签以显示题干与选项文字」。

---

## 八、相关文档

- 需求与约定：README「项目定位与需求约定」、`.cursor/rules/project-standards.mdc`
- 符合度与 Backlog：`需求与规则符合度检查_20260317.md`、`Backlog_短期优先级_20260317.md`
- io 实现：`survey_tools/utils/io.py`（`load_sav`、`read_table_auto`）

---

*文档版本：2026-03-17；供排期与实现参考，不强制一次性落地。*
