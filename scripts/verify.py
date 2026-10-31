"""Run the standard verification gates and report one unambiguous verdict.

Usage, from anywhere inside the repository:

    uv run scripts/verify.py          # the standard verification gate
    uv run scripts/verify.py --fix    # Engineer only, while working: apply Ruff fixes and formatting first

Every gate runs, even after an earlier gate fails. A passing gate prints one line; a failing gate prints its full
output. The last line is exactly `VERIFY: PASS` or `VERIFY: FAIL`, and the exit code is 0 only when every gate passed.
`--fix` rewrites files before the gates run; its own results never decide the verdict.

The script uses only the standard library and runs on Python 3.9+, because `scripts/finish_cycle.py` runs it with
the interpreter that runs the closeout.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Step:
    name: str
    command: tuple[str, ...]


GATES = (
    Step("ruff check", ("uv", "run", "ruff", "check", ".")),
    Step("ruff format", ("uv", "run", "ruff", "format", "--check", ".")),
    Step("mypy", ("uv", "run", "mypy", "src")),
    Step("pytest", ("uv", "run", "pytest", "-q")),
)

FIXES = (
    Step("ruff fix", ("uv", "run", "ruff", "check", "--fix", ".")),
    Step("ruff format", ("uv", "run", "ruff", "format", ".")),
)


@dataclass(frozen=True)
class Result:
    returncode: int
    output: str
    seconds: float


def run_step(step: Step, cwd: Path) -> Result:
    """Run one step to completion, capturing stdout and stderr together. A step that cannot start fails."""
    started = time.monotonic()
    try:
        completed = subprocess.run(
            step.command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False
        )
    except OSError as error:
        return Result(127, f"could not run {' '.join(step.command)}: {error}\n", time.monotonic() - started)
    return Result(completed.returncode, completed.stdout, time.monotonic() - started)


def _summary(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def run(gates: Sequence[Step], fixes: Sequence[Step], cwd: Path, out: TextIO) -> int:
    """Run the fixes (if any), then every gate; return 0 only when every gate exited 0."""
    for step in fixes:
        result = run_step(step, cwd)
        out.write(f"FIX   {step.name} (exit {result.returncode}) {_summary(result.output)}\n")
        if result.returncode != 0:
            out.write(result.output)

    failed = []
    for step in gates:
        result = run_step(step, cwd)
        if result.returncode == 0:
            out.write(f"PASS  {step.name} ({result.seconds:.1f}s) {_summary(result.output)}\n")
            continue
        failed.append(step.name)
        out.write(f"FAIL  {step.name} (exit {result.returncode}, {result.seconds:.1f}s)\n")
        out.write(f"----- {step.name} output -----\n")
        out.write(result.output)
        if result.output and not result.output.endswith("\n"):
            out.write("\n")
        out.write(f"----- end {step.name} output -----\n")

    if failed:
        out.write(f"Failed gates: {', '.join(failed)}\n")
        out.write("VERIFY: FAIL\n")
        return 1
    out.write("VERIFY: PASS\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the standard verification gates.")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Engineer only: apply Ruff fixes and formatting before the gates (rewrites files)",
    )
    arguments = parser.parse_args(argv)
    code = run(GATES, FIXES if arguments.fix else (), REPO_ROOT, sys.stdout)
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
