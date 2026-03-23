import importlib.metadata as md
import sys
from packaging.version import Version


MATRIX = [
    {"name": "streamlit", "min": "1.54.0", "max": "1.59.999"},
    {"name": "pandas", "min": "2.3.3", "max": "2.3.999"},
    {"name": "numpy", "min": "2.4.2", "max": "2.4.999"},
    {"name": "scipy", "min": "1.17.0", "max": "1.17.999"},
    {"name": "seaborn", "min": "0.13.2", "max": "0.13.999"},
    {"name": "matplotlib", "min": "3.10.8", "max": "3.10.999"},
    {"name": "plotly", "min": "6.5.2", "max": "6.5.999"},
    {"name": "statsmodels", "min": "0.14.6", "max": "0.14.999"},
    {"name": "scikit-learn", "min": "1.8.0", "max": "1.8.999"},
    {"name": "scikit-posthocs", "min": "0.11.4", "max": "0.11.999"},
    {"name": "semopy", "min": "2.3.11", "max": "2.3.999"},
    {"name": "factor-analyzer", "min": "0.5.1", "max": "0.5.999"},
    {"name": "langchain-openai", "min": "1.1.10", "max": "1.1.999"},
    {"name": "langchain-core", "min": "1.2.17", "max": "1.2.999"},
    {"name": "jieba", "min": "0.42.1", "max": "0.42.999"},
    {"name": "openpyxl", "min": "3.1.5", "max": "3.1.999"},
    {"name": "XlsxWriter", "min": "3.2.9", "max": "3.2.999"},
    {"name": "kneed", "min": "0.8.5", "max": "0.8.999"},
]


def main():
    print(f"Python: {sys.version.split()[0]}")
    failures = 0
    for item in MATRIX:
        name = item["name"]
        min_v = Version(item["min"])
        max_v = Version(item["max"])
        try:
            cur_raw = md.version(name)
        except md.PackageNotFoundError:
            print(f"[FAIL] {name}: 未安装")
            failures += 1
            continue
        cur = Version(cur_raw)
        if cur < min_v or cur > max_v:
            print(f"[FAIL] {name}: {cur} 不在 [{min_v}, {max_v}]")
            failures += 1
        else:
            print(f"[PASS] {name}: {cur}")
    if failures > 0:
        print(f"依赖矩阵检查失败: {failures}/{len(MATRIX)}")
        return 1
    print(f"依赖矩阵检查通过: {len(MATRIX)}/{len(MATRIX)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
