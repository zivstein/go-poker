# M8 C5.2 AI Organization Design — Decision Package

**Status: ARCHIVED RATIONALE. Tier A, approved by the PO on 2026-11-09 with three refinements (section 16), was recorded in its operational sources in C5.3 (2026-11-09). Those sources are authoritative and win over this document. C5.3 refined the map's kinds (`tooling` and `tooling-tests` for OD20) and limited closeout kinds to `architecture` and `design`. Tier B and Tier C stay deferred to their gates (`docs/CURRENT_CYCLE.md`).**

Date: 2026-11-09 · Repository snapshot: commit `dc7a750` · Author: Engineering Lead · Input: [C5 audit](M8_C5_AI_ORGANIZATION_AUDIT.md) · Independent review: section 20

This package records the Product Owner's (PO) decisions on the multi-team organization and the C5.3–C5.6 plan, with their rationale. It is reference material, not an operational source. C5.3 records each approved decision in its own source of truth (sections 14 and 15), and this document is then archived as rationale, like the audit.

The decision register in section 16 replaces the audit's D1–D13 and maps to them.

## 0. Summary

Today's proven Cycle (Brief → Engineer → QA → Reviewer → closeout) stays unchanged as the inner loop. Around it:

- **Orchestrator.** One session in the main checkout. It plans, writes Work Orders, sequences dependencies, integrates and keeps status. It reads reports, not diffs. It makes its own edits (status, plans, ADR drafts) in Org Work Orders, like any other lane.
- **Work Orders and Cycle Leads.** Each Work Order (WO) belongs to one **lane** (Core, Backend/API, Design, Org or Meta; Web later) and runs in its own branch and worktree. A fresh **Cycle Lead** session runs it with the existing Engineer, QA and Reviewer agents.
- **Persistence and binding.** Gates are bound to commits through local checkpoint commits. A gate stays valid only while the WO's own change, apart from its declared closeout paths, is unchanged, which a Git `patch-id` checks. The WO record survives session loss and becomes the pull request description.
- **Integration.** A pull request into a protected `master`. CI runs verification, plus an ownership check that executes from `master`'s code, not the PR's. The Orchestrator runs an integration check, and the PO merges.
- **One home for ownership.** `.claude/ownership.json` holds the lane paths and role permissions in one place. A guard hook uses it to prevent violations; the CI check uses it to block them; the Reviewer judges what tooling cannot.
- **Activation switch.** Nothing changes for today's flow until a switch in `ownership.json` flips in C5.6.
- **Contract-first parallelism (OD11, approved).** A producer and a consumer may develop concurrently against an accepted, versioned contract. Integration waits for the verified producer implementation and a matching contract version (section 6).
- **Supervised sessions (OD18, approved).** Each WO runs in a short-lived top-level session. Launch, monitoring, escalation, resume and return are documented step by step, with every manual PO step named (section 2). Cross-session coordination is not claimed to be autonomous until C5.6 demonstrates it.
- **Technology freeze (OD16, approved 2026-11-09).** The freeze covers AI orchestration and organization tooling only.
  - In C5, C6 and the Friends Alpha implementation, the AI organization runs on the existing native stack: Claude models through Claude Code; Claude Code sessions, subagents, worktrees and hooks; GitHub PRs, Actions and branch protection; the `gh` CLI; stdlib project scripts.
  - Deferred until after Friends Alpha: Paperclip, OpenRouter, Codex worker integration, multi-provider routing and other orchestration frameworks.
  - Not covered by the freeze, and unchanged: the existing development toolchain (uv, Ruff, mypy, pytest), the approved Figma MCP design workflow, and the product's own technology (revisited in C7).
  - Usage and performance telemetry are preserved (section 10).
  - The freeze's home is `ENGINEERING_PROCESS.md` (recorded in C5.3). The M8 Plan's C6 row points to it (section 14).

## 1. Implemented, approved and proposed

Four different states. Only the first exists as running tooling.

**A. Implemented mechanisms** (in the repository at `dc7a750`, executed by tooling)

| Mechanism | Where |
| --- | --- |
| Single PASS/FAIL verification (Ruff check, Ruff format check, mypy, pytest) | `scripts/verify.py`, tested in `tests/tooling/` |
| Fail-closed closeout: manifest equals the working tree, verify, one commit, push to the tracked upstream, git-command guard | `scripts/finish_cycle.py`, invoked through the user-only `/finish-cycle` skill (`disable-model-invocation`) |
| Usage and context telemetry with non-blocking warnings | `scripts/usage_report.py` |
| CI `quality` job running `verify.py` on every push and PR | `.github/workflows/ci.yml` |
| Engineer, QA and Reviewer agents with per-agent model, effort and tools; the Reviewer has no Edit/Write tools | `.claude/agents/` |
| Layer boundary test: `core/` and `game/` never import `app/` | `tests/test_layering.py` |
| Machine-local permission allowlist (not committed) | `.claude/settings.local.json` |

Not present: hooks, committed `.claude/settings.json`, branch protection, worktrees, PRs. All work happens in one checkout on `master`.

**B. Approved policy** (in operational documents, followed by instruction and review, not enforced by tooling)

- `ENGINEERING_PROCESS.md`:
  - Cycle Flow, Brief approval, Small-Change Path, Definition of Ready/Done;
  - severity model and gates, Lead triage;
  - approval-level decision list;
  - Ownership table; no commit or push without user approval;
  - Meta boundary and control-file list;
  - Cycle Sizing, Verification Discipline, scratch-copy mutation experiments;
  - model routing, context and session policy;
  - ADR policy, Documentation Sources.
- `AGENTS.md` engineering rules; `CLAUDE.md` Lead role and verification rule.
- The M8 Plan (approved in C0), including the C5 and C6 rows and the exit gates; Product Contract precedence over `ROADMAP.md` (2026-11-09).

**C. Approved by the PO on 2026-11-09, not yet recorded or implemented** (the Tier A register, section 16), described in sections 2–15:

- Orchestrator and Cycle Leads; lanes and `ownership.json`;
- Work Orders and their operations; checkpoint commits and patch-id binding; contract-first parallelism;
- the guard hook and the `ownership` CI job; PR-mode closeout;
- gates G0 and G4–G7; the new escalation triggers; budgets;
- the technology freeze.

C5.3 records them; C5.4–C5.6 implement and activate them. Until then, A and B above are what is in force.

**D. Deferred** (Tier B and Tier C, section 16):

- acceptance of the single-account risk, which is required before the PR workflow or branch protection is enabled;
- `gh` as a tooling dependency; the C6 pilot choice; lane-specific agents;
- identity separation; auto-merge; nested sessions.

### What is preserved

| Mechanism | Disposition |
| --- | --- |
| Cycle Flow, Definition of Ready/Done, Small-Change Path | unchanged, inside each WO |
| Engineer, QA, Reviewer agents and models | unchanged roles; lane-neutral wording; the Reviewer adds a contract and section-ownership check |
| Reviewer independence (no Engineer reasoning) | unchanged; the Reviewer reviews the WO's merge-base diff at a SHA |
| Severity model, finding triage by the Lead | unchanged; the Cycle Lead triages |
| Approval-level decision list | unchanged; organization triggers added (section 8) |
| Cycle Sizing, Verification Discipline, telemetry as non-gates | unchanged, per WO |
| Mutation experiments in a scratch copy | unchanged; copy the WO worktree |
| Fail-closed closeout behind an approved manifest, invoked only by the user | kept; adds a PR mode with its own explicit checks (section 11) |
| `verify.py` as the single PASS/FAIL gate | unchanged; also the CI gate |
| One home per fact; Meta boundary; ADR policy | unchanged; the control-file list grows (section 13) |
| Fresh session per completed unit of work | unchanged; one session per WO |

### Compatibility with the current workflow and approved policy

- **Inner loop.** Engineer → QA → Reviewer runs exactly as today inside every WO: same agents, models, tools, handoff contents, Reviewer independence, severity gates, Verification Discipline and Small-Change Path. The additions are a checkpoint SHA in each handoff and the Reviewer's contract and section check.
- **Before activation.** Until the C5.6 switch, the organization runs in `single-team` mode. Work stays in one checkout on `master` with the Lead and today's `/finish-cycle`, and the guard enforces only what prose already forbids (raw state-changing Git).
- **Approved policy kept.** The approval-level decision list, the Meta boundary, the ADR policy, one home per fact, user-only closeout and "no push without user approval" all stay.
- **Approved policy changed.** Only the deltas in section 13, each tied to a decision in the register.

## 2. Organization model

```
                     Product Owner (human)
       decisions · WO approval · /finish-cycle · merge · GitHub settings
                              │
                        Orchestrator
       main checkout on master (read-only once multi-lane is active)
   plans · Work Orders · sequencing · integration check · Cycle completion
                              │   WO record ↓   ↑ BLOCKED / Cycle Report
   ┌─────────┬──────────┬─────┴────┬──────────┬──────────┐
  Core    Backend/API  Design     Org        Meta      (Web: after C7)
   └──── one Cycle Lead session per active WO, own branch + worktree
         └── Engineer → QA → Reviewer (shared agents)
```

**A lane is an ownership boundary, not a standing team.** A Cycle Lead lives only as long as one WO. A long-lived per-domain lead would accumulate context across WOs, which is the growth recorded in AIE-006. Domain continuity lives in the repository: architecture sections, ADRs, tests.

### Responsibilities

