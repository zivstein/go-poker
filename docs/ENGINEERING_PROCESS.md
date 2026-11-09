# Engineering Process

This is the normative operating model for the current Go! Poker AI engineering team.

Role-specific behavior belongs in `.claude/agents/`.

Detailed rationale and AI-engineering reference material belong under `docs/company/` and are not required for normal feature work.

## Documentation Sources

| Source | Holds |
| --- | --- |
| `ARCHITECTURE.md` | current implemented technical truth and durable boundaries |
| `ROADMAP.md` | authoritative milestone status and approved future/unbuilt product decisions, except where the Friends Alpha Product Contract governs (see the top of `ROADMAP.md`) |
| `CURRENT_CYCLE.md` | active milestone/Cycle working state only |
| `docs/milestones/` | a milestone's approved plan, when it has one: its Cycle split, deliverables, dependencies, and exit gates |
| `docs/product/` | approved product contracts and product direction; the Friends Alpha Product Contract is authoritative for Friends Alpha scope and requirements, and its precedence over `ROADMAP.md` is stated at the top of `ROADMAP.md` |
| `docs/design/` | design direction, the design workflow, and the approval status of design decisions |
| `README.md` | human-facing overview; not authoritative for milestone status or history |
| implementation-facing docs | README, API, and module documentation describing implemented behavior |
| ADRs | why an important durable decision was made |

Each fact has one home. Other documents link to it rather than restating it.

## Current Team

The current organization is one Core Engineering Team.

| Role | Owns |
| --- | --- |
| User | product/domain/architecture decisions, milestone scope, Cycle Brief approval, dependencies, ownership changes, process changes, commit/release approval |
| Engineering Lead | planning, orchestration, escalation, finding triage, final verification, status, Cycle completion |
| Engineer | production implementation, focused implementation tests, affected implementation-facing docs |
| QA Engineer | independent behavioral/adversarial validation and test code |
| Reviewer | final independent architecture/code/test review; read-only |

Only the Engineering Lead may mark a Cycle complete.

No role commits or pushes without explicit user approval.

## Approval and Escalation

User approval is required for a new decision about:

- product or domain behavior;
- architecture;
- public API;
- ownership boundaries;
- dependencies;
- milestone scope;
- control/process files;
- commit or release.

Ordinary implementation choices stay autonomous when they remain inside approved boundaries.

Examples include:

- private helpers;
- local refactors;
- internal naming;
- test organization;
- parametrization;
- equivalent low-level implementation choices.

If implementation reveals a genuinely new approval-level decision, stop and escalate instead of guessing.

## Milestone Flow

Before implementation of a new milestone:

1. Lead studies the relevant code and architecture.
2. Lead proposes milestone design, scope, important decisions, and Cycle split.
3. User approves approval-level decisions.
4. Lead records approved decisions in their sources of truth: milestone status, and future product decisions not governed by the Friends Alpha Product Contract, in `ROADMAP.md`; product decisions within that contract's scope in the contract; the Cycle split in the milestone's plan under `docs/milestones/` when the milestone has one, otherwise in `CURRENT_CYCLE.md`; open decisions in `CURRENT_CYCLE.md`; and an ADR when the ADR policy calls for one. `ARCHITECTURE.md` changes when the behavior is implemented.
5. Implementation Cycles begin.

Do not implement while milestone-level decisions remain unresolved.

## Cycle Sizing

A Cycle is one coherent work unit. Delegation separates roles from each other but does not bound the work each role carries: an oversized Cycle makes the Engineer and QA sessions themselves long-context sessions.

The Lead checks size when proposing a milestone's Cycle split and again when drafting each Cycle Brief, before execution.

Sizing signals:

- several implementation surfaces that could each be verified on their own;
- more than about three production subsystems changed;
- a significant test-harness redesign alongside new production behavior;
- a large migration of existing tests or assertions;
- a major stress-suite expansion;
- a large expected diff, roughly 20+ changed paths or 2k+ inserted lines;
- the Engineer asked to build both production behavior and substantial independent validation infrastructure;
- a natural midpoint that is independently testable.

The signals are heuristics. None is a hard threshold, and no number of signals requires a split by itself.

Multiple signals trigger an explicit sizing decision. Split when there is a natural, independently verifiable seam and the split materially reduces the work and context a role carries. Otherwise keep the Cycle whole and state why in the Brief.

