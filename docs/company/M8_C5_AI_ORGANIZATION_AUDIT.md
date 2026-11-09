# M8 C5 AI Organization Audit

**Status: HISTORICAL ANALYSIS. NO PROPOSAL IN THIS DOCUMENT IS APPROVED.**

Date: 2026-11-09 · Repository snapshot: commit `c1312ef` · Author: Engineering Lead (read-only audit)

This is reference material, not an operational instruction source and not a source of truth. It records the analysis the Lead presented to the Product Owner at the start of M8 C5. Every team, ownership, workflow, tooling, and pilot proposal below is **NOT APPROVED**. A proposal becomes a decision only when the Product Owner approves it, and it is then recorded in its own source of truth (`docs/ENGINEERING_PROCESS.md`, `docs/CURRENT_CYCLE.md`, an ADR, or the relevant control file), not here. When this document conflicts with an operational file, the operational file wins.

The inventory describes the snapshot above. Later changes are in Git.

## Since the audit

M8 C5.1 reconciled the M8 status documents and the documentation sources under its own Product-Owner-approved scope (finding 1 below). That work did not approve any proposal in this document.

## Scope

The Product Owner asked the Lead to inventory the existing AI engineering workflow and to propose an autonomous multi-team organization (Core, Backend/API, Web, Design, QA and independent Review, coordinated by one Lead/Orchestrator): team responsibilities, handoff contracts, worktree/branch ownership, PR/review gates, escalation, a native Claude Code vs Paperclip comparison, a C6 pilot, and a C5 implementation sequence. No files were edited during the audit.

## 1. Inventory at the snapshot

| Area | State |
| --- | --- |
| Agents | `engineer` (Sonnet, high; Read/Edit/Write/Grep/Glob/Bash), `qa-engineer` (Sonnet, high; same tools), `reviewer` (Opus, high; Read/Grep/Glob/Bash) |
| Skills | `/finish-cycle`, user-only, delegating to `scripts/finish_cycle.py` |
| Scripts | `verify.py` (single PASS/FAIL gate), `finish_cycle.py` (fail-closed closeout with a git-command guard), `usage_report.py` (cost and context telemetry); all tested in `tests/tooling/` |
| Hooks | none, intentionally |
| Settings | only the git-ignored `.claude/settings.local.json`; its allowlist included `Bash(uv run *)` and `Bash(python3 -)` |
| CI | GitHub Actions runs `verify.py` on push and pull request; `master` has no branch protection; the repository is public |
| Git | one checkout on `master`; closeout commits and pushes directly to `master`; a stale, fully merged local branch `meta-cycle-1-core-team` |
| Workflow | Brief → approval → Engineer → Lead check → QA → Reviewer → closeout → verification → Cycle Report with closeout manifest → `/finish-cycle`; Small-Change Path; severity gates; ownership matrix; verification discipline; model routing; Meta-work separation; ADR policy |
| Escalation | the approval-level decision list, `BLOCKED` from the Engineer, and Lead triage of every finding |

## 2. Findings

Capabilities the audit recommended preserving: the Cycle machinery and its gates; QA before an independent Reviewer that does not see the Engineer's reasoning; the severity model; fail-closed scripts behind an approved manifest; one home per fact; Cycle sizing with usage measurement; mutation experiments in a scratch copy; the Meta-work boundary.

Gaps found:

1. **Status drift.** `ROADMAP.md` and `CURRENT_CYCLE.md` said M8 had not started, while `M8_PLAN.md` showed C0 approved and Git (commit `3bd51b8`) and the Product Vision showed C1 complete. `docs/product/`, `docs/design/` and `docs/milestones/` were not in the Documentation Sources table. *(Addressed in C5.1.)*
2. **C5 scope mismatch.** `M8_PLAN.md` names a Product team and a `docs/organization/AI_ORGANIZATION.md` deliverable; the audit brief named a Design team, and `docs/company/` already holds organization material.
3. **Ownership is enforced only by prose.** QA can write to `src/`; the Reviewer has Bash; `Bash(uv run *)` permits arbitrary commands through `uv run`. Multiple teams would make cross-ownership edits easy.
4. **Single-checkout git model.** `finish_cycle.py` requires an existing remote upstream (it cannot create one) and pushes directly; there is no PR step, and CI runs after code lands.
5. **Per-subagent worktree isolation does not fit the role chain.** QA in a separate worktree cannot see the Engineer's uncommitted work, so Engineer, QA and Reviewer would have to share one worktree per work unit.
6. **New worktrees lack local state**: the git-ignored settings file and `.venv`.
7. **Usage telemetry would likely miss worktree sessions**, because `usage_report.py` derives the transcript directory from the main checkout's path (unverified).
8. **Handoffs exist only in the conversation**, which does not survive across sessions or teams.
9. **A single Lead holding every team's context** would repeat the context growth recorded in AIE-006.
10. **The Web framework is decided twice**: React and Vite in `ROADMAP.md`, delegated to C7 in Product Contract §12.

