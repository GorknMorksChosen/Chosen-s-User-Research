"""工具注册表：所有分析工具的统一元数据中心。

web_tools_launcher.py 及其他调度器从此处读取工具列表，不得在外部硬编码。
AI agent 可通过 input_schema 了解每个工具接受的核心输入参数。
"""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "id": "quant",
        "name": "问卷定量交叉分析 (Quant Engine 2.0)",
        "entry": "survey_tools/web/quant_app.py",
        "cli": None,
        "core_fn": "survey_tools.core.quant.run_quant_cross_engine",
        "port": 8501,
        "stage": "web",
        "description": (
            "上传问卷数据（csv/xlsx/sav），选择核心分组变量，"
            "对单选、多选、评分、矩阵题进行交叉分析并导出多 sheet Excel。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "输入文件路径，支持 .csv / .xlsx / .sav",
                },
                "core_segment_col": {
                    "type": "string",
                    "description": "核心分组列的列名（如「Type.玩家分类」）",
                },
                "analysis_cols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要交叉分析的题目列名列表；为空时分析全部非忽略列",
                },
            },
            "required": ["file_path", "core_segment_col"],
        },
    },
    {
        "id": "satisfaction",
        "name": "满意度与体验建模工具 (Standard)",
        "entry": "survey_tools/web/satisfaction_app.py",
        "cli": None,
        "core_fn": "survey_tools.core.advanced_modeling",
        "port": 8502,
        "stage": "web",
        "description": (
            "上传满意度问卷数据，进行 IPA 象限分析、多元回归/驱动力分析、"
            "玩家分群（聚类）及 AI 辅助命名，输出可解释的体验建模报告。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "输入文件路径，支持 .csv / .xlsx / .sav",
                },
                "overall_col": {
                    "type": "string",
                    "description": "整体满意度列名（因变量）",
                },
                "feature_cols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "各维度满意度列名列表（自变量）",
                },
            },
            "required": ["file_path", "overall_col"],
        },
    },
    {
        "id": "game_analyst",
        "name": "全链路归因分析工具 (Advanced)",
        "entry": "game_analyst.py",
        "cli": None,
        "core_fn": "survey_tools.core.advanced_modeling.GameExperienceAnalyzer",
        "port": 8503,
        "stage": "web",
        "description": (
            "游戏体验全链路分析工具：数据质量检查、描述统计、相关分析、"
            "回归建模、SEM 结构方程模型，适合深度归因与体验机制研究。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "输入文件路径，支持 .csv / .xlsx / .sav",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "id": "cluster",
        "name": "玩家分群分析工具 (Advanced)",
        "entry": "survey_tools/web/cluster_app.py",
        "cli": None,
        "core_fn": "survey_tools.core.clustering.perform_clustering",
        "port": 8504,
        "stage": "web",
        "description": (
            "对玩家行为/态度数据进行聚类分析：支持因子分析降维、"
            "K-Means / 层次聚类算法选择、轮廓系数评估、AI 辅助命名分群。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "输入文件路径，支持 .csv / .xlsx",
                },
                "feature_cols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "参与聚类的特征列名列表",
                },
                "n_clusters": {
                    "type": "integer",
                    "minimum": 2,
                    "description": "聚类数量 K（默认由肘部法则自动推荐）",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "id": "text",
        "name": "问卷文本分析工具",
        "entry": "问卷文本分析工具 v1.py",
        "cli": None,
        "core_fn": None,
        "port": 8505,
        "stage": "web",
        "description": (
            "对问卷开放题文本进行 AI 辅助分析：关键词提取、主题聚类、"
            "情感分析、词频统计及可视化，支持 OpenAI 兼容接口。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "输入文件路径，支持 .csv / .xlsx",
                },
                "text_col": {
                    "type": "string",
                    "description": "需要分析的开放题列名",
                },
            },
            "required": ["file_path", "text_col"],
        },
    },
    {
        "id": "playtest_pipeline",
        "name": "一键 Playtest 流水线",
        "entry": "survey_tools/web/pipeline_app.py",
        "cli": "scripts/run_playtest_pipeline.py",
        "core_fn": "scripts.run_playtest_pipeline.run_pipeline",
        "port": 8506,
        "stage": "web",
        "description": (
            "上传问卷数据并一键执行 Playtest 自动化流水线："
            "自动题型识别、交叉分析、满意度回归建模与 Excel 报告导出。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "输入文件路径，支持 .csv / .xlsx / .sav",
                },
                "segment_col": {
                    "type": "string",
                    "description": "交叉分组列名；为空时自动推断",
                },
                "per_question_sheets": {
                    "type": "boolean",
                    "description": "是否为每道题独立生成 Sheet，默认 false",
                },
            },
            "required": ["file_path"],
        },
    },
]

# 快速查询辅助
_id_to_tool: dict[str, dict] = {t["id"]: t for t in TOOLS}
_port_to_tool: dict[int, dict] = {t["port"]: t for t in TOOLS}


def get_tool_by_id(tool_id: str) -> dict | None:
    """通过 id 查询工具元数据，未找到返回 None。"""
    return _id_to_tool.get(tool_id)


def get_tool_by_port(port: int) -> dict | None:
    """通过端口号查询工具元数据，未找到返回 None。"""
    return _port_to_tool.get(port)
