#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
依赖升级后自动检查脚本（供 AI Agent / Cursor 等统一调用）。

默认检查项：
1) 依赖矩阵校验：tests/verify_dependency_matrix.py
2) 锁定依赖 OSV 漏洞扫描（基于 requirements.lock.txt）

可选检查项：
3) 质量矩阵：tests/run_quality_matrix.py（--with-quality-matrix）

返回码：
- 0: 全部检查通过
- 1: 任一检查失败
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REQ_LOCK = ROOT / "requirements.lock.txt"


def _print(msg: str) -> None:
    print(msg, flush=True)


def run_py_script(script_rel: str) -> bool:
    script_path = ROOT / script_rel
    _print(f"[RUN] python {script_rel}")
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(ROOT),
    )
    ok = proc.returncode == 0
    _print(f"[{'PASS' if ok else 'FAIL'}] {script_rel}")
    return ok


def parse_lock_requirements(lock_path: Path) -> list[tuple[str, str]]:
    reqs: list[tuple[str, str]] = []
    for raw in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        name = name.strip()
        version = version.strip()
        if name and version:
            reqs.append((name, version))
    return reqs


def osv_scan(reqs: list[tuple[str, str]]) -> tuple[bool, list[dict]]:
    if not reqs:
        return True, []
    payload = {
        "queries": [
            {"package": {"ecosystem": "PyPI", "name": name}, "version": ver}
            for name, ver in reqs
        ]
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.osv.dev/v1/querybatch",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    findings: list[dict] = []
    results = body.get("results", [])
    for (name, ver), item in zip(reqs, results):
        vulns = item.get("vulns", []) or []
        for v in vulns:
            findings.append(
                {
                    "package": name,
                    "version": ver,
                    "id": v.get("id", "UNKNOWN"),
                    "summary": (v.get("summary") or "").strip(),
                }
            )
    return len(findings) == 0, findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run post-dependency-upgrade checks for this repository."
    )
    parser.add_argument(
        "--with-quality-matrix",
        action="store_true",
        help="Also run tests/run_quality_matrix.py (slower).",
    )
    args = parser.parse_args()

    _print("== 依赖升级后自动检查 ==")

    all_ok = True

    # 1) 依赖矩阵
    if not run_py_script("tests/verify_dependency_matrix.py"):
        all_ok = False

    # 2) OSV 漏洞扫描
    _print("[RUN] OSV scan on requirements.lock.txt")
    try:
        reqs = parse_lock_requirements(REQ_LOCK)
        osv_ok, findings = osv_scan(reqs)
        if osv_ok:
            _print("[PASS] OSV scan: no known vulnerabilities in locked set.")
        else:
            _print("[FAIL] OSV scan: vulnerabilities found.")
            for f in findings:
                _print(
                    f"  - {f['package']}=={f['version']} | {f['id']}"
                    + (f" | {f['summary']}" if f["summary"] else "")
                )
            all_ok = False
    except Exception as e:
        _print(f"[FAIL] OSV scan exception: {e}")
        all_ok = False

    # 3) 可选质量矩阵
    if args.with_quality_matrix:
        if not run_py_script("tests/run_quality_matrix.py"):
            all_ok = False

    _print("== 检查结束 ==")
    if all_ok:
        _print("RESULT: PASS")
        return 0
    _print("RESULT: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

