"""统一配置模块：从环境变量读取所有外部依赖配置。

所有模块应从此处 import 配置常量，不得在业务代码中直接调用 os.getenv。
本地开发：在项目根目录创建 .env 文件（参考 .env.example），运行时自动加载。
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ---------- OpenAI / LLM ----------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ---------- 路径 ----------
DEFAULT_INPUT_DIR: str = os.getenv("INPUT_DIR", "input_example")
DEFAULT_OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")
