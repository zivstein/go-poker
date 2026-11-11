# 0005: Player view, table session, and server boundary

Status: Accepted (2026-11-02); partly superseded by [ADR 0006](0006-shared-table-revision-and-private-intents.md) (2026-11-03) and by [ADR 0008](0008-fastapi-server-and-single-writer-tables.md) (2026-11-11: §12's single-instance and restart-loss clauses and §14's Starlette clause; §14's serializer clause refined)

> **Supersession note (2026-11-03).** This record is kept as written. [ADR 0006](0006-shared-table-revision-and-private-intents.md) supersedes parts of it: decision 8's increment rule, including its example "an accepted leave or sit-out intent" (the revision is now the shared table-state revision, and private intents alone never increment it); decision 7's closed command list, extended by the pre-action command; and decision 13's "after every successful state change" (after a shared transition every connected viewer receives their own snapshot; after a private-only change, only the owner). Everything else stands, including `expected_revision` on every state-changing command, the revision guard before the engine, and timers re-checking the revision. Milestone numbers after 7 in this record use the roadmap numbering of 2026-11-02, which is being replanned (see `ROADMAP.md`).

## Context

Milestones 0–6 deliver a complete, continuous No-Limit Hold'em engine:

- `HoldemGame`;
- full betting, all-ins, and side pots;
- interactive showdown and settlement;
- derived hand strength;
- a stable logical participant identity;
- an immutable hand history.

The engine is authoritative, and its state and history hold hidden information:

- every player's hole cards, including folded and mucked ones;
- the burned cards;
- the undealt deck.

[ADR 0004](0004-hand-history-and-event-contract.md) §9 classifies which facts may reach whom, and leaves the projection to a later milestone.

On 2026-11-02 the roadmap was re-planned around a **Friends Alpha**: friends share a URL, join a private table in a desktop browser, and play consecutive real Hold'em hands (see `ROADMAP.md`). Milestone 7 builds the first end-to-end path, from the engine to a browser. That needs three new boundaries:

- a player-specific projection of engine state;
- an application layer that turns client requests into engine calls for a private table;
- a server that owns live tables and pushes state to connected players.

These boundaries are durable. Later work builds on them: Milestone 8 deployment and UI, Milestone 9 table-life rules, and later accounts, persistence, reconnect, mobile clients, and variants.

The engine also sets caller preconditions that this layer must honor ([ADR 0002](0002-hand-lifecycle-orchestration-contract.md) §9):

- never stand up a hand participant or change a participant's stack during a hand;
- drive one `Table` through one `HoldemGame`.

`HoldemGame.start` is one-time. The lifecycle cannot continue when no `READY` player with chips remains.

Milestone numbers in ADRs 0002–0004 use the roadmap numbering before 2026-11-02 (see Consequences).

## Decision

1. **Layers and dependency direction.**
   - The layers are `core` ← `game` (engine) ← `app` ← `server`. The browser client talks only to the server.
     - `src/go_poker/app/` is the application layer: transport-free and synchronous.
     - `src/go_poker/server/` is the server: ASGI, WebSocket, and JSON.
   - The engine never imports `app` or `server`, and `app` never imports `server`. A test enforces this direction.
   - The engine keeps no runtime dependencies. The server's dependencies are not engine dependencies.
   - The engine stays importable and usable alone.

2. **The projection is engine-owned, read-only derived state.**
   - Who may see which cards is a poker rule, so the projection lives in the engine:
     - the variant-agnostic visibility rule (which seats' hole cards a viewer may see) in `game/visibility.py`;
     - the Hold'em view in the Hold'em variant package.
   - A view is a pure function of the engine table, the current hand, and a viewer. It returns immutable values: never live engine objects, and never the hand's own lists.
   - It is derived on request and never stored. No rule reads it, and it changes nothing.
   - **Viewer.** The engine knows a viewer only as a seat number, or as nobody (the public view).
     - Mapping a guest to a seat is the application's job.
     - A player's view is the public view plus that seat's private facts.
     - A seated player who is not in the current hand sees no private hand facts.

3. **Visibility rules.** These implement ADR 0004 §9; they do not change it.

   | Fact | Rule |
   | --- | --- |
   | The viewer's own hole cards | Visible to that seat, always, including after it folds or mucks. |
   | Other seats' hole cards | Hidden. The view tells only whether the seat holds cards. |
   | Shown cards | Public once shown: every live seat once an `ALL_IN` showdown starts, and each SHOW in an `INTERACTIVE` showdown. They are derived from the showdown record, their single source. |
   | Mucked cards, folded cards, and the cards of a last contender who wins without showing | Never visible to another seat. |
   | Board | Public, as dealt. |
   | Burned cards and the undealt deck | Never in any view. The view types have no field that could hold them. |
   | Derived hand strength | Visible to the owning seat. Public for a seat once its cards are shown. |
   | Legal betting actions | Only in the current actor's view, exactly as `legal_actions` derives them. |
   | SHOW/MUCK options | Only in the current decider's view. |
   | Current actor and decision kind | Public. |
   | Stacks, chips in front, folded, all-in, positions, blinds, button | Public. |
   | Pots | Public, as derived. |
   | Showdown kind, order, and decisions | Public. |
   | Completed-hand result | Public: the pot awards, plus the rank and best five cards of shown seats only. |

4. **Where a view's facts come from.**
   - The current state comes from the live engine: the hand, the table, the players, and the engine's derived reads.
   - The log comes from the current hand's history.
   - A hand that is no longer current is never projected from a live `PokerHand`. Its `Player` objects are shared with later hands, so their stacks have moved on. Any past-hand view is derived from that hand's history.
   - A settled hand stays the current hand, and is projected, until the next hand replaces it.

5. **The log is redacted by allowlist.**
   - Each event type of the closed `HandEvent` union is classified explicitly. A view carries only the facts that are public or visible to that viewer:
     - hole-card deals carry only the viewer's own cards;
     - street deals carry only the board cards, never the burned ones.
   - The classification is exhaustive. An engine event type added later cannot reach a view until it has been classified, and the type checker fails until then.
   - Which view types carry the log is a Cycle Brief choice.

6. **`TableSession` is the application-level private table.** One `TableSession` per private table owns:
   - the engine objects of its current engine generation: one engine `Table` and at most one `HoldemGame`;
   - the private table's identity and code;
   - its stakes and buy-in;
   - its host: the guest who created it;
   - its guests, each with:
     - a server-issued bearer token, never sent to other clients and never put in a URL;
     - an application-level display name;
     - the seat they own;
     - an opaque engine `player_id`, generated by the application, distinct from the display name and stable for that participant at that table (ADR 0004 §6);
   - its pending hand-boundary intents (§9);
   - its revision (§8).

   Anyone holding a table's code may join it. The engine never sees tokens, names, codes, or revisions.

7. **Commands, and the engine as sole authority.**
   - Clients change a table only through `TableSession` commands:
     - create a table;
     - join and sit;
     - leave;
     - sit out and sit back;
     - start the game (host only);
     - a betting action;
     - a SHOW/MUCK decision.
   - Starting the next hand is triggered by the application or server, not the client (§10).
   - For each command, `TableSession`:
     - resolves the guest to their seat;
     - checks that they own it;
     - checks the revision;
     - passes poker actions to the engine unchanged.
   - Only the engine judges poker legality. The application never re-derives legal actions, turn order, or any other poker rule or state.
   - An engine rejection becomes a typed application rejection. A rejected command changes nothing.

8. **Revision: the concurrency and stale-command token.**
   - `TableSession.revision` is the monotonic version of the authoritative application-level table and session state. It is application concurrency state, not poker state.
   - It increments after every successful authoritative session mutation that may affect current or future behavior, or any emitted snapshot. For example:
     - a successful engine action, including an automatic action;
     - a join, or any change of seat ownership;
     - an accepted leave or sit-out intent;
     - applying a hand-boundary intent;
     - starting a hand, or advancing to the next hand;
     - replacing the engine generation;
     - any other successful session-state change.
   - A rejected command does not increment it, and neither does a pure read or query.
   - It never resets for the life of the private table.
   - Every snapshot carries the current revision.
   - Every state-changing client command carries the revision it expects. A mismatch is rejected before the engine is called.
   - A timer task records the revision it was scheduled from, and re-checks it before acting.
   - It keeps commands safe:
     - across hands;
     - across joins and leaves;
     - across automatic actions;
     - across replacement of the engine game (§11);
     - between racing clients;
     - against an old browser tab.
   - After the revision check passes, the engine remains the authority on legality.

9. **Hand-boundary intents.** A leave or sit-out requested while a hand is in progress never changes the current hand's engine state or a participant's `Player.status`. The application records it as a pending intent instead.

   **Pending leave:**
   - The hand and the participant's state stay intact.
   - When a betting action is required of that player, the application submits CHECK if it is legal, otherwise FOLD, as a normal engine action.
   - When a showdown decision is required of them, it submits MUCK.
   - After settlement, the stand-up is applied at the hand boundary.

   **Pending sit-out:**
   - The player plays the current hand normally.
   - The sit-out applies from the next hand.
   - A sit-back intent likewise takes effect at a boundary.

   With no hand in progress, these requests apply at once.

10. **Automatic next hand and waiting.**
    - After a hand settles, the next hand starts automatically after a short pause. The application or server owns the pause, and the engine keeps no clock. Its length is a product setting, initially about 5 seconds.
    - At the hand boundary, in this order:
      1. pending leaves are applied;
      2. sit-out and sit-back intents are applied;
      3. the next hand is started.
    - When too few eligible players remain, the table waits, and resumes after a later change makes play possible.
    - The host's start command starts a private table's first hand. After that, the table continues on its own, including after an engine-generation reset.

11. **Engine-generation reset.**
    - **Trigger.** At a hand boundary, the current engine generation may no longer be able to progress because no `READY` player with chips remains. The fully empty table is only the degenerate case. The application then:
      1. applies pending leaves, so a player who left is not recreated;
      2. discards the old engine `Table` and `HoldemGame`;
      3. creates a fresh engine `Table`;
      4. recreates each still-seated logical participant in the same seat, with:
         - the same `player_id`;
         - the stack they have in the old engine at the boundary;
         - their application-level participation intent, which decides whether they join the new generation;
      5. creates a fresh `HoldemGame`;
      6. starts it once at least two eligible, willing players with chips are available, and otherwise waits until that is true.
    - **What persists.**
      - The private table's identity and code.
      - Guest tokens and seat ownership.
      - Display names.
      - The revision, which stays monotonic.
    - **What it is not.**
      - A new engine `Player` with the same `player_id` is the same logical participant. Identity is the `player_id`, not the Python object.
      - The application keeps no second authoritative stack. It reads a stack from the old engine only at the generation boundary, to build the replacement participant.
      - Hand numbers may restart in the fresh `HoldemGame`. They are scoped to one engine generation, and the revision, not the hand number, is the concurrency token.
      - No engine epoch, table-wide hand sequence, or global hand identifier is introduced.
      - The engine lifecycle contract is unchanged. One `Table` is still driven by exactly one `HoldemGame`, and each `HoldemGame` is started once.

12. **One authoritative process.**
    - A single server process holds every live `TableSession` in memory. It is the only authority for its tables, so exactly one instance runs.
    - Engine and application calls are synchronous. Each command runs to completion before another command for the same table starts, with no yielding in the middle of a command. Concurrent requests are therefore serialized, and the loser of a race gets a rejection.
    - Timers (the next-hand pause, and later the action timer) are server tasks that re-check the revision before acting (§8).
    - A restart loses every table. That is accepted for the Friends Alpha.

13. **Real-time delivery.**
    - Each client connection is a WebSocket that carries commands to the server and snapshots back.
    - After every successful state change, the server sends each connected viewer of that table its own full snapshot, carrying the revision. There is no diff protocol and no public event stream.
    - A rejection goes only to the client that sent the command.
    - Rejoining, for example after a page refresh, means presenting the guest token and receiving the current snapshot.
    - Plain HTTP serves the client and table creation.

14. **Serialization and the server.**
    - Views are serialized to JSON at the server boundary, by explicit serializers from view values.
    - Engine and application objects are never serialized directly.
    - The engine has no serialization.
    - The server is Python ASGI on Starlette and uvicorn. Python 3.14 compatibility is confirmed before the server is implemented.

## Alternatives considered

- **Projection in the application or server layer.** Visibility is a poker rule. Outside the engine it would be a second owner of poker knowledge, and every future client surface would have to repeat it.
- **Projecting the current state from history alone.** Live state is the authority for the present, and legal actions are derived from it. History serves the log and past hands.
- **Deny-list redaction.** A new event type, or a new field, would leak by default.
- **A diff or event-stream protocol.** It adds ordering, gap, and resynchronization problems. Full snapshots of a single table are small, and rejoining becomes trivial.
- **Polling, or server-sent events plus HTTP commands.** Polling adds latency. Server-sent events need two channels. One WebSocket carries both directions.
- **The hand number plus the history length as the stale-command token.** It does not cover joins, leaves, or the table between hands, and it restarts with a fresh engine generation. An application revision covers every visible change.
- **Changing `Player.status` when a leave or sit-out is requested mid-hand.** It changes the meaning of the current hand's state, and it crosses the ADR 0002 §9 caller boundary.
- **Restarting a game in the engine, an engine epoch, or several sequential `HoldemGame` instances on one `Table`.** These broaden the engine lifecycle contract for what is an application concern. A fresh engine generation needs no engine change.
- **An application-held stack ledger.** It would be a second source of truth for chips. The stack is read from the engine only at a generation boundary.
- **Clients computing legality or hand results.** That violates the single authority and invites divergence.
- **Several server processes or a distributed table store.** Premature for a private Alpha. Accounts, persistence, and scaling are post-Alpha milestones.

## Consequences

- **Engine.**
  - It gains a read-only projection and visibility rule, and nothing else.
  - Poker rules, the lifecycle, history, and the existing ADR 0001–0004 contracts are unchanged.
  - `ARCHITECTURE.md` changes as each Cycle lands.
- **ADR 0004 §9** is implemented here and is not modified.
- **ADR 0002 §9.** Its caller preconditions are enforced by `TableSession`, which alone seats players, applies intents, and rebuilds engine generations at hand boundaries.
- **Hand numbers** are scoped to an engine generation. Any later table-wide sequence for logs or persistence is an application or persistence concern.
- **Verification.**
  - The visibility invariant is tested at every layer, relative to each viewer: no card may appear in a viewer payload unless ADR 0004 or this ADR says that card is visible to that specific viewer at that moment. The leak tests enforce this rule per viewer, at every emitted state.
  - Adding the TypeScript client to verification requires dedicated Meta work on the control files before the client Cycle.
- **Later milestones.** These boundaries leave room for later work without building it now:
  - accounts can map onto the guest and `player_id` mapping;
  - persistence can store a `TableSession` and its completed histories;
  - reconnect builds on rejoining by token;
  - mobile clients consume the same snapshot protocol;
  - variants add their own view layer over the variant-agnostic visibility rule.
- **Old milestone numbers in earlier ADRs.** ADRs 0002–0004 keep the numbering from before 2026-11-02:

  | Old number | Now |
  | --- | --- |
  | 7 (bots) | 10 |
  | 8 (Omaha) | 11 |
  | 10 (variant selection) | 13 |
  | 12 (statistics) | 15 |
  | 13 (persistence) | 16; the wire form of player views moved to 7 |
  | 14 (the projection) | 7 |

- **Left to Cycle Briefs and later milestones.** This ADR does not decide:
  - the names of messages, commands, and view fields;
  - the card encoding;
  - endpoint paths;
  - the client library and build tooling (recorded in `ROADMAP.md`);
  - hosting (Milestone 8);
  - the action timer and rebuy/top-up policies (Milestone 9);
  - completed-history logs (Milestone 9);
  - persistence, accounts, and spectator UI.
