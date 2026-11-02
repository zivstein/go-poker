# Current Cycle

**Milestone 7 — Player view + local table** is in progress. Cycle 1 (player view projection) is complete; Cycle 2 is next and has no Brief yet.

Milestone 6 is complete. Its behavior is recorded in `ARCHITECTURE.md` and its history in Git.

Milestone status, the Roadmap-to-Alpha, and approved product decisions live in `ROADMAP.md` ([Reach a Friends Alpha](ROADMAP.md#reach-a-friends-alpha)).

The boundary contract for this milestone is [ADR 0005](adr/0005-player-view-and-table-session-boundary.md), cited below as ADR 0005 §N. It builds on earlier contracts:

- the visibility classes of [ADR 0004](adr/0004-hand-history-and-event-contract.md) §9;
- the caller preconditions of [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md) §9.

## Planning Gate

**Satisfied.** ADR 0005 was accepted on 2026-11-02.

- The milestone scope, the Cycle split, and every product and architecture decision were approved on 2026-11-02.
- The engine-generation reset (ADR 0005 §11) resolved the last planning question.
- No planning-level question remains open.
- Cycle 1 is complete. Each later Cycle still needs its own approved Brief.

## Goal

Turn the engine into a multiplayer table that several local browser tabs play together.

- A server owns one authoritative `HoldemGame` per private table.
- Each tab sees only what its viewer may see.
- Every decision goes through commands; the engine decides legality.
- Hands follow one another without anyone resetting the engine.

In scope:

- the engine's read-only player-view projection and visibility rule, with an allowlist-redacted log of the current hand (ADR 0005 §2–5);
- the transport-free `TableSession` application layer (ADR 0005 §6–11):
  - guest seats and commands;
  - the revision guard;
  - pending hand-boundary intents and the automatic action of a leaving player;
  - the automatic next hand;
  - the waiting state;
  - the engine-generation reset;
- the single-process real-time server: WebSocket delivery of full per-viewer snapshots, and JSON serialization of views (ADR 0005 §12–14);
- an unstyled browser client skeleton that can create or join a table and play;
- viewer-relative leak tests: no card appears in a viewer payload unless ADR 0004 or ADR 0005 says that card is visible to that specific viewer at that moment.

Out of scope:

- deployment and hosting;
- the styled table UI and the private-table landing flow (Milestone 8);
- the action timer, rebuy and top-up, and completed-history logs (Milestone 9);
- persistence and accounts;
- a spectator UI;
- bots and a dev-only autoplayer;
- variants;
- reconnect beyond rejoining by guest token;
- every Friends Alpha non-goal in `ROADMAP.md`;
- any change to the engine's poker rules or lifecycle contract.

## Cycles

| Step | Title | Surface | Status |
| --- | --- | --- | --- |
| Cycle 1 | Player view projection | Engine: `game/visibility.py`, the Hold'em view layer | Complete; its behavior is in `ARCHITECTURE.md` ([Player View](ARCHITECTURE.md#player-view)) |
| Cycle 2 | `TableSession` application layer | `src/go_poker/app/` | Not started |
| Cycle 3 | Real-time table server | `src/go_poker/server/` | Not started |
| Meta | Frontend tooling in verification | `scripts/verify.py`, CI, agent instructions | Not started; separate Meta work needing its own approval |
| Cycle 4 | Browser client skeleton | `web/` | Not started |

Dependencies:

- Cycle 2 depends on Cycle 1.
- Cycle 3 depends on Cycle 2.
- Cycle 4 depends on Cycle 3 and on the Meta step.

The Meta step changes control files, so it runs as dedicated Meta work, never inside a feature Cycle.

Checkpoints:

- **Cycle 1:** per-seat views of the same hand differ exactly as ADR 0004 §9 requires.
- **Cycle 3:** scripted WebSocket clients play hands, each receiving only its own snapshot.
- **Cycle 4:** several local browser tabs play consecutive hands at one table.

Sizing:

- Each seam is approved as coherent and independently verifiable.
- The Cycle Sizing check is applied again to each Cycle before its Brief is approved.
- Cycle 3 must be split before execution if server transport, timers, and session orchestration together form several natural, independently verifiable surfaces.
- Cycle 1 may split into a snapshot part and a log-and-result part if its sizing signals fire.

Before the Cycle 3 Brief is approved, confirm that Starlette and uvicorn work with Python 3.14.

## Invariants

- **Viewer-relative visibility.**
  - No card may appear in a viewer payload unless ADR 0004 or ADR 0005 says that card is visible to that specific viewer at that moment.
  - This applies to views and to serialized payloads sent to clients alike.
  - The leak tests enforce it per viewer, at every emitted state.
  - Burned cards and the undealt deck are never visible to any viewer.
- **One authority.**
  - The engine is the only judge of poker legality.
  - The application layer and clients never re-derive or duplicate poker rules or state.
- **Revision.**
  - `TableSession.revision` is the monotonic version of the authoritative application-level table and session state.
  - It increments after every successful authoritative session mutation that may affect current or future behavior, or any emitted snapshot (ADR 0005 §8).
  - A rejected command or a pure read never increments it.
  - It never resets for the life of the private table, including across an engine-generation reset.
  - Every snapshot carries the current revision, and every state-changing client command carries `expected_revision`.
  - A state-changing command whose expected revision does not match is rejected before the engine is called.
  - Timer tasks re-check the revision they were scheduled from.
- **Boundary intents.**
  - A leave or sit-out requested during a hand never changes the current hand's engine state or a participant's `Player.status`.
  - These intents are applied at the hand boundary.
- **No engine contract change.**
  - The engine-generation reset happens entirely in the application layer.
  - No engine epoch, table-wide hand sequence, or second authoritative stack is introduced.

## Brief-Level Choices

Each Cycle Brief settles its own implementation-level choices within ADR 0005 and the approved decisions in `ROADMAP.md`.

Cycle 1 settled its choices in its Brief, approved on 2026-11-02. The implemented result is recorded in `ARCHITECTURE.md` ([Player View](ARCHITECTURE.md#player-view)).
