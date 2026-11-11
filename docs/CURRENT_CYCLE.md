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
| C6 | Not started | Replanned on 2026-11-10 as C6.1–C6.5 ([M8 Plan](milestones/M8_PLAN.md#c6-parallel-development-poc)). Next: C6.1, the Backend/API architecture plan |
| C7 | Not started | |

## Pending Gates

None active. The C5.6 gates (the public repository's `pull_request_target` policy, live `ownership` enforcement on a real PR, and the first mode switch) are deferred with C5.6. They apply only if multi-lane activation is approved later.

## Open Decisions

For C6:

- **The POC's functional slice and its success targets:** C6.3, with the two Briefs. Decided on 2026-11-10 (OD17): the POC runs contract-first, with Core and Backend in two sessions and worktrees, and Web joins the next iteration.

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

- The approved server and client decisions in `ROADMAP.md` (Python with Starlette, uvicorn and WebSocket; TypeScript with React and Vite), which `ROADMAP.md` already says Milestone 8 may revisit, against Product Contract §12, which delegates the Web framework and the real-time protocol to C7. These are technical decisions, so the product-description precedence rule does not settle them.
- The application layer's host (the table's creator, succeeded by the earliest-joined member) and the contract's Table Owner (owner-only configuration; play continues without the Owner) have no defined relationship.
- C6 is still described as an "AI teams and orchestration benchmark" in `docs/design/BRAND_ASSET_PRODUCTION_BRIEF.md`. The [M8 Plan](milestones/M8_PLAN.md) now describes it as a native-first parallel-development POC (2026-11-10).
- The milestone name: "Multi-Agent Engineering Organization + Product Architecture" in `ROADMAP.md`, "Go! Product & Company Foundation" in the M8 Plan.
- C4 is in progress although the M8 Plan's dependency graph places it after C2 and C3; `docs/design/DESIGN_INDEX.md` still has no Figma file link.
- The document pointers in `CLAUDE.md` and the Company Manual's operational context have no entries for `docs/milestones/`, `docs/product/` or `docs/design/`.
