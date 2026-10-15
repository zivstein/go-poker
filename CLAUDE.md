@AGENTS.md

# Claude Code Workflow

For non-trivial changes, explore the relevant implementation first, then present a concise implementation plan and wait for approval before editing files.

Surface unresolved product or domain decisions instead of inventing them. Reuse existing architecture and domain logic, and implement only the approved scope.

# Verification

Before completing code changes, run:

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`

Report failures rather than hiding or bypassing them.