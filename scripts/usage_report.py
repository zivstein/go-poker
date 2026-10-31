"""Summarize the cost signals of local Claude Code sessions for this project.

Usage:

    uv run scripts/usage_report.py                    # the most recent session
    uv run scripts/usage_report.py SESSION_ID ...     # specific sessions
    uv run scripts/usage_report.py --latest 5         # the five most recent sessions
    uv run scripts/usage_report.py --five-hour 45 --weekly 42 --append

It reads the session transcripts Claude Code keeps on this machine (`~/.claude/projects/<project>/`, or under
`$CLAUDE_CONFIG_DIR`), including each session's subagents. For the Lead it splits calls into phases: `planning`
until the first Agent launch, `execution` after it, and `finish` after `/finish-cycle` is invoked. Subagents
are grouped by agent type. Per group it reports calls, model split, first-call and peak context, calls above the
context threshold, cache hit rate (cache reads over all input), cold cache writes (calls writing more than the
cold-write threshold to cache, typically a model switch or a fresh context), and verification runs.

Costs appear only with a pricing file: `--pricing FILE`, or `.claude/usage/pricing.json` when present. Prices are
USD per million tokens, per model id; a key also matches model ids it prefixes. A group with an unpriced model shows
no cost rather than a partial one. Cache writes without a 5-minute/1-hour breakdown are priced as 5-minute writes.

    {"models": {"claude-opus-5-5": {"input": 0.0, "output": 0.0, "cache_read": 0.0,
                                    "cache_write_5m": 0.0, "cache_write_1h": 0.0}}}

Plan-limit usage is not in the transcripts. `--five-hour` and `--weekly` record percentages read from the app's
usage display; without them the report says "not recorded". Never pass estimates.

`--append` adds one CSV row per group to `.claude/usage/history.csv` (or `--history FILE`). It refuses any path
Git does not ignore, so personal usage history cannot be committed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
USAGE_DIR = REPO_ROOT / ".claude" / "usage"
FINISH_COMMAND = "<command-name>/finish-cycle</command-name>"
AGENT_TOOLS = frozenset({"Agent", "Task"})
PRICE_KEYS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")
CSV_FIELDS = (
    "session_id",
    "title",
    "session_end",
    "group",
    "calls",
    "models",
    "input",
    "cache_read",
    "cache_write_5m",
    "cache_write_1h",
    "output",
    "first_context",
    "peak_context",
    "calls_over_threshold",
    "cache_hit",
    "cold_writes",
    "verify_runs",
    "cost_usd",
    "five_hour_pct",
    "weekly_pct",
)


@dataclass(frozen=True)
class Call:
    model: str
    input: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int
    output: int

    @property
    def context(self) -> int:
        return self.input + self.cache_read + self.cache_write_5m + self.cache_write_1h

    @property
    def cache_write(self) -> int:
        return self.cache_write_5m + self.cache_write_1h


@dataclass
class Group:
    name: str
    calls: list[Call] = field(default_factory=list)
    verify_runs: int = 0


@dataclass
class Session:
    session_id: str
    title: str
    start: str
    end: str
    groups: dict[str, Group]


def project_dir(repo_root: Path) -> Path:
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    return base / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(repo_root))


def _entries(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                yield entry


def _call(model: str, usage: dict[str, Any]) -> Call:
    write_total = int(usage.get("cache_creation_input_tokens") or 0)
    breakdown = usage.get("cache_creation") or {}
    write_1h = int(breakdown.get("ephemeral_1h_input_tokens") or 0)
    return Call(
        model=model,
        input=int(usage.get("input_tokens") or 0),
        cache_read=int(usage.get("cache_read_input_tokens") or 0),
        cache_write_5m=write_total - write_1h,
        cache_write_1h=write_1h,
        output=int(usage.get("output_tokens") or 0),
    )


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(block.get("text", "") for block in content if isinstance(block, dict))
    return ""


def _is_verification(command: str) -> bool:
    return "scripts/verify.py" in command or ("pytest" in command and "mypy" in command)


def read_transcript(path: Path, lead: bool) -> tuple[dict[str, Group], list[str]]:
    """Calls grouped by phase (Lead) or into one group (subagent), and the transcript's timestamps.

    Streamed chunks of one response share a message id; the last chunk carries its final usage.
    """
    phase = "planning" if lead else "agent"
    groups: dict[str, Group] = {}
    calls: dict[str, tuple[str, Call]] = {}
    tool_uses: set[str] = set()
    timestamps = []
    for entry in _entries(path):
        if isinstance(entry.get("timestamp"), str):
            timestamps.append(entry["timestamp"])
        raw_message = entry.get("message")
        message: dict[str, Any] = raw_message if isinstance(raw_message, dict) else {}
        if entry.get("type") == "user" and lead and FINISH_COMMAND in _text(message.get("content")):
            phase = "finish"
        if entry.get("type") != "assistant" or message.get("model") in (None, "<synthetic>"):
            continue
        group = groups.setdefault(phase, Group(phase))
        for block in message.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use" or block.get("id") in tool_uses:
                continue
            tool_uses.add(str(block.get("id")))
            if lead and phase == "planning" and block.get("name") in AGENT_TOOLS:
                phase = "execution"
                group = groups.setdefault(phase, Group(phase))
            command = (block.get("input") or {}).get("command")
            if block.get("name") == "Bash" and isinstance(command, str) and _is_verification(command):
                group.verify_runs += 1
        message_id = str(message.get("id") or entry.get("uuid"))
        known = calls.get(message_id)
        calls[message_id] = (known[0] if known else group.name, _call(message["model"], message.get("usage") or {}))
    for group_name, call in calls.values():
        groups.setdefault(group_name, Group(group_name)).calls.append(call)
    return groups, timestamps


def load_session(directory: Path, session_id: str) -> Session:
    lead_path = directory / f"{session_id}.jsonl"
    if not lead_path.is_file():
        raise SystemExit(f"no transcript for session {session_id} in {directory}")
    lead_groups, timestamps = read_transcript(lead_path, lead=True)
    groups = {
        f"lead/{name}": Group(f"lead/{name}", group.calls, group.verify_runs) for name, group in lead_groups.items()
    }
    for path in sorted((directory / session_id / "subagents").glob("*.jsonl")):
        meta_path = path.with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
        name = str(meta.get("agentType") or "subagent")
        agent_groups, agent_timestamps = read_transcript(path, lead=False)
        timestamps += agent_timestamps
        target = groups.setdefault(name, Group(name))
        for group in agent_groups.values():
            target.calls += group.calls
            target.verify_runs += group.verify_runs
    title_path = directory / session_id / "custom-title.json"
    title = str(json.loads(title_path.read_text()).get("customTitle", "")) if title_path.is_file() else ""
    timestamps.sort()
    return Session(session_id, title, timestamps[0] if timestamps else "", timestamps[-1] if timestamps else "", groups)


def latest_sessions(directory: Path, count: int) -> list[str]:
    transcripts = [path for path in directory.glob("*.jsonl") if path.stat().st_size > 0]
    transcripts.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [path.stem for path in transcripts[:count]]


def load_pricing(path: Path | None) -> dict[str, dict[str, float]] | None:
    if path is None:
        return None
    models = json.loads(path.read_text()).get("models")
    if not isinstance(models, dict):
        raise SystemExit(f"{path}: expected an object with a 'models' mapping")
    for model, prices in models.items():
        missing = [key for key in PRICE_KEYS if not isinstance(prices.get(key), (int, float))]
        if missing:
            raise SystemExit(f"{path}: {model} is missing numeric prices: {', '.join(missing)}")
    return {model: {key: float(prices[key]) for key in PRICE_KEYS} for model, prices in models.items()}


def price_for(model: str, pricing: dict[str, dict[str, float]]) -> dict[str, float] | None:
    if model in pricing:
        return pricing[model]
    prefixes = [key for key in pricing if model.startswith(key)]
    return pricing[max(prefixes, key=len)] if prefixes else None


def cost(calls: Sequence[Call], pricing: dict[str, dict[str, float]] | None) -> float | None:
    if pricing is None:
        return None
    total = 0.0
    for call in calls:
        prices = price_for(call.model, pricing)
        if prices is None:
            return None
        total += (
            call.input * prices["input"]
            + call.output * prices["output"]
            + call.cache_read * prices["cache_read"]
            + call.cache_write_5m * prices["cache_write_5m"]
            + call.cache_write_1h * prices["cache_write_1h"]
        ) / 1_000_000
    return total


@dataclass(frozen=True)
class Summary:
    group: str
    calls: int
    models: str
    input: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int
    output: int
    first_context: int
    peak_context: int
    calls_over_threshold: int
    cache_hit: float | None
    cold_writes: int
    verify_runs: int
    cost_usd: float | None


def summarize(
    name: str,
    calls: Sequence[Call],
    verify_runs: int,
    pricing: dict[str, dict[str, float]] | None,
    context_threshold: int,
    cold_write_threshold: int,
) -> Summary:
    models = Counter(call.model.removeprefix("claude-") for call in calls)
    all_input = sum(call.context for call in calls)
    return Summary(
        group=name,
        calls=len(calls),
        models=" ".join(f"{model}x{count}" for model, count in models.most_common()),
        input=sum(call.input for call in calls),
        cache_read=sum(call.cache_read for call in calls),
        cache_write_5m=sum(call.cache_write_5m for call in calls),
        cache_write_1h=sum(call.cache_write_1h for call in calls),
        output=sum(call.output for call in calls),
        first_context=calls[0].context if calls else 0,
        peak_context=max((call.context for call in calls), default=0),
        calls_over_threshold=sum(1 for call in calls if call.context > context_threshold),
        cache_hit=sum(call.cache_read for call in calls) / all_input if all_input else None,
        cold_writes=sum(1 for call in calls if call.cache_write > cold_write_threshold),
        verify_runs=verify_runs,
        cost_usd=cost(calls, pricing),
    )


def session_summaries(
    session: Session, pricing: dict[str, dict[str, float]] | None, context_threshold: int, cold_write_threshold: int
) -> list[Summary]:
    order = {"lead/planning": 0, "lead/execution": 1, "lead/finish": 2}
    names = sorted(session.groups, key=lambda name: (order.get(name, 3), name))
    rows = [
        summarize(
            name,
            session.groups[name].calls,
            session.groups[name].verify_runs,
            pricing,
            context_threshold,
            cold_write_threshold,
        )
        for name in names
    ]
    every_call = [call for name in names for call in session.groups[name].calls]
    verify_runs = sum(group.verify_runs for group in session.groups.values())
    total = summarize("total", every_call, verify_runs, pricing, context_threshold, cold_write_threshold)
    return [*rows, total]


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _money(value: float | None) -> str:
    return "n/a" if value is None else f"${value:.2f}"


def format_report(
    session: Session, rows: Sequence[Summary], five_hour: float | None, weekly: float | None, threshold: int
) -> str:
    header = (
        "group",
        "calls",
        "models",
        "first ctx",
        "peak ctx",
        f">{threshold // 1000}k",
        "cache hit",
        "cold",
        "verify",
        "cost",
    )
    table = [header] + [
        (
            row.group,
            str(row.calls),
            row.models,
            f"{row.first_context:,}",
            f"{row.peak_context:,}",
            str(row.calls_over_threshold),
            _percent(row.cache_hit),
            str(row.cold_writes),
            str(row.verify_runs),
            _money(row.cost_usd),
        )
        for row in rows
    ]
    widths = [max(len(line[column]) for line in table) for column in range(len(header))]
    lines = [f"Session {session.session_id}  {session.title}".rstrip(), f"{session.start} -> {session.end}"]
    lines += ["  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip() for line in table]
    plan = [
        f"{label} {'not recorded' if value is None else f'{value:g}% (as recorded)'}"
        for label, value in (("5-hour:", five_hour), ("weekly:", weekly))
    ]
    lines.append("Plan usage: " + ", ".join(plan))
    return "\n".join(lines) + "\n"


def require_ignored(path: Path, repo_root: Path) -> None:
    completed = subprocess.run(
        ("git", "check-ignore", "--quiet", "--no-index", str(path)), cwd=repo_root, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise SystemExit(f"refusing to write usage history to {path}: Git does not ignore it")


def append_history(
    path: Path,
    session: Session,
    rows: Sequence[Summary],
    five_hour: float | None,
    weekly: float | None,
    repo_root: Path,
) -> None:
    path = path.resolve()
    require_ignored(path, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **{key: getattr(row, key) for key in CSV_FIELDS if hasattr(row, key)},
                    "session_id": session.session_id,
                    "title": session.title,
                    "session_end": session.end,
                    "cache_hit": "" if row.cache_hit is None else f"{row.cache_hit:.4f}",
                    "cost_usd": "" if row.cost_usd is None else f"{row.cost_usd:.4f}",
                    "five_hour_pct": "" if five_hour is None else five_hour,
                    "weekly_pct": "" if weekly is None else weekly,
                }
            )


def _percentage(text: str) -> float:
    value = float(text)
    if not 0 <= value <= 100:
        raise argparse.ArgumentTypeError("must be between 0 and 100")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize local Claude Code session usage for this project.")
    parser.add_argument("sessions", nargs="*", help="session ids (default: the most recent session)")
    parser.add_argument("--latest", type=int, default=1, help="report the N most recent sessions when none are named")
    parser.add_argument("--projects-dir", type=Path, help="transcript directory (default: this project's)")
    parser.add_argument("--pricing", type=Path, help="pricing JSON (default: .claude/usage/pricing.json if present)")
    parser.add_argument("--context-threshold", type=int, default=150_000)
    parser.add_argument("--cold-write-threshold", type=int, default=50_000)
    parser.add_argument("--five-hour", type=_percentage, help="5-hour usage percent read from the app")
    parser.add_argument("--weekly", type=_percentage, help="weekly usage percent read from the app")
    parser.add_argument("--append", action="store_true", help="append rows to the git-ignored usage history")
    parser.add_argument("--history", type=Path, default=USAGE_DIR / "history.csv")
    arguments = parser.parse_args(argv)

    directory = arguments.projects_dir or project_dir(REPO_ROOT)
    pricing_path = arguments.pricing or (USAGE_DIR / "pricing.json" if (USAGE_DIR / "pricing.json").is_file() else None)
    pricing = load_pricing(pricing_path)
    session_ids = arguments.sessions or latest_sessions(directory, arguments.latest)
    if not session_ids:
        raise SystemExit(f"no session transcripts in {directory}")
    for index, session_id in enumerate(session_ids):
        session = load_session(directory, session_id)
        rows = session_summaries(session, pricing, arguments.context_threshold, arguments.cold_write_threshold)
        report = format_report(session, rows, arguments.five_hour, arguments.weekly, arguments.context_threshold)
        sys.stdout.write(("\n" if index else "") + report)
        if arguments.append:
            append_history(arguments.history, session, rows, arguments.five_hour, arguments.weekly, REPO_ROOT)
    if arguments.append:
        print(f"Appended to {arguments.history}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
