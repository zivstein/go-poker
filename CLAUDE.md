@AGENTS.md

# Go! Poker

The main Claude session is the Engineering Lead while `.claude/ownership.json` has `mode: single-team`.

In `multi-lane` mode (inactive until activation), a session's identity comes from its checkout. In the main checkout it is the Orchestrator. In a Work Order worktree, on a lane-prefixed branch with a Work Order record, it is that Work Order's Cycle Lead. The roles are in `docs/ENGINEERING_PROCESS.md` (Multi-lane organization).

Use the repository as the durable source of truth:

- `docs/ARCHITECTURE.md` — current architecture, ownership, and invariants
- `docs/ROADMAP.md` — product direction and milestone status
- `docs/CURRENT_CYCLE.md` — active milestone and Cycle
- `docs/ENGINEERING_PROCESS.md` — team workflow, approvals, gates, and model/context policy
- `.claude/agents/` — role-specific instructions
- `.claude/ownership.json` — lanes, path kinds, role write permissions, and the organization mode

Read only the documents relevant to the task. For milestone planning or implementation Cycles, read the engineering process, architecture, roadmap, and current cycle before acting.

Control/process files are changed only in dedicated Meta work, not during feature implementation.

Do not add AI/Claude attribution, Co-Authored-By trailers, generated-by text, or session URLs to commits or pull requests.

## Verification

For code or test changes, the standard verification is one command:

- `uv run scripts/verify.py`

It runs Ruff check, Ruff format check, mypy, and pytest, then the Web gates in `web/` (`tsc --noEmit`, `biome ci`, `vitest run`, `vite build`), keeps their real exit codes, and ends with `VERIFY: PASS` or `VERIFY: FAIL`. Only `VERIFY: PASS` with exit code 0 passes. Run it directly; do not pipe or truncate it.

A checkout needs both toolchains before its first run: `uv sync --locked` at the root and `npm ci` in `web/`, with Node on the major line pinned in `web/.nvmrc`. Without Node or the installed Web dependencies, every Web gate fails and says why.

A gate's full run is made independently and without `--fix`. How often each role runs it is in `docs/ENGINEERING_PROCESS.md` (Verification Discipline); `/finish-cycle` always runs it. While implementing, the Engineer may run `uv run scripts/verify.py --fix`, which first rewrites files with Ruff's and Biome's fixes and formatting.

Never hide, weaken, or bypass failures.
