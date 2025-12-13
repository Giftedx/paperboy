#!/usr/bin/env python3
"""
Project healthcheck script.

Runs a sequence of checks to verify the integrity and readiness of the system:
  1) run_tests.py: Static analysis and structure checks.
  2) which_requests.py: Verifies the requests library implementation.
  3) main.py (dry-run): Simulates the pipeline execution.

Exits non-zero if any step fails.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Tuple

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None


def run_cmd(cmd: List[str], env: dict | None = None) -> Tuple[int, str]:
    """Runs a shell command and captures its output.

    Args:
        cmd (List[str]): The command and its arguments.
        env (dict | None): Environment variables to use.

    Returns:
        Tuple[int, str]: A tuple containing the return code and the combined stdout/stderr output.
    """
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
    """Main healthcheck execution routine.

    Returns:
        int: 0 if all checks pass, 1 otherwise.
    """
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

    if RICH_AVAILABLE:
        console.print(Panel.fit("[bold blue]System Health Check[/bold blue]"))

    for cmd, env, label in steps:
        if RICH_AVAILABLE:
            console.rule(f"[bold]{label}[/bold]")
        else:
            print(f"\n=== {label} ===")

        code, out = run_cmd(cmd, env=env)

        if RICH_AVAILABLE:
            if code == 0:
                console.print(f"[green]✔ PASS[/green]")
                # Only print output if strictly necessary or verbose?
                # For now let's print it dim/grey
                console.print(out, style="dim")
            else:
                console.print(f"[red]✖ FAIL[/red]")
                console.print(out, style="red")
        else:
            print(out)
            if code != 0:
                print(f"[ERROR] Step failed with exit code {code}: {label}")

        if code != 0:
            overall_ok = False

    if overall_ok:
        if RICH_AVAILABLE:
            console.print(Panel("[bold green]All health checks passed.[/bold green]", expand=False))
        else:
            print("\nAll health checks passed.")
        return 0
    else:
        if RICH_AVAILABLE:
            console.print(Panel("[bold red]Some health checks failed.[/bold red]", expand=False))
        else:
            print("\nSome health checks failed.")
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
