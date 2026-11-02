"""`scripts/usage_report.py` turns local session transcripts into per-phase and per-agent usage signals.

Transcripts here are small synthetic files in the shape Claude Code writes.
"""

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

type Script = Callable[[str], ModuleType]

FINISH = "<command-message>finish-cycle</command-message>\n<command-name>/finish-cycle</command-name>"


def usage(read: int, write_1h: int = 0, write_5m: int = 0, output: int = 10, fresh: int = 1) -> dict[str, Any]:
    return {
        "input_tokens": fresh,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write_1h + write_5m,
        "cache_creation": {"ephemeral_1h_input_tokens": write_1h, "ephemeral_5m_input_tokens": write_5m},
        "output_tokens": output,
    }


def assistant(message_id: str, model: str, use: dict[str, Any], *blocks: dict[str, Any]) -> dict[str, Any]:
    content = list(blocks) or [{"type": "text", "text": "ok"}]
    message = {"id": message_id, "model": model, "usage": use, "content": content}
    return {"type": "assistant", "timestamp": f"2026-11-01T00:00:{message_id[-1]}0Z", "message": message}


def tool(name: str, tool_id: str, **arguments: str) -> dict[str, Any]:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": arguments}


def user(text: str) -> dict[str, Any]:
    return {"type": "user", "timestamp": "2026-11-01T00:00:00Z", "message": {"role": "user", "content": text}}


def write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries) + "not json\n")


@pytest.fixture
def projects(tmp_path: Path) -> Path:
    directory = tmp_path / "projects"
    write_jsonl(
        directory / "s1.jsonl",
        [
            user("Draft the brief"),
            assistant("m1", "claude-opus-5-5", usage(1000, output=1), {"type": "text", "text": "streamed"}),
            assistant("m1", "claude-opus-5-5", usage(1000, write_1h=500, output=40)),
            assistant(
                "m2",
                "claude-opus-5-5",
                usage(1500, write_1h=100),
                tool("Agent", "t1", subagent_type="engineer", prompt="go"),
            ),
            assistant("m3", "claude-opus-5-5", usage(200_000), tool("Bash", "t2", command="uv run scripts/verify.py")),
            assistant("m3", "claude-opus-5-5", usage(200_000), tool("Bash", "t2", command="uv run scripts/verify.py")),
            user(FINISH),
            assistant("m4", "claude-sonnet-5-5", usage(40_000, write_1h=160_000)),
            assistant("m5", "<synthetic>", usage(0, output=0)),
        ],
    )
    write_jsonl(
        directory / "s1" / "subagents" / "agent-a.jsonl",
        [
            assistant("a1", "claude-sonnet-5-5", usage(0, write_5m=8000)),
            assistant("a2", "claude-sonnet-5-5", usage(8000)),
        ],
    )
    (directory / "s1" / "subagents" / "agent-a.meta.json").write_text(json.dumps({"agentType": "engineer"}))
    (directory / "s1" / "custom-title.json").write_text(json.dumps({"customTitle": "Cycle 9"}))
    return directory


def rows_by_group(script: Script, projects: Path, pricing: Any = None) -> dict[str, Any]:
    report = script("usage_report")
    session = report.load_session(projects, "s1")
    return {row.group: row for row in report.session_summaries(session, pricing, 150_000, 50_000)}


def test_lead_calls_split_into_planning_execution_and_finish(script: Script, projects: Path) -> None:
    rows = rows_by_group(script, projects)

    assert list(rows) == ["lead/planning", "lead/execution", "lead/finish", "engineer", "total"]
    assert rows["lead/planning"].calls == 1
    assert rows["lead/execution"].calls == 2
    assert rows["lead/finish"].calls == 1
    assert rows["engineer"].calls == 2
    assert rows["total"].calls == 6


def test_streamed_chunks_count_once_with_their_final_usage(script: Script, projects: Path) -> None:
    planning = rows_by_group(script, projects)["lead/planning"]

    assert (planning.output, planning.cache_write_1h, planning.first_context) == (40, 500, 1501)