| Role | Owns | Never |
| --- | --- | --- |
| Product Owner | approval-level decisions (unchanged list); each WO's approval (G0); `/finish-cycle`; merges; GitHub settings; design approval (OD6) | — |
| Orchestrator | milestone/Cycle planning; drafting and splitting WOs; dependency and overlap analysis; lane assignment; cross-lane escalation triage; integration check (G6); Cycle completion; running Org WOs (see below); running the start, fast-forward and cleanup scripts | edits outside a WO worktree once multi-lane is active; edits `src/` or `tests/`; approval-level decisions; push or merge |
| Cycle Lead | running one approved WO: delegation, delivery check, triage, closeout docs in the lane, final verification, gate ledger, Cycle Report | edits outside the WO's lane; cross-lane decisions; push or merge |
| Engineer / QA / Reviewer | as today, inside the WO's lane | as today |

**Status writes have one path.** At each M8 Cycle boundary, the Orchestrator runs one **Org boundary WO**. It records the closing Cycle's completion and the next Cycle's WO split in `CURRENT_CYCLE.md`, plus any `ROADMAP.md`, plan or ADR change approved for that boundary. It is a Small-Change WO with Reviewer and verification: one extra PR per M8 Cycle, not per WO. The live state of each WO (open, blocked, merged) lives only in its WO record or PR, never in `CURRENT_CYCLE.md`.

**Org WOs.** The Orchestrator runs an Org WO either in a separate Cycle Lead session (the default), or by switching its own session into the WO worktree with Claude Code's worktree switch and back. While it is switched in, it is that WO's Cycle Lead: the guard reads the hook input's `cwd`, and the WO's gates apply.

**Session identity.** While multi-lane mode is active (`ownership.json`), a session is the Orchestrator in the main checkout. In a WO worktree, it is that WO's Cycle Lead: a branch with a lane prefix and a WO record present. `CLAUDE.md` states this conditionally in C5.3, so it is inert until activation.

### Interfaces

| From → To | Interface | Carrier |
| --- | --- | --- |
| PO → Orchestrator | decisions, WO approval | conversation |
| Orchestrator → Cycle Lead | approved WO | WO record (section 6) |
| Cycle Lead ↔ Engineer/QA/Reviewer | as today, plus the checkpoint SHA | conversation inside the WO session |
| Cycle Lead → Orchestrator / PO | `BLOCKED`, or Cycle Report + gate ledger | WO record, then PR description |
| Producer lane → consumer lane | an accepted contract ADR (version), then the merged implementation | `master` at pinned SHAs |
| Design → Web | approved frame, merged tokens, states, motion, viewports | `docs/design/` and the token source |
| PO → `master` | merge | GitHub |

### Work Order operations (OD18)

Each WO session is a short-lived, top-level Claude Code session in the WO worktree. Sessions do not message each other: the WO record and the PO connect them. Manual PO steps are marked **[PO]**.

**Launch**

1. The Orchestrator drafts the WO. **[PO]** approves it (G0).
2. The Orchestrator runs `start_work_order.py`, which creates the branch from a fresh `origin/master`, the worktree, `uv sync` and the WO record, then prints the worktree path.
3. **[PO]** opens a new top-level session in that worktree (desktop app: a new session on the folder; CLI: `claude` in the directory) and sends `Run Work Order <id>`. The Orchestrator may open the session itself where the desktop app supports it; the PO still owns that session. This is not relied on.
4. The Cycle Lead identifies its role from the checkout, reads the WO record and the documents it references, and runs the inner loop. Engineer → QA → Reviewer handoffs inside the session are autonomous, as today.

**Monitor**

- The PO sees each WO session directly.
- On request, or before planning the next step, the Orchestrator reads every active worktree's WO record (ledger, escalations) and PR and CI state through read-only `gh` calls. It runs no polling loop and edits no WO record. Only the WO's own session writes its record.
- `usage_report.py` runs per WO session after it ends (section 10).

**Escalate**

1. The Cycle Lead writes a `BLOCKED` entry and ends its turn.
2. **[PO]** brings it to the Orchestrator.
3. The Orchestrator triages. An approval-level question goes to the PO.
4. **[PO]** passes the answer into the WO session, where the Cycle Lead records it under Escalations and continues.

**Resume** (session lost, context exhausted, CI failure, merge conflict, or a concurrent consumer whose producer has merged)

0. **[PO]** notices the trigger: the session has ended, GitHub reports a CI failure or conflict on the PR, or the Orchestrator reports that a producer has merged.
1. **[PO]** opens a fresh session in the same worktree and sends `Resume Work Order <id>`.
2. The Cycle Lead reads the WO record (the PR description and pending ledger once the PR is open) and the checkpoint log, and continues from the last recorded gate.
3. Uncommitted changes since the last checkpoint are treated as unvalidated work, never as gated.

**Return**

1. The Cycle Lead finishes the Cycle Report and closeout manifest.
2. **[PO]** invokes `/finish-cycle` in the WO session: G4 runs, then the PR opens or updates.
3. CI runs (G5).
4. **[PO]** asks the Orchestrator for G6. The Orchestrator reads the PR and recommends merge or not.
5. **[PO]** merges (G7).
6. **[PO]** tells the Orchestrator the merge happened. The Orchestrator then runs `sync_master.py` and `cleanup_work_order.py`, and checks the open WOs that list this one in `integrates-after`.
7. For each such concurrent consumer, the Orchestrator reports that phase 2 can start. **[PO]** passes that to the consumer's session, or opens a resume session for it.

**Manual steps per WO**: approve, open the session, invoke `/finish-cycle`, request G6, merge, report the merge to the Orchestrator. Add:

- one relay per `BLOCKED`;
- one noticing step plus one session per resume (CI failure, conflict, lost session);
- for a concurrent consumer, one phase 2 relay.

C5.6 counts them and measures their time. Until C5.6 has demonstrated this lifecycle, the organization is described as **supervised multi-session**, not autonomous.

## 3. Lanes and the ownership map

`.claude/ownership.json` (control file, created in C5.3) is the single home for:

- **lanes**: branch prefix → owned path patterns. Each path has a **kind**. Kinds mirror the rows of today's Ownership table (`ENGINEERING_PROCESS.md:294-303`), plus new rows for areas the table does not cover yet (marked *new*). When patterns overlap (for example `tests/tooling/` under `tests/`), the most specific pattern wins:
  - `production`: `src/`;
  - `tests`: `tests/`;
  - `docs`: implementation-facing docs, `README.md`;
  - `architecture`: `docs/ARCHITECTURE.md`;
  - `records`: `ROADMAP.md`, `CURRENT_CYCLE.md`, `docs/adr/`, and *new* `docs/milestones/`, `docs/product/`, `docs/company/`;
  - `design` (*new*): `docs/design/` and the future token/asset source;
  - `control`: every Meta-only path (section 13).
- **co-owned paths**: paths several named lanes may edit (machine-checked); the Reviewer judges which section belongs to whom;
- **role permissions**: role → the kinds it may write, the same in every lane, copied from today's table:
  - Engineer: `production`, `tests`, `docs`, `architecture` (implemented-behavior detail), `design` (*new*, for token and asset files in Design WOs);
  - QA: `tests`;
  - Reviewer: nothing;
  - Cycle Lead: `architecture` (approved decisions), `records` (ADRs as drafts the PO accepts), `design` (*new*), plus `control` in a `meta` WO only.

  The Orchestrator writes only as the Cycle Lead of an Org WO.

  **Changes to today's table.** The *new* rows are OD5 decisions; today they are edited by the Lead by convention. The other change is OD20: in a `meta` WO, the Engineer may also write `scripts/` and `tests/tooling/`, and QA may write `tests/tooling/`. Today these are control files and only the Lead edits them. The change is what lets C5.4/C5.5 run the full Engineer → QA → Reviewer flow. Every other control path stays Cycle-Lead-only.
- **mode**: `single-team` or `multi-lane`. The map describes ownership in both modes; the guard enforces paths only in `multi-lane` mode (section 12).

A path that matches no lane is **unmapped**, and unmapped changes fail closed. `ENGINEERING_PROCESS.md` links to the map and keeps only the principles (who decides what). **Control files are defined as the Meta lane's own paths in the map (Meta minus Org)**: the Control Files section of `ENGINEERING_PROCESS.md` keeps that definition and the Meta rules, and drops its path list. No other document lists the paths. This package's illustration below is exempt once archived.

Proposed content:

| Lane | Prefix | Owns |
| --- | --- | --- |
| Core | `core/` | `src/go_poker/core/`, `src/go_poker/game/`, `src/go_poker/__init__.py`, `tests/core/`, `tests/game/` |
| Backend/API | `backend/` | `src/go_poker/app/`, `tests/app/`; future server packages |
| Design | `design/` | `docs/design/`; the future token/asset source. The Figma file is outside Git and needs no WO. |
| Org | `org/` | `docs/ROADMAP.md`, `docs/CURRENT_CYCLE.md`, `docs/milestones/`, `docs/adr/`, `docs/product/`, `docs/company/`, `README.md` |
| Meta | `meta/` | Org paths plus control files: `CLAUDE.md`, `AGENTS.md`, `docs/ENGINEERING_PROCESS.md`, `.claude/agents/`, `.claude/skills/`, `.claude/settings.json`, `.claude/ownership.json`, `scripts/`, `tests/tooling/`, `.github/`, `pyproject.toml`, `uv.lock`, `.gitignore`, other repository-root files |
| Web | `web/` | added to the map only when activated |

Co-owned: `docs/ARCHITECTURE.md` (Core, Backend, Org; each lane edits only its sections) and `tests/test_layering.py` (Core, Backend).

Consequences:

