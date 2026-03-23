# pipeline_app 下载链路压测结论（read_bytes vs file-like）

## 目的

验证 `st.download_button` 数据准备阶段中，`Path.read_bytes()` 与 file-like 方式在大文件场景下的内存开销差异。

## 压测条件

- 文件大小：50MB（二进制临时文件）
- 环境：本地 Python（Windows）
- 指标：准备阶段耗时、`tracemalloc` 峰值内存

## 结果

- `read_bytes`：
  - 耗时约 `0.0104s`
  - 峰值内存约 `50.0MB`
- file-like（仅 `open("rb")`，不读取全量字节）：
  - 耗时约 `0.000205s`
  - 峰值内存约 `0.1254MB`

## 结论

- 在“数据准备阶段”，`read_bytes()` 会引入与文件大小接近的额外内存峰值。
- 对于可能达到几十 MB 的报告文件，推荐使用 file-like 方式传递给 `st.download_button`，以降低瞬时内存占用风险。
- 因 `st.download_button` 的内部处理仍可能持有下载数据，后续如遇极大文件（如 100MB+）仍建议继续实测整链路内存表现。

