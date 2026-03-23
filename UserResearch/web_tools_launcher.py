"""Web 工具启动菜单：从 tool_registry 读取工具列表，用户选择后启动对应 Streamlit 应用。"""

import os
import subprocess
import sys

from tool_registry import TOOLS


def parse_choices(choice_text: str) -> list[str]:
    normalized = choice_text.replace("，", ",").replace(" ", ",")
    parts = [p.strip() for p in normalized.split(",") if p.strip()]
    seen: set[str] = set()
    unique_parts: list[str] = []
    for p in parts:
        if p not in seen:
            unique_parts.append(p)
            seen.add(p)
    return unique_parts


def run_tools(choice_text: str) -> bool:
    choices = parse_choices(choice_text)
    if not choices:
        return False
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 构建序号 → 工具的映射（1-based）
    idx_to_tool = {str(i + 1): t for i, t in enumerate(TOOLS)}

    selected: list[dict] = []
    for choice in choices:
        tool = idx_to_tool.get(choice)
        if not tool:
            return False
        selected.append(tool)

    for tool in selected:
        script_path = os.path.join(base_dir, tool["entry"])
        if not os.path.exists(script_path):
            print(f"未找到脚本文件: {script_path}")
            continue
        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            script_path,
            "--server.port",
            str(tool["port"]),
        ]
        subprocess.Popen(cmd, cwd=base_dir)
        print(f'已启动: {tool["name"]} -> http://localhost:{tool["port"]}')
    return True


def main() -> None:
    while True:
        print()
        print("==== 问卷 Web 工具启动菜单 ====")
        for i, t in enumerate(TOOLS, start=1):
            print(f'{i}. {t["name"]} (http://localhost:{t["port"]})')
        print("0. 退出")
        choice = input("请输入序号（支持多选：如 1,3,5）并回车: ").strip()
        if choice == "0":
            break
        if not run_tools(choice):
            print("无效选择，请重试。")


if __name__ == "__main__":
    main()
