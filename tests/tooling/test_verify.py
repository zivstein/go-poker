"""`scripts/verify.py` runs every gate, keeps real exit codes, and ends with one unambiguous verdict.

The gates here are small Python commands, so the suite never runs itself.
"""

import io
import json
import re
import shutil
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


def test_the_standard_gates_are_the_python_checks_then_the_web_checks(script: Script) -> None:
    verify = script("verify")

    assert [(gate.directory, gate.command) for gate in verify.GATES] == [
        (".", ("uv", "run", "ruff", "check", ".")),
        (".", ("uv", "run", "ruff", "format", "--check", ".")),
        (".", ("uv", "run", "mypy", "src")),
        (".", ("uv", "run", "pytest", "-q")),
        ("web", ("node_modules/.bin/tsc", "--noEmit")),
        ("web", ("node_modules/.bin/biome", "ci", "--colors=off", ".")),
        ("web", ("node_modules/.bin/vitest", "run")),
        ("web", ("node_modules/.bin/vite", "build")),
    ]
    assert [gate.prerequisite for gate in verify.GATES] == [None] * 4 + [verify.web_toolchain_problem] * 4


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
    assert [(fix.directory, fix.command, fix.prerequisite) for fix in verify.FIXES] == [
        (".", ("uv", "run", "ruff", "check", "--fix", "."), None),
        (".", ("uv", "run", "ruff", "format", "."), None),
        ("web", ("node_modules/.bin/biome", "check", "--write", "--colors=off", "."), verify.web_toolchain_problem),
    ]


def test_a_step_runs_in_its_own_directory_under_the_root(script: Script, tmp_path: Path) -> None:
    verify = script("verify")
    (tmp_path / "web").mkdir()
    record = tmp_path / "where"
    gates = [
        verify.Step("here", (sys.executable, "-c", f"import os; open({str(record)!r}, 'w').write(os.getcwd())"), "web")
    ]

    code, _ = run(verify, gates, tmp_path)

    assert code == 0
    assert Path(record.read_text()).resolve() == (tmp_path / "web").resolve()


def test_a_gate_whose_prerequisite_fails_fails_without_running_and_the_others_still_run(
    script: Script, tmp_path: Path
) -> None:
    verify = script("verify")
    checks = []
    ran = tmp_path / "ran"

    def missing_toolchain(root: Path) -> str:
        checks.append(root)
        return "Node.js is not on PATH"

    gates = [
        verify.Step(
            "needs node", (sys.executable, "-c", f"open({str(ran)!r}, 'a').write('node ')"), ".", missing_toolchain
        ),
        verify.Step("also needs node", (sys.executable, "-c", "pass"), ".", missing_toolchain),
        step(verify, "plain", f"open({str(ran)!r}, 'a').write('plain')"),
    ]

    code, output = run(verify, gates, tmp_path)

    assert code == 1
    assert ran.read_text() == "plain"
    assert checks == [tmp_path]
    assert output.splitlines()[:2] == [
        "FAIL  needs node (not run: Node.js is not on PATH)",
        "FAIL  also needs node (not run: Node.js is not on PATH)",
    ]
    assert output.endswith("Failed gates: needs node, also needs node\nVERIFY: FAIL\n")


def test_a_fix_whose_prerequisite_fails_is_reported_and_never_decides_the_verdict(
    script: Script, tmp_path: Path
) -> None:
    verify = script("verify")
    fixes = (verify.Step("web fix", (sys.executable, "-c", "pass"), ".", lambda root: "no web dependencies"),)

    code, output = run(verify, [step(verify, "gate", "pass")], tmp_path, fixes)

    assert code == 0
    assert output.splitlines()[0] == "FIX   web fix (not run: no web dependencies)"
    assert output.endswith("VERIFY: PASS\n")


WEB_TOOLS = ("tsc", "biome", "vitest", "vite")


@pytest.fixture
def web_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A root with the pinned `web/.nvmrc`, every Web tool installed, and a `node` on PATH that reports 26.2.0."""
    web = tmp_path / "root" / "web"
    (web / "node_modules" / ".bin").mkdir(parents=True)
    (web / ".nvmrc").write_text("26.13.1\n")
    for tool in WEB_TOOLS:
        (web / "node_modules" / ".bin" / tool).write_text("")
    fake_node("v26.2.0", tmp_path / "bin")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    return tmp_path / "root"


def fake_node(version: str, directory: Path) -> None:
    directory.mkdir(exist_ok=True)
    node = directory / "node"
    node.write_text(f"#!/bin/sh\necho {version}\n")
    node.chmod(0o755)


def test_the_web_toolchain_is_ready_with_node_on_the_pinned_line_and_every_tool_installed(
    script: Script, web_root: Path
) -> None:
    assert script("verify").web_toolchain_problem(web_root) is None


def test_the_web_toolchain_needs_node_on_path(script: Script, web_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(web_root / "nothing-here"))

    assert script("verify").web_toolchain_problem(web_root) == (
        "Node.js is not on PATH; install Node 26 (26.13.1 is pinned in web/.nvmrc)"
    )


def test_the_web_toolchain_needs_node_on_the_pinned_major_line(script: Script, web_root: Path, tmp_path: Path) -> None:
    fake_node("v24.22.3", tmp_path / "bin")

    assert script("verify").web_toolchain_problem(web_root) == (
        "Node v24.22.3 is not on the pinned Node 26 line (26.13.1 in web/.nvmrc)"
    )


def test_the_web_toolchain_needs_the_pinned_node_version_file(script: Script, web_root: Path) -> None:
    (web_root / "web" / ".nvmrc").unlink()

    assert script("verify").web_toolchain_problem(web_root) == "web/.nvmrc is missing; it pins the Node version"


def test_the_web_toolchain_needs_the_installed_web_dependencies(script: Script, web_root: Path) -> None:
    verify = script("verify")
    shutil.rmtree(web_root / "web" / "node_modules")

    assert verify.web_toolchain_problem(web_root) == (
        "the Web dependencies are not installed (node_modules/.bin/biome, node_modules/.bin/tsc, "
        "node_modules/.bin/vite, node_modules/.bin/vitest missing); run `npm ci` in web/"
    )


def test_the_web_toolchain_names_each_missing_web_tool(script: Script, web_root: Path) -> None:
    (web_root / "web" / "node_modules" / ".bin" / "vitest").unlink()

    assert script("verify").web_toolchain_problem(web_root) == (
        "the Web dependencies are not installed (node_modules/.bin/vitest missing); run `npm ci` in web/"
    )


def test_the_pinned_node_version_and_the_web_engines_range_name_the_same_major_line() -> None:
    web = Path(__file__).resolve().parents[2] / "web"
    pinned = (web / ".nvmrc").read_text().strip()
    engines = json.loads((web / "package.json").read_text())["engines"]

    assert re.fullmatch(r"\d+\.\d+\.\d+", pinned)
    assert engines == {"node": f"^{pinned.split('.')[0]}.0.0"}
