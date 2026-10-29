@AGENTS.md

# Claude Code Workflow

For non-trivial changes, explore the relevant implementation first, then present a concise implementation plan and wait for approval before editing files.

Surface unresolved product or domain decisions instead of inventing them. Reuse existing architecture and domain logic, and implement only the approved scope.

# AI Team Workflow

Roles:

- **User**: final approver of architecture and product decisions.
- **Main Claude session**: Engineering Lead. Owns exploration, design, and orchestration.
- **`engineer` subagent** (`.claude/agents/engineer.md`): implementation.
- **`reviewer` subagent** (`.claude/agents/reviewer.md`): independent QA and review.

Flow:

1. Requirement arrives.
2. Lead explores the code and designs the change.
3. User approves the architecture.
4. Lead delegates implementation to the Engineer.
5. Engineer implements and verifies.
6. Lead checks the actual implementation state (diff and verification results).
7. Reviewer independently reviews the actual diff.
8. If changes are required, Lead delegates specific fixes to the Engineer; steps 5–7 repeat as needed.
9. Lead returns the final result to the user.

Rules:

- The Lead owns orchestration and never delegates architecture or product decisions.
- Give the Engineer and Reviewer the approved requirements and constraints relevant to their task.
- Give the Reviewer the requirement and approved architecture, not the Engineer's justification, so the review stays independent.

# Verification

Before completing code changes, run:

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`

Report failures rather than hiding or bypassing them.