def test_context_cache_and_verification_signals(script: Script, projects: Path) -> None:
    rows = rows_by_group(script, projects)

    assert rows["lead/execution"].peak_context == 200_001
    assert rows["lead/execution"].calls_over_threshold == 1
    assert rows["lead/execution"].verify_runs == 1
    assert rows["lead/finish"].cold_writes == 1
    assert rows["lead/finish"].models == "sonnet-5-5x1"
    assert rows["engineer"].cache_hit == pytest.approx(8000 / 16_002)
    assert rows["total"].models == "opus-5-5x3 sonnet-5-5x3"


def test_costs_need_prices_for_every_model(script: Script, projects: Path, tmp_path: Path) -> None:
    prices = {"input": 2.0, "output": 10.0, "cache_read": 0.2, "cache_write_5m": 2.5, "cache_write_1h": 4.0}
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(json.dumps({"models": {"claude-sonnet": prices}}))
    pricing = script("usage_report").load_pricing(pricing_file)

    rows = rows_by_group(script, projects, pricing)

    assert rows["engineer"].cost_usd == pytest.approx((2 * 2.0 + 20 * 10.0 + 8000 * 0.2 + 8000 * 2.5) / 1e6)
    assert rows["lead/finish"].cost_usd == pytest.approx((2.0 + 10 * 10.0 + 40_000 * 0.2 + 160_000 * 4.0) / 1e6)
    assert rows["lead/planning"].cost_usd is None
    assert rows["total"].cost_usd is None
    assert rows_by_group(script, projects)["engineer"].cost_usd is None


def test_a_pricing_file_with_missing_prices_is_rejected(script: Script, tmp_path: Path) -> None:
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(json.dumps({"models": {"claude-opus": {"input": 1.0}}}))

    with pytest.raises(SystemExit, match="missing numeric prices"):
        script("usage_report").load_pricing(pricing_file)


def test_plan_usage_is_shown_only_when_recorded(script: Script, projects: Path) -> None:
    report = script("usage_report")
    session = report.load_session(projects, "s1")
    rows = report.session_summaries(session, None, 150_000, 50_000)

    assert "Plan usage: 5-hour: not recorded, weekly: not recorded" in report.format_report(
        session, rows, None, None, 150_000, []
    )
    assert "Plan usage: 5-hour: 45% (as recorded), weekly: 42.5% (as recorded)" in report.format_report(
        session, rows, 45.0, 42.5, 150_000, []
    )


def test_verification_counts_only_executions_of_the_verify_script(script: Script, tmp_path: Path) -> None:
    commands = {
        "uv run scripts/verify.py": 1,
        "uv run scripts/verify.py --fix": 1,
        'cd "$S/go-poker" && uv run scripts/verify.py': 1,
        "python3 scripts/verify.py": 1,
        '(cd "$S/go-poker" && uv run scripts/verify.py)': 1,
        "uv run scripts/verify.py --fix && uv run scripts/verify.py": 2,
        "sed -n 1,40p scripts/verify.py": 0,
        "grep -n GATES scripts/verify.py": 0,
        "python3 scripts/finish_cycle.py <<'MANIFEST'\nmessage: chore: x\npath: scripts/verify.py\nMANIFEST": 0,
        "uv run pytest -q tests/game && uv run mypy src": 0,
        "uv run scripts/verify.pyc": 0,
    }
    blocks = [tool("Bash", f"t{index}", command=command) for index, command in enumerate(commands)]
    write_jsonl(tmp_path / "s2.jsonl", [assistant("m1", "claude-opus-5-5", usage(1000), *blocks)])
    report = script("usage_report")

    for command, runs in commands.items():
        assert report._verify_runs(command) == runs, command
    session = report.load_session(tmp_path, "s2")
    assert session.groups["lead/planning"].verify_runs == sum(commands.values())


