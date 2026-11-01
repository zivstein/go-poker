# 0004: Hand history and event contract

Status: Accepted (2026-11-01)

## Context

Milestones 0–5 deliver a complete continuous No-Limit Hold'em engine. A hand's live state is enough to play it but not to record it:

- the action sequence is lost, and per-action amounts are lost when rounds are collected;
- uncalled returns are folded into contributions;
- all-in exists only as current state, and both a returned excess and payout clear it;
- starting stacks are lost once the next hand begins;
- state cannot tell whether an all-in showdown started before the runout, or which streets were runout streets;
- hands have no identity, and nothing makes `Player.player_id` stable.

[ADR 0002](0002-hand-lifecycle-orchestration-contract.md) §7 records that a settled `PokerHand` is not a durable historical snapshot: its `HandPlayerState`s reference shared `Player` objects whose stacks and statuses change in later hands. ADR 0001, ADR 0002 and [ADR 0003](0003-interactive-showdown-and-muck.md) leave Milestone 6 to record events in order. Those events include the showdown start, each SHOW/MUCK decision, the runout, and facts current state loses, such as who was all-in.

The hand history is a durable contract. Milestone 7 bots and simulation, Milestone 12 statistics, Milestone 13 persistence, the Milestone 14 API projection, and clients all build on it. A future serialized or stored history must mean the same thing as an in-memory one.

## Decision

1. **Recording ownership.**
   - Each public low-level mutation operation records its own transition events in the same call:
     - `PokerHand` construction;
     - `initialize_betting` and `deal_hole_cards`;
     - `deal_next_street` and `start_betting_round`;
     - `apply_action`;
     - `start_showdown`, `apply_showdown_action` and `settle_hand`.
   - `hand_flow` and `HoldemGame` record nothing themselves. Orchestrated play produces exactly the events of the low-level calls it makes.
   - Internal helpers record nothing. When an operation's helper changes chips, as `collect_round` does when it returns an uncalled excess, the helper reports it to that operation, which records it.

2. **The record.**
   - `PokerHand.history` is an immutable, append-only `HandHistory` value. Recording replaces it with a new value holding one more event. A `HandHistory` taken at any moment never changes.
   - It is a record, not event sourcing. `PokerHand` state remains the only input to rules, and no rule reads history. History duplicates facts that state also holds; the low-level operations are its single writer, which keeps the two consistent.
   - The contract uses value equality only:
     - every event field is an immutable value type with value equality (frozen dataclasses, tuples, frozensets, enums, ints, strs), never a list, dict, `Player`, `HandPlayerState`, or other live object;
     - every history, replay and durability invariant is stated with `==`;
     - Python object identity (`is`) is never part of the contract. Sharing an instance in memory, for example the same `Settlement` object, promises nothing.
   - The invariants must hold for any equal copy, including a future deserialized one.

3. **Event catalog and granularity.**
   - There is one event type per meaningful transition. There is none per chip movement, and not one per public call.
   - Events are a closed union of frozen dataclasses in the variant-agnostic `game/hand_history.py`. There are no base classes, protocols, or registries.
   - Events carry resolved facts, including the cards dealt and the chips actually committed.

   | Event | Recorded by | Facts |
   | --- | --- | --- |
   | `HandStarted` | `PokerHand` construction | the hand `number`; `participants`, a tuple of `HandParticipant(seat, player_id, position, blind, starting_stack)` in hand order, button first |
   | `BlindsPosted` | `initialize_betting` | `stakes`; `posts`, a tuple of `BlindPost(seat, blind, chips, all_in)`, where `chips` is the amount actually posted |
   | `HoleCardsDealt` | `deal_hole_cards` | each seat's hole cards in hand order |
   | `StreetDealt` | `deal_next_street` | `street`, the `burned` cards, the `cards` dealt |
   | `BettingRoundStarted` | `start_betting_round` | `street` |
   | `ActionTaken` | `apply_action` | `seat`, `action`, the `chips` this action committed (the resolved call amount included), `all_in` |
   | `ChipsReturned` | the operation that completes a betting round | `seat`, the uncalled `chips` returned |
   | `BettingRoundCompleted` | the operation that completes a betting round | `street` |
   | `ShowdownStarted` | `start_showdown`, or `settle_hand` when it records an `ALL_IN` showdown | `kind`, `order` |
   | `ShowdownDecided` | `apply_showdown_action` | `seat`, `action` |
   | `HandSettled` | `settle_hand` | `settlement`, equal to `hand.settlement` |

   - **Why stakes are in `BlindsPosted`.** A hand captures its stakes when betting is initialized, so `BlindsPosted` holds them rather than `HandStarted`.
   - **Showdown order.** For an `ALL_IN` showdown, `ShowdownStarted.order` is storage order, not a sequence (ADR 0003 §5).
   - **History and the showdown record.** The showdown record holds seats and decisions, not cards. History is not the showdown record and does hold cards, including mucked and unshown ones.
   - **Adding events later.** Later event types, such as a voluntary show or reveal, can be added without changing the rules below.

