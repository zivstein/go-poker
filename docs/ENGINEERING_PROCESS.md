# Engineering Process

This is the normative operating model for the current Go! Poker AI engineering team.

The organization runs in the mode set in `.claude/ownership.json`. In `single-team` mode, everything in this document applies except [Multi-lane organization](#multi-lane-organization-inactive-until-activation), which is inactive until activation.

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
| `.claude/ownership.json` | lanes, path kinds, co-owned paths, the kinds each role may write, and the organization mode |
| `README.md` | human-facing overview; not authoritative for milestone status or history |
| implementation-facing docs | README, API, and module documentation describing implemented behavior |
| ADRs | why an important durable decision was made |

Each fact has one home. Other documents link to it rather than restating it.

## Current Team

In `single-team` mode, the organization is one engineering team.

| Role | Owns |
| --- | --- |
| User | product/domain/architecture decisions, milestone scope, Cycle Brief approval, dependencies, ownership changes, process changes, commit/release approval |
| Engineering Lead | planning, orchestration, escalation, finding triage, final verification, status, Cycle completion |
| Engineer | production implementation, focused implementation tests, affected implementation-facing docs |
| QA Engineer | independent behavioral/adversarial validation and test code |
| Reviewer | final independent architecture/code/test review; read-only |

In this document and the agent files, **the Lead** is the Engineering Lead in `single-team` mode and the Work Order's Cycle Lead in `multi-lane` mode.

In `single-team` mode, only the Engineering Lead may mark a Cycle complete. In `multi-lane` mode, the Orchestrator does, through the Org boundary Work Order.

No role commits or pushes without explicit user approval. The one exception applies only in `multi-lane` mode: the project scripts make checkpoint and update commits on Work Order branches (see [Commit binding and staleness](#commit-binding-and-staleness)). Pushes still happen only through the user-invoked `/finish-cycle`.

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

Handoffs are conversation outputs, not repository documents. In `multi-lane` mode they stay conversation outputs inside the Work Order session, each naming its checkpoint SHA, and the Work Order record persists (see [Work Order record](#work-order-record)).

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

Write permissions are defined in [`.claude/ownership.json`](../.claude/ownership.json). The map gives every path a **kind** and lists the kinds each role may write. Patterns, precedence and the fail-closed rule for unmapped paths are in the map.

- The permissions apply in both modes. Tooling enforces paths only in `multi-lane` mode.
- In `single-team` mode, the whole repository is one lane, and the Engineering Lead holds the Cycle Lead's permissions.
- Every role may read everything. The Reviewer writes nothing.

Rules the map cannot express:

- The Engineer edits `ARCHITECTURE.md` only for implemented-behavior detail. The Lead records approved decisions there.
- The Lead verifies implementation-facing docs at closeout. QA reports documentation issues and does not edit them.
- The Engineer's `design` permission covers token and asset files only. The Reviewer judges this, because tooling cannot.
- The `tooling` and `tooling-tests` kinds exist only in Meta work. There, the Engineer may write both and QA may write `tooling-tests`, so a Meta Cycle can run the full Engineer → QA → Reviewer flow. This applies in both modes.

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
- In `multi-lane` mode, ADRs are Org-owned. An ADR lands in an Org Work Order before the lane Work Order that depends on it.

The ADR template is in `docs/company/COMPANY_MANUAL.md`.

## Control Files and Meta Work

Control/process files are the Meta lane's own paths in [`.claude/ownership.json`](../.claude/ownership.json), excluding the Org paths the Meta lane includes. No other operational document lists them.

They are not modified during feature work.

Process improvements are applied as dedicated Meta work with user approval.

In Meta work, the Lead edits control files. The exception is the `tooling` and `tooling-tests` kinds, which the Engineer and QA may also write (see [Ownership](#ownership)).

Meta work does not change production code, product tests, dependencies, or product behavior unless that change is separately approved as product work. Workflow-tooling tests change with the tooling they test.

## Technology Freeze

In force for M8 C5, C6 and the Friends Alpha implementation, in both organization modes. It covers AI orchestration and organization tooling only.

- **Permitted:** Claude models through Claude Code; Claude Code sessions, subagents, worktrees and hooks; GitHub pull requests, Actions and branch protection; the `gh` CLI; stdlib project scripts.
- **Deferred until after Friends Alpha:** Paperclip, OpenRouter, Codex worker integration, multi-provider routing and other orchestration frameworks.
- **Not covered, and unchanged:** the development toolchain (uv, Ruff, mypy, pytest), the approved Figma MCP design workflow, and the product's own technology (revisited in M8 C7).
- Usage and performance telemetry are preserved (see Usage Measurement and [Parallelism and budgets](#parallelism-and-budgets)).

## Multi-lane organization (inactive until activation)

**Inactive.** Nothing in this section applies while `.claude/ownership.json` has `mode: single-team`, and roles skip it in that mode, except in Meta work that implements it.

The exceptions are the rules marked **both modes**. They apply in `single-team` mode too:

- since C5.4a, the `quality` push trigger limited to `master`, and the `ownership` job's repository and base checks (see [Git and integration](#git-and-integration));
- once C5.4b builds them, the guard's Git rule and the Permit layer (see [Enforcement](#enforcement)).

How the section becomes active:

- **Activation.** In M8 C5.6, a Meta Work Order flips the mode and activates the Core, Backend/API, Design, Org and Meta lanes. Three things come first: the tooling from C5.4 and C5.5, the Product Owner's acceptance of the single-account risk, and branch protection on `master`.
- **Supervised.** Until C5.6 has demonstrated the Work Order lifecycle, this is a **supervised multi-session** organization. Sessions are connected by the Work Order record and the Product Owner. A step is described as unattended only after C5.6 has shown it working without the Product Owner.
- **Rationale** is in [ADR 0007](adr/0007-lane-ownership-and-cross-lane-contracts.md) and the archived [C5.2 design package](company/M8_C5_2_ORGANIZATION_DESIGN.md).

The Product Owner is the User in [Current Team](#current-team). Inside every Work Order, these are unchanged: the Cycle Flow, Definition of Ready and Done, the Small-Change Path, severity and gates, Verification Discipline, the handoff contents and Reviewer independence.

### Roles

| Role | Owns | Never |
| --- | --- | --- |
| Product Owner | approval-level decisions (Approval and Escalation); each Work Order's approval (G0); `/finish-cycle`; merges; GitHub settings; design approval | — |
| Orchestrator | milestone and Cycle planning; drafting and splitting Work Orders; dependency and overlap analysis; lane assignment; cross-lane escalation triage; the integration check (G6); Cycle completion; Org Work Orders; running the start, sync and cleanup scripts | writing outside a Work Order worktree; approval-level decisions; push or merge |
| Cycle Lead | running one approved Work Order: delegation, delivery check, finding triage, closeout docs in the lane, final verification, the gate ledger, the Cycle Report | writing outside the Work Order's lane; cross-lane decisions; push or merge |
| Engineer, QA, Reviewer | their agent roles, inside the Work Order's lane | as in their agent files |

- **Lanes.** A lane is an ownership boundary, not a standing team. A Cycle Lead exists only as long as one Work Order. Domain continuity lives in the repository: architecture sections, ADRs and tests.
- **Session identity** is defined in `CLAUDE.md`.
- **Org boundary Work Order.** At each M8 Cycle boundary, the Orchestrator runs one Small-Change Org Work Order, with Reviewer and verification.
  - It records the closing Cycle's completion and the next Cycle's Work Order split in `CURRENT_CYCLE.md`, plus any roadmap, plan or ADR change approved for that boundary.
  - A Work Order's live state (open, blocked, merged) lives only in its record or PR, never in `CURRENT_CYCLE.md`.
- **Org Work Orders.** The Orchestrator runs one in a separate Cycle Lead session (the default), or by switching its own session into the Work Order worktree and back. While switched in, it is that Work Order's Cycle Lead, and the Work Order's gates apply.
- **No Product lane.** Product drafting is Orchestrator work in Org Work Orders, under Product Owner approval as today.

### Lanes

Lanes, their branch prefixes and their paths are in `.claude/ownership.json`. A Web lane is added only when activated, after M8 C7.

- A Work Order belongs to exactly one lane. It edits only that lane's paths and the co-owned paths the map gives its lane; on a co-owned path, only its lane's sections, which the Reviewer judges.
- A Work Order that crosses lanes is invalid. The Orchestrator splits it into one Work Order per lane.
- A change needed in another lane is a **Contract Request** to the Orchestrator, who opens a Work Order in the owning lane.
- Tooling derives the lane only from the branch prefix. An unmapped path or an unknown prefix fails closed.
- Only the Meta lane changes control files. An approved dependency lands in a Meta Work Order before the Work Order that uses it.
- The main checkout is read-only for every role.

### Work Order

A Work Order is a Cycle Brief plus a coordination header. The header uses `key: value` lines, the closeout manifest's format. One approved M8 Cycle is one or more Work Orders, and the Org boundary Work Order records the split.

```
id: WO-M8C6-01
title: <title>
lane: core
type: behavioral          # behavioral | small-change | meta | design
branch: core/wo-m8c6-01-<slug>
base: <origin/master SHA at start>
depends: none             # Work Orders merged before this one starts
integrates-after: none    # Work Orders merged before this one's G6 (contract-first)
consumes: none            # ADR-NNNN @ <master SHA> (concurrent | after-merge), or <doc>#<section> @ <SHA>
produces: none            # ADR-NNNN -> <consumer lanes>
co-owned: none            # co-owned paths this Work Order expects to touch
closeout: none            # paths of a closeout kind; none for org and meta Work Orders
size: <paths, lines>; sizing decision: <whole | split>
qa: required              # or: skipped — <reason> (Small-Change Path)
approved: <date> by PO
```

The body is the eight Cycle Brief sections. While the Work Order runs, three sections are appended:

- `## Gate ledger`, with rows written by the checkpoint script: gate, verdict, SHA, gated patch-id, phase (concurrent consumers only), verification;
- `## Escalations`;
- `## Cycle Report`. Its gate outcomes are the ledger and are not repeated. It adds wall-clock time (from checkpoint timestamps), gate and fix rounds, the full-verification count, resumes and manual Product Owner steps.

Rules:

- `lane`, `type` and `branch` agree. The branch is `<lane prefix>wo-<milestone><cycle>-<nn>-<slug>`, and a `meta` type requires the `meta/` prefix.
- A Work Order with an unmerged `depends` entry is not started. An unmerged `integrates-after` entry blocks only its G6.
- `consumes` pins each cross-lane contract to the `master` SHA it was read at.
- `closeout` paths are only of the map's `closeout_kinds`, never a deliverable and never a control file. They may be edited after G3 without re-review.

### Work Order record

There is one record per Work Order at any moment:

1. It is drafted and approved in the Orchestrator session.
2. The start script writes it to the git-ignored `.claude/work-order.md` in the Work Order worktree. Any later session resumes from it.
3. PR-mode closeout copies it into the pull request description. From then on, the PR is the record. New ledger rows (for example after a CI fix) go to a git-ignored pending-ledger file. The next PR-mode run merges them into the PR description and deletes the file.

The repository is public, so PR descriptions carry engineering content only: no usage or cost figures, no personal data.

### Work Order operations

Each Work Order runs in a short-lived, top-level Claude Code session in its worktree. Sessions do not message each other. Manual Product Owner steps are marked **[PO]**.

**Launch**

1. The Orchestrator drafts the Work Order. **[PO]** approves it (G0).
2. The Orchestrator runs the start script. It creates the branch from a fresh `origin/master`, the worktree, `uv sync` and the record, then prints the worktree path.
3. **[PO]** opens a new top-level session in that worktree and sends `Run Work Order <id>`. The Orchestrator may open the session itself where the app supports it, but the Product Owner still owns it, and the procedure does not rely on it.
4. The Cycle Lead identifies its role from the checkout, reads the record and the documents it references, and runs the Engineer → QA → Reviewer loop.

**Monitor**

- The Product Owner sees each Work Order session directly.
- On request, or before planning the next step, the Orchestrator reads every active worktree's record and the PR and CI state with read-only `gh` calls. It runs no polling loop and edits no Work Order record; only the Work Order's own session writes it.
- `scripts/usage_report.py` runs for each Work Order session after it ends.

**Escalate**

1. The Cycle Lead writes a `BLOCKED` entry and ends its turn.
2. **[PO]** brings it to the Orchestrator, which triages it. An approval-level question goes to the Product Owner.
3. **[PO]** passes the answer into the Work Order session. The Cycle Lead records it under Escalations and continues.

**Resume** (session lost, context exhausted, CI failure, merge conflict, or a concurrent consumer whose producer has merged)

1. **[PO]** notices the trigger: the session has ended, GitHub reports a CI failure or conflict, or the Orchestrator reports that a producer has merged.
2. **[PO]** opens a fresh session in the same worktree and sends `Resume Work Order <id>`.
3. The Cycle Lead reads the record (from the PR once it is open) and the checkpoint log, and continues from the last recorded gate. Uncommitted changes since the last checkpoint are unvalidated work, never gated work.

**Return**

1. The Cycle Lead finishes the Cycle Report and the closeout manifest.
2. **[PO]** invokes `/finish-cycle` in the Work Order session. G4 runs, then the PR opens or updates.
3. CI runs (G5).
4. **[PO]** asks the Orchestrator for G6. The Orchestrator reads the PR and recommends merging or not.
5. **[PO]** merges (G7).
6. **[PO]** tells the Orchestrator. The Orchestrator then:
   - fast-forwards the main checkout;
   - removes the worktree and local branch;
   - checks the open Work Orders that list this one in `integrates-after`.
7. For each such concurrent consumer, the Orchestrator reports that phase 2 can start. **[PO]** relays it to that session, or opens a resume session for it.

Every Work Order needs these manual steps: approve, open the session, invoke `/finish-cycle`, request G6, merge, report the merge. Add:

- one relay per `BLOCKED`;
- one noticing step and one session per resume;
- one phase 2 relay per concurrent consumer.

### Commit binding and staleness

- At each gate, the Cycle Lead runs the checkpoint script with an explicit path list. The script:
  - refuses unless the working tree's changed paths equal that list;
  - refuses on `master`, on an unmapped branch, or with an empty diff;
  - never pushes.
- The script writes the gate's ledger row, including the **gated patch-id**: `git patch-id --verbatim` over the merge-base diff against a freshly fetched `origin/master` (`origin/master...HEAD`), excluding only the declared `closeout` paths.
  - `--verbatim` is required, because `--stable` ignores whitespace, Python indentation included.
  - The local `master` is never the base, because it can be stale in a worktree.
  - Every other file is gated, Markdown and control files included.

Two staleness rules apply:

1. **Patch-id rule** (every Work Order). A gate stays valid while the head's gated patch-id equals the one at that gate's SHA.
2. **Contract-first rule** (concurrent consumers only). A gate is a **phase 2** gate when the producer's squash-merge commit on `origin/master` is an ancestor of its SHA; otherwise it is **provisional**. The checkpoint script writes the phase. Once the producer has merged, provisional G1–G3 are invalid regardless of the patch-id, and only phase 2 gates count for G4–G6.

| Change after a gate | Gated patch-id | Effect |
| --- | --- | --- |
| fix commit | changes | the affected gates re-run under the existing re-validation rules |
| any other edit after G3, Markdown and control files included | changes | G3 re-runs; G2 too if behavior may change |
| edit to a declared `closeout` path after G3 | unchanged | allowed; the Cycle Lead verifies |
| `origin/master` merged in without conflicts | unchanged | only G5 re-runs |
| merge with conflict resolution, or changed context lines | changes | G3 re-runs for the affected files; G2 too if behavior may change |
| producer merged (concurrent consumer) | either | provisional G1–G3 re-run as phase 2 gates |

Updating a branch always merges `origin/master` into it and never rebases, because a rebase would rewrite the gated SHAs.

- The Product Owner may use GitHub's "Update branch" only when the Work Order session reports no unpushed checkpoint.
- Otherwise, the Cycle Lead runs the update script. It first brings in the remote branch if it is ahead (fast-forward, or a merge if they diverged), then merges `origin/master`. On a conflict it stops, so the Cycle Lead can resolve it and checkpoint.

### Contract-first parallelism

- The producing lane owns the implemented contract: its `ARCHITECTURE.md` sections and public docstrings.
- A cross-lane contract that is not yet implemented is versioned as an accepted ADR (Org lane, Product Owner acceptance).
  - The ADR number is the contract version, and a change is a new ADR that supersedes it.
  - Once the producer has merged, `ARCHITECTURE.md` describes the implemented contract and cites the ADR. There is no separate contract registry.
- Consumer-driven contract tests live in the consumer lane.
- A change to a contract another lane consumes needs the Reviewer's contract check. If it is public API, it also needs Product Owner approval.

At G0, the Orchestrator chooses one of two modes:

- **After-merge.** The consumer lists the producer in `depends`, starts after the producer merges, and pins `consumes` to that `master` SHA. This mode is used when:
  - no stable contract exists;
  - the consumer cannot be built or verified without the producer's real symbols and has no approved port;
  - concurrency saves nothing.
- **Concurrent**, when the contract is stable:
  1. *Contract first.* An Org Work Order lands the accepted contract ADR: signatures, semantics, errors, invariants, and how the consumer is isolated. The producer pins `produces: ADR-N`. The consumer pins `consumes: ADR-N @ <SHA> (concurrent)` and `integrates-after: <producer>`.
  2. *Producer.* It implements the ADR with conformance tests in its own lane, and integrates through the normal gates.
  3. *Consumer, phase 1.* It builds what does not need the producer's real symbols, tested against consumer-owned doubles under its own test paths.
     - Doubles never live in producer paths or on a production code path.
     - A consumer-owned port (for example a `Protocol`) is a new abstraction, so it is allowed only when the contract ADR approves it.
     - Phase 1 gates are provisional.
  4. *Consumer, phase 2.* After the producer merges, the consumer brings in `origin/master`, wires the real implementation, runs its contract tests against it, and re-runs G1–G3 as phase 2 gates. Phase 1 verdicts never carry over.
  5. *Integration.* The consumer's G6 requires:
     - the producer merged;
     - both Work Orders pinned to the same contract ADR, with no superseding ADR merged since;
     - phase 2 gates;
     - no double reachable from production code (the Reviewer's check).
  6. *Contract change.* A needed change is a `BLOCKED` Contract Request. A new ADR supersedes the old one, and every pinned Work Order re-pins and is re-approved at G0. If the producer has already merged, a new producer Work Order is needed before the consumer can reach G6.

An unclear contract is escalated, not interpreted.

**Design handoff.** A Web Work Order is Ready only when it has all five of: an approved Figma frame URL, merged token names, component states, the motion specification and acceptance viewports. Design approval is the Product Owner's (`docs/design/DESIGN_INDEX.md`).

### Gates

| Gate | Owner | Passes when | Bound to |
| --- | --- | --- | --- |
| G0 Ready | Product Owner, approving the Orchestrator's Work Order | Definition of Ready; `depends` merged; contracts pinned (in concurrent mode, the contract ADR is on `master`); co-owned overlap checked | base SHA |
| G1 Delivery | Engineer, then the Cycle Lead's check | `DELIVERED`; full verification | SHA + patch-id |
| G2 QA | QA | `PASSED`, or skipped under the Small-Change Path with the reason | SHA + patch-id |
| G3 Review | Reviewer | `APPROVED`; no open Critical or Major finding; contract and section-ownership check | SHA + patch-id |
| G4 Closeout | PR-mode `/finish-cycle` | gated patch-id equals G3's; ownership check; final verification; manifest equals the merge-base diff | head SHA |
| G5 CI | GitHub Actions | `quality` and `ownership` green; branch up to date | PR head |
| G6 Integration | Orchestrator | `integrates-after` merged; contract versions match and are not superseded; consumer gates are phase 2; no conflicting open PR; the PR head's gated patch-id equals the ledger's G3 | PR head |
| G7 Merge | Product Owner | squash merge | PR head |

### Escalation

1. **Engineer, QA, Reviewer → Cycle Lead:** as in Approval and Escalation.
2. **Cycle Lead → Orchestrator:** the Cycle Lead writes a `BLOCKED` entry and stops when:
   - a change is needed outside the lane (Contract Request);
   - a consumed contract is ambiguous, or changed after its pin;
   - a co-owned overlap or conflict with another Work Order appears;
   - a failure is caused by another lane's merge;
   - a third fix round on the same finding would be needed;
   - the Brief does not answer a scope question.
3. **Orchestrator → Product Owner:** every approval-level decision, plus:
   - Work Order approval, `/finish-cycle` and merge;
   - lane activation or a change to the ownership map;
   - a contract change that is public API;
   - raising the concurrency cap;
   - a Web Work Order without approved design;
   - any GitHub setting.

A `BLOCKED` entry states the trigger, the need, the options, a recommendation, and who decides. Telemetry never stops a Work Order.

### Parallelism and budgets

| Situation | Rule |
| --- | --- |
| Different lanes, no unmerged dependency | parallel, within the cap |
| Producer and consumer with an accepted contract ADR | concurrent when the Orchestrator chooses it at G0; the consumer's G6 waits for the producer's merge |
| Consumer without a stable contract, or needing the producer's real symbols with no approved port | starts after the producer merges; its Brief may be drafted earlier |
| Two Work Orders on the same co-owned path | allowed; overlap is declared at G0, and the Orchestrator serializes them when the sections overlap; the second to merge resolves conflicts |
| Same lane | one active Work Order per lane during the pilot |
| Meta Work Order | exclusive: starts only with no Work Order in flight, and none starts until it merges |
| Org boundary Work Order | between M8 Cycles, with no product Work Order open |
| Design → Web | Web blocked until approved design and merged tokens |

- **Concurrency cap:** two active Work Order sessions during the pilot. Parallel lanes save wall-clock time, not usage, and drain the 5-hour limit faster.
- **Size:** each Work Order carries its Cycle Sizing decision. There are no new thresholds.
- **Telemetry:**
  - `usage_report.py` runs per Work Order session, aggregated across worktree transcript directories. Raw usage stays in the git-ignored `.claude/usage/`.
  - Performance is recorded in each Cycle Report (see [Work Order](#work-order)).
  - The C6 pilot summarizes both in `docs/company/TOOLING_EVALUATION.md`. None of it is a gate.
- **Context:**
  - The Orchestrator reads Work Order records, Cycle Reports and PR and CI state, never full diffs. Each M8 Cycle gets one fresh Orchestrator session.
  - Each Work Order gets a fresh Cycle Lead session, and a resume starts a fresh session from the record.
- **Models:** routing is unchanged. The Orchestrator and Cycle Leads use the normal Cycle Lead row; planning-heavy Orchestrator sessions use the milestone-architecture row.
- **Agent teams** (experimental in Claude Code) stay disabled. They would start named subagents as teammates in the lead's permission mode, bypassing per-role routing and tool limits.

### Git and integration

- **Branch:** one per Work Order, from the latest `origin/master`, created by the start script after G0.
- **Worktree:** under the git-ignored `.claude/worktrees/<id>/`, bootstrapped with `uv sync`. One writer session per worktree.
- **Main checkout:** stays on `master` with a clean tree.
  - After a merge, the Orchestrator fast-forwards it (fast-forward only, clean tree only).
  - The Orchestrator removes the worktree and local branch only when `gh` reports the PR merged.
- **Merge:** squash merge into protected `master`, with the manifest's commit message.
- **Protection,** set by the Product Owner in C5.6:
  - a pull request is required, with required checks `quality` and `ownership`;
  - the branch must be up to date;
  - no force push or deletion;
  - squash merge only;
  - enforced for administrators.
- **CI:**
  - `quality` runs `verify.py` on pull requests and on pushes to `master` only (**both modes**).
  - A separate `ownership` job runs on `pull_request_target`. It checks out `master`, fetches the PR head as data only, and runs `master`'s `scripts/check_ownership.py`, so a PR never runs code that judges it. It installs nothing and uses no cache.
    - **Both modes:** it fails a PR whose head is in another repository or whose base is not `master`.
    - In `single-team` mode it makes no path checks.
    - The script's docstring is the home of its rules.

**PR-mode closeout.** `/finish-cycle` stays user-only. In a Work Order worktree it keeps today's checks for:

- machine-local paths;
- an operation in progress, or unmerged paths;
- git-ignored paths;
- verification that passes and leaves the tree unchanged;
- committing with hooks.

The checks that assume one commit pushed straight to `master` are replaced:

- **P1** The branch has a mapped lane prefix and is not `master`. Its upstream is absent, or is an ancestor of HEAD (never force). A remote that is ahead stops the run.
- **P2** `origin/master` is fetched. The leftover changes are a subset of the manifest. They are staged by explicit path and committed as the closeout checkpoint.
- **P3** The merge-base diff's path set equals the manifest.
- **P4** The ownership check passes.
- **P5** The gated patch-id equals the record's G3 entry. For a concurrent consumer, that must be a phase 2 gate.
- **P6** The push goes out without force or tags (`-u` the first time), and the remote equals HEAD afterwards.
- **P7** The PR is created or updated with the record and the head SHA. Its title is the manifest's `message:` line, which becomes the squash commit message.

The manifest keeps its format. Its `path:` lines list the whole merge-base diff. When C5.5 implements PR mode, the script's docstring becomes the home of these checks, and this list becomes a pointer to it.

### Enforcement

| Layer | Mechanism | Strength |
| --- | --- | --- |
| Prevent | a PreToolUse guard hook that reads the map (see below) | best effort: command matching is not a security boundary |
| Detect | the `ownership` CI job, run from `master`'s code. Every merge-base-diff path must be in the branch's lane or in a co-owned entry for it. Unmapped paths and unknown prefixes fail, and only `meta/` may touch control files. | authoritative for path ownership |
| Permit (**both modes**, from C5.4b) | committed `.claude/settings.json` (hook registration and deny rules); the Product Owner trims the machine-local allowlist | narrows routine risk |
| Judge | the Reviewer's scope, contract and section-ownership checks | what tooling cannot decide |

The guard hook:

- **Scope:** this repository and its worktrees only. Scratch copies, mutation experiments and scratchpad files are outside it.
- **Both modes**, once C5.4b builds it: it blocks raw state-changing Git and `gh` write subcommands, and allows the project scripts. This enforces only what `AGENTS.md` and this document already forbid.
- **`multi-lane` mode only:** it also blocks:
  - writes outside the branch's lane or the role's kinds;
  - writes in the main checkout;
  - work on an unmapped branch.

  The Work Order's own git-ignored record files stay writable.

**Single-account limit.** Every session acts with the Product Owner's Git and GitHub credentials. GitHub cannot tell an agent from the Product Owner, and a required PR approval is impossible, because an author cannot approve their own PR.

- Protection stops accidental direct pushes to `master`. It does not stop a deliberate agent, because the sessions hold administrator credentials.
- Pushes of Work Order branches and merges rest on the guard, deny rules and instructions. That is the same class of risk as today.
- The Product Owner accepts this residual risk explicitly before the C5.6 Brief is Ready; the decision is deferred until then (`CURRENT_CYCLE.md`).
- Identity separation (a machine user or token, or a credential sandbox) is a deferred decision (`CURRENT_CYCLE.md`).