## 3. Proposed organization (NOT APPROVED)

**Orchestrator over Cycle Leads.** The main session in the main checkout becomes an Orchestrator: planning, Work Orders, dependency sequencing, integration and status, reading Cycle Reports rather than diffs. Each Work Order runs in its own session and worktree, where a Cycle Lead runs today's Engineer → QA → Reviewer flow unchanged.

**Teams as ownership lanes**, reusing the existing role agents, with the lane and its paths taken from the Work Order and enforced by a hook. Lane-specific agents only when tooling differs.

| Lane | Proposed ownership | Proposed activation |
| --- | --- | --- |
| Core | `src/go_poker/core/`, `src/go_poker/game/`, their tests, engine sections of `ARCHITECTURE.md` | now |
| Backend/API | `src/go_poker/app/` (moved from Core), later `server/`, `tests/app/` | C6 pilot |
| Web | `web/` | with client work |
| Design | `docs/design/`, the Figma file, the future token source | C4 |
| QA | tests within the lane plus cross-lane contract tests | with each lane |
| Review | read-only; a contract check when a shared interface changes | always |
| Orchestrator | `ROADMAP.md`, `CURRENT_CYCLE.md`, ADR drafts, shared contracts, control files in Meta work | always |

**Handoff contracts**, each gate result bound to the commit SHA it covered, with any later change making it stale:

- *Work Order*: the Cycle Brief plus lane, branch, base commit, owned paths, consumed contracts pinned to a commit, produced contract, dependencies, and a usage estimate.
- *Engineering Delivery, QA Report, Review Verdict*: as today, plus the SHA covered.
- *Contract handoff*: the producer merges first; the consumer starts from `master` after that merge (no rebase); the consumer never edits producer paths and raises a Contract Request instead.
- *Design handoff*: a `DESIGN APPROVED` Figma frame link (Product Owner approval), token names, component states, motion specification, and acceptance viewports.

**Git model**: one branch per Work Order (`<lane>/<milestone>-<cycle>-<slug>`); one worktree per branch under `.claude/worktrees/`; one writer per worktree at a time; squash merge of one commit per Work Order; `master` protected (pull request and the CI `quality` check required, no force push).

**Gates**: G0 Work Order approved → G1 Engineering Delivery (verification at the SHA) → G2 QA passed at the SHA → G3 Review approved at the SHA → G4 CI green on the merge result → G5 Orchestrator integration check → G6 Product Owner merge approval, replacing the direct push of `/finish-cycle`.

**Added escalation triggers**: a change needed in another lane's paths; an ambiguous consumed contract; two Work Orders touching the same files; a breakage caused by another lane's merge; more than two fix rounds on one finding; usage above twice the estimate or worker peak context above the `usage_report` threshold; Web implementing a design that is not `DESIGN APPROVED`; any GitHub-visible action.

## 4. Native Claude Code vs Paperclip (NOT APPROVED)

| | Native | Paperclip |
| --- | --- | --- |
| Form | existing agents, worktree sessions, one guard hook, GitHub PRs and CI | self-hosted Node server, React UI and database with an org chart, tickets, heartbeats, budgets and approvals; drives Claude Code through adapters (MIT, launched March 2026) |
| Operations | about three tooling changes, tested in `tests/tooling/` | a server and database to run, upgrade, supervise and back up; headless Claude authentication; a young, fast-changing project |
| Source of truth | repository and GitHub only | its ticket store becomes a second source of truth, against "the repository is durable memory" |
| Usage cost | as today per Cycle (Milestone 6 Cycles: $4.90–$10.92 equivalent); parallel lanes save wall time, not total usage, and use the 5-hour limit faster | the same model tokens, plus cold-starting heartbeat runs (AIE-005: a cold closeout cost about eight times a warm one) and idle heartbeats |
| Budget control | after-the-fact telemetry used as an escalation trigger | hard real-time budget stops, its main advantage |
| Control | desktop review, per-tool permissions, fail-closed scripts | headless runs probably need broad permissions, a risk on a public repository (unverified) |

The audit recommended native first, revisiting Paperclip after C6 only if lanes routinely run three or more at once, the Product Owner's coordination time per Work Order becomes too high, or hard budget stops or scheduled autonomous runs are needed. Paperclip details came from third-party sources and were to be verified in a time-boxed spike: the Claude Code adapter, the permission mode it needs, and whether headless runs bill to a subscription or an API key.

## 5. Proposed C6 pilot (NOT APPROVED)

