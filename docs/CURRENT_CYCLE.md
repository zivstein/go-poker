# Current Cycle

There is currently no active implementation Cycle.

Milestone 4 — Showdown + settlement is complete. Milestone status lives in `ROADMAP.md`; the showdown and settlement contract lives in [ADR 0001](adr/0001-showdown-settlement-contract.md); implemented behavior lives in `ARCHITECTURE.md`.

## Next Milestone

**Milestone 5 — Complete continuous PokerHand/game loop**

Status: **not started**

Planning happens before implementation.

Expected capability, from the decisions already recorded in `ROADMAP.md` and ADR 0001:

- orchestrate a full hand from start to settlement, calling `settle_hand(hand)` once the hand has reached its end;
- once betting is closed with at least two live players, reveal the relevant hands and complete the board runout before showdown;
- block dealing and betting operations after settlement as part of the hand lifecycle;
- continue from one hand to the next.

## Open Decisions

Milestone 5 planning must resolve these before implementation:

- the hand lifecycle and orchestration design, and its public entry points;
- which hands are revealed at showdown, and in what order;
- any other product/domain decisions the orchestration design exposes.
