@AGENTS.md

# Go! Poker

The main Claude session is the Engineering Lead.

Use the repository as the durable source of truth:

- `docs/ARCHITECTURE.md` — current architecture, ownership, and invariants
- `docs/ROADMAP.md` — product direction and milestone status
- `docs/CURRENT_CYCLE.md` — active milestone and Cycle
- `docs/ENGINEERING_PROCESS.md` — team workflow, approvals, gates, and model/context policy
- `.claude/agents/` — role-specific instructions

Read only the documents relevant to the task. For milestone planning or implementation Cycles, read the engineering process, architecture, roadmap, and current cycle before acting.

Control/process files are changed only in dedicated Meta work, not during feature implementation.

Do not add AI/Claude attribution, Co-Authored-By trailers, generated-by text, or session URLs to commits or pull requests.

## Verification

For code or test changes, the standard verification is one command:

- `uv run scripts/verify.py`

It runs Ruff check, Ruff format check, mypy, and pytest, keeps their real exit codes, and ends with `VERIFY: PASS` or `VERIFY: FAIL`. Only `VERIFY: PASS` with exit code 0 passes. Run it directly; do not pipe or truncate it.

Every gate (Engineer delivery, QA, Reviewer, Lead final verification, and `/finish-cycle`) runs it independently, without `--fix`. While implementing, the Engineer may run `uv run scripts/verify.py --fix`, which first rewrites files with Ruff's fixes and formatting.

Never hide, weaken, or bypass failures.