- `pyproject.toml`/`uv.lock` hold gate configuration (Ruff, mypy, pytest), so they are Meta. An approved dependency lands in a Meta WO before the WO that uses it.
- There is no Product lane or agent. Product drafting (C2 UX flows, contract amendments) is Orchestrator work in Org WOs, under PO approval as today.
- ADRs are Org-owned. A lane WO whose decision needs an ADR depends on an Org WO that lands the accepted ADR.
- QA and Review are role patterns inside every WO, not lanes.

## 4. Work Order schema

A WO is today's Cycle Brief plus a coordination header. One approved M8 Cycle is one or more WOs; their split is recorded by the Org boundary WO. The header uses the closeout manifest's `key: value` line format, so stdlib tooling parses it.

```
id: WO-M8C6-01
title: Engine chip entry for a seated non-participant
lane: core
type: behavioral          # behavioral | small-change | meta | design
branch: core/wo-m8c6-01-chip-entry
base: <origin/master SHA at start>
depends: none             # WO ids that must be merged before this WO starts
integrates-after: none    # WO ids that must be merged before this WO's G6 (contract-first)
consumes: none            # ADR-NNNN @ <master SHA> (concurrent | after-merge), or <doc>#<section> @ <SHA>
produces: ADR-0008 -> backend   # the contract version this WO implements, and its consumers
co-owned: docs/ARCHITECTURE.md   # co-owned paths this WO expects to touch
closeout: none            # paths of a kind the Cycle Lead may write (architecture, records, design),
                          # editable after G3 without re-review;
                          # never a deliverable, never control files; none for org/meta WOs
size: ~4 paths, ~300 lines; sizing decision: whole
qa: required              # or: skipped — <reason> (Small-Change Path)
approved: <date> by PO
```

Body: the eight Cycle Brief sections, unchanged.

Appended while the WO runs:

```
## Gate ledger
| Gate | Verdict | SHA | Gated patch-id | Phase | Verification |   (rows written by checkpoint.py; Phase only for concurrent consumers)
| G1 | DELIVERED | a1b2c3d | 5e6f… | — | full PASS |
| G2 | PASSED    | d4e5f6a | 7a8b… | — | full PASS |
| G3 | APPROVED  | 9f8e7d6 | 7a8b… | — | targeted + relied on G2 |

## Escalations
## Cycle Report   (gate outcomes = the ledger above; not repeated)
```

Rules:

- `lane`, `type` and `branch` agree. Tooling derives the lane only from the branch prefix, and a `meta` type requires `meta/`.
- A WO with an unmerged `depends` entry is not started. An unmerged `integrates-after` entry blocks only that WO's G6.
- `consumes` pins each cross-lane contract to the `master` SHA it was read at.
- A WO that crosses lanes is invalid. The Orchestrator splits it into one WO per lane.

## 5. Ownership boundaries

- A WO never edits paths outside its lane. A needed change elsewhere becomes a **Contract Request** to the Orchestrator, who opens a WO in the owning lane.
- **Contract ownership follows path ownership.** The producing lane owns the implemented contract: its `ARCHITECTURE.md` sections and public docstrings.
- **A cross-lane contract that is not yet implemented is versioned as an accepted ADR** (Org lane, PO acceptance). The ADR number is the contract version, and a change is a new ADR that supersedes it. Once the producer has merged, `ARCHITECTURE.md` describes the implemented contract and cites the ADR. No separate contract registry exists.
- Consumer-driven contract tests live in the consumer lane (for example, Backend tests pinning Core behavior under `tests/app/`).
- A change to a contract another lane consumes needs a Reviewer contract check. When it is public API, it also needs the PO approval that public API already requires.
- Once multi-lane mode is active, the main checkout is read-only for every role. Claude Code already blocks worktree sessions from editing the main checkout through Edit/Write, git redirection and Bash cwd. The guard adds the Orchestrator's own session.

## 6. Handoff rules

**One record per WO at any moment:**

1. Drafted and approved in the Orchestrator session.
2. Written by `start_work_order.py` to the git-ignored `.claude/work-order.md` in the WO worktree. Any later session resumes from it.
3. Copied into the PR description by PR-mode closeout. From then on the PR is the record (section 11 describes how later ledger rows reach it).

Engineer → QA → Reviewer handoffs stay conversation outputs inside the WO session, each naming its checkpoint SHA.

The repository is public, so PR descriptions are public. They carry engineering content only: no usage or cost figures, no personal data.

**Commit binding.**

- At each gate, the Cycle Lead runs `checkpoint.py` with an explicit path list. It refuses unless the working tree's changed paths equal that list, the same protection `finish_cycle.py` step 5 gives today. It refuses on `master` or on an unmapped branch, and never pushes.
- `checkpoint.py` also writes the ledger row: the gate and verdict the Cycle Lead passes, the SHA, and the **gated patch-id**. The gated patch-id is `git patch-id --verbatim` over the WO's merge-base diff against a freshly fetched `origin/master` (`origin/master...HEAD`), excluding only the WO's declared `closeout` paths.
- `--verbatim` is required. `--stable` ignores whitespace, so it misses Python indentation changes that alter behavior and edits inside string literals (reproduced in a scratch repository). `--verbatim` still ignores line numbers, so a conflict-free `master` merge does not invalidate gates. Binary and mode-only changes are detected.
- An empty diff is refused, so a WO's gated patch-id can never be empty. A docs-only, Org or Meta WO is fully covered: every file except declared closeout paths is gated, including Markdown and control files.
- The local `master` branch is never the base, because it can be stale in a worktree.

**Staleness.** Two rules:

1. **Patch-id rule** (every WO): a gate stays valid while the head's gated patch-id equals the one at that gate's SHA.
2. **Contract-first rule** (concurrent consumers only): a gate is a **phase 2 gate** when its SHA has the producer's squash-merge commit on `origin/master` as an ancestor; otherwise it is **provisional**. `checkpoint.py` computes the phase and writes it to the ledger. Once the producer has merged, provisional G1–G3 are invalid regardless of the patch-id, and only phase 2 gates count for G4–G6.

| Change after a gate | Gated patch-id | Effect |
| --- | --- | --- |
| fix commit | changes | affected gates re-run under the existing re-validation rules |
| any other edit after G3, Markdown and control files included | changes | G3 re-runs (G2 too if behavior may change) |
| edit to a declared `closeout` path after G3 | unchanged | allowed, as today's post-review closeout; the Cycle Lead verifies |
| `origin/master` merged in, no conflicts | unchanged | G5 re-runs only |
| merge with conflict resolution, or `master` changed context lines | changes | G3 re-runs for the affected files; G2 too if behavior may change |
| producer merged (concurrent consumer) | either | provisional G1–G3 invalid; they re-run as phase 2 gates (contract-first rule) |

The PO uses "Update branch" only when the WO session reports no unpushed checkpoint. Updating a branch merges `origin/master` into it, never a rebase: rebasing would rewrite the gated SHAs. The PO may click GitHub's "Update branch" (no local push needed). Otherwise the Cycle Lead runs `update_branch.py`, which:

- first brings in the remote WO branch when it is ahead (for example after "Update branch"): a fast-forward when possible. If the branches diverged (an unpushed local checkpoint plus a remote update), it merges the remote branch, and the conflict rules below apply;
- then merges `origin/master`;
- stops on conflict, for the Cycle Lead to resolve and checkpoint.

**Contract handoff (OD11, contract-first).** Two modes; the Orchestrator chooses one at G0:

- **After-merge**: the consumer lists the producer in `depends`, starts after the producer has merged, and pins `consumes` to that `master` SHA. Used when no stable contract exists or concurrency saves nothing.
- **Concurrent**: used when the contract is stable. The rules:
  1. *Contract first.* An Org WO lands an accepted contract ADR (signatures, semantics, errors, invariants, and how the consumer is isolated). Both WOs pin it: the producer as `produces: ADR-N`, the consumer as `consumes: ADR-N @ <SHA> (concurrent)` and `integrates-after: <producer WO>`.
  2. *Producer.* Implements the ADR, with conformance tests in its own lane, and integrates independently through the normal gates.
  3. *Consumer, phase 1.* Builds everything that does not need the producer's real symbols, and tests it against consumer-owned doubles under its own test paths. Doubles never live in producer paths or on a production code path. A consumer-owned port (for example a `Protocol`) is allowed only when the contract ADR approves it as architecture, because it is a new abstraction. Gates G1–G3 in phase 1 are **provisional**.
  4. *Consumer, phase 2.* Starts when the producer has merged. The consumer brings in `origin/master`, wires the real implementation, and runs its consumer-side contract tests against it. Under the contract-first rule, G1–G3 re-run on the real implementation as phase 2 gates. Phase 1 verdicts never carry over, even when the patch-id is unchanged.
  5. *Integration gate (G6).* The consumer's PR is accepted only if:
     - the producer is merged;
     - both WOs pin the same contract ADR, and no superseding ADR has merged since the pin;
     - the consumer's gates are phase 2 gates;
     - no double is reachable from production code (Reviewer check).
  6. *Contract change.* A needed change is a `BLOCKED` Contract Request. A new ADR supersedes the old one, and every pinned WO re-pins and is re-approved at G0. If the producer has already merged, the change needs a new producer WO before the consumer can reach G6.

Sequential execution is required only where it is necessary: no stable contract, or a consumer that cannot be built or verified without the producer's real symbols and has no approved port. An unclear contract is escalated, not interpreted.

**Design handoff.** A Web WO needs an approved Figma frame URL (approval authority: OD6), merged token names, component states, the motion specification and acceptance viewports. Without all five, it is not Ready.

## 7. Quality gates

