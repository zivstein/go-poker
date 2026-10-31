# Current Cycle

There is currently no active implementation Cycle.

Milestone 5 — Complete continuous PokerHand/game loop is complete. Milestone status lives in `ROADMAP.md`; the hand lifecycle and orchestration contract lives in [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md) and the showdown contract in [ADR 0003](adr/0003-interactive-showdown-and-muck.md); implemented behavior lives in `ARCHITECTURE.md`.

## Next Milestone

**Milestone 6 — Structured Hand History / Event Log**

Status: **not started**

Planning happens before implementation.

Expected capability, from the decisions already recorded in `ROADMAP.md`, ADR 0002 and ADR 0003:

- structured raw hand history/events as reconstructable source data, before persistence, analytics, or AI depend on them;
- events recorded in order, including the showdown start, each SHOW/MUCK decision, and the runout, plus facts current state loses, such as who was all-in;
- derived player hand strength for client display (category and rank, best five cards, description), as approved in `ROADMAP.md`.

## Open Decisions

Milestone 6 planning must resolve these before implementation:

- the event model, its granularity, and its ownership relative to `PokerHand`, `hand_flow`, and `HoldemGame`;
- how history relates to low-level operations versus orchestrated play;
- any other product/domain decisions the history design exposes.
