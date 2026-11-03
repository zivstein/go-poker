# Current Cycle

**Milestone 7 — Player view + local table** is in progress. Cycle 1 (player view projection) and Cycle 2 (TableSession Core) are complete. Cycle 3 (Pre-actions + Call Obligation) is next and needs its Brief. Milestone 7 completes after Cycle 3.

Milestone 6 is complete. Its behavior is recorded in `ARCHITECTURE.md` and its history in Git.

Milestone status, the road to the Friends Alpha, and approved product decisions live in `ROADMAP.md` ([Reach a Friends Alpha](ROADMAP.md#reach-a-friends-alpha)).

The boundary contracts for this milestone are:

- [ADR 0005](adr/0005-player-view-and-table-session-boundary.md), cited below as ADR 0005 §N;
- [ADR 0006](adr/0006-shared-table-revision-and-private-intents.md), which partly supersedes ADR 0005 §7, §8 and §13 (shared revision and private intents).

They build on earlier contracts:

- the visibility classes of [ADR 0004](adr/0004-hand-history-and-event-contract.md) §9;
- the caller preconditions of [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md) §9.

## Planning Gate

**Satisfied.**

- ADR 0005 was accepted on 2026-11-02, with the milestone's original scope and decisions.
- On 2026-11-03 the milestone was re-scoped to end after the application layer, the Cycle split was revised, ADR 0006 was accepted, and the Cycle 2 and Cycle 3 decisions were approved.
- No planning-level question remains open.
- Cycles 1 and 2 are complete. Cycle 3 still needs its own approved Brief, based on the decisions below.

## Goal

Turn the engine into a transport-free multiplayer table that several users play together, hand after hand.

- One `TableSession` owns one authoritative `HoldemGame` per private table.
- Each user's view shows only what that user may see.
- Every decision goes through `TableSession` commands; the engine decides legality.
- Hands follow one another without anyone resetting the engine.

In scope:

- the engine's read-only player-view projection and visibility rule, with an allowlist-redacted log of the current hand (ADR 0005 §2–5; Cycle 1, complete);
- the transport-free `TableSession` application layer (ADR 0005 §6–11, ADR 0006):
  - users, seats, the host, and commands;
  - the shared revision and private intents;
  - pending hand-boundary intents and the automatic action of a leaving player;
  - the hand boundary, the waiting state, and the engine-generation reset;
  - betting pre-actions, with the minimal engine read they need;
- viewer-relative leak tests: no card appears in a viewer's view unless ADR 0004 or ADR 0005 says that card is visible to that specific viewer at that moment.

Out of scope:

- HTTP, WebSocket, a JSON protocol, and serialization;
- any server or client code, React, and UI design;
- bearer tokens and the token → `UserId` mapping;
- timers and clocks (the next-hand pause is triggered by the caller);
- accounts, account usernames, authentication, persistence, and any user or account entity (a separate future capability);
- rejoining a table after an explicit Leave, transport reconnect, rebuy, and top-up;
- the remaining Friends Alpha work, which is replanned during Milestone 8 (see `ROADMAP.md`);
- any change to the engine's poker rules or lifecycle contract.

## Cycles

| Step | Title | Surface | Status |
| --- | --- | --- | --- |
| Cycle 1 | Player view projection | Engine: `game/visibility.py`, the Hold'em view layer | Complete; its behavior is in `ARCHITECTURE.md` ([Player View](ARCHITECTURE.md#player-view)) |
| Cycle 2 | TableSession Core | `src/go_poker/app/`, the layering test | Complete; its behavior is in `ARCHITECTURE.md` ([Application Layer](ARCHITECTURE.md#application-layer)) |
| Cycle 3 | Pre-actions + Call Obligation | `game/betting/legal_actions.py` (`call_obligation`), `src/go_poker/app/` | Not started; Brief to be drafted from the decisions below |

Dependencies:

- Cycle 2 depends on Cycle 1.
- Cycle 3 depends on Cycle 2.

Checkpoints:

- **Cycle 1:** per-seat views of the same hand differ exactly as ADR 0004 §9 requires.
- **Milestone 7 (after Cycle 3):** scripted multi-user `TableSession` tests play consecutive hands, including an engine-generation reset and pre-actions, and each user's views hold only what that user may see.

Sizing:

- The application layer was split on 2026-11-03 into Cycle 2 and Cycle 3. Kept whole, it had several independently verifiable surfaces, an engine change alongside the application work, a new stress suite, and an expected diff of about 3k lines over 20+ paths.
- Cycle 2 builds the transition, cascade and private-intent machinery that the leaving player's automatic action already needs. Cycle 3 adds pre-actions to it, together with the only engine change.

## Invariants

- **Viewer-relative visibility.**
  - No card may appear in a viewer's view unless ADR 0004 or ADR 0005 says that card is visible to that specific viewer at that moment.
  - The leak tests enforce it per viewer, at every emitted state.
  - Burned cards and the undealt deck are never visible to any viewer.
  - No view carries a `UserId` (and therefore no `player_id`).
- **One authority.**
  - The engine is the only judge of poker legality.
  - The application layer never re-derives or duplicates poker rules or state. Stacks, participation status, turn, legality, pots and cards are read from the engine.
- **Shared revision (ADR 0006).**
  - `TableSession.revision` is the monotonic revision of shared table state. It increments exactly once per successful shared transition.
  - A rejection, a read, or a change to private intents alone never increments it. It never resets, including across an engine-generation reset.
  - Every view carries the shared revision. Two views for the same viewer at the same revision differ only in that viewer's private intents.
  - Every state-changing command, private ones included, carries `expected_revision`. A mismatch is rejected before anything else is checked and before the engine is called.
  - Reconciliation of private intents caused by a shared transition happens inside that transition, before its views are captured. An automatic poker action is its own shared transition.
  - The hand-boundary step is guarded by the revision, like every other state-changing command.
- **Boundary intents.**
  - A leave or sit-out requested by a participant during a hand never changes the current hand's engine state or that participant's `Player.status`.
  - These intents are private until they are applied at the hand boundary.
- **No engine contract change.**
  - The engine-generation reset happens entirely in the application layer.
  - No engine epoch, table-wide hand sequence, or second authoritative stack is introduced.
  - The only engine addition in this milestone after Cycle 1 is the read-only `call_obligation` (Cycle 3).

## Cycle 2 — TableSession Core

Approved on 2026-11-03. Complete; the implemented behavior is recorded in `ARCHITECTURE.md` ([Application Layer](ARCHITECTURE.md#application-layer)), which is authoritative where it is more precise than this Brief:

- the only pending participation intent is a sit-out, which `sit_back` cancels, because a participant of the hand in progress is always `READY` (so no pending sit-back can arise);
- `DisplayName` rejects every character of Unicode category C (control, format, surrogate, private-use, unassigned), not only control characters;
- on 2026-11-03, before closeout, the identity boundary was narrowed (approved): there is no `User` value, the table-visible name is a `DisplayName` with plain value equality, and table-local collisions compare its `conflict_key`.

**Goal.** A transport-free `TableSession` that runs a private table above `HoldemGame`: users and seats, the host's start, commands with the shared revision and private intents, hand-boundary intents, the automatic next hand when triggered, the waiting state, and the engine-generation reset, with per-user views composed from the Cycle 1 projection.

**Identity.**

- `UserId` is an opaque, non-empty string value. It is the one logical identity: the engine receives `Player.player_id = user_id.value`. The engine's `player_id` and the application's `user_id` are the same identity at two boundaries.
- There is no second application id and no id factory. The caller supplies a `UserId` and a `DisplayName`; minting ids, guest and registered accounts, account usernames, authentication, and mapping tokens to a `UserId` belong to a future Accounts and API capability.
- `TableSession` defines no user or account entity: it owns only the identity facts a table needs, and pairs them itself as a membership.
- Commands are authorized by `UserId`.
- `DisplayName`, the table-visible name: NFC-normalized and trimmed, 1–20 characters, no control characters. It is a table display policy only. No two current members of a table may have names that differ only by case or normalization (`DISPLAY_NAME_TAKEN`).

**Ownership.**

- `TableSession` owns the table id and code (supplied by the caller), `TableSettings` (stakes, buy-in as a positive integer, max seats), the host, the members, the pending intents, the departed users, the revision, and its current engine generation: one `Table` and one `HoldemGame`, never handed to callers.
- A member is a user who owns a seat. Joining means joining and sitting, as an engine `WAITING` player with the buy-in.
- The phase is derived: `NOT_STARTED`, `HAND_IN_PROGRESS`, `HAND_COMPLETE`, and `WAITING_FOR_PLAYERS` (the only stored flag, set when a boundary or resume attempt cannot start a hand).
- The host's start command starts the first hand. After that the table continues on its own, including after a reset.

**Commands and results.**

- `TableSession.create(...)` seats the host and starts at revision 1. The button chooser is injected.
- User commands take `(user_id, expected_revision, ...)`: `join`, `leave`, `sit_out`, `sit_back`, `start_game` (host only), and `act` with an `Action` or a `ShowdownAction`, passed to the engine unchanged.
- The system command `advance_hand(expected_revision)` performs the hand boundary. It is accepted only in `HAND_COMPLETE`.
- Queries never change anything: `revision`, `phase`, `view_for(user_id)`, `is_member(user_id)`.
- Results are values: `Accepted(transitions, view)` or `Rejected(code, message)`. Each `Transition` carries its revision, its cause, and every member's full view captured at that moment. `view` is the requester's view after the command; it is `None` for `advance_hand` and when the requester has just left. A private-only command returns no transitions.
- Check order: the revision, membership, the host, application state, then the engine call as the last fallible step. Application state changes only after the engine call succeeds. A rejection changes nothing. Engine errors map to rejection codes through one explicit function; an unmapped exception is a defect and propagates.

**Leave, sit-out and sit-back.**

- With no hand in progress (including `HAND_COMPLETE`), or for a seated user who is not a participant of the current hand, the request applies at once and is a shared transition: leave stands the user up; sit-out sets `SITTING_OUT`; sit-back sets `WAITING`, so the user re-enters through the engine's existing waiting rule.
- For a participant of the hand in progress, the request is a private pending intent. A pending sit-out or sit-back can be cancelled by the opposite request; a pending leave has no cancel.
- When a betting action is required of a user with a pending leave, the application submits `CHECK` if legal, otherwise `FOLD`; at a showdown decision it submits `MUCK`. This includes the moment of the request when it is that user's turn. Each such action is its own shared transition.
- An explicit Leave removes the user from the session. A user who has left cannot join the same `TableSession` again (`LEFT_TABLE`). Their display name becomes free.
- When the host leaves, the earliest-joined remaining member becomes host. On an empty table, the next user to join becomes host.
- Repeating a request that is already in effect is rejected with `NO_CHANGE`.

**Hand boundary and waiting.** One shared transition, in this order:

1. apply pending leaves;
2. apply pending sit-outs and sit-backs;
3. resume: `next_hand()`, or `start(...)` for a fresh generation that has not started; the engine decides who can play.
   - `InvalidPlayerCount`: the table waits (`WAITING_FOR_PLAYERS`).
   - `GameNotStartedError`: the engine-generation reset.

While waiting, every accepted join, sit-back or leave is followed, in the same command, by a resume attempt; a hand that starts is its own shared transition. A failed attempt changes nothing.

**Engine-generation reset (ADR 0005 §11).** Build a fresh `Table` and, for each member in the same seat, a `Player` with the same `player_id` (the `UserId`), their stack in the old engine, and status `SITTING_OUT` if they were sitting out, otherwise `WAITING`. Build a fresh `HoldemGame`, swap both in only once everything is built, then try to start. The table id and code, members, seats, display names, host and revision persist; hand numbers restart.

**Views.** `TableView` holds the revision, the table id and code, the settings, the phase, each seat's display name and host flag, the Cycle 1 `HoldemView` for the viewer's own seat, and the viewer's own pending intents. Pending intents are private to their owner. No view carries a `UserId`.

**Tests.**

- Focused command tests over every command and phase. Every rejection is checked for an unchanged revision and unchanged views.
- Revision tests: one increment per shared transition, consecutive revisions across a cascade, none for private intents, reads or rejections, stale commands rejected before the engine, and continuity across a reset.
- Scenarios on stacked decks, using the `Deck` shuffle seam through a local `tests/app/conftest.py`: consecutive hands, a leave mid-hand with an automatic check, fold or muck, a pending sit-out, waiting and resuming, a reset when every `READY` player sits out or leaves, host change, a rejected rejoin, and display-name collisions.
- An application leak test at every emitted transition: each member's game view equals the Cycle 1 projection for their own seat, its cards are only their own, the board, and shown cards, and no `UserId` appears.
- A layering test: `game` never imports `app`, and `app` never imports `server`.

**Expected files.** `src/go_poker/app/` (`__init__.py`, `identity.py`, `session.py`, `views.py`, `results.py`; the Engineer may split out a boundary module), `tests/app/`, `tests/test_layering.py`, and a new Application Layer section in `ARCHITECTURE.md`. About 13–15 paths and 1.8–2.3k lines.

**Roles.**

- Engineer: the production code, focused tests, and the `ARCHITECTURE.md` section.
- QA: attacks rejection atomicity across every command and phase, stale commands after cascades and at the boundary, boundary order, reset correctness, the leaving player's automatic actions in betting and at showdown, display-name edge cases, and a seeded multi-user session stress test with leak checks.
- Reviewer: conformance with ADR 0005 and ADR 0006, no poker rule or state re-derived in `app/`, the engine untouched, no `UserId` in any view, the dependency direction, and rejections as values while defects propagate.

## Cycle 3 — Pre-actions + Call Obligation

Approved decisions on 2026-11-03; its Brief is drafted after Cycle 2.

- **Engine read.** `call_obligation(hand, seat) -> CallObligation | None` in `game/betting/legal_actions.py`, with `amount_owed`, `call_amount` and `call_is_all_in`. It is `None` when no betting round is open, or when the seat is not a participant, has folded, or is all-in. It is read-only and unguarded, raises `BettingNotInitializedError` like `legal_actions`, and shares one calculation with `legal_actions`; for the current actor, the two agree.
- **Pre-actions** are private intents that exist only while it is not the player's turn: while a hand is in progress, a betting round is open, the user is that seat's own participant and not the current actor, `call_obligation` is not `None`, and no leave is pending.

  | Amount owed | Offered |
  | --- | --- |
  | 0 | `CHECK`, `CHECK_OR_FOLD` |
  | > 0 | `FOLD`, `CALL_CURRENT(amount_owed)` |

  - A selection's effective presentation is the kind itself, except that a `CHECK_OR_FOLD` selected while check was available presents as selected `FOLD` once chips are owed; its stored intent stays `CHECK_OR_FOLD`.
  - In each shared transition, a selection survives only while its effective presentation is still offered (`CALL_CURRENT` with the same amount). So `CHECK` clears when check becomes unavailable, `CALL_CURRENT` clears when the amount owed changes, and `CHECK_OR_FOLD` survives betting pressure.
  - Every selection clears when the betting round or street ends, the hand settles, the seat can no longer act, or the user requests a leave.
  - When the turn arrives, the selection is consumed in that transition, and its action is the next shared transition: `CHECK` checks if it can, otherwise it is dropped; `CHECK_OR_FOLD` checks if it can, otherwise folds; `FOLD` folds; `CALL_CURRENT(b)` calls if call is legal and the amount owed is still `b`, otherwise it is dropped. A dropped selection leaves the player their full `legal_actions`.
  - Only an offered option can be selected (`PRE_ACTION_UNAVAILABLE`). Selecting what is already the effective presentation is `NO_CHANGE`. There is no `CALL_ANY`.

## Brief-Level Choices

Each Cycle Brief settles its own implementation-level choices within ADR 0005, ADR 0006, and the approved decisions in `ROADMAP.md`.

Cycle 1 settled its choices in its Brief, approved on 2026-11-02. The implemented result is recorded in `ARCHITECTURE.md` ([Player View](ARCHITECTURE.md#player-view)).

Cycle 2's choices are recorded above; the implemented result is in `ARCHITECTURE.md` ([Application Layer](ARCHITECTURE.md#application-layer)).