Every part of a split:

- has a coherent goal;
- is independently testable and reviewable;
- leaves docs accurate;
- is independently committable.

Typical seams are production behavior first and harness, migration, or stress expansion second, or one subsystem per Cycle. Small-Change Path work is not split unnecessarily.

A split proposed in a Cycle Brief is approved with it and recorded in `CURRENT_CYCLE.md`. An executing Cycle is not split; it continues autonomously, and sizing lessons go into the Cycle Report's process improvements.

`scripts/usage_report.py` warnings after a Cycle inform later sizing decisions; they are not gates.

## Cycle Flow

Behavioral work follows:

1. Lead presents the Cycle Brief.
2. User approves the Brief; approval starts the Cycle.
3. Engineer implements.
4. Lead checks the delivery.
5. QA validates; fixes are followed by affected QA re-validation.
6. Reviewer reviews; fixes are followed by affected QA and Reviewer re-review.
7. Lead closes out docs and status.
8. Lead runs final verification over the final working tree.
9. Lead returns the Cycle Report.
10. User approves the commit.

After Brief approval, Engineer → QA → Reviewer handoffs run autonomously.

The Lead returns to the user before the commit only for an approval-level escalation.

### Small-Change Path

For work that clearly cannot change runtime or domain behavior:

- use a short goal/scope instead of a full Cycle Brief;
- QA may be skipped;
- Reviewer and final verification still apply.

Examples include docs, comments, private renames, and clearly behavior-preserving refactors.

If the Reviewer believes behavior may be affected, QA becomes required.

## Definition of Ready

A behavioral Cycle is ready when the Lead can state without guessing:

- goal;
- in scope;
- out of scope;
- relevant domain behavior and invariants;
- architecture and ownership;
- test strategy;
- known deferred behavior;
- a bounded size (see Cycle Sizing).

An unresolved approval-level decision blocks implementation.

## Cycle Brief

Keep it concise and specific to the Cycle.

Include only information that is not already clear from durable repository context:

1. Goal
2. In scope
3. Out of scope
4. Architecture / ownership
5. Important behavior and invariants
6. Test strategy
7. Risks / deferred decisions
8. Execution plan

Do not restate the whole architecture or engineering process.

When multiple Cycle Sizing signals apply, the Execution plan records the sizing decision: the split, or why the Cycle stays whole.

## Definition of Done

A behavioral Cycle is complete when:

- approved scope is implemented;
- distinct rules have effective validation;
- relevant integration behavior is covered;
- QA passes;
- Reviewer approves;
- standard verification passes;
- affected docs are accurate;
- no Critical or Major finding remains;
- status is updated;
- meaningful Plan vs implementation differences are reported.

The user still approves the commit.

## Findings and Gates

Severity:

- **Critical** — incorrect outcome/accounting, corruption, unsafe mutation, or broken fundamental boundary.
- **Major** — any of:
  - realistic approved behavior is missing or wrong;
  - an approved rule has no effective test;
  - a duplicated source of truth;
  - a meaningful ownership or boundary violation;
  - incorrect documentation of implemented behavior or public API.
- **Minor** — maintainability, clarity, or test-strength issue without incorrect approved behavior or documentation.
- **Nit** — optional style or wording.

Critical and Major findings block the gate.

The Lead decides whether each finding is:

- fixed;
- rejected with a reason;
- deferred;
- escalated.

## Handoffs

Handoffs are conversation outputs, not repository documents.

### Engineering Delivery

Engineer reports:

- implementation;
- files changed;
- tests;
- verification;
- meaningful deviations;
- risks/deferred items;
- blocker when applicable.

### QA Report

QA reports:

- scenarios and boundaries;
- tests added or strengthened;
- findings;
- documentation inaccuracies;
- stress/mutation work when useful;
- verification;
- verdict.

### Reviewer Input

The Reviewer's first pass receives:

- the approved requirement and Cycle Brief;
- the actual repository diff and state;
- QA evidence and finding resolutions, or why QA was skipped;
- relevant architecture.

It does not receive the Engineer's implementation reasoning or self-justification.

### Review Verdict

Reviewer reports:

- findings by severity;
- architecture assessment;
- test assessment;
- documentation;
- verification;
- verdict.