| Gate | Owner | Passes when | Bound to |
| --- | --- | --- | --- |
| G0 Ready | PO approves the Orchestrator's WO | Definition of Ready; `depends` merged; contracts pinned (for concurrent mode, the contract ADR is on `master`); co-owned overlap checked | base SHA |
| G1 Delivery | Engineer → Cycle Lead check | `DELIVERED`; full verification | SHA + patch-id |
| G2 QA | QA | `PASSED`, or skipped under the Small-Change Path with the reason | SHA + patch-id |
| G3 Review | Reviewer | `APPROVED`; no open Critical/Major; contract and section-ownership check | SHA + patch-id |
| G4 Closeout | PR-mode `finish_cycle.py` | gated patch-id equals G3's; ownership check; final verification; manifest equals the merge-base diff | head SHA |
| G5 CI | GitHub Actions | `quality` (verify) on the PR; `ownership` (executed from `master`) green; branch up to date | PR head |
| G6 Integration | Orchestrator | `integrates-after` merged; contract versions match and are not superseded; consumer gates are phase 2 gates; no conflicting open PR; PR head's gated patch-id equals the ledger's G3 | PR head |
| G7 Merge | PO | squash merge | PR head |

Mapping to the audit: the audit's G0–G3 are G0–G3; its G4 (CI) is G5; its G5 (integration) is G6; its G6 (merge) is G7. G4 Closeout is new.

## 8. Escalation rules

1. **Engineer/QA/Reviewer → Cycle Lead**: as today.
2. **Cycle Lead → Orchestrator**: write a `BLOCKED` entry to the WO record and stop, when:
   - a change is needed outside the lane (Contract Request);
   - a consumed contract is ambiguous, or changed after its pin;
   - a co-owned overlap or conflict appears with another WO;
   - a failure is caused by another lane's merge;
   - a third fix round on the same finding would be needed (new rule, OD12);
   - the Brief does not answer a scope question.
3. **Orchestrator → PO**: every approval-level decision (unchanged list), plus:
   - WO approval, `/finish-cycle`, merge;
   - lane activation or a change to the ownership map;
   - a contract change that is public API;
   - raising the concurrency cap;
   - a Web WO without approved design;
   - any GitHub setting.

A `BLOCKED` entry states the trigger, the need, the options, a recommendation, and who decides. Telemetry never stops a WO (section 10).

## 9. Parallel and dependent work

| Situation | Rule |
| --- | --- |
| Different lanes, no unmerged dependency | parallel, within the cap |
| Producer and consumer with an accepted contract ADR | concurrent when the Orchestrator chooses concurrent mode at G0 (section 6); the consumer's G6 waits for the producer's merge |
| Consumer without a stable contract, or needing the producer's real symbols with no approved port | starts after the producer merges; the Brief may be drafted |
| Two WOs on the same co-owned path | allowed; the second to merge resolves conflicts (section 6 staleness). Overlap is declared at G0 so the Orchestrator can serialize instead when the sections overlap |
| Same lane | one active WO per lane during the pilot |
| Meta WO | exclusive: starts only with no WO in flight, and none starts until it merges, because it changes the rules running WOs follow |
| Org boundary WO | runs between M8 Cycles, with no product WO open |
| Design → Web | Web blocked until approved design and merged tokens |
| Dependency | approved, then landed in a Meta WO first |

Applied to the current plan:

- C5.3–C5.5 are Meta work in today's single-checkout flow and run in sequence. They cannot run in parallel: they share `ENGINEERING_PROCESS.md` and the guard's command list, and no isolation tooling exists yet.
- Until activation, design work (C2–C4) shares the single checkout, so it does not run while a C5 session edits. After activation, design repository changes go through Design WOs (OD4). Figma work needs none.
- C6 pilot: Core WO-A and Backend WO-B can run concurrently if their contract ADR is accepted first; otherwise WO-B starts after WO-A merges. The two fill the concurrency cap of 2.
- C7 waits for C4, C6 and Architecture Discovery (M8 Plan).

## 10. Budgets and context

- **Concurrency cap**: two active WO sessions during the pilot. Parallel lanes save wall-clock time, not usage, and drain the 5-hour limit faster.
- **Size**: each WO carries its Cycle Sizing decision. No new thresholds.
- **Telemetry (preserved under OD16)**:
  - *Usage*: `usage_report.py`, run per WO session and aggregated across worktree transcript directories (C5.5). Raw usage and cost stay in the git-ignored `.claude/usage/`.
  - *Performance*: each Cycle Report records wall-clock time (from checkpoint timestamps), gate and fix rounds, full-verification count, resumes, and manual PO steps.
  - C6 summarizes both in `docs/company/TOOLING_EVALUATION.md`, as the AI Engineering Log does today. None of it is a gate.
- **Orchestrator context**: reads WO records, Cycle Reports, PR and CI state, never full diffs. One fresh Orchestrator session per M8 Cycle.
- **Cycle Lead context**: fresh per WO. A resumed WO (CI failure, conflict) starts a fresh session from the WO record.
- **Models**: routing unchanged. Orchestrator and Cycle Lead use the "normal Cycle Lead" row; planning-heavy Orchestrator sessions use the milestone-architecture row.
- **Agent teams** (experimental in Claude Code) stay disabled, which is also required by the technology freeze. When enabled, named subagents start as teammates in the lead's permission mode, which would bypass per-role routing and tool limits.

## 11. Git and integration model

- **Branch per WO**: `<prefix>/wo-<milestone><cycle>-<nn>-<slug>`, from the latest `origin/master`. The Orchestrator creates it with `start_work_order.py`, after the PO approves the WO. The script does not use `claude --worktree`, which names branches `worktree-<name>`.
- **Worktree** under `.claude/worktrees/<wo-id>/` (git-ignored), bootstrapped with `uv sync`. Machine-local settings are read from the main checkout root (to be confirmed in C5.5). One writer session per worktree.
- **Main checkout**: stays on `master` with a clean tree. The Orchestrator fast-forwards it after merges with `sync_master.py` (fast-forward only, clean tree only). After a merge, `cleanup_work_order.py` removes the worktree and local branch, only when `gh` reports the PR merged.
- **Squash merge**, with the manifest's commit message.

**PR-mode `finish_cycle.py`**, invoked only through user-only `/finish-cycle` in a WO worktree.

It keeps today's checks 1 (no machine-local path), 2 (no operation in progress, nothing unmerged), 4 (no git-ignored path), 6 (`verify.py` passes and leaves the tree unchanged) and 8 (commit with hooks). It replaces checks 3, 5, 7, 9 and 10, which assume one new commit pushed straight to `master`, with:

- **P1** The branch has a mapped lane prefix and is not `master`. Its upstream is absent, or is an ancestor of HEAD (never force). If the remote is ahead, the script stops and directs the Cycle Lead to `update_branch.py`.
- **P2** `origin/master` is fetched. The leftover working-tree changes are a subset of the manifest paths. Exactly those leftovers are staged by explicit path, the staged set equals the leftover set, and they are committed as the closeout checkpoint (none is fine).
- **P3** The path set of the merge-base diff against `origin/master` equals the manifest exactly.
- **P4** The ownership check passes.
- **P5** The gated patch-id equals the G3 entry in the WO record. For a concurrent consumer, that G3 must be a phase 2 gate. PR mode refuses to run on provisional gates, so a consumer cannot open its PR before phase 2.
- **P6** The push goes out without force or tags, with `-u` the first time, and the remote must equal HEAD afterwards.
- **P7** The PR is created or updated with the WO record and the head SHA. Its title is the manifest's `message:` line, which becomes the squash commit message.

**Record after the PR opens.** The PR description is the record. The local file is replaced by a pending-ledger file that holds only new rows from `checkpoint.py` (for example after a CI fix). The next PR-mode run reads the G3 entry from the PR description plus pending rows (`gh pr view`), writes the merged record back to the PR, and deletes the pending file. A resumed session reads the record from the PR. So the record has one home at a time, and the G3 value is never lost.

The manifest keeps its format. `message:` becomes the squash commit message, and `path:` lists the WO's whole merge-base diff.

**`master` protection (PO, in C5.6)**: pull request required; required checks `quality` and `ownership`; branch up to date; no force push or deletion; squash merge only; enforced for administrators.

**CI changes**:

- `quality` keeps running on pull requests and on pushes to `master`. Push triggers are limited to `master` from C5.4, so each WO push does not run it twice.
- A separate `ownership` job runs on `pull_request_target`. It checks out `master`, fetches the PR head **as data only**, and runs `master`'s `check_ownership.py`. PR code is never executed in that job, so a PR cannot weaken the check that judges it.
- Pushes to `master` do not run the ownership job.

## 12. Enforcement and its limits

| Layer | Mechanism | Strength |
| --- | --- | --- |
| Prevent | `scripts/guard.py` PreToolUse hook (stdlib). It reads `ownership.json`, the hook input's `cwd` and `agent_type`, and the branch. **Scope:** only paths inside this repository and its worktrees, and Git commands whose target repository is this one. Scratch repositories, mutation-experiment copies and scratchpad files are outside its scope. **Both modes:** raw state-changing Git (commit, push, merge, reset, …) and `gh` write subcommands are blocked; the project scripts are allowed. That matches what today's prose already forbids, so today's flow is unaffected. **`multi-lane` mode only:** in a WO worktree, Edit/Write/NotebookEdit outside the branch's lane, or outside the kinds the role may write there, are blocked; writes in the main checkout are blocked; an unmapped branch is blocked. The WO's own git-ignored record files (`.claude/work-order.md`, the pending ledger) are writable by the Cycle Lead; they are exempt from lane checks. In `single-team` mode there are no path checks, so C5.5 and other Meta work in the main checkout proceed as today. | best effort: Claude Code's docs say Bash rules and command matching are not a security boundary (`sh -c`, path-qualified binaries) |
| Detect | `ownership` CI job from `master`'s code: every merge-base-diff path is inside the branch's lane or a co-owned entry for it; unmapped paths and unknown prefixes fail; `meta/` is the only prefix allowed to touch control files | authoritative for path ownership, against mistakes and agent drift |
| Permit | committed `.claude/settings.json` (hook registration and deny rules); the PO removes `Bash(uv run *)` and `Bash(python3 -)` from the machine-local allowlist. "Don't ask again" approvals in worktrees land in the main checkout's local file and apply to all worktrees. | narrows routine risk |
| Judge | Reviewer scope, contract and section-ownership checks | what tooling cannot decide |

