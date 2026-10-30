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

For code or test changes, the standard verification is:

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`

Never hide, weaken, or bypass failures.