### Cycle Report

Lead reports:

- delivered behavior;
- gate outcomes, including whether QA was skipped and why;
- finding resolutions;
- final verification;
- docs/status;
- Plan vs implementation;
- deferred work;
- proposed engineering-process improvements discovered during the Cycle;
- Git state;
- the closeout manifest, last.

Keep reports proportional to the work.

The closeout manifest is the proposed commit message and every path the Cycle commit will contain, in the exact form `/finish-cycle` passes to `scripts/finish_cycle.py`:

    message: feat: add continuous Hold'em game
    path: src/go_poker/game/variants/texas_holdem/game.py
    path: tests/game/variants/texas_holdem/test_holdem_game.py

It lists every changed path in the working tree, including deleted files and both sides of a rename. The script commits nothing unless the working tree's changes match it exactly.

## Ownership

| Area | Engineer | QA | Reviewer | Lead |
| --- | --- | --- | --- | --- |
| `src/` | edit | no | read | no |
| `tests/` | edit | edit | read | no |
| implementation-facing docs | edit affected content | report issues | read | verify at closeout |
| `ARCHITECTURE.md` | edit implemented-behavior detail only | report issues | read | edit; records approved decisions |
| `ROADMAP.md`, `CURRENT_CYCLE.md` | no | no | read | edit |
| ADRs | no | no | read | draft; user accepts |
| control/process files | no | no | no | Meta work only |

## Testing

Principle:

**distinct rule → focused test**

Prefer:

- exact boundaries;
- representative integration sequences through public operations;
- invariants for large state spaces;
- deterministic seeded stress testing when useful.

Avoid:

- constant-only tests;
- duplicate coverage with no distinct failure mode;
- Cartesian-product matrices for their own sake;
- impossible internal states constructed only to test defensive code.

Test helpers stay local to their test directory. Small duplication does not justify restructuring by itself.

Hypothesis is not currently a dependency.

Reconsider it only when a concrete milestone benefits enough from property generation and shrinking to justify the dependency.

### Verification Discipline

The standard verification command and its rules are in `CLAUDE.md`. This section sets how often it runs.

Iterate with targeted checks: `uv run pytest <paths>` or `-k`, and `uv run ruff check <paths>` or `uv run mypy src` when relevant. Run the full standard verification at handoffs, over the tree being handed off. Each role's default is in its agent file.

An extra full run is justified when:

- the previous full run failed and was fixed;
- the change touches shared test infrastructure (conftest, fixtures, helpers) or cross-cutting production code, where targeted selection may miss affected tests;
- a targeted run shows an unexpected interaction or a failure outside the expected area;
- the tree changed after the last full run in a way targeted checks do not cover.

These are defaults, not caps. Never skip a full run a handoff requires, and never report a targeted run as full verification.

The Lead reads the verification reported at each handoff rather than re-running it. After closeout docs and status are updated, the Lead runs one final full verification over the final working tree, and runs it again if anything changes afterwards. `/finish-cycle` runs its own verification inside the script.

### Deliberate Breakage

Never intentionally break production code in the active working tree, even briefly.

Mutation experiments run in an isolated copy that includes the current working-tree changes, and the copy is discarded afterward:

```bash
scratch="$(mktemp -d)"
rsync -a --exclude .git --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .mypy_cache --exclude .ruff_cache ./ "$scratch/go-poker/"
cd "$scratch/go-poker" && uv run pytest -q <tests that should catch the mutation>
```

Do not use a Git worktree: it checks out committed code, not the uncommitted work under test. Mutation experiments never change the real repository's Git state.

## Model and Effort Routing

Routing is a default, not a quality ceiling.

| Work | Default |
| --- | --- |
| milestone architecture / difficult design | Opus, `xhigh`, Plan Mode |
| normal Cycle Lead | Opus, `high`, for the whole session |
| Engineer | Sonnet, `high` |
| QA Engineer | Sonnet, `high` |
| Reviewer | Opus, `high` |
| mechanical work in a fresh subagent | Sonnet or Haiku, `medium` |
| difficult debugging / ambiguous cross-cutting work | Opus, `xhigh` |
| exceptional correctness-critical reasoning | `max`, as an explicit escalation |

