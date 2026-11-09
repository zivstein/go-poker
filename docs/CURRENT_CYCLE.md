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
| C5 | Started | The AI organization audit is complete (2026-11-09) and archived as historical analysis in [`docs/company/M8_C5_AI_ORGANIZATION_AUDIT.md`](company/M8_C5_AI_ORGANIZATION_AUDIT.md); C5.1, documentation reconciliation, is complete (2026-11-09); the next C5 step awaits the audit decisions below |
| C6 | Not started | |
| C7 | Not started | |

## Open Decisions

- The C5 audit's organization proposals await Product Owner decision. None is approved, and none is recorded as a decision until it is. They gate C5 implementation, not the milestone's Planning Gate.

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
- The milestone name: "Multi-Agent Engineering Organization + Product Architecture" in `ROADMAP.md`, "Go! Product & Company Foundation" in the M8 Plan.
- The M8 Plan's C5 row names a Product team and a `docs/organization/AI_ORGANIZATION.md` deliverable; the audit brief named a Design team, and `docs/organization/` does not exist.
- C4 is in progress although the M8 Plan's dependency graph places it after C2 and C3; `docs/design/DESIGN_INDEX.md` still has no Figma file link.
- The M8 Plan's parallel Architecture Discovery track has no recorded status.
- The Ownership table in `ENGINEERING_PROCESS.md`, the document pointers in `CLAUDE.md`, and the Company Manual's operational context have no entries for `docs/milestones/`, `docs/product/` or `docs/design/`.
