# Current Cycle

**Milestone 8 — Multi-Agent Engineering Organization + Product Architecture** is in progress.

Milestone 7 is complete. Its behavior is recorded in `ARCHITECTURE.md`, its boundary contracts in [ADR 0005](adr/0005-player-view-and-table-session-boundary.md) and [ADR 0006](adr/0006-shared-table-revision-and-private-intents.md), and its history in Git.

**Status snapshot (2026-11-19, verified against GitHub and `master` at `033f945`):** no Cycle is in progress. A1 (PR #16) and the Core pot-settlement fix (PR #21, Issue #2 closed) are merged. The next primary engineering Cycle is R1 Backend Stability; see [Planned Cycles](#planned-cycles).

Milestone status lives in `ROADMAP.md`. The milestone plan — each Cycle's purpose and completion artifact, the dependencies, and the exit gates — is in [M8 Plan](milestones/M8_PLAN.md). This file holds the Cycle working state.

## Planning Gate

**Satisfied.** The M8 Plan and the [Friends Alpha Product Contract](product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md) were approved in C0 on 2026-11-08.

## Cycles

| Cycle | Status | Detail |
| --- | --- | --- |
| C0 | Complete (2026-11-08) | Product Contract and M8 Plan approved |
| C1 | Complete (2026-11-08) | [Product Vision](product/PRODUCT_VISION.md) approved |
| C2 | Partially explored | `docs/product/UX_FLOWS.md` not yet produced |
| C3 | Design in progress | Creative direction recorded in `docs/design/`; final brand assets, `docs/design/BRAND.md` and trademark clearance pending |
| C4 | Prototype in progress | `docs/design/DESIGN_SYSTEM.md` and `docs/design/MOTION_CONTRACTS.md` not yet produced |
| C5 | Closed (2026-11-10) | The AI organization audit is complete (2026-11-09) and archived as historical analysis in [`docs/company/M8_C5_AI_ORGANIZATION_AUDIT.md`](company/M8_C5_AI_ORGANIZATION_AUDIT.md). C5.1, documentation reconciliation, is complete (2026-11-09). C5.2, the organization design, was approved (2026-11-09); its rationale is archived in [`docs/company/M8_C5_2_ORGANIZATION_DESIGN.md`](company/M8_C5_2_ORGANIZATION_DESIGN.md). C5.3, the organization specification, is complete (2026-11-09): the rules are in `ENGINEERING_PROCESS.md`, the lane map in `.claude/ownership.json` (`mode: single-team`), and the rationale in [ADR 0007](adr/0007-lane-ownership-and-cross-lane-contracts.md). C5.4 is split in two (approved 2026-11-09): C5.4a, the ownership map resolver and the CI `ownership` check, is complete (2026-11-09). C5.4b, the guard hook, was stopped on 2026-11-10 and is superseded. It had been registered locally, caused a lockout, and was disabled and removed without being committed. Its code and the Option B redesign are archived, and the committed `.claude/settings.json` keeps the native deny rules only. C5.5 and C5.6 are not pursued in M8. The record is [`docs/company/C5_4_ENFORCEMENT_RETROSPECTIVE.md`](company/C5_4_ENFORCEMENT_RETROSPECTIVE.md) |
| C6 | In progress | Replanned on 2026-11-10 as C6.1–C6.5 ([M8 Plan](milestones/M8_PLAN.md#c6-parallel-development-poc)). C6.1, the Backend/API architecture plan, is complete (2026-11-11): the [C6.1 plan](milestones/M8_C6_1_BACKEND_API_PLAN.md) (decisions E1–E18) and [ADR 0008](adr/0008-fastapi-server-and-single-writer-tables.md), accepted. The POC is now Backend ∥ Web after a bounded preflight (E9-A). C6.2, the Web architecture and design foundation plan, is complete (2026-11-11): the [C6.2 plan](milestones/M8_C6_2_WEB_PLAN.md) (decisions W1–W30), approved; the design references are recorded as concepts. C6.3, the shared wire contract, is complete (2026-11-12): [ADR 0009](adr/0009-wire-protocol-v1.md) revision 2, protocol `go-poker.v1`, is accepted; its [canonical fixtures](adr/0009-wire-protocol-v1/README.md) are frozen for C6.4; the [C6.3 plan](milestones/M8_C6_3_WIRE_CONTRACT_PLAN.md) (P1–P17, Q1–Q5) and both C6.4 Briefs ([Backend](milestones/M8_C6_4_BACKEND_BRIEF.md), [Web](milestones/M8_C6_4_WEB_BRIEF.md)) are approved; B1–B7 are resolved. The toolchain preflight (C6.3 plan D2, Meta, Small-Change Path) is complete (2026-11-12): the `server` extra (`fastapi`, `uvicorn`, `websockets`) and dev `httpx2` on Python 3.14 (the Owner chose it over the planned `httpx` on 2026-11-12, because Starlette's `TestClient` deprecates `httpx`); the `web/` skeleton (React, strict TypeScript, Vite, Biome, Vitest, Testing Library, npm lockfile, Node 26 LTS pinned in `web/.nvmrc`); the four Web gates in `scripts/verify.py`; Node and `npm ci` in CI. C6.4 is integrated on `master`: the Backend (PR #1) and Web (PR #9) Cycles are merged. The C6.5 evaluation is not yet recorded here. Web follow-up Cycles are listed [below](#web-follow-up-cycles) |
| C7 | Not started | |

## Web follow-up Cycles

M8 Web follow-up Cycles after C6.4. They improve the playable table without changing the milestone structure, the protocol or server authority.

| Cycle | Status | Detail |
| --- | --- | --- |
| Visual Rescue | Complete (merged 2026-11-15, PR #15) | Table readability and layout: card readability, seat collisions, clipping, chip positions |
| A1 — Betting and Action Safety | Complete (merged 2026-11-17, PR #16) | A fixed two-row, 70 px Action Dock in every state; Min and Max as draft selectors only; invalid or out-of-range typed amounts never clamp and cannot commit; a two-press Fold while Check is free; the provisional 350 ms turn-arrival guard; inline pending, rejection and reconnect feedback; Leave in a secondary table menu with a native confirmation dialog. Contract amendments AM1–AM3 are [C6.2 plan](milestones/M8_C6_2_WEB_PLAN.md) revision 3; the component states are [`ACTION_DOCK.md`](design/ACTION_DOCK.md) (AM4). Non-blocking review findings are tracked as Issues #17–#20 |
| A2 — Player Action Feedback | Planned; not started (Issue #23, with #17 and #20) | Prioritized by the Owner before pre-actions and keyboard shortcuts. Timed transitions wait for the B0 motion contracts |

## Planned Cycles

Nothing below has started, and none is marked In Progress until work begins. Scope and Issue numbers are in [`ROADMAP.md`](ROADMAP.md).

| Cycle | Status | Detail |
| --- | --- | --- |
| R0 — Core Correctness | Complete (2026-11-17) | Issue #2 via PR #21 |
| **R1 — Backend Stability** | **Next primary engineering Cycle (planned)** | Issues #3–#7. Start with #3 (cancel and await WebSocket reader/writer tasks) and #4 (next-hand timer re-arm). Needs a Cycle Brief; #5–#7 follow or join the Brief at the Owner's choice |
| F0 — Friends Session Contracts | Planned parallel design Cycle | Issue #22: specification, authority, persistence, privacy and failure semantics, reconciled with the Product Contract's wallet model, before any decomposition. May run beside R1 |
| R2 — Web Connectivity & Secure Hosting | Planned | Issues #10–#13. #10 needs the Friends Alpha origin/hosting decision first |
| A2 — Player Action Feedback | Planned | Issues #23, #17, #20 |
| B0 — Motion contracts and showdown experience | Planned | Issues #24, #14, #19 |
| Show/Muck 3-second timer | Planned, not implemented | Issue #25. Needs an approved server/protocol/design contract first |
| Offline Variant Lab | Ongoing personal track, not a release gate | Issue #26; [offline guide](company/OFFLINE_DEVELOPMENT_GUIDE.md) |

## Pending Gates

None active for C6.

**Friends Alpha blockers** (mandatory, or explicitly re-approved by the Owner, before the Friends Alpha). The Issues are the source of truth; the grouping is in [`ROADMAP.md`](ROADMAP.md#release-blockers).

- **Resolved: equivalent pot layers and odd chips** (GitHub Issue #2, closed 2026-11-19). `pots()` now merges adjacent layers with identical eligible seats, so the reproduced case pays 65 / 65. Merged as PR #21 (`033f945`): the ADR 0001 clarification note, regression and chip-oracle tests, and the `three_way_side_pots` fixture regenerated under C6.3 P17 (ADR 0009 §10 and the fixtures README). Detail: [C6.3 plan](milestones/M8_C6_3_WIRE_CONTRACT_PLAN.md) §7.
- **Open, labelled `release-blocker`:** #3, #4, #5, #6, #7 (Backend, R1) and #10, #11, #12 (Web, R2).
- **Also required, not labelled:** #22 Friends Session (`priority:p1`, Product Contract P0).

The C5.6 gates (the public repository's `pull_request_target` policy, live `ownership` enforcement on a real PR, and the first mode switch) are deferred with C5.6. They apply only if multi-lane activation is approved later.

## Open Decisions

For C6:

- **The POC's functional slice and its success targets:** decided on 2026-11-12 (C6.3).
  - The slice is in the two approved C6.4 Briefs.
  - The M8 Plan's C6 success targets are confirmed unchanged (C6.3 P16).
  - The POC runs contract-first in two sessions and worktrees (OD17, 2026-11-10), and the pair is Backend and Web (C6.1 E9, 2026-11-11).
- **ADR 0009 contract blockers B1–B7** from C6.2: resolved by ADR 0009 (accepted 2026-11-12; [C6.3 plan](milestones/M8_C6_3_WIRE_CONTRACT_PLAN.md) §2).
- **Long-term protocol compatibility:** C7, before any installed client that cannot simply reload ships. It covers backward compatibility, multiple accepted protocol versions and HTTP API versioning (ADR 0009 §1.6). `go-poker.v1` stays frozen for C6.4.
- **Deferred C6.2 items:** pot-based sizing presets (W21), defined in a later game/betting contract cycle before any preset button is built.
- **Bet sizer slider increments** (raised in A1, 2026-11-16): the slider moves in $1 steps. The engine accepts every whole-number target in `[min_full_target, max_target]`, and no chip denomination or betting increment exists in the engine, the view or the protocol. Snapping the slider to multiples of the small blind would not change legality, but it means client-computed amounts, which C6.2 §2.3 rule 7 forbids. It needs either a rule 7 clarification (UI-only selection granularity, with the exact minimum, maximum and short all-in always selectable and typed entry unchanged) or an authoritative chip-unit or increment in the game contract.
- **Display-only money arithmetic** (A1 D1, 2026-11-16): deferred to a separate follow-up; rule 7 is unchanged.
- **Friends Alpha hosting origin** (Issue #10, 2026-11-19): the browser origin strategy for non-local clients (HTTPS/WSS) is undecided. It gates R2 and release validation.
- **Friends Session versus Wallet** (Issue #22, 2026-11-19): the Product Contract describes a persistent wallet, grants and rebuys; Issue #22 describes a session ledger with external Settle Up. F0 reconciles them.
- **Show/Muck timer contract** (Issue #25, 2026-11-19): deadline ownership, legality of auto-Show, reconnect and race semantics, and any wire change, before implementation.
- **Where the archived approved decisions live** (2026-11-19): the roadmap rewrite left their text in [`milestones/ROADMAP_ARCHIVE_2026-11-19.md`](milestones/ROADMAP_ARCHIVE_2026-11-19.md). The Owner decides whether to move them to ADRs, `ARCHITECTURE.md` or the Product Contract.
- **Deferred C6.1 decisions:** E3, the showdown-timeout rule (with the action timer); E5, Host versus Table Owner (C7); the E14 Quick Play pool details (Quick Play design); the E16 recovery mechanism (C7).

Deferred C5.2 organization decisions, each decided at its gate:

- **Single-account residual risk** (OD10b): explicit Product Owner acceptance before any multi-lane activation Brief is Ready. Deferred with C5.6.
- **`gh` as a tooling dependency** (OD15), including how the checkpoint script finds a producer's merge commit: deferred with C5.5.
- **Lane-specific agents**, for example a Figma-equipped designer (OD19): when a Design Work Order needs one.
- **Identity separation** (machine user or token, credential sandbox): after Friends Alpha, or earlier after an incident.
- **Pre-approved auto-merge**: after C6 measurement.
- **Nested Cycle Lead sessions**: after Friends Alpha.

## Open Contradictions

Identified for follow-up; none is resolved by changing an approved product decision.

Stale product descriptions in the archived roadmap ([`milestones/ROADMAP_ARCHIVE_2026-11-19.md`](milestones/ROADMAP_ARCHIVE_2026-11-19.md), formerly `ROADMAP.md`) that the Friends Alpha Product Contract governs (precedence approved on 2026-11-09). The roadmap text still needs editorial reconciliation:

- [Reach a Friends Alpha](milestones/ROADMAP_ARCHIVE_2026-11-19.md#reach-a-friends-alpha): "a simple guest identity", "visual polish can be modest" and the non-goal "complex accounts or authentication", against the contract's persistent anonymous server accounts, persistent wallet and ledger, and a branded, visibly designed lobby and table.
- The same section's non-goals "reconnect perfection", against the contract's exact reconnect, sit-out and grace timings, and "social features, matchmaking, and lobby discovery", against the contract's P0 lobby (matchmaking stays deferred in both).
- The approved decisions on rebuy ("may be added") and Leave ("rebuy/top-up stays deferred"), against Rebuys and Top-ups in Friends Alpha P0.
- The Leave decision that a user who left "cannot rejoin the same table session", against the 30-minute anti-ratholing claim on the same Session (D36), which implies a return to it.
- [Grow the Platform](milestones/ROADMAP_ARCHIVE_2026-11-19.md#grow-the-platform) and the milestone table: accounts and persistence (Milestone 16) after the Alpha, replacing guest-only, in-memory tables, against persistent accounts, wallets and saved tables in Friends Alpha.

Open for C7 or a Product Owner decision, not covered by the precedence rule:

- The application layer's host (the table's creator, succeeded by the earliest-joined member) and the contract's Table Owner (owner-only configuration; play continues without the Owner) have no defined relationship.
- C6 is still described as an "AI teams and orchestration benchmark" in `docs/design/BRAND_ASSET_PRODUCTION_BRIEF.md`. The [M8 Plan](milestones/M8_PLAN.md) now describes it as a native-first parallel-development POC (2026-11-10).
- The milestone name: "Multi-Agent Engineering Organization + Product Architecture" in `ROADMAP.md`, "Go! Product & Company Foundation" in the M8 Plan.
- C4 is in progress although the M8 Plan's dependency graph places it after C2 and C3. (Since C6.2 W15, approved design specifications in the repository are the design source of truth, and Figma is optional tooling.)
- The document pointers in `CLAUDE.md` and the Company Manual's operational context have no entries for `docs/milestones/`, `docs/product/` or `docs/design/`.