**Single-account limit.** Every session acts with the PO's own Git and GitHub credentials. GitHub cannot tell an agent from the PO, and a required PR approval is impossible, because an author cannot approve their own PR. An agent that deliberately ran `python3 scripts/finish_cycle.py`, or used `gh` through a wrapper, could push a WO branch or merge a PR.

- **Hard against mistakes**: protection with administrator enforcement stops direct pushes to `master`. It is not hard against a deliberate agent: the sessions hold the PO's administrator credentials, so an agent could relax protection through `gh api`. Blocking that is the guard's job, which is best effort.
- **Best effort**: push of WO branches and merge approval rest on the guard, deny rules and agent instructions. That is the same class of risk as today, where nothing technical stops an agent from running `git push`.

OD10b (Tier B, deferred) asks the PO to accept this residual risk explicitly before the PR workflow is enabled in C5.6. Identity separation is deferred until after Friends Alpha unless an incident justifies it earlier:

- a machine user or fine-grained token without merge rights for agent sessions;
- a Claude Code sandbox that denies the agents access to the PO's credentials.

Identity separation would make a required PO review possible.

## 13. Policy deltas

| Current rule | Proposed | Decision |
| --- | --- | --- |
| `CLAUDE.md`: "The main Claude session is the Engineering Lead" | conditional Orchestrator/Cycle Lead identity in multi-lane mode | OD1 |
| One Core Engineering Team | lanes Core, Backend/API, Design, Org, Meta (Web later) | OD2–OD4 |
| `ENGINEERING_PROCESS.md`: "Handoffs are conversation outputs, not repository documents" | intra-WO handoffs unchanged; WO record persisted (local file, then PR) | OD7 |
| `ENGINEERING_PROCESS.md` "No role commits or pushes…" and `AGENTS.md:10` "Do not commit…" | checkpoint and update commits by script on WO branches; pushes only through user-invoked `/finish-cycle` | OD8 |
| `/finish-cycle` pushes to `master` | PR mode; PO merges | OD9 |
| Ownership table in `ENGINEERING_PROCESS.md` | moved as role → kind to `ownership.json`, with lanes; new rows: `docs/milestones/`, `docs/product/`, `docs/company/` → `records` (Cycle Lead); `docs/design/` → `design` (Engineer, Cycle Lead) | OD5 |
| control files: only the Lead edits them, in Meta work | in `meta` WOs, Engineer may write `scripts/` and `tests/tooling/`, QA `tests/tooling/`; every other control path stays Cycle-Lead-only | OD20 |
| "Go! Poker currently uses no Hooks" (Company Manual) | one guard hook plus a CI ownership job | OD10a |
| Control-file list in `ENGINEERING_PROCESS.md` | the definition stays there; the paths move to the map's Meta lane, which adds `.claude/settings.json`, `.claude/ownership.json`, `.github/`, hook scripts and `pyproject.toml`/`uv.lock` (gate config) | OD5, OD10a |
| Only the Engineering Lead marks a Cycle complete | the Orchestrator, through the Org boundary WO | OD1 |
| ADRs land in the Cycle commit that implements the decision | an ADR lands in an Org WO before the lane WO that depends on it | OD11 |
| M8 Plan C6 benchmarks Paperclip/hybrid and alternatives; graph node "C6: Tooling Benchmark"; `PRODUCT_VISION.md:158` "Benchmark orchestration tools in C6." | native-only pilot; other arms after Friends Alpha; node and sentence reworded (section 14) | OD16 |
| No limit on fix rounds | a third round on one finding escalates to the Orchestrator | OD12 |
| `DESIGN_INDEX.md:42` records a "reviewer decision" for `DESIGN APPROVED` without naming the approver | the PO approves designs (or names a delegate) | OD6 |
| Agents restate "Core Engineering Team" | lane-neutral wording | OD1 |

## 14. Reconciliation with the M8 Plan

| M8 Plan says | Decision | Status |
| --- | --- | --- |
| C5 org: "Lead, Core, Backend, Web, Product, QA/Reviewer" | Orchestrator + per-WO Cycle Leads; lanes Core, Backend/API, Design, Org, Meta, Web later; no Product lane; QA/Reviewer shared | approved (OD1, OD2); amends the row |
| C5 covers "task contracts, escalation and budgets" | sections 4, 6, 8, 10 | consistent |
| C5 artifact `docs/organization/AI_ORGANIZATION.md` | normative rules in `ENGINEERING_PROCESS.md`; lanes and permissions in `ownership.json`; why in ADR 0007; this package archived in `docs/company/`; no `docs/organization/` | approved (OD13); amends the row |
| C6 artifact `docs/organization/TOOLING_EVALUATION.md` | `docs/company/TOOLING_EVALUATION.md` | approved (OD13) |
| C5 = specification (exit gate 4 "specified") | C5 also builds tooling and runs a dry run (C5.4–C5.6) | approved (OD14) |
| C6 benchmark: "lean Claude workflow, Paperclip/hybrid, alternatives" | under the technology freeze, C6 runs only the lean Claude Code workflow: the feature-sized pilot, measured. The Paperclip/hybrid and alternative arms move to after Friends Alpha | approved (OD16); amends the row |
| Exit gate 5: feature-sized task, with cost and intervention; "tooling choice based on results" | the C6 pilot; the C5.6 dry run is docs-only and does not count. Under the freeze, the "tooling choice" is to keep or adjust the native workflow | approved (OD16); amends the gate text |
| C5 depends only on C0 | unchanged | consistent |

### Proposed M8 Plan amendments (exact text, applied in C5.3)

`docs/milestones/M8_PLAN.md`, Cycles table, C5 row. Replace:

    | C5 | AI org structure: Lead, Core, Backend, Web, Product, QA/Reviewer; task contracts, escalation and budgets | `docs/organization/AI_ORGANIZATION.md` |

with:

    | C5 | AI organization: an Orchestrator and short-lived per-Work-Order Cycle Leads over lanes Core, Backend/API, Design, Org and Meta (Web after C7), with shared Engineer/QA/Reviewer roles; Work Orders, handoffs, contract-first parallelism, escalation and budgets; ownership and closeout tooling; an activation dry run (C5.1–C5.6) | Rules in `docs/ENGINEERING_PROCESS.md`, the lane map `.claude/ownership.json`, ADR 0007; rationale in `docs/company/M8_C5_2_ORGANIZATION_DESIGN.md` |

C6 row. Replace:

    | C6 | Evidence-based agent orchestration benchmark (lean Claude workflow, Paperclip/hybrid, alternatives as justified) | `docs/organization/TOOLING_EVALUATION.md`, delegated pilot findings |

with:

    | C6 | Native Claude Code organization pilot: a feature-sized cross-lane task, measured for outcome, usage, performance and manual intervention, under the technology freeze in `docs/ENGINEERING_PROCESS.md` | `docs/company/TOOLING_EVALUATION.md` (pilot findings) |

Exit gate 5. Replace:

    5. A real feature-sized task goes through Lead → Engineer → QA → Reviewer with documented outcome, cost and manual intervention; tooling choice based on results.

with:

    5. A real feature-sized task goes through Orchestrator → Cycle Lead → Engineer → QA → Reviewer with documented outcome, usage, performance and manual intervention; the native workflow is kept or adjusted based on the results.

Dependency graph node (line 36). Replace:

    C6["C6: Tooling Benchmark"]

with:

    C6["C6: Native Org Pilot"]

The line keeps its original 4-space indent inside the Mermaid block.

The graph's edges, the other Cycles and the other exit gates are unchanged. C5.3 also verifies the exact current wording before replacing it.

`docs/product/PRODUCT_VISION.md:158` ends with "Benchmark orchestration tools in C6." That sentence becomes stale too. C5.3 replaces it with "Pilot the native organization in C6." That is a product document, so the PO approves the wording in the C5.3 review.

## 15. Implementation sequence C5.3–C5.6

Each step is one Meta Cycle with its own Brief, in today's flow, closed with today's `/finish-cycle`. The switch flips in C5.6.

### C5.3 — Organization specification (Cycle Brief)