**Rebuy for a busted player, Core → Backend**, chosen because Product Contract §4 already approves it, it needs a real engine change (the application may not hold a second authoritative stack), and it has a real application consumer.

- *WO-A, Core*: an engine primitive adding chips to a seated player who is not a participant of the current hand; positive amounts only; atomic rejection; the chip-entry rule documented. About 4 paths and 300 lines.
- *WO-B, Backend*: `TableSession.rebuy(user_id, expected_revision)`, accepted only for a member with zero chips outside a hand they play, adding exactly `settings.buy_in` through WO-A; one shared transition; a resume attempt while waiting; rejections as values. Starts from `master` after WO-A merges; may not edit `game/`. About 6–8 paths.
- *Measures*: usage and peak context per lane, Product Owner interventions and time, wall-clock time, handoff defects, stale-gate events, hook blocks, CI results; intended to satisfy M8 exit gate 5.
- *Ready questions*: engine behavior for a zero-stack player; whether a mid-hand rebuy is rejected (recommended) or held as a pending intent; wallet debit left to the caller as a C7 concern.
- *Fallback*: the action-timer timeout command (Product Contract §6), Backend only, without a cross-team handoff.

## 6. Proposed C5 sequence (NOT APPROVED)

1. **C5-1 Status reconciliation** in the current workflow. *(Carried out as C5.1 under its own approved scope.)*
2. **C5-2 Organization specification**: normative rules in `ENGINEERING_PROCESS.md`, rationale under `docs/company/`, ADR 0007 for team ownership boundaries, and updates to `CLAUDE.md`, `ORGANIZATION_ROADMAP.md` and the Company Manual's hooks section.
3. **C5-3 Ownership and git guard**: a machine-readable ownership map, a standard-library `scripts/guard.py` PreToolUse hook, and a committed `.claude/settings.json`, with tooling tests for blocked and allowed edits; removal of `uv run *` and `python3 -` from local settings.
4. **C5-4 Worktree and closeout tooling**: `.claude/worktrees/` ignored, worktree bootstrap, a branch-and-PR mode for `finish_cycle.py`, and worktree session aggregation in `usage_report.py`.
5. **C5-5 Branch protection**, configured by the Product Owner on GitHub.
6. **C5-6 Dry run**: the C6 planning record through worktree → PR → CI → merge.

## 7. Decisions presented to the Product Owner (all NOT APPROVED)

| ID | Proposal |
| --- | --- |
| D1 | Teams: Core, Backend/API, Web, Design, with shared QA and Review roles; no Product agent |
| D2 | `src/go_poker/app/` moves from Core to Backend/API |
| D3 | Teams as lanes reusing role agents; Web and Design agents only when needed |
| D4 | PR/worktree git model with squash merge, protected `master`, Product Owner merge approval |
| D5 | Handoffs carried in pull request descriptions and comments, which are public |
| D6 | A branch-and-PR mode for `/finish-cycle` |
| D7 | The first project hook (ownership and git guard) and a committed `.claude/settings.json` |
| D8 | Usage budgets as escalation triggers, not gates |
| D9 | Native first; Paperclip only on the triggers in section 4 |
| D10 | The rebuy pilot (or the timer fallback), after its Ready questions are settled |
| D11 | C5 documents: normative rules in `ENGINEERING_PROCESS.md`, rationale in `docs/company/`, no `docs/organization/` |
| D12 | Status reconciliation (C5-1) |
| D13 | ADR 0007 for team ownership boundaries |

## Sources consulted

Third-party, unverified against primary documentation:

- [Paperclip GitHub mirror](https://b-lab.team/en/content/ba8aff92-eea5-4c10-8ae1-99c38f4eb44a)
- [Paperclip overview (rywalker)](https://rywalker.com/research/paperclip)
- [Paperclip explained (Towards AI)](https://pub.towardsai.net/paperclip-the-open-source-operating-system-for-zero-human-companies-2c16f3f22182)
- [Paperclip deployment (Zeabur)](https://zeabur.com/blogs/deploy-paperclip-ai-agent-orchestration)
- [Paperclip (jimmysong)](https://jimmysong.io/ai/paperclip/)
- [Paperclip framework (MindStudio)](https://www.mindstudio.ai/blog/what-is-paperclip-zero-human-ai-company-framework)
- [Worktree isolation (claudelog)](https://claudelog.com/faqs/what-is-worktree-isolation-in-claude-code/)
- [Worktree isolation for teammates (issue)](https://claudeissues.com/issue/29614-global-worktree-isolation-for-subagents-and-teammates)
- [Worktree auto-reap (issue)](https://claudeissues.com/issue/50889-worktrees-from-isolation-worktree-auto-reap-when-subagent-returns-without-change)
- [Claude Code hooks guide](https://ytrofr.github.io/claude-code-guide/docs/guide/13-claude-code-hooks.html)
