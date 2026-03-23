# 下一步 To-Do List（项目主管视角）

> 基于：当前工具验收（阶段 A/B/C 已完成）、项目需求与规则（README + project-standards.mdc + 功能可执行清单）、版本迭代计划（P2 中期演进）。  
> 优先级：**先验收再补缺，先规则落地再能力扩展**。

---

## 一、立即执行（1～2 周）

| 序号 | 事项 | 说明 | 产出/完成标准 |
|------|------|------|----------------|
| 1 | **执行映射验收表** | 按 `UserResearch/docs/core_modules_wjxspss_acceptance_matrix.md` 共 16 条，逐条按「验收方式」跑通核心模块，使用 `input_example` 或等价数据 | 每条状态更新为「通过」或「不通过」；不通过项记录原因（界面/导出/报错） |
| 2 | **验收问题清单** | 将不通过项整理为问题清单（条目 + 对应剑客 + 现象 + 可能原因），便于排期修复 | `UserResearch/验收问题清单_yyyymmdd.md` 或合并进 DEV_LOG |
| 3 | **需求与规则符合度检查** | 对照 README「项目定位与需求约定」与 project-standards.mdc：① 各工具是否支持 .csv/.xlsx，是否已接 .sav（pyreadstat）② 导出是否为「一工作簿多 sheet」、是否支持「用户勾选再打包」 | 结论：符合 / 部分符合（列差异）/ 不符合（列缺口），并标出需改动的工具或文档 |

---

## 二、短期（2～4 周）

| 序号 | 事项 | 说明 | 产出/完成标准 |
|------|------|------|----------------|
| 4 | **修复验收不通过项** | 根据问题清单，按「统计正确性 > 兼容性 > 稳健性」优先修复，修完再回归验收 | 不通过条数归零或剩余项明确列入 backlog |
| 5 | **验收用例沉淀为回归用例** | 将映射验收表中「通过」的验收方式，转化为可重复执行的用例（脚本或步骤文档），纳入现有质量矩阵（如 `run_quality_matrix.py` / P2 基线） | 至少 Quant / Standard / 聚类 / Text 各 1 条可回归用例，游研视情况 |
| 6 | **功能缺口与 Backlog** | 从 `功能可执行清单_参考wjxspss.md` 与 `core_modules_wjxspss_mapping.md`「未实现」中，选出与需求强相关且可排期的项（如：单样本/配对 t、偏相关、导出勾选多 sheet、.sav 读取等） | Backlog 列表（优先级 + 对应清单条目 + 目标模块） |

**Backlog P1 已含（排期见 Backlog）**：多选事后检验与显著性矩阵、题型标记按题号视图、矩阵题命名一致化、用户标签列（type.）识别与手动列归属。

**执行记录（2026-03-17）**：
- 4：已优先落地最明确缺口 **.sav 入口接入**（五剑客入口均支持上传 `.sav` 并统一读取）。
- 5：已新增 Standard/聚类/Text 的自动回归脚本并并入质量矩阵（质量矩阵 9/9 通过）。
- 6：已整理短期优先级 Backlog：`UserResearch/Backlog_短期优先级_20260317.md`。

---

## 三、中期（与 P2 对齐，季度内）

| 序号 | 事项 | 说明 | 产出/完成标准 |
|------|------|------|----------------|
| 7 | **分析管线统一化** | 继续收敛 web 与 core 双轨重复实现，形成清晰模块边界（README 已列为重点风险） | 双轨项减少、core 为单一统计/数据来源 |
| 8 | **依赖与环境锁定** | 推进依赖版本系统锁定（requirements.lock.txt / 矩阵校验），减少跨环境漂移（README 已列风险） | 新环境按 lock 安装可复现；CI 或本地定期跑 `verify_dependency_matrix.py` |
| 9 | **导出约定落地** | 若当前各工具导出尚未统一为「一工作簿多 sheet + 用户勾选」，则分工具排期落地并更新文档 | 与需求约定一致或差异在 README 中说明 |

**执行记录（2026-03-17）**：Quant 已改为多 sheet + 勾选导出；Standard 满意度已改为勾选三 sheet 后打包；均使用 `ExportBundle`/`export_xlsx`。需求符合度与 Backlog 已更新；聚类/文本/游研待扩展。

---

## 四、可选 / 持续

| 序号 | 事项 | 说明 |
|------|------|------|
| 10 | **.sav 支持** | 若需求明确要读 .sav，在入口层接入 pyreadstat，并在 README/依赖文件中注明（需求已约定） |
| 11 | **功能可执行清单迭代** | 随 wjxspss 或业务需求更新 `功能可执行清单_参考wjxspss.md`，并同步刷新对应表与映射验收表（新增条目标实现状态与验收方式） |
| 12 | **分群模板治理** | 分群推荐模板（balanced / stability_first / discrimination_first）的版本化与说明文档（README 已列后续风险） |

---

## 五、执行顺序建议

1. **先做一（1～3）**：验收表执行 + 问题清单 + 需求/规则符合度检查，为后续修复与 backlog 提供依据。  
2. **再做二（4～6）**：修验收问题、沉淀回归用例、定功能缺口 backlog。  
3. **三与四**：按 P2 节奏和资源与 7～12 穿插安排。

---

## 六、参考文档

- 需求与约定：`README.md`「项目定位与需求约定」、`.cursor/rules/project-standards.mdc`
- 验收与映射：`UserResearch/docs/core_modules_wjxspss_acceptance_matrix.md`、`UserResearch/docs/core_modules_wjxspss_mapping.md`
- 功能与任务：`UserResearch/功能可执行清单_参考wjxspss.md`、`UserResearch/docs/task_list_wjxspss_mapping_acceptance.md`
- 迭代与风险：`README.md`「版本优化与迭代计划」「当前重点风险」

---

*文档版本：基于 2026-03 工具验收与需求/规则整理；可根据执行结果与排期更新。*
