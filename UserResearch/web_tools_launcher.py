"""Web 工具启动菜单：从 tool_registry 读取工具列表，用户选择后启动对应 Streamlit 应用。"""

import os
import subprocess
import sys

from tool_registry import TOOLS


def parse_choices(choice_text: str) -> list[str]:
    normalized = choice_text.replace("，", ",").replace(" ", ",")
    parts = [p.strip() for p in normalized.split(",") if p.strip()]
    return list(dict.fromkeys(parts))


def run_tools(choice_text: str) -> tuple[bool, list[subprocess.Popen]]:
    choices = parse_choices(choice_text)
    if not choices:
        return False, []
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 构建序号 → 工具的映射（1-based）
    idx_to_tool = {str(i + 1): t for i, t in enumerate(TOOLS)}

    selected: list[dict] = []
    for choice in choices:
        tool = idx_to_tool.get(choice)
        if not tool:
            return False, []
        selected.append(tool)

    launched: list[subprocess.Popen] = []
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
        launched.append(subprocess.Popen(cmd, cwd=base_dir))
        print(f'已启动: {tool["name"]} -> http://localhost:{tool["port"]}')
    return True, launched


def main() -> None:
    managed_processes: list[subprocess.Popen] = []
    while True:
        print()
        print("==== Web 工具启动菜单 ====")
        for i, t in enumerate(TOOLS, start=1):
            print(f'{i}. {t["name"]} (http://localhost:{t["port"]})')
        print("0. 退出")
        choice = input("请输入序号（可多选，如 1,3,5）并回车: ").strip()
        if choice == "0":
            break
        ok, launched = run_tools(choice)
        if not ok:
            print("无效选择，请重试。")
            continue
        managed_processes.extend(launched)

    # 托管模式：退出启动器时，优雅终止本次启动的 Streamlit 子进程，避免端口占用累积。
    running = [p for p in managed_processes if p.poll() is None]
    for p in running:
        p.terminate()
    already_exited = len(managed_processes) - len(running)
    msg = f"已退出启动器。已向 {len(running)} 个仍在运行的子进程发送终止信号。"
    if already_exited:
        msg += f"（另有 {already_exited} 个已自行结束。）"
    print(msg)


if __name__ == "__main__":
    main()