4. **Ordering, and what each history guarantees.**
   - **Within one operation:**
     - `ActionTaken`, then any `ChipsReturned`, then any `BettingRoundCompleted`;
     - when the blinds alone complete the round, `BlindsPosted`, then any `ChipsReturned`, then any `BettingRoundCompleted`;
     - a direct contested `ALL_IN` settlement records `ShowdownStarted`, then `HandSettled`, only after every rejectable check.
   - **Across operations,** events follow the order of the successful calls. An event's index in the history is its sequence number.
   - **Rejections and reads.** A rejected operation records nothing, so the history stays equal to its previous value. Derived reads record nothing.
   - **Bookends.** Exactly one `HandStarted`, always first. At most one `HandSettled`, always last.
   - **Every history,** at either usage level, guarantees two things:
     - It is a faithful record of the transitions the engine actually performed, in the order performed.
     - Its poker and game facts are reconstructable from it alone. Those facts are:
       - participants and starting stacks;
       - hole cards; board and burned cards by street;
       - every action and its chips;
       - uncalled returns, contributions, and folds;
       - all-in state;
       - the showdown kind, order, and decisions;
       - the settlement and final stacks.

     "Reconstructable" means these facts. It does not mean rebuilding a live `PokerHand` or its deck order, and it never means an inferred presentation classification.
   - **Orchestrated histories only.** Histories produced entirely through `hand_flow` (`begin_hand` / `act`) or `HoldemGame` also guarantee presentation order:
     - when showdown becomes certain before the board is complete, `ShowdownStarted(ALL_IN)` precedes every remaining `StreetDealt`, and those runout streets have no `BettingRoundStarted`;
     - an `INTERACTIVE` `ShowdownStarted` follows `BettingRoundCompleted(RIVER)`, with one `ShowdownDecided` per decision;
     - `HandSettled` is last.

     A consumer of an orchestrated history may treat each `StreetDealt` after `ShowdownStarted` as a runout street. The guarantee comes from orchestration's call order, not from event data.
   - **Raw low-level histories** record exactly the calls the caller made, and are not normalized.
     - Example: a caller that deals the remaining streets and then calls `settle_hand` directly produces `StreetDealt…`, then `ShowdownStarted(ALL_IN)`, then `HandSettled`.
     - That history is factually complete. It makes no runout or presentation claim, and consumers must not infer one from it.
   - **Mixed usage.** Mixing the two usage levels within one hand stays unsupported (ADR 0002 §1). History records faithfully whatever operations ran, but gives no guarantee beyond that.
   - **No markers.** There is no runout flag, provenance marker, timestamp, clock, or pacing field. Dealing never reads or owns showdown state. Pacing a runout for display is a presentation concern served by the order of an orchestrated history; the engine still advances instantly.

5. **Hand identity.**
   - **The number.** Every hand has a positive integer `number`, recorded in `HandStarted`. `PokerHand(players, deck, number)` rejects a number that is not a positive integer.
   - **Lifecycle.** `start_game` creates hand 1. `start_next_hand(table, hand_number)` takes the number from its caller; the lifecycle stores no counter.
   - **`HoldemGame`.** It passes the current hand's number plus one, so its hands are numbered 1, 2, 3, … consecutively. A rejected `next_hand` consumes no number.
   - **Scope.** Numbers are scoped to one `HoldemGame`. UUIDs and global hand, table, or session identifiers belong to the platform milestones.

6. **Participant identity.**
   - **Meaning.** `Player.player_id` is the stable logical identity of an engine participant: an opaque, caller-assigned string. The same `player_id` in different hand histories means the same logical participant.
   - **The caller's duty.** A caller must not reuse an existing `player_id` for a different logical participant in histories that are intended to be linked.
   - **What the engine enforces.** A `player_id` is:
     - non-empty when the `Player` is created;
     - immutable after creation;
     - unique among the players currently seated at a table (the existing seating rule).
   - **What it does not enforce.** Milestone 6 adds no registry or historical-identifier tracking to `Table` or `HoldemGame`. Keeping identity consistent beyond the current table is the responsibility of the caller, and later of the platform and session layer, once it exists.
   - **What it is not.** It is not a display name, account identity, or platform identity; the platform maps those to it later.
   - **In history.** Within a hand, events identify participants by seat. `HandStarted` records each seat's `player_id` by value, so a history says who held each seat, and histories that share a `player_id` refer to the same participant.

