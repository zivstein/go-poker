"""`scripts/verify.py` runs every gate, keeps real exit codes, and ends with one unambiguous verdict.

The gates here are small Python commands, so the suite never runs itself.
"""

import io
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

type Script = Callable[[str], ModuleType]


def step(verify: ModuleType, name: str, code: str) -> object:
    return verify.Step(name, (sys.executable, "-c", code))


def run(verify: ModuleType, gates: list[object], tmp_path: Path, fixes: tuple[object, ...] = ()) -> tuple[int, str]:
    out = io.StringIO()
    code = verify.run(gates, fixes, tmp_path, out)
    return code, out.getvalue()


def test_the_standard_gates_are_the_four_project_checks(script: Script) -> None:
    verify = script("verify")

    assert [gate.command for gate in verify.GATES] == [
        ("uv", "run", "ruff", "check", "."),
        ("uv", "run", "ruff", "format", "--check", "."),
        ("uv", "run", "mypy", "src"),
        ("uv", "run", "pytest", "-q"),
    ]


def test_passing_gates_print_one_line_each_and_pass(script: Script, tmp_path: Path) -> None:
    verify = script("verify")
    gates = [step(verify, "first", "print('noise'); print('all good')"), step(verify, "second", "pass")]

    code, output = run(verify, gates, tmp_path)

    assert code == 0
    lines = output.splitlines()
    assert lines[0].startswith("PASS  first (") and lines[0].endswith(" all good")
    assert lines[1].startswith("PASS  second (")
    assert lines[2:] == ["VERIFY: PASS"]
    assert "noise" not in output


def test_a_failing_gate_prints_its_full_output_and_every_gate_still_runs(script: Script, tmp_path: Path) -> None:
    verify = script("verify")
    marker = tmp_path / "later-gate-ran"
    gates = [
        step(
            verify,
            "broken",
            "import sys; print('detail one', flush=True); print('detail two', file=sys.stderr); sys.exit(3)",
        ),
        step(verify, "later", f"open({str(marker)!r}, 'w').close()"),
    ]

    code, output = run(verify, gates, tmp_path)

    assert code == 1
    assert "FAIL  broken (exit 3," in output
    assert "detail one\ndetail two\n" in output
    assert marker.exists()
    assert output.endswith("Failed gates: broken\nVERIFY: FAIL\n")


def test_a_failure_after_a_pass_still_fails_the_run(script: Script, tmp_path: Path) -> None:
    verify = script("verify")
    gates = [step(verify, "fine", "pass"), step(verify, "last", "import sys; sys.exit(1)")]

    code, output = run(verify, gates, tmp_path)

    assert code == 1
    assert output.splitlines()[-1] == "VERIFY: FAIL"


def test_a_gate_killed_by_a_signal_fails(script: Script, tmp_path: Path) -> None:
    verify = script("verify")
    gates = [step(verify, "killed", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)")]

    code, output = run(verify, gates, tmp_path)

    assert code == 1
    assert "FAIL  killed (exit -15," in output


def test_a_gate_that_cannot_start_fails(script: Script, tmp_path: Path) -> None:
    verify = script("verify")
    gates = [verify.Step("missing", ("definitely-not-a-real-command-xyz",))]

    code, output = run(verify, gates, tmp_path)

    assert code == 1
    assert "FAIL  missing (exit 127," in output
    assert "could not run definitely-not-a-real-command-xyz" in output


def test_fix_steps_run_first_and_never_decide_the_verdict(script: Script, tmp_path: Path) -> None:
    verify = script("verify")
    order = tmp_path / "order"
    fixes = (step(verify, "fixer", f"import sys; open({str(order)!r}, 'a').write('fix '); sys.exit(1)"),)
    gates = [step(verify, "gate", f"open({str(order)!r}, 'a').write('gate')")]

    code, output = run(verify, gates, tmp_path, fixes)

    assert code == 0
    assert order.read_text() == "fix gate"
    assert output.startswith("FIX   fixer (exit 1)")
    assert output.endswith("VERIFY: PASS\n")


def test_fix_steps_run_only_with_the_fix_flag(script: Script, monkeypatch: pytest.MonkeyPatch) -> None:
    verify = script("verify")
    calls = []
    monkeypatch.setattr(verify, "run", lambda gates, fixes, cwd, out: calls.append((gates, fixes)) or 0)

    assert verify.main([]) == 0
    assert verify.main(["--fix"]) == 0

    assert calls == [(verify.GATES, ()), (verify.GATES, verify.FIXES)]
    assert [fix.command for fix in verify.FIXES] == [
        ("uv", "run", "ruff", "check", "--fix", "."),
        ("uv", "run", "ruff", "format", "."),
    ]
