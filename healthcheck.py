#!/usr/bin/env python3
"""
Project healthcheck script.
Runs:
  1) run_tests.py
  2) which_requests.py
  3) Dry-run of main.py

Exits non-zero if any step fails.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Tuple


def run_cmd(cmd: List[str], env: dict | None = None) -> Tuple[int, str]:
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        out, _ = proc.communicate()
        text = out.decode('utf-8', errors='replace')
        return proc.returncode, text
    except FileNotFoundError as exc:
        return 127, f"Command not found: {' '.join(cmd)}\n{exc}"
    except Exception as exc:
        return 1, f"Error running: {' '.join(cmd)}\n{exc}"


def main() -> int:
    steps = []

    # 1) run_tests.py
    steps.append((['python3', 'run_tests.py'], None, 'Run tests'))

    # 2) which_requests.py
    steps.append((['python3', 'which_requests.py'], None, "Check requests implementation"))

    # 3) Dry-run main.py
    env = os.environ.copy()
    env['MAIN_PY_DRY_RUN'] = 'true'
    steps.append((['python3', 'main.py'], env, 'Dry-run pipeline'))

    overall_ok = True
    for cmd, env, label in steps:
        print(f"\n=== {label} ===")
        code, out = run_cmd(cmd, env=env)
        print(out)
        if code != 0:
            print(f"[ERROR] Step failed with exit code {code}: {label}")
            overall_ok = False

    if overall_ok:
        print("\nAll health checks passed.")
        return 0
    else:
        print("\nSome health checks failed.")
        return 1


if __name__ == '__main__':
    raise SystemExit(main())