7. **Snapshot.**
   - The durable snapshot of a hand is its `HandHistory` value. There is no separate snapshot type.
   - A history is complete when its last event is `HandSettled`. Before that, it is the live record of a hand in progress.
   - `HoldemGame` does not retain past histories. Its current `hand.history` is readable at any time, and a caller who wants past hands keeps the values.

8. **All-in in history.**
   - `BlindPost` and `ActionTaken` record whether the commitment left the player all-in. `ChipsReturned` always ends all-in.
   - "All-in at showdown" is a seat's last such state before `HandSettled`.
   - No per-seat summary is stored.

9. **Visibility.** History is authoritative and complete, hidden data included. Milestone 6 builds no projection or redaction; Milestone 14 builds it over the history and derived hand strength.

   | Class | Facts |
   | --- | --- |
   | Authoritative (engine and history) | everything in the history, plus the live deck order |
   | Public to the table | participants; blinds; every action with its chips and all-in flag; returns; round completions; board cards by street; the showdown kind and order; SHOW/MUCK decisions; the settlement |
   | Public once shown | the hole cards, and derived strength, of every live seat in an `ALL_IN` showdown and of every SHOW in an `INTERACTIVE` one |
   | Private to the owning seat | that seat's own hole cards and derived strength, always visible to that seat |
   | Never public to other seats | folded, mucked, and otherwise unshown hole cards (for example a last contender who wins without showing), until a future voluntary-reveal feature exists |
   | Never exposed to any client | burned cards and the undealt deck order |

10. **Representation.**
    - `HandHistory` holds only `events`. `HandStarted` is always `events[0]` and is the single source of the hand number and participants. `HandHistory.number` and `HandHistory.participants` read it, and `PokerHand.number` reads the history.
    - `HandHistory.settlement` and `is_complete` are derived from the last event.
    - Like `Showdown`, `HandHistory` does not validate on construction. Engine-produced histories are well-formed, and validating external records belongs to a future boundary.
    - Other query helpers are later work (Milestone 12).

## Alternatives considered

- **Event sourcing:** state would become a projection of events and every rule would be rewritten, for no product need. A record beside the existing state is enough.
- **Recording in `hand_flow` or `HoldemGame`:** low-level usage would produce no history, and orchestration would duplicate knowledge of what each operation did.
- **Normalizing low-level histories into the orchestrated order:** the history would no longer be a faithful record of what happened.
- **A runout flag or provenance marker on events or the history:** dealing would need to know showdown state, and the flag would duplicate what orchestrated order already tells the consumer, who knows its own usage level.
- **An end-of-hand snapshot type:** a second record that can disagree with the events.
- **Deriving history from state at settlement:** impossible, because the sequence and per-action amounts are already lost.
- **A separate header beside `HandStarted`:** two sources of the hand number and participants.
- **Object identity in the contract:** cannot survive copying, serialization, or storage.
- **UUIDs or global identifiers for hands:** randomness and an identity concept the platform will own; game-scoped numbers are deterministic and sufficient.
- **Recording seats only, with no participant identity:** a history could not say who played once seats are re-occupied, and hands could not be linked.
- **An engine-generated participant identifier:** adds randomness and an identity concept the platform will own; the existing `player_id` serves once it is stable.
- **Timestamps or pacing fields:** a clock in the engine and presentation data in the domain; order alone serves pacing.
- **One event per chip movement:** noise; resolved per-transition facts are enough to reconstruct every amount.
- **Retaining past histories in `HoldemGame`:** an unbounded collection and a storage concern ahead of the persistence milestone.
- **Validating a `HandHistory` on construction:** engine-produced histories are well-formed by construction; validating external records belongs to the boundary that receives them.

## Consequences

- **Lifecycle.**
  - `PokerHand` construction requires a hand number.
  - `start_next_hand` takes `hand_number`.
  - Test helpers that build hands or start hands are updated.
- **`Player`.** It rejects an empty `player_id`, and `player_id` can no longer be reassigned. Tests may keep name-like ids as opaque strings, but documentation must not present them as names.
- **Betting.** `collect_round` reports the excess it returns so its caller can record it.
- **Settled hands.** A settled `PokerHand` is still not a durable snapshot (ADR 0002 §7); its `HandHistory` is.
- **Consumers.** Consumers that pace or classify a runout for display must use orchestrated histories. Raw low-level histories remain valid factual records.
- **Later milestones.**
  - Milestone 7 bots and simulation can check every simulated hand by replaying its history's facts.
  - Milestone 12 statistics, Milestone 13 persistence, and the Milestone 14 projection build over `HandHistory`, relying on value equality rather than object identity.
- **Durability tests.** They compare a history with an independent equal copy, never with object identity.
- **Derived hand strength.** It is never stored in the history.
- **Later features.** Later event types (voluntary show and reveal, timeouts, table events) extend the catalog without changing recording ownership, ordering, or equality.
