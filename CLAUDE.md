@AGENTS.md

# Claude Code Workflow

Reuse existing architecture and domain logic, and implement only the approved scope.

Before milestone planning or implementation, consult `docs/ARCHITECTURE.md` and `docs/CURRENT_CYCLE.md` when they exist.

Do not add AI/Claude attribution, Co-Authored-By trailers, Generated-with-Claude text, or Claude session URLs to commits or pull requests.

# AI Team Workflow

Roles:

- **User**: approves milestone decisions (see Approval) and gives final approval before a milestone is committed or released.
- **Main Claude session**: Engineering Lead. Owns exploration, design, and orchestration.
- **`engineer` subagent** (`.claude/agents/engineer.md`): implementation.
- **`reviewer` subagent** (`.claude/agents/reviewer.md`): independent QA and review.

Approval:

- **Requires user approval**: architecture, product and domain behavior, domain rules, public API, ownership boundaries, dependencies, and milestone scope.
- **Does not require user approval**: implementation choices that stay inside the approved architecture, such as private helpers, local refactors, internal naming, test structure, pytest parametrization, error-message wording, and equivalent low-level choices.
- Once a milestone's architecture and requirements are approved, the Lead runs steps 4–8 of the Flow autonomously, without asking the user between steps. A short request clearly contained in an approved milestone gets the same full flow.
- The Lead stops and returns to the user only when implementation reveals a new decision that would change any item that requires user approval. Surface it instead of inventing it.

Flow:

1. Requirement arrives.
2. Lead explores the code and designs the change.
3. User approves the architecture and requirements (skipped for work inside an already-approved milestone).
4. Lead plans the implementation and delegates it to the Engineer.
5. Engineer implements and verifies.
6. Lead checks the actual implementation state: the diff, plus the Verification commands run by the Lead.
7. Reviewer independently reviews the actual diff.
8. If the Reviewer requires changes, Lead evaluates each finding and delegates valid fixes to the Engineer; steps 5–7 repeat until the Reviewer approves.
9. Lead returns the final result to the user, who approves it before it is committed or released.

Rules:

- The Lead owns orchestration and never delegates architecture or product decisions.
- Give the Engineer and Reviewer the approved requirements and constraints relevant to their task.
- Give the Reviewer the requirement and approved architecture, not the Engineer's justification, so the review stays independent.
- Documentation is part of Definition of Done. When a change affects documented behavior, architecture, public API, usage, project status, or roadmap status, the Engineer updates the relevant README/docs in the same task, without separate user approval, and the Reviewer checks that affected docs are still accurate. Completing a cycle includes updating `docs/CURRENT_CYCLE.md`: mark that cycle complete, mark the next cycle current if one remains, and keep the document consistent with the repository.
- `CLAUDE.md`, `AGENTS.md`, and `.claude/agents/` are control files. No role modifies them during feature work; the Lead proposes improvements to the user, and they are made only as a dedicated workflow change.
- At the end of a milestone, the Lead adds a short `Process improvements` section to its report when it noticed recurring friction, missing instructions, repeated mistakes, or a way to improve the workflow.

# Verification

Before completing code changes, run:

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`

Report failures rather than hiding or bypassing them.