1. **Goal.** Record every approved C5.2 decision in its single operational home. The multi-team organization is specified but inactive (`mode: single-team`), and today's flow runs unchanged until C5.6.
2. **In scope** (14 paths; Meta work by the Lead under today's rules):
   - `docs/ENGINEERING_PROCESS.md`, a new "Multi-lane organization (inactive until activation)" section:
     - roles (Orchestrator, Cycle Lead);
     - lanes, by reference to the map;
     - the Work Order schema;
     - Work Order operations, including the manual steps;
     - handoff persistence, checkpoint binding and staleness (`--verbatim` patch-id);
     - contract-first parallelism;
     - gates G0–G7;
     - escalation levels and triggers, including the fix-round rule;
     - parallelism rules;
     - budgets and telemetry;
     - the technology freeze.

     The Ownership table and the control-file path list are replaced by the definition plus a link to the map. The commit rule is amended for checkpoint commits on WO branches (OD8), and OD20 is added.
   - `.claude/ownership.json` (new): `mode: single-team`; lanes with kinds; co-owned paths; role → kind permissions, including the new rows (OD5) and OD20; a most-specific-pattern rule; no Web lane.
   - `.claude/agents/engineer.md`, `qa-engineer.md`, `reviewer.md`: lane-neutral wording, plus clauses stated as applying in `multi-lane` mode only: the checkpoint SHA in each handoff, and the Reviewer's contract and section checks, including phase 2 and no reachable double. In `single-team` mode the agents behave exactly as today. Models, effort and tools are unchanged.
   - `CLAUDE.md`: conditional session identity (Orchestrator or Cycle Lead, in `multi-lane` mode only); a pointer to the map.
   - `AGENTS.md`: the commit rule's exception for scripted checkpoint commits on WO branches.
   - `docs/adr/0007-lane-ownership-and-cross-lane-contracts.md` (new; the PO accepts it): **why** lanes are ownership boundaries, why contract versions are ADRs, and why contract-first integration is gated on phase 2. The operative rules are only in `ENGINEERING_PROCESS.md`; the ADR links to them.
   - `docs/milestones/M8_PLAN.md`: the four amendments in section 14 (C5 row, C6 row, exit gate 5, graph node).
   - `docs/product/PRODUCT_VISION.md`: the C6 sentence (section 14), with PO approval.
   - `docs/company/ORGANIZATION_ROADMAP.md`: the planned multi-lane structure, active from C5.6.
   - `docs/CURRENT_CYCLE.md`: C5.2 complete; C5.3 status; resolved contradictions removed (the C5 row's team list and artifact path). The bullet on missing entries is narrowed: the Ownership table part is resolved through `ownership.json`, while the `CLAUDE.md` pointers and the Company Manual parts remain unless C5.3's `CLAUDE.md` pointer edit closes them; the deferred decisions listed with their gates.
   - `docs/design/DESIGN_INDEX.md`: the `DESIGN APPROVED` line names the PO as the authority (OD6).
   - `docs/company/M8_C5_2_ORGANIZATION_DESIGN.md`: the status line becomes "archived rationale; decisions recorded in C5.3".
3. **Out of scope.**
   - Any script, hook, `.claude/settings.json`, CI or `.gitignore` change (C5.4/C5.5).
   - The Company Manual hooks section (C5.4) and its current-organization text (C5.6).
   - Product code and tests.
   - Tier B and Tier C decisions.
   - `ROADMAP.md` editorial reconciliation (a C5.6 dry-run candidate).
4. **Architecture / ownership.** Meta work; the Lead edits control files (today's rule; OD20 applies from C5.4). `ownership.json` has no consumer until C5.4. It is the data home, not a behavior.
5. **Behavior and invariants.**
   - Every approved decision appears exactly once, in its home. Deferred decisions appear only as deferred.
   - Lane paths, kinds and role permissions appear only in `ownership.json`.
   - Every multi-lane rule is visibly inactive until the switch.
   - Today's Cycle Flow, `/finish-cycle` and agent behavior are unchanged in `single-team` mode.
   - No silent change to approved policy: every change is in section 13.
6. **Test strategy.** No product or tooling tests change. The Lead checks that `ownership.json` parses (`python3 -m json.tool`) and covers every tracked path (a one-off `git ls-files` check, not committed). Standard verification runs at the end.
7. **Risks / deferred.**
   - `ENGINEERING_PROCESS.md` grows, and every role reads it. Keep the new section concise and link rather than repeat.
   - ADR 0007 needs PO acceptance inside the Cycle.
   - Tier B (OD10b, OD15) and Tier C (OD17, OD19) stay deferred.
8. **Execution plan.**
   1. The Lead drafts the changes.
   2. Small-Change Path: QA is skipped, because there is no runtime behavior.
   3. The Reviewer checks single homes, the section 13 deltas, the M8 Plan wording and the inactive marking.
   4. Fixes are re-reviewed.
   5. The Lead runs final verification, writes the Cycle Report and the closeout manifest, and the PO runs `/finish-cycle` (today's direct push).

   About 14 paths and 600–900 inserted lines, all documentation and config. No sizing signal calls for a split, so the Cycle stays whole.

### C5.4 — Guard and ownership check

- `scripts/guard.py`, `scripts/check_ownership.py`, committed `.claude/settings.json`, the `ownership` CI job (`pull_request_target`, `master` code only), tests in `tests/tooling/`, Company Manual hooks section. The PO trims the local allowlist.
- **Entry check**: capture one real PreToolUse payload from a subagent to confirm where `agent_type`/`agent_id` appear (documented, placement unverified). The hook uses the input `cwd`, not `CLAUDE_PROJECT_DIR`, which can point at another root after a worktree switch.
- Full flow with QA.
- **Done when** tests show:
  - in `multi-lane` mode, per-lane and per-role-kind allowed and blocked edits, including Engineer edits to `scripts/` and QA edits to `tests/tooling/` allowed only on `meta/` branches;
  - raw state-changing Git and `gh` writes blocked, project scripts allowed;
  - main-checkout writes blocked only in `multi-lane` mode;
  - the WO record files writable; scratch repositories, mutation copies and scratchpad untouched by the guard;
  - unmapped paths, unknown prefixes and non-`meta/` control-file changes failing the check;
  - the check never executing PR code;
  - in `single-team` mode, no path checks at all, and today's flow unaffected: edits in the main checkout (including C5.5's own `scripts/` and `tests/tooling/` work), `/finish-cycle` direct push, CI on `master`.

### C5.5 — Worktree, checkpoint and PR closeout

- `.claude/worktrees/` ignored; `start_work_order.py`, `checkpoint.py`, `update_branch.py`, `sync_master.py`, `cleanup_work_order.py`; PR mode in `finish_cycle.py` (section 11) and the `/finish-cycle` skill; guard allowlist for the new scripts; `usage_report.py` aggregation across worktree transcript directories (each worktree path gets its own `~/.claude/projects/` directory, confirmed in the docs).
- `gh` becomes a tooling dependency of PR mode and cleanup (OD15). Tests use a local bare remote plus a fake `gh` on `PATH`.
- **Sizing**: several surfaces. Proposed split: C5.5a (start, checkpoint, update, PR mode) and C5.5b (sync, cleanup, usage aggregation); decided in the Brief.
- Full flow with QA.
- **Done when** tests cover:
  - start → checkpoints → PR-mode closeout against a bare remote;
  - every refusal (on `master`, unexpected files, patch-id changed since G3 — including a whitespace-only Python indentation change and a non-closeout Markdown or control-file edit — manifest mismatch, diverged upstream);
  - patch-id unchanged across a conflict-free `origin/master` merge and a closeout-path edit;
  - an update merge with and without conflicts;
  - cleanup refusing an unmerged PR;
  - worktree sessions included in usage reports.

### C5.6 — Activation and dry run

0. **Gate:** the C5.6 Brief is not Ready until the PO has explicitly accepted OD10b (single-account risk). Before this point, no real PR is opened: C5.5 tests PR mode only against local bare remotes.
1. After C5.5 is on `master`: the PO enables protection (section 11). This must not happen earlier, because protection stops today's direct-push closeout.
2. The first PR, a Meta WO, flips `mode` to `multi-lane` and records activation in `CURRENT_CYCLE.md`.
3. Two concurrent docs-only WOs in different lanes, for example:
   - an Org WO for the stale `ROADMAP.md` reconciliation listed in `CURRENT_CYCLE.md`;
   - a Design WO, such as the `DESIGN_INDEX.md` Figma link once the file exists, or another approved design-doc correction.

   Each goes through worktree → checkpoints → PR → `quality` + `ownership` → G6 → PO merge. One deliberate out-of-lane edit attempt is blocked by the guard, and one is caught by the CI job.
4. The Org boundary WO marks C5 complete. The PO may delete the merged local branch `meta-cycle-1-core-team`.

- QA, `depends`/`consumes` and a behavioral cross-lane handoff are not exercised by a docs-only run. They are the C6 pilot's job.
- **Done when** all PRs merged through G0–G7 with SHAs and patch-ids in their descriptions; both enforcement layers observed; the WO lifecycle (launch, monitor, escalate, resume, return) exercised at least once, including one resume and one `BLOCKED` relay; manual PO steps, interventions and wall-clock time recorded for C6. Afterwards, the documents may describe as unattended only the steps C5.6 showed working without the PO. Every step that still needs a PO relay stays described as supervised.

## 16. Decision register

Approved by the PO on 2026-11-09. "PO #" is the numbering of the Tier A decision table presented to the PO, which the PO's approval cites (its "OD10", "OD15" and "OD16" are rows 10, 15 and 16); "ID" is this package's identifier. "Audit" maps to the [C5 audit](M8_C5_AI_ORGANIZATION_AUDIT.md). C5.3 records every approved decision in its home.

**Tier A — approved**

| PO # | ID | Decision | Status | Recorded in (C5.3) |
| --- | --- | --- | --- | --- |
| 1 | OD1 | Orchestrator plus short-lived per-WO Cycle Leads; Cycle completion through the Org boundary WO (audit D1, D3) | approved | `ENGINEERING_PROCESS.md`, `CLAUDE.md` |
| 2 | OD2 | Lanes Core, Backend/API, Design, Org, Meta; Web after C7; no Product lane; QA/Reviewer shared (D1) | approved | `ownership.json`, M8 Plan C5 row |
| 3 | OD3 | `src/go_poker/app/` and `tests/app/` move to Backend/API (D2) | approved | `ownership.json` |
| 4 | OD4 | Activation at C5.6 for Core, Backend, Design, Org and Meta | approved | `ENGINEERING_PROCESS.md` |
| 5 | OD5 | `ownership.json` as the single home of lanes, kinds, co-owned paths, role → kind permissions and mode; new rows for `docs/milestones/`, `docs/product/`, `docs/company/` and `docs/design/`; unmapped paths fail closed | approved | `ownership.json`, `ENGINEERING_PROCESS.md` |
| 6 | OD6 | The PO is the `DESIGN APPROVED` authority | approved | `DESIGN_INDEX.md` |
| 7 | OD7 | WO record: a local file, then the public PR description; no usage or personal data (D5) | approved | `ENGINEERING_PROCESS.md` |
| 8 | OD8 | Scripted checkpoint and update commits on WO branches | approved | `ENGINEERING_PROCESS.md`, `AGENTS.md` |
| 9 | OD9 | PR-based Git model, squash merge, no rebase, PO merges by hand (D4, D6) | approved; enabled only at C5.6 after OD10b | `ENGINEERING_PROCESS.md` |
| 10 | OD11 | Contract rules, **refined: contract-first parallelism** (section 6). Concurrent producer and consumer work against an accepted, versioned contract ADR; integration gated on the merged, verified producer and matching contract versions; sequential only where necessary (D13) | approved with refinement | `ENGINEERING_PROCESS.md`, ADR 0007 |
| 11 | OD10a | Enforcement design: guard hook, committed settings, `ownership` CI job from `master` code, control-file definition (D7) | approved; built in C5.4 | `ENGINEERING_PROCESS.md` |
| 12 | OD12 | Concurrency cap 2; one WO per lane; fix-round escalation; telemetry not gates (D8) | approved | `ENGINEERING_PROCESS.md` |
| 13 | OD13 | Rules in `ENGINEERING_PROCESS.md`; no `docs/organization/`; the M8 Plan artifact paths amended (D11) | approved | M8 Plan |
| 14 | OD14 | C5 includes C5.4–C5.6 | approved | M8 Plan C5 row |
| 15 | OD18 | **Refined:** short-lived top-level Cycle Lead sessions, with the launch, monitor, escalate, resume and return procedure and its manual steps documented (section 2); not described as autonomous until C5.6 demonstrates it | approved with refinement | `ENGINEERING_PROCESS.md`, `CLAUDE.md` |
| 16 | OD16 | **Refined:** technology freeze on AI orchestration and organization tooling. The native Claude Code stack is used in C5, C6 and the Friends Alpha implementation (section 0); Paperclip, OpenRouter, Codex workers and other orchestration frameworks are deferred until after Friends Alpha; the dev toolchain, the Figma MCP workflow and product technology are unaffected; usage and performance telemetry preserved (D9) | approved with refinement | `ENGINEERING_PROCESS.md` (home); M8 Plan C6 row, graph node and exit gate 5; `PRODUCT_VISION.md` sentence |
| 17 | OD20 | In `meta` WOs, the Engineer may write `scripts/` and `tests/tooling/`, and QA `tests/tooling/` | approved; applies from C5.4 | `ownership.json`, `ENGINEERING_PROCESS.md` |

**Tier B — deferred to their gates**

| ID | Decision | Gate |
| --- | --- | --- |
| OD10b | Accept the single-account residual risk (section 12) until Friends Alpha | **explicit PO acceptance before the C5.6 Brief is Ready**, so before protection is enabled or any real PR opens |
| OD15 | `gh` as a tooling dependency for PR mode, G6 reads and cleanup. The C5.5 Brief also decides how `checkpoint.py` finds the producer's merge commit for the phase check: from the SHA the Orchestrator records when it reports the merge, or through `gh` | the C5.5 Brief |

**Tier C — deferred to their gates**

| ID | Decision | Gate |
| --- | --- | --- |
| OD17 | C6 pilot (rebuy Core → Backend, or the timer fallback) and its Ready questions; whether it runs contract-first | C6 planning |
| OD19 | Lane-specific agents, for example a Figma-equipped designer | when a Design WO needs one |
| — | Identity separation (machine user or token, credential sandbox) | after Friends Alpha, or earlier after an incident (OD10b) |
| — | Pre-approved auto-merge | after C6 measurement |
| — | Nested Cycle Lead sessions | after Friends Alpha |

Audit D9 is replaced by OD16. Audit D12 was carried out as C5.1.

## 17. Acceptance criteria

1. Every Tier A decision in the register is recorded in its own home in C5.3. Tier B and Tier C decisions appear only as deferred, with their gates.
2. After C5.3, `ENGINEERING_PROCESS.md` and `ownership.json` satisfy M8 exit gate 4: roles, ownership, handoffs, autonomy and escalation, context strategy and budget controls specified.
3. After C5.3, no fact has two homes: lane paths and role permissions only in `ownership.json`; process rules only in `ENGINEERING_PROCESS.md`; boundary rationale only in ADR 0007. The archived package is reference material and exempt.
4. Every section 14 difference is approved and amended in the M8 Plan, or the proposal is changed to match the plan.
5. The C5.3 diff changes only what section 13 lists. Section 1 mechanisms are otherwise unchanged.
6. In `single-team` mode, today's flow works unchanged through C5.3–C5.5, each of which closes with today's `/finish-cycle`.
7. C5.4–C5.6 meet their "Done when" criteria. C5 completes only after the C5.6 WOs merge through G0–G7.
8. No document describes cross-session coordination as autonomous before C5.6's "Done when" is met.
9. No framework or provider outside the native stack (OD16) appears in C5 or C6 scope.

## 18. Verified platform facts, open items and risks

Checked against the current Claude Code documentation (2026-11-09):

| Fact | Consequence |
| --- | --- |
| PreToolUse input includes `agent_id`/`agent_type` for subagent calls; a hook can deny with a reason shown to the model; agent frontmatter can declare agent-scoped hooks | role checks are feasible in one hook; field placement is confirmed in the C5.4 entry check |
| Subagents can start subagents, up to three levels by default | the nested Cycle Lead variant exists; deferred until after Friends Alpha |
| Committed project settings apply in worktree sessions; the desktop app reads project config from the main checkout root | a Meta WO's settings change takes effect only after merge, which is acceptable |
| Worktree sessions are blocked from editing the main checkout via Edit/Write, git redirection and Bash cwd; shell redirects are not blocked | the guard's main-checkout rule mainly covers the Orchestrator session |
| `--worktree` defaults: `.claude/worktrees/<name>/`, branch `worktree-<name>`; `.worktreeinclude` copies git-ignored files | our script creates lane-named branches itself |
| Transcripts are stored per working-directory path | `usage_report.py` aggregation is needed (C5.5) |
| Bash permission rules match command text, are not a security boundary, and wrappers like `sh -c` evade them | section 12's best-effort label |
| Agent teams are experimental and turn named subagents into teammates | keep disabled (section 10) |

Open items, each confirmed at the start of the Cycle that needs it:

- the hook payload field placement (C5.4);
- `git patch-id --verbatim` on every machine that runs the scripts (present in local git 2.50.1; the minimum version is confirmed in C5.5);
- whether the worktree switch can enter an existing worktree created by `start_work_order.py` (C5.5). If not, Org WOs use a separate session;
- whether machine-local settings need copying into worktrees (C5.5);
- whether this public repository supports protection with administrator enforcement, squash-only merges and a `pull_request_target` required check (C5.6).

Risks:

- **More PO touchpoints**: WO approval, `/finish-cycle`, merge, plus one Org boundary PR per M8 Cycle. Measured in C5.6/C6; pre-approved auto-merge is the later mitigation.
- **Parallel sessions spend the 5-hour limit faster**: the cap, plus C6 measurement.
- **Resumed sessions add cold cache starts** (AIE-005), beyond today's one fresh session per Cycle.
- **`ARCHITECTURE.md` conflicts** between lanes: handled by the staleness rule. If they recur in C6, a Meta WO splits the file by lane.
- **Public PR descriptions** expose engineering reasoning: OD7's alternative keeps the WO local.
- **Residual single-account risk** (section 12): OD10b. No PR workflow is enabled before explicit acceptance.
- **Contract-first rework**: when a contract changes mid-flight, both WOs re-pin and the consumer's provisional work may be partly redone. Mitigations: an accepted ADR before start, phase 1 limited to symbol-independent work, and Contract Requests escalated early.
- **Doubles drifting from the real producer**: phase 1 verdicts never carry over; phase 2 re-gates on the real implementation, and the Reviewer checks that no double is reachable from production code.
- **Manual relay latency**: `BLOCKED` entries wait until the PO relays them. C5.6 and C6 measure this; the freeze rules out an orchestration framework as the fix before the Alpha.

## 19. Proposed final structure

```
Product Owner — decisions · WO approval · /finish-cycle · merge
└── Orchestrator — main checkout (read-only), plans, WOs, G6, Org boundary WO
    ├── Core      core/      ┐
    ├── Backend   backend/   │  one Cycle Lead session per WO
    ├── Design    design/    │  own branch + worktree
    ├── Org       org/       │  Engineer → QA → Reviewer
    ├── Meta      meta/ (exclusive)
    └── Web       web/ (after C7)
Single home: .claude/ownership.json (lanes · co-owned · roles · mode)
Gates: G0 Ready → G1–G3 at SHA + patch-id → G4 closeout → G5 CI (quality + ownership from master)
       → G6 integration → G7 PO squash merge
Enforcement: guard (prevent, best effort) · CI ownership (detect) · protection (hard, master only) · Reviewer (judge)
```

## 20. Independent review record

**First pass.** The Reviewer agent, read-only, without the author's reasoning, returned `CHANGES REQUIRED`: 0 Critical, 9 Major, 7 Minor, 4 Nits. A separate documentation check of Claude Code platform behavior found one false assumption (no subagent nesting) and several caveats. Resolutions:

| Finding | Resolution |
| --- | --- |
| M1: no role could write status, ADRs or product drafts | Org boundary WO; the Orchestrator acts as Cycle Lead of Org WOs; ADRs Org-owned (sections 2, 3) |
| M2: the CI check ran PR code; unversioned `shared:` escape hatch; Meta not machine-distinguishable | `ownership` job on `pull_request_target` runs `master` code only; co-owned paths live in the versioned map; `meta/` prefix (sections 3, 11, 12) |
| M3: merge-approval safety overstated | best-effort vs hard barrier stated; residual-risk decision plus identity-separation option (section 12, OD10b) |
| M4: PR-mode closeout contradicted `finish_cycle.py`; no update path; staleness rows conflicted; two-dot diff | explicit PR-mode check list; `checkpoint.py` with an exact path list; `update_branch.py` and GitHub "Update branch"; a single patch-id staleness rule over merge-base diffs (sections 6, 11) |
| M5: C5.4 would break CI on `master` and the current flow | the ownership job runs only on PRs; `mode` switch in `ownership.json`, flipped in C5.6; conditional `CLAUDE.md` (sections 3, 11, 15) |
| M6: design track blocked after activation; dry-run lane conflict | Design activates at C5.6; the dry run uses Org + Design (sections 9, 15, OD4) |
| M7: tiers did not match C5.3 needs | OD8, OD9, OD11, OD12 moved to Tier A |
| M8: role table had two homes; sections not expressible | role permissions moved into `ownership.json`; co-owned paths plus the Reviewer's section check (sections 3, 5) |
| M9: unlisted policy changes | `AGENTS.md:10`, design-approval authority, fix-round rule added to section 13; Paperclip scope left unnarrowed (OD16) |
| Minors and Nits | usage-multiple trigger dropped; unmapped paths fail closed; Web absent from the map until activated; script runners named; `gh` decision (OD15); QA enforcement tied to the C5.4 entry check; dry-run limits stated; gate mapping to the audit added; ledger is the Cycle Report's gate outcomes |
| Platform: nesting is possible | nested Cycle Lead option added (OD18) |
| Platform caveats | `cwd` not `CLAUDE_PROJECT_DIR`; desktop reads config from the main root; built-in worktree write guard; agent teams disabled; `--worktree` branch naming (sections 10–12, 18) |

**Re-review.** The same Reviewer returned `CHANGES REQUIRED`. It confirmed M1–M3, M5, M6, M8 and M9 resolved in the text, and M4 and M7 mostly resolved. It tested the patch-id rule in a scratch repository: line numbers are ignored, context changes within three lines are detected, and a stale local `master` corrupts the diff. It raised two new Majors and five Minors, resolved as follows:

| Finding | Resolution |
| --- | --- |
| N1: excluding `*.md` left docs-only, Org and Meta WOs unbound (empty patch-id) | gated patch-id excludes only declared `closeout` paths (never deliverables or control files; none for Org/Meta); empty diffs refused (sections 4, 6) |
| N2: guard semantics undefined in `single-team` mode; role table could not express Meta work | guard checks Git in both modes, paths only in `multi-lane`; role permissions are role → lane-relative kinds, so Meta WOs allow `scripts/` and `tests/tooling/` work (sections 3, 12, 15) |
| m1: PR mode vs check 7 | kept checks (1, 2, 4, 6, 8) and replaced checks (3, 5, 7, 9, 10) listed; P2 stages exactly the leftovers (section 11) |
| m2: stale local `master`; "Update branch" leaves the local branch behind | freshly fetched `origin/master` everywhere; `update_branch.py` fast-forwards to the remote first (sections 6, 11) |
| m3: C5.3 needs part of OD10 | split into OD10a (enforcement design, Tier A) and OD10b (residual risk, Tier B) |
| m4: Orchestrator as Org Cycle Lead vs identity by checkout | separate session by default, or a worktree switch, during which it is the Cycle Lead (section 2; open item in section 18) |
| m5: G3 patch-id source and record after the PR opens | `checkpoint.py` writes ledger rows; pending-ledger file merged into the PR record by PR mode (sections 4, 11) |
| Nit: ADR timing | added to section 13 |

**Technology-freeze update (2026-11-09).** After the second pass, the PO froze the organization's technology scope until Friends Alpha. Sections 0, 1, 10, 12, 13, 14 and 16 were updated: OD16 moved to Tier A as an M8 Plan amendment; identity separation and the nested Cycle Lead variant are deferred. Section 1 now separates implemented, approved and proposed mechanisms.

**Third pass (fresh Reviewer, no prior context).** `CHANGES REQUIRED`. It confirmed every earlier finding resolved in the text and the freeze applied everywhere, and it reproduced the mechanics in scratch repositories: merge invariance, closeout exclusion, a non-empty patch-id for docs-only WOs, stale-`master` corruption. New findings and resolutions:

| Finding | Resolution |
| --- | --- |
| C1: `patch-id --stable` ignores whitespace, so a dedented Python line that changes behavior passes as gated (reproduced twice, independently) | `--verbatim` required; whitespace and Markdown/control cases added to C5.5 "Done when" (section 6) |
| M1: the guard blocked the WO record files and out-of-repository work (scratch copies) | guard scoped to this repository and its worktrees; WO record files exempt from lane checks (section 12) |
| M2: control-file list in two homes | term defined in `ENGINEERING_PROCESS.md`, paths only in the map's Meta lane (sections 3, 13) |
| M3: role-permission change unlisted; Org paths without kinds | kinds mirror today's rows; new rows (including `design`) listed under OD5; the Meta tooling change is OD20 (Tier A) (sections 3, 13) |
| m1: protection is not hard against admin credentials | stated (section 12) |
| m2: "Update branch" with an unpushed checkpoint | `update_branch.py` merges a diverged remote branch, plus a usage rule (section 6) |
| m3: Git block reached scratch repositories | covered by the M1 scoping |
| m4: OD18 shapes C5.3 | moved to Tier A |
| m5: the freeze's allowed list read as the PO's words | at that point, marked as this package's reading; now the approved OD16, scoped to orchestration tooling (section 0) |
| Nits | PR title = manifest message; `push` trigger limited to `master` |

**Confirmation pass (same Reviewer).** C1, M1, M2, m1–m5 and Nits confirmed, with `--verbatim` re-reproduced (dedent caught; merge and closeout edits equal; binary and mode changes caught). It found a remaining gap: `docs/design/` had no kind, and the new rows had been described as unchanged. A Minor (closeout comment versus Cycle Lead kinds) and a Nit (overlapping patterns) were also raised. All three were resolved by adding the `design` kind, listing the new rows under OD5, rewording `closeout:`, and adding a most-specific-pattern rule (sections 3, 4, 13).

**Final verdict on the proposal: `APPROVED`** (same Reviewer, 2026-11-09). No Critical or Major findings remain. Two non-blocking Nits stay open for the C5.3 Brief:

- `records` can never be a closeout kind, because it exists only in Org and Meta WOs, which have no closeout paths.
- The Engineer's `design` permission is meant for token and asset files, but the tooling cannot see that difference, so it is left to the Reviewer.

**Product Owner decisions applied (2026-11-09).** Tier A was approved with three refinements: contract-first parallelism (OD11), documented supervised session operations (OD18), and the technology freeze with telemetry preserved (OD16). Tier B and Tier C stay deferred, and OD10b gates the PR workflow. Applied to sections 0, 1, 2, 4, 5, 6, 7, 9, 10, 14, 15, 16, 17 and 18, including the exact M8 Plan amendment text and the C5.3 Cycle Brief.

**Focused review of the applied decisions (fresh Reviewer).** `CHANGES REQUIRED`. 0 Critical, 4 Major, 5 Minor, 4 Nits. It confirmed byte-identical "Replace:" quotes, a complete register, the OD10b gate placement, freeze compliance and telemetry consistency. Resolutions:

| Finding | Resolution |
| --- | --- |
| Section 1 still called everything unapproved | split into C (approved, not yet recorded or implemented) and D (deferred) |
| The freeze read as banning the dev toolchain, Figma MCP and product technology | scoped to AI orchestration and organization tooling, with the unaffected items listed; one home (`ENGINEERING_PROCESS.md`), which the C6 row points to |
| Manual steps missing: phase 2 relay, merge report, noticing CI failures | added to the procedure and the count |
| Phase 2 gates undefined; "one rule" contradiction | phase defined by ancestry of the producer's merge commit and written to the ledger; staleness has two named rules; PR mode refuses provisional gates |
| Minors | §9 and §6 agree; ADR 0007 holds rationale only; C5.6 checks escalation, and "unattended" is limited to proven steps; agent clauses for `multi-lane` only; the graph node and the `PRODUCT_VISION.md` sentence added to C5.3 |
| Nits | escalate added to the summary; `CURRENT_CYCLE.md` bullet narrowed, not removed; after-merge `depends` and the post-merge contract change specified; the "PO #" source explained |

**Confirmation (same Reviewer): `APPROVED`.** All fixes confirmed, and the Mermaid and `PRODUCT_VISION.md` quotes match. Its six non-blocking notes were applied: four states, the section 13 OD16 row, the indent note, the phase-check source in OD15, "revisited in C7", and whitespace.