@pytest.fixture
def pressure(tmp_path: Path) -> Path:
    """A session at the edge of every warning: the engineer at the context threshold, QA just above it."""
    directory = tmp_path / "pressure"
    verify_blocks = [tool("Bash", f"v{index}", command="uv run scripts/verify.py") for index in range(8)]
    write_jsonl(
        directory / "s3.jsonl",
        [
            assistant("m1", "claude-opus-5-5", usage(1000), tool("Agent", "t1", subagent_type="engineer", prompt="go")),
            assistant("m2", "claude-opus-5-5", usage(300_000), *verify_blocks),
            user(FINISH),
            assistant("m3", "claude-opus-5-5", usage(300_000, write_1h=50_000)),
        ],
    )
    subagents = directory / "s3" / "subagents"
    for name, read in (("engineer", 149_999), ("qa-engineer", 150_000), ("reviewer", 200_000)):
        write_jsonl(subagents / f"{name}.jsonl", [assistant("a1", "claude-sonnet-5-5", usage(read))])
        (subagents / f"{name}.meta.json").write_text(json.dumps({"agentType": name}))
    return directory


def test_pressure_warnings_flag_worker_context_and_verification_above_their_thresholds(
    script: Script, pressure: Path
) -> None:
    report = script("usage_report")
    rows = report.session_summaries(report.load_session(pressure, "s3"), None, 150_000, 50_000)

    assert report.pressure_warnings(rows, 150_000, 50_000, 8) == ["qa-engineer peak context 150,001 > 150,000"]
    assert report.pressure_warnings(rows, 149_999, 50_000, 7) == [
        "engineer peak context 150,000 > 149,999",
        "qa-engineer peak context 150,001 > 149,999",
        "full verifications 8 > 7",
    ]


def test_cold_finish_writes_are_flagged(script: Script, projects: Path, pressure: Path) -> None:
    report = script("usage_report")
    rows = report.session_summaries(report.load_session(projects, "s1"), None, 150_000, 50_000)
    edge = report.session_summaries(report.load_session(pressure, "s3"), None, 150_000, 49_999)

    assert report.pressure_warnings(rows, 150_000, 50_000, 8) == ["lead/finish cold cache writes 1 (each > 50,000)"]
    assert "lead/finish cold cache writes 1 (each > 49,999)" in report.pressure_warnings(edge, 150_000, 49_999, 8)


def test_warnings_are_reported_without_changing_the_exit_code(
    script: Script, pressure: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = script("usage_report")
    session = report.load_session(pressure, "s3")
    rows = report.session_summaries(session, None, 150_000, 50_000)
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(json.dumps({"models": {}}))

    assert report.format_report(session, rows, None, None, 150_000, []).endswith(
        "Warnings: none\nPlan usage: 5-hour: not recorded, weekly: not recorded\n"
    )
    exit_code = report.main(
        ["s3", "--projects-dir", str(pressure), "--pricing", str(pricing_file), "--verify-threshold", "7"]
    )

    assert exit_code == 0
    assert "Warnings:\n  qa-engineer peak context 150,001 > 150,000\n  full verifications 8 > 7\nPlan usage:" in (
        capsys.readouterr().out
    )


def test_history_is_written_only_to_a_git_ignored_path(
    script: Script, projects: Path, tmp_path: Path, git_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    report = script("usage_report")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(("git", "init", "--quiet"), cwd=repo, env=git_env, check=True)
    (repo / ".gitignore").write_text(".claude/usage/\n")
    session = report.load_session(projects, "s1")
    rows = report.session_summaries(session, None, 150_000, 50_000)
    tracked = repo / "history.csv"
    ignored = repo / ".claude" / "usage" / "history.csv"

    with pytest.raises(SystemExit, match="Git does not ignore it"):
        report.append_history(tracked, session, rows, None, None, repo)
    report.append_history(ignored, session, rows, 45.0, None, repo)
    report.append_history(ignored, session, rows, None, None, repo)

    (repo / "src").mkdir()
    monkeypatch.chdir(repo / "src")
    with pytest.raises(SystemExit, match="Git does not ignore it"):
        report.append_history(Path(".claude/usage/history.csv"), session, rows, None, None, repo)

    assert not tracked.exists()
    assert not (repo / "src" / ".claude").exists()
    lines = ignored.read_text().splitlines()
    assert lines[0].startswith("session_id,title,session_end,group,calls")
    assert len(lines) == 1 + 2 * len(rows)
    assert lines[1].startswith("s1,Cycle 9,") and lines[1].endswith(",45.0,")
