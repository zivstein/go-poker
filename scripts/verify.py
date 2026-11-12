"""Run the standard verification gates and report one unambiguous verdict.

Usage, from anywhere inside the repository:

    uv run scripts/verify.py          # the standard verification gate
    uv run scripts/verify.py --fix    # Engineer only, while working: apply Ruff and Biome fixes and formatting first

The gates are the Python gates (Ruff check, Ruff format check, mypy, pytest), then the Web gates in `web/`
(`tsc --noEmit`, `biome ci`, `vitest run`, `vite build`). Every gate runs, even after an earlier gate fails. A passing
gate prints one line; a failing gate prints its full output. The last line is exactly `VERIFY: PASS` or `VERIFY: FAIL`,
and the exit code is 0 only when every gate passed. `--fix` rewrites files before the gates run; its own results never
decide the verdict.

The Web gates need Node on the major line pinned in `web/.nvmrc` and the dependencies that `npm ci` installs in `web/`.
When either is missing, every Web gate fails without running and says why. They are never skipped silently.

The script uses only the standard library and runs on Python 3.9+, because `scripts/finish_cycle.py` runs it with
the interpreter that runs the closeout.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TextIO

REPO_ROOT = Path(__file__).resolve().parent.parent

WEB = "web"
NODE_VERSION_FILE = ".nvmrc"

# Given the repository root: why a step cannot run there, or None when it can.
Prerequisite = Callable[[Path], Optional[str]]


@dataclass(frozen=True)
class Step:
    name: str
    command: tuple[str, ...]
    directory: str = "."  # where the command runs, relative to the repository root
    prerequisite: Prerequisite | None = None


def web_toolchain_problem(root: Path) -> str | None:
    """Why the Web steps cannot run in `root`: no Node on PATH, Node off the pinned major line, or a Web tool not
    installed. None when all of them are present."""
    web = root / WEB
    try:
        pinned = (web / NODE_VERSION_FILE).read_text().strip()
    except OSError:
        return f"{WEB}/{NODE_VERSION_FILE} is missing; it pins the Node version"
    line = pinned.lstrip("v").split(".")[0]
    node = shutil.which("node")
    if node is None:
        return f"Node.js is not on PATH; install Node {line} ({pinned} is pinned in {WEB}/{NODE_VERSION_FILE})"
    try:
        version = subprocess.run(
            (node, "--version"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False
        ).stdout.strip()
    except OSError as error:
        return f"could not run {node} --version: {error}"
    if version.lstrip("v").split(".")[0] != line:
        return f"Node {version} is not on the pinned Node {line} line ({pinned} in {WEB}/{NODE_VERSION_FILE})"
    missing = sorted({step.command[0] for step in WEB_GATES if not (root / step.directory / step.command[0]).is_file()})
    if missing:
        return f"the Web dependencies are not installed ({', '.join(missing)} missing); run `npm ci` in {WEB}/"
    return None


def _web(name: str, tool: str, *arguments: str) -> Step:
    return Step(name, (f"node_modules/.bin/{tool}", *arguments), WEB, web_toolchain_problem)


PYTHON_GATES = (
    Step("ruff check", ("uv", "run", "ruff", "check", ".")),
    Step("ruff format", ("uv", "run", "ruff", "format", "--check", ".")),
    Step("mypy", ("uv", "run", "mypy", "src")),
    Step("pytest", ("uv", "run", "pytest", "-q")),
)

WEB_GATES = (
    _web("tsc", "tsc", "--noEmit"),
    _web("biome ci", "biome", "ci", "--colors=off", "."),
    _web("vitest", "vitest", "run"),
    _web("vite build", "vite", "build"),
)

GATES = PYTHON_GATES + WEB_GATES

FIXES = (
    Step("ruff fix", ("uv", "run", "ruff", "check", "--fix", ".")),
    Step("ruff format", ("uv", "run", "ruff", "format", ".")),
    _web("biome fix", "biome", "check", "--write", "--colors=off", "."),
)


@dataclass(frozen=True)
class Result:
    returncode: int
    output: str
    seconds: float


def run_step(step: Step, cwd: Path) -> Result:
    """Run one step to completion in `cwd / step.directory`, capturing stdout and stderr together. A step that
    cannot start fails."""
    started = time.monotonic()
    try:
        completed = subprocess.run(
            step.command,
            cwd=cwd / step.directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except OSError as error:
        return Result(127, f"could not run {' '.join(step.command)}: {error}\n", time.monotonic() - started)
    return Result(completed.returncode, completed.stdout, time.monotonic() - started)


def _summary(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def run(gates: Sequence[Step], fixes: Sequence[Step], cwd: Path, out: TextIO) -> int:
    """Run the fixes (if any), then every gate; return 0 only when every gate exited 0. A step whose prerequisite
    reports a problem does not run; as a gate, it fails."""
    problems: dict[Prerequisite, str | None] = {}

    def problem(step: Step) -> str | None:
        if step.prerequisite is None:
            return None
        if step.prerequisite not in problems:
            problems[step.prerequisite] = step.prerequisite(cwd)
        return problems[step.prerequisite]

    for step in fixes:
        blocked = problem(step)
        if blocked is not None:
            out.write(f"FIX   {step.name} (not run: {blocked})\n")
            continue
        result = run_step(step, cwd)
        out.write(f"FIX   {step.name} (exit {result.returncode}) {_summary(result.output)}\n")
        if result.returncode != 0:
            out.write(result.output)

    failed = []
    for step in gates:
        blocked = problem(step)
        if blocked is not None:
            failed.append(step.name)
            out.write(f"FAIL  {step.name} (not run: {blocked})\n")
            continue
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
        help="Engineer only: apply Ruff and Biome fixes and formatting before the gates (rewrites files)",
    )
    arguments = parser.parse_args(argv)
    code = run(GATES, FIXES if arguments.fix else (), REPO_ROOT, sys.stdout)
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