Use model-family aliases rather than pinned versions unless a concrete reason requires otherwise.

A session keeps one model. Prompt caches are per model, so switching a large session's model for a skill or a step rewrites its whole context into a fresh cache, which usually costs more than the cheaper model saves. Skills do not set `model`; they inherit the session model. Fresh subagents start with a small context and keep their configured models.

Do not remove quality gates to save usage.

Per-agent `model` frontmatter is intentional. Do not enable `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` while relying on this routing. When routing correctness matters, verify the models agents actually run with `/tasks`.

### Model Escalation

A cheaper model is useful only while it completes the role reliably.

Escalate when:

- the task remains ambiguous after a good Brief;
- the change becomes strongly cross-cutting;
- Sonnet repeatedly misunderstands the requirement;
- repeated repair loops erase the expected usage saving;
- difficult debugging requires deeper reasoning.

Evaluate routing by total cost of completion, not token count alone.

## Context and Session Policy

The repository is durable memory.

Conversations are temporary working context.

- Start a fresh session after completed milestone planning.
- Start a fresh session after a completed and committed Cycle.
- Use `/compact` only while continuing the same unfinished task.
- Read focused files and relevant sections instead of the entire repository.
- Reference durable repository context instead of copying it into prompts.
- Do not duplicate durable rules across prompts, docs, agents, and skills.

Task prompts should normally contain only:

- goal;
- task-specific scope;
- unusual constraints;
- success criteria.

Detailed company/reference docs under `docs/company/` are loaded only for Meta work, organization design, onboarding, or AI-engineering analysis.

### Usage Measurement

`scripts/usage_report.py` summarizes this project's local Claude Code session transcripts: Lead phases (planning, execution, finish), agents, models, context, cache, and verification signals. Run it after a Cycle when measuring workflow cost.

- Costs appear only with a local pricing file; prices are not recorded in process docs.
- 5-hour and weekly percentages are recorded only when read from the app's usage display, never estimated.
- Pricing and history live in the git-ignored `.claude/usage/`; personal usage data never enters the repository.
- Each session report ends with workflow-pressure warnings: Engineer or QA peak context above the context threshold, a high full-verification count, and cold cache writes during `/finish-cycle`. They are telemetry, never gates.

## Cycle Closeout

Only the user invokes `/finish-cycle`; the Lead never invokes it. Invoking it is the user's approval to commit and push the work in the latest Cycle Report's closeout manifest. A non-empty `/finish-cycle` argument replaces the manifest's commit message.

The skill passes the manifest to `scripts/finish_cycle.py`, which performs and checks the whole Git closeout and stops without committing or pushing on anything unexpected. The script's docstring lists its checks. No role runs the script, commits, or pushes outside `/finish-cycle`.

After it returns `SESSION COMPLETE`:

- perform no further project work in that session;
- the user closes the session;
- the next Cycle starts fresh.

## Architecture Decision Records

Use an ADR only when the reasoning behind a durable decision is likely to matter later.

Examples:

- public contracts;
- persistent state models;
- subsystem ownership boundaries;
- external dependencies;
- cross-team integration contracts;
- broad domain interpretations.

`ARCHITECTURE.md` records what is true now.

An ADR records why an important decision was made.

Do not create ADRs for local implementation choices.

Mechanics:

- ADRs live under `docs/adr/` as numbered, descriptive files (`NNNN-short-title.md`). Create the directory with the first real ADR, not before.
- The Lead drafts an ADR for a qualifying decision; user approval accepts it.
- An accepted ADR is a historical record and is not rewritten to change the decision. A later ADR supersedes it.

The ADR template is in `docs/company/COMPANY_MANUAL.md`.

## Control Files and Meta Work

Control/process files include:

- `CLAUDE.md`;
- `AGENTS.md`;
- `docs/ENGINEERING_PROCESS.md`;
- `.claude/agents/`;
- `.claude/skills/`;
- workflow tooling under `scripts/` (verification, closeout, and usage measurement) and its tests under `tests/tooling/`;
- future hooks/config that change AI-team behavior.

They are not modified during feature work.

Process improvements are applied as dedicated Meta work with user approval.

Meta work does not change production code, product tests, dependencies, or product behavior unless that change is separately approved as product work. Workflow-tooling tests under `tests/tooling/` change with the tooling they test.
