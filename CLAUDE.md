@AGENTS.md

# Claude Code Workflow

Reuse existing architecture and domain logic, and implement only the approved scope.

Before milestone planning or implementation, consult `docs/ARCHITECTURE.md` and `docs/CURRENT_CYCLE.md` when they exist.

Do not add AI/Claude attribution, Co-Authored-By trailers, Generated-with-Claude text, or Claude session URLs to commits or pull requests.

# AI Team Workflow

The main Claude session is the **Engineering Lead** of the Core Engineering Team. The other roles are the `engineer`, `qa-engineer`, and `reviewer` subagents in `.claude/agents/`. The team's organization and role ownership, approval and escalation policy, Cycle flow, Definitions of Ready and Done, Cycle Brief, handoffs, testing policy, and ADR policy are in `docs/ENGINEERING_PROCESS.md`, imported here:

@docs/ENGINEERING_PROCESS.md

# Verification

Before completing code changes, run:

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`

Report failures rather than hiding or bypassing them.
