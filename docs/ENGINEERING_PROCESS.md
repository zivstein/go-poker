# Engineering Process

How the AI engineering team builds Go! Poker: the organization, who owns what, how a Cycle runs, and what still goes back to the user. This is the single shared source of truth for the workflow. `CLAUDE.md` is the entry point and imports this file; rules that apply to one role only are in that role's agent file under `.claude/agents/`.

## Organization

There is one team, the **Core Engineering Team**. It owns the poker engine: `src/go_poker/`, its tests, and the project docs.

| Role | Who | Owns |
| --- | --- | --- |
| User | the project owner | the decisions in [Approval and escalation](#approval-and-escalation), and final approval of every commit or release |
| Engineering Lead | the main Claude session | design, planning, orchestration, finding triage, final verification, status docs, and the Cycle Report |
| Engineer | `engineer` subagent ([engineer.md](../.claude/agents/engineer.md)) | production code, the tests tied to it, and implementation-facing docs |
| QA Engineer | `qa-engineer` subagent ([qa-engineer.md](../.claude/agents/qa-engineer.md)) | independent behavioral and adversarial validation; test code only |
| Reviewer | `reviewer` subagent ([reviewer.md](../.claude/agents/reviewer.md)) | the final independent engineering and design review; read-only |

### Engineering Lead

The Lead:

- reads the approved architecture, roadmap, and current cycle before planning;
- designs changes and brings every decision that needs approval to the user;
- checks the [Definition of Ready](#definition-of-ready), presents the [Cycle Brief](#cycle-brief), and continues without waiting for a reply;
- assigns implementation and fixes to the Engineer, validation to QA, and the final review to the Reviewer, with the inputs listed in [Handoffs](#handoffs);
- triages every QA and Reviewer finding (see [Findings and gates](#findings-and-gates)) and makes sure fixes are re-validated and re-reviewed;
- runs the final verification, closes out the status docs, marks the Cycle Complete, and writes the Cycle Report.

The Lead delegates implementation and test work instead of doing it, and never delegates architecture or product decisions.

### QA Engineer and Reviewer are different gates

QA runs first and asks: *does the delivered behavior hold under realistic and adversarial use?* It executes the code, designs edge cases and sequences, attacks plausible implementation mistakes, and writes the tests that prove what it found.

The Reviewer runs last and asks: *is this the right change, built the right way, and will it stay correct?* It judges architecture, ownership, domain correctness, API clarity, maintainability, scope, documentation, and whether the final test suite, including QA's additions, would catch plausible bugs. It writes nothing.

### Who may change what

| Area | Engineer | QA Engineer | Reviewer | Lead |
| --- | --- | --- | --- | --- |
| Production code (`src/`) | yes | no | no | no |
| Tests and test helpers (`tests/`) | yes | yes | no | no |
| Implementation-facing docs (README features, usage, module tree, and test descriptions; implementation details in `docs/ARCHITECTURE.md`) | yes | no; reports inaccuracies in its QA Report | no | final closeout updates |
| Approved decisions (`docs/ARCHITECTURE.md` decisions, ADRs) | no | no | no | yes, after user approval |
| Status (`docs/CURRENT_CYCLE.md`, `docs/ROADMAP.md`, the README's Project Status) | no | no | no | yes |
| Control files (see [Control files and Meta Cycles](#control-files-and-meta-cycles)) | no | no | no | only in a Meta Cycle |

No role adds or upgrades dependencies, or commits, pushes, or rewrites Git history, without explicit user approval (see `AGENTS.md`).

## Approval and escalation

- **Requires user approval**: architecture, product and domain behavior, domain rules, public API, ownership boundaries, dependencies, milestone scope, control-file changes, and the final commit or release.
- **Does not require user approval**: implementation choices that stay inside the approved architecture, such as private helpers, local refactors, internal naming, test structure, pytest parametrization, error-message wording, and equivalent low-level choices.
- Once a milestone's architecture and requirements are approved, the team runs each Cycle from the Brief to the Cycle Report without asking the user between steps. A short request clearly contained in an approved milestone gets the same flow.
- Any role that finds the work needs a new decision in an approval category stops and reports it to the Lead. The Lead stops the Cycle and brings the decision to the user, with options and a recommendation, instead of inventing it. The Cycle resumes once the user decides.

## Milestone flow

1. A requirement arrives.
2. The Lead explores the code and designs the change.
3. The user approves the architecture, requirements, and milestone scope. The Lead records the approved design in `docs/ARCHITECTURE.md` (and an ADR when the [ADR policy](#architecture-decision-records) calls for one), the milestone in `docs/ROADMAP.md`, and its cycles in `docs/CURRENT_CYCLE.md`.
4. Each cycle runs the [Cycle flow](#cycle-flow).

Steps 1–3 are skipped for work inside an already-approved milestone.

## Cycle flow

1. The Lead reads the architecture, the current cycle, and any relevant ADRs, and checks the Definition of Ready.
2. The Lead presents the Cycle Brief.
3. The Lead continues straight away; the Brief is informational.
4. The Engineer implements and returns an Engineering Delivery.
5. The Lead checks the delivery: the actual diff against the Brief, and the Verification commands run by the Lead. An incomplete, failing, or out-of-scope delivery goes back to the Engineer.
6. QA performs independent behavioral validation and returns a QA Report.
7. If QA reports production or documentation findings, the Engineer fixes the valid ones, the Lead checks the delivery again, and QA re-validates the production fixes and reruns the affected validation, until the QA gate passes.
8. The Reviewer performs the independent final review and returns a Review Verdict.
9. If the Reviewer requires changes, the Engineer fixes the valid findings, the Lead checks the delivery again, QA reruns its affected checks when a fix changed behavior, and the Reviewer re-reviews, until it approves.
10. The Lead runs the final verification on the final tree.
11. The Lead updates the status docs, makes any final closeout updates, and confirms that every affected doc is accurate.
12. The Lead marks the Cycle Complete in `docs/CURRENT_CYCLE.md`, and the next cycle current if one remains, only when the Definition of Done holds.
13. The Lead returns the Cycle Report.
14. The user approves the commit or release.

**Small-change path.** The full flow is for changes to behavior. The Lead may skip QA only when it is confident the change does not alter runtime or domain behavior, for example docs, comments, a private rename, or a clearly behavior-preserving refactor already covered by existing tests. A one-line goal and scope then replaces the full Brief. The Reviewer still reviews, and if it believes the change was wrongly classified as behavior-preserving, it requires QA; the Lead then runs QA before the Reviewer re-reviews. The Lead still verifies, the rest of the Definition of Done still applies, and the Cycle Report says QA was skipped and why.

## Definition of Ready

A Cycle is ready when the Lead can state, from approved decisions and without guessing:

- the goal, what is in scope, and what is out of scope;
- the relevant domain behavior and its important invariants;
- the architecture and ownership boundaries;
- the test strategy;
- the known deferred behavior.

These are the Cycle Brief's items 1–5, 7, and 8, so a ready Cycle is one whose Brief can be written without open questions. If one of them exposes an unresolved decision in an approval category, escalate before implementation. A change on the small-change path (see [Cycle flow](#cycle-flow)) needs only a one-line goal and scope.

## Definition of Done

A normal implementation Cycle is Done only when:

- the approved scope is implemented;
- focused tests exist for each distinct rule, with integration coverage where behavior spans operations;
- QA has passed;
- the Reviewer has approved;
- the Lead's final verification passes;
- the affected docs are accurate;
- no Critical or Major finding is unresolved;
- the Lead has updated the Cycle status;
- the Cycle Report includes Plan vs implementation.

The user still approves the commit.

## Cycle Brief

At the start of every implementation Cycle, before delegating to the Engineer, the Lead presents a concise, structured `Cycle Brief` to the user. It is informational only: the Lead does not wait for approval and continues straight into the Cycle flow. If preparing it reveals an unresolved decision that requires user approval, the Lead stops under [Approval and escalation](#approval-and-escalation) instead of starting implementation.

1. **Goal**: the concrete capability or behavior the Cycle adds.
2. **In scope**: the approved requirements implemented in this Cycle.
3. **Out of scope**: nearby behavior deferred to later cycles or milestones.
4. **Architecture / ownership**: which existing modules own the relevant responsibilities, where the new behavior is expected to live, and the boundaries that must stay intact.
5. **Expected domain behavior**: the important rules and invariants the implementation must satisfy.
6. **Expected code changes**: the modules and files likely to be added or changed. This is a forecast, not a commitment to exact filenames; low-level implementation choices stay autonomous.
7. **Test strategy**: the distinct behaviors to test and the representative integration cases, following the [testing policy](#testing-policy).
8. **Risks / deferred decisions**: known edge cases, technical risks, and deliberately deferred behavior relevant to the Cycle.
9. **Execution plan**: a short ordered plan (for example: models/state, domain helpers, behavior, tests, integration, verification, QA, Reviewer).

## Handoffs

`Cycle Brief` → `Engineering Delivery` → `QA Report` → `Review Verdict` → `Cycle Report`

| Handoff | From → to | Format |
| --- | --- | --- |
| Cycle Brief | Lead → user (informational) and Engineer | [above](#cycle-brief) |
| Engineering Delivery | Engineer → Lead | [engineer.md](../.claude/agents/engineer.md) |
| QA Report | QA Engineer → Lead | [qa-engineer.md](../.claude/agents/qa-engineer.md) |
| Review Verdict | Reviewer → Lead | [reviewer.md](../.claude/agents/reviewer.md) |
| Cycle Report | Lead → user | [below](#cycle-report) |

What the Lead gives each role:

- **Engineer**: the Cycle Brief and the approved requirements, constraints, and architecture sections it touches; for a fix, the findings to fix.
- **QA Engineer**: the Cycle Brief, the Engineering Delivery, and the approved requirements; for re-validation, the findings and what the fix changed.
- **Reviewer**: the approved requirements and architecture, the Cycle Brief, and the QA findings with their resolution (or a note that QA was skipped as behavior-preserving), but not the Engineer's justification, so the review stays independent; for a re-review, its earlier findings and what changed.

Handoffs are conversation outputs, not repository files. The repository keeps only what lasts: the Cycle status and its delivered summary in `docs/CURRENT_CYCLE.md`, decisions in `docs/ARCHITECTURE.md`, and ADRs.

### Findings and gates

QA and the Reviewer use the same severities:

- **Critical**: an incorrect poker outcome or chip accounting, corrupted or partially mutated state, or a broken engine boundary.
- **Major**: an approved requirement missing or wrong in a realistic case, a duplicated source of truth, a distinct rule with no test, or wrong documentation of behavior or public API.
- **Minor**: a maintainability, clarity, or test-strength issue with no incorrect behavior.
- **Nit**: optional style or wording.

A gate blocks while a Critical or Major finding is open. The Lead evaluates every finding: valid ones go to the Engineer, invalid ones are rejected with a reason recorded in the Cycle Report, and each Minor finding or Nit is either fixed now or deferred with a recorded reason. A finding whose resolution needs a decision in an approval category is escalated, not decided.

Each role reports only its own status: the Engineer `DELIVERED` or `BLOCKED`, QA `PASSED` or `FINDINGS`, and the Reviewer `APPROVED` or `CHANGES REQUIRED`. Only the Lead turns these into Cycle completion, and only the Lead edits Cycle or milestone status in the docs.

### Cycle Report

The Lead's final report to the user, concise:

1. **Outcome**: Cycle Complete, or not complete and why (an escalation or a block).
2. **Delivered**: what the Cycle added.
3. **Gates**: the Engineering Delivery, QA, and Review outcomes, including fix rounds.
4. **Findings**: each QA and Reviewer finding and its resolution (fixed, rejected with a reason, or deferred with a reason).
5. **Verification**: the Lead's final run of each Verification command.
6. **Docs**: the docs updated.
7. **Plan vs implementation**: whether the implementation followed the Cycle Brief, any meaningful deviations, and why they were necessary. Private-helper and test-organization changes are not deviations.
8. **Deferred**: follow-ups and deferred items.
9. **Process improvements**: recurring friction, missing instructions, repeated mistakes, or a better way to work, when noticed; always considered at the end of a milestone.
10. **Git status**: the uncommitted changes awaiting the user's approval.

## Model and effort routing

Use the cheapest model that does a role reliably, and keep stronger reasoning for decisions where mistakes are expensive. Name models by family alias (`opus`, `sonnet`, `haiku`), not by pinned version, so defaults follow each family's current model.

| Role or work | Model | Set by |
| --- | --- | --- |
| Lead: milestone architecture and difficult planning | Opus | the session model |
| Lead: Cycle Brief | Opus | the session model, in plan mode under `opusplan` |
| Lead: normal Cycle execution and orchestration | Sonnet | the session model |
| Engineer | Sonnet | `model: sonnet` in its agent file |
| QA Engineer | Sonnet | `model: sonnet` in its agent file |
| Reviewer | Opus | `model: opus` in its agent file |
| Mechanical one-off work | Sonnet, or Haiku for trivial edits | the session model, or a one-off model override; no dedicated agent |

- `opusplan` uses Opus in plan mode and Sonnet otherwise, which matches the Lead's split. If it is unavailable, switch between `opus` and `sonnet` by hand; the principle is what matters, not the alias.
- The Lead may override a subagent's model for a single task that needs stronger reasoning, but never moves a gate to a cheaper model to save usage.
- Do not set `CLAUDE_CODE_SUBAGENT_MODEL` or any other setting that forces one model on every subagent: it overrides the per-role defaults.

The Lead sets its own effort per session (`/effort`, `--effort`): Medium, High, or `xhigh`, depending on the task. The Engineer, QA Engineer, and Reviewer default to High through `effort: high` in their agent files, independently of the Lead, so raising the Lead's effort does not raise the whole team. Escalating a subagent above High is a deliberate choice for one task the Lead judges hard, never automatic.

| Work | Effort |
| --- | --- |
| Routine or mechanical work | Medium |
| Normal implementation, QA, and review | High |
| Difficult architecture, broad ambiguous reasoning, hard debugging | Extra High (`xhigh`) |
| Genuinely difficult, correctness-critical work, as an explicit escalation | Max |

Normal Cycles never require Extra High or Max. Escalate for the hard step, then return to the default.

Recommended settings:

| Work | Session |
| --- | --- |
| Milestone planning | fresh session, `/model opus`, `/effort xhigh` |
| Implementation Cycle | fresh session, `/model opusplan`, `/effort high`: draft the Cycle Brief in plan mode on Opus, then leave plan mode to run the Cycle on Sonnet; Engineer and QA run on Sonnet and the Reviewer on Opus, all at High, by their defaults |
| Mechanical task | `/model sonnet` (or `haiku`), `/effort medium` |
| Hard-debugging escalation | `/model opus`, `/effort xhigh`; `/effort max` only as an explicit escalation; return to the Cycle settings afterward |

## Context budget

The repository is the durable project memory; a conversation is not.

- Start a fresh session, or `/clear`, after a Cycle is complete and committed, and after milestone planning before implementation.
- Use `/compact` only to continue the same unfinished task when the conversation still holds useful transient context.
- Do not carry several completed Cycles in one conversation for continuity.
- A new session recovers state from `CLAUDE.md`, this document, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/CURRENT_CYCLE.md`, Git status and history, and the relevant code and tests.

Habits:

- Reference repository paths and doc sections in handoffs instead of pasting large files.
- Read the focused files a task needs; do not load unrelated files or re-read the whole repository.
- Keep `CLAUDE.md` a concise operational entry point.
- Use a subagent for isolation, independent validation, or parallel work, not for a trivial single-step task.

Usage optimization never weakens quality. Behavioral changes still go Engineer → QA → Reviewer, and the Verification commands still run in full. Savings come from model routing, effort routing, shorter contexts, and fewer unnecessary agent and tool calls.

## Isolation for deliberate breakage

Mutation and deliberate-breakage experiments (breaking code on purpose to check that a test fails) run only in an isolated copy, never by editing and restoring files in the active working tree, even briefly. This applies to every role.

Copy the working tree, including uncommitted changes, without `.git` and `.venv`, so the copy builds its own environment and imports its own `src/`:

```bash
scratch="$(mktemp -d)"
rsync -a --exclude .git --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .mypy_cache --exclude .ruff_cache ./ "$scratch/go-poker/"
cd "$scratch/go-poker" && uv run pytest -q
```

Break the copy, run the relevant tests there, report what was broken and whether a test caught it, then delete the copy.

## Testing policy

`distinct rule -> focused test`

Use representative boundaries and a small number of integration tests that drive realistic sequences through the public operations. Avoid:

- tests that only assert constants
- duplicated coverage across layers
- large combinatorial matrices without distinct behavior
- defensive tests for impossible state created only by manually corrupting internals

Tests are deterministic: randomness comes only through the test seams in `docs/ARCHITECTURE.md`, and randomized or stress tests use fixed seeds. A milestone plan in `docs/CURRENT_CYCLE.md` links here and adds only milestone-specific test guidance.

Standing tooling decisions:

- **Hypothesis is not used.** Milestone 3 found the deterministic seeded stress test with invariant checks sufficient: the limit is the oracle, not the generator. Revisit only when a milestone offers a concrete benefit; adding it is a dependency decision.
- **Integration-test helpers stay local** to their test directory (the betting `conftest.py` and module-level helpers), accepting some duplication, and the pytest and `pythonpath` configuration stays unchanged. A shared test-helper package is a possible future tooling change, only if the duplication becomes materially painful.

## Architecture Decision Records

`docs/ARCHITECTURE.md` is the source of truth for the current architecture. An ADR records why a lasting decision was made, when future work needs its context and rejected alternatives.

Write an ADR when a decision establishes or materially changes a lasting:

- public API contract
- persistent state model
- subsystem or team ownership boundary
- external dependency
- cross-team integration contract
- major domain interpretation with broad consequences

Private helpers, test structure, local naming, and ordinary refactors do not get ADRs. Past decisions are not backfilled: they stay recorded in `docs/ARCHITECTURE.md` and the cycle records.

- The Lead drafts the ADR while designing; it becomes Accepted when the user approves the decision.
- ADRs live in `docs/adr/NNNN-short-title.md`, numbered from `0001`; the directory is created with the first ADR.
- `docs/ARCHITECTURE.md` states the resulting architecture and links to the ADR instead of restating its reasoning.
- An accepted ADR is not rewritten. A later ADR supersedes it, and both say so.

Template:

```markdown
# NNNN: Title

Status: Accepted (YYYY-MM-DD) | Superseded by NNNN

## Context

## Decision

## Alternatives considered

## Consequences
```

## Control files and Meta Cycles

Control files define how the team works: `CLAUDE.md`, `AGENTS.md`, `.claude/agents/`, and this document. No role modifies them during feature work. The Lead proposes improvements in the Process improvements section of its report, and control files change only in a **Meta Cycle**: a dedicated workflow change the user asks for. A Meta Cycle changes no production code, and no tests except to verify the workflow itself. It is verified with the project Verification and a consistency check of the control files, and committed only with user approval.

## Future organization

This direction is recorded, not built. A new team is created only when there is a real, independently ownable subsystem and enough parallel work to justify a boundary between teams; until then, the Core Engineering Team does the work. Creating a team is an ownership decision for the user and a Meta Cycle, and its integration contract normally gets an ADR.

- Once the core engine is complete and stable, likely around Milestone 5 (complete continuous hand/game loop), revisit the structure. The expected split is a **Core Engine Team** and a **Platform / Backend Team**.
- Once stable client/server contracts exist (the backend API and real-time milestones): a **Web/Desktop Team** and a **Mobile Team**.
- Specialized teams only when justified: **Simulation/Bots**, **Data/Analytics**, and **AI/Coaching**.
