# Current Cycle

**Milestone 8 — Multi-Agent Engineering Organization + Product Architecture** is in progress.

Milestone 7 is complete. Its behavior is recorded in `ARCHITECTURE.md`, its boundary contracts in [ADR 0005](adr/0005-player-view-and-table-session-boundary.md) and [ADR 0006](adr/0006-shared-table-revision-and-private-intents.md), and its history in Git.

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
| C6 | In progress | Replanned on 2026-11-10 as C6.1–C6.5 ([M8 Plan](milestones/M8_PLAN.md#c6-parallel-development-poc)). C6.1, the Backend/API architecture plan, is complete (2026-11-11): the [C6.1 plan](milestones/M8_C6_1_BACKEND_API_PLAN.md) (decisions E1–E18) and [ADR 0008](adr/0008-fastapi-server-and-single-writer-tables.md), accepted. The POC is now Backend ∥ Web after a bounded preflight (E9-A). C6.2, the Web architecture and design foundation plan, is complete (2026-11-11): the [C6.2 plan](milestones/M8_C6_2_WEB_PLAN.md) (decisions W1–W30), approved; the design references are recorded as concepts. C6.3, the shared wire contract, is complete (2026-11-12): [ADR 0009](adr/0009-wire-protocol-v1.md) revision 2, protocol `go-poker.v1`, is accepted; its [canonical fixtures](adr/0009-wire-protocol-v1/README.md) are frozen for C6.4; the [C6.3 plan](milestones/M8_C6_3_WIRE_CONTRACT_PLAN.md) (P1–P17, Q1–Q5) and both C6.4 Briefs ([Backend](milestones/M8_C6_4_BACKEND_BRIEF.md), [Web](milestones/M8_C6_4_WEB_BRIEF.md)) are approved; B1–B7 are resolved. Next, on the Owner's instruction: the bounded toolchain preflight, then C6.4 |
| C7 | Not started | |

## Pending Gates

None active for C6.

**Friends Alpha blockers** (mandatory before the Friends Alpha):
- **A known Core correctness defect: equivalent pot layers and odd chips.**
  - `pots()` never merges adjacent pot layers with identical eligible-seat sets, and settlement splits each layer independently (ADR 0001 §1).
  - With a tie, the odd chips can then differ from the merged pot. A reproduced five-player case pays 66 / 64 instead of 65 / 65 for an aggregate 130-chip pot. Chips are conserved and winner eligibility is correct.
  - It is accepted for the C6.4 POC only.
  - **The fix:** a Core Cycle after C6.4 that clarifies ADR 0001, merges equivalent adjacent layers in Core, and adds regression tests for ties, odd chips, eligibility and conservation. The affected fixtures are then updated under C6.3 P17.
  - Detail: [C6.3 plan](milestones/M8_C6_3_WIRE_CONTRACT_PLAN.md) §7.

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

Stale `ROADMAP.md` product descriptions that the Friends Alpha Product Contract governs (precedence approved on 2026-11-09). The roadmap text still needs editorial reconciliation:

- [Reach a Friends Alpha](ROADMAP.md#reach-a-friends-alpha): "a simple guest identity", "visual polish can be modest" and the non-goal "complex accounts or authentication", against the contract's persistent anonymous server accounts, persistent wallet and ledger, and a branded, visibly designed lobby and table.
- The same section's non-goals "reconnect perfection", against the contract's exact reconnect, sit-out and grace timings, and "social features, matchmaking, and lobby discovery", against the contract's P0 lobby (matchmaking stays deferred in both).
- The approved decisions on rebuy ("may be added") and Leave ("rebuy/top-up stays deferred"), against Rebuys and Top-ups in Friends Alpha P0.
- The Leave decision that a user who left "cannot rejoin the same table session", against the 30-minute anti-ratholing claim on the same Session (D36), which implies a return to it.
- [Grow the Platform](ROADMAP.md#grow-the-platform) and the milestone table: accounts and persistence (Milestone 16) after the Alpha, replacing guest-only, in-memory tables, against persistent accounts, wallets and saved tables in Friends Alpha.

Open for C7 or a Product Owner decision, not covered by the precedence rule:

- The application layer's host (the table's creator, succeeded by the earliest-joined member) and the contract's Table Owner (owner-only configuration; play continues without the Owner) have no defined relationship.
- C6 is still described as an "AI teams and orchestration benchmark" in `docs/design/BRAND_ASSET_PRODUCTION_BRIEF.md`. The [M8 Plan](milestones/M8_PLAN.md) now describes it as a native-first parallel-development POC (2026-11-10).
- The milestone name: "Multi-Agent Engineering Organization + Product Architecture" in `ROADMAP.md`, "Go! Product & Company Foundation" in the M8 Plan.
- C4 is in progress although the M8 Plan's dependency graph places it after C2 and C3. (Since C6.2 W15, approved design specifications in the repository are the design source of truth, and Figma is optional tooling.)
- The document pointers in `CLAUDE.md` and the Company Manual's operational context have no entries for `docs/milestones/`, `docs/product/` or `docs/design/`.
