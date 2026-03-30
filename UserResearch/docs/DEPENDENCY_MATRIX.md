# 依赖版本锁定与兼容矩阵（P2-3）

## Python 版本基线

- 主验证版本：`Python 3.14.2`

## 依赖矩阵（核心运行）

| 包名 | 兼容区间 | 锁定版本 |
| :--- | :--- | :--- |
| streamlit | >=1.54.0, <1.60 | 1.54.0 |
| pandas | >=2.3.3, <2.4 | 2.3.3 |
| numpy | >=2.4.2, <2.5 | 2.4.2 |
| scipy | >=1.17.0, <1.18 | 1.17.0 |
| seaborn | >=0.13.2, <0.14 | 0.13.2 |
| matplotlib | >=3.10.8, <3.11 | 3.10.8 |
| plotly | >=6.5.2, <6.6 | 6.5.2 |
| statsmodels | >=0.14.6, <0.15 | 0.14.6 |
| scikit-learn | >=1.8.0, <1.9 | 1.8.0 |
| scikit-posthocs | >=0.11.4, <0.12 | 0.11.4 |
| semopy | >=2.3.11, <2.4 | 2.3.11 |
| factor-analyzer | >=0.5.1, <0.6 | 0.5.1 |
| langchain-openai | >=1.1.10, <1.2 | 1.1.10 |
| langchain-core | >=1.2.22, <1.3 | 1.2.22 |
| jieba | >=0.42.1, <0.43 | 0.42.1 |
| openpyxl | >=3.1.5, <3.2 | 3.1.5 |
| XlsxWriter | >=3.2.9, <3.3 | 3.2.9 |
| kneed | >=0.8.5, <0.9 | 0.8.5 |

## 文件说明

- `requirements.txt`：兼容区间约束，用于常规安装。
- `requirements.lock.txt`：精确锁定版本，用于复现实验与回归环境。
- `tests/verify_dependency_matrix.py`：环境版本自动校验脚本（工作目录为 `UserResearch/`）。

## 推荐安装方式

```bash
cd UserResearch
pip install -r requirements.lock.txt
```

## 校验命令

```bash
cd UserResearch
python tests/verify_dependency_matrix.py
```

## 质量矩阵串联

```bash
cd UserResearch
python tests/run_quality_matrix.py
```
</think>


<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
Read
