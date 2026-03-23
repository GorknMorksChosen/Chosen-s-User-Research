import os
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_TESTS_DIR = Path(__file__).resolve().parent

SCRIPT_TIMEOUT = 180  # 单脚本最长允许 180 秒，防止死循环挂起（L14）


def run_one(rel_name: str):
    script_path = str(_TESTS_DIR / rel_name)
    cmd = [sys.executable, script_path]
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_ROOT),
            text=True,
            capture_output=True,
            timeout=SCRIPT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return {
            "script": rel_name,
            "ok": False,
            "code": -1,
            "duration": duration,
            "stdout": "",
            "stderr": f"[TIMEOUT] 脚本超过 {SCRIPT_TIMEOUT}s 未结束，已强制终止。",
        }
    duration = time.time() - start
    return {
        "script": rel_name,
        "ok": proc.returncode == 0,
        "code": proc.returncode,
        "duration": duration,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main():
    scripts = [
        "verify_dependency_matrix.py",
        "verify_no_legacy_quant_engine_import.py",
        "test_migration.py",
        "verify_current_v1_logic.py",
        "auto_verify_v1.py",  # 核心 schema 验收（test_assets/mock，断言 p_value/effect_size/assumption_checks）
        "verify_standard_regression_core.py",
        "verify_clustering_recommendation_core.py",
        "verify_text_ingestion_io.py",
        "verify_p2_baseline.py",
        "verify_p24_clustering.py",
    ]
    for s in scripts:
        abs_s = str(_TESTS_DIR / s)
        if not os.path.exists(abs_s):
            print(f"缺少脚本: {abs_s}")
            return 1
    results = [run_one(s) for s in scripts]
    print("=== 质量矩阵执行结果 ===")
    failed = 0
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        print(f"[{status}] {r['script']} ({r['duration']:.2f}s)")
        if not r["ok"]:
            failed += 1
            if r["stdout"]:
                print("--- stdout ---")
                print(r["stdout"][-2000:])
            if r["stderr"]:
                print("--- stderr ---")
                print(r["stderr"][-2000:])
    if failed > 0:
        print(f"质量矩阵失败: {failed}/{len(results)}")
        return 1
    print(f"质量矩阵通过: {len(results)}/{len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
