# Current Cycle

**Milestone 6 — Structured Hand History / Event Log** is planned. Cycle 1 is next; no Cycle has started.

Milestone status, approved product decisions, and deferred work live in `ROADMAP.md`. The hand history and event contract is in [ADR 0004](adr/0004-hand-history-and-event-contract.md); its numbered decisions are cited below as ADR 0004 §N. Earlier contracts still apply:

- settlement, in [ADR 0001](adr/0001-showdown-settlement-contract.md);
- the hand lifecycle and orchestration, in [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md);
- the showdown, in [ADR 0003](adr/0003-interactive-showdown-and-muck.md).

Implemented behavior is recorded in `ARCHITECTURE.md` as each Cycle lands.

## Planning Gate

Satisfied. ADR 0004 was accepted on 2026-11-01, and Cycle 1 is ready to begin with its Cycle Brief.

No milestone-level product or architecture decisions remain open.

## Goal

For every hand, the engine produces:

- an immutable, append-only hand history, recorded by the low-level operations as each transition happens. It is a record, not event sourcing, and rules never read it.
- a hand number, consecutive and scoped to a `HoldemGame`;
- a stable logical participant identity, `Player.player_id`: the same `player_id` in different histories means the same participant. Keeping it consistent beyond the currently seated table is the caller's responsibility (ADR 0004 §6);
- derived current hand strength for a seat: none preflop, then the `HandRank`, the exact best five cards, and a description. It is never stored.

Every history reconstructs the hand's poker and game facts. Only orchestrated histories guarantee presentation and runout order.

Out of scope:

- the items deferred in `ROADMAP.md`;
- database, HTTP API, UI, and bots;
- Omaha and variant abstraction;
- tournaments, blind levels, antes, and straddles;
- reconnect and timeouts;
- rake and run it twice.

Tests drive hands through public operations, using the existing `stacked_hand` fixture and the `shuffle_decks_with` monkeypatch pattern (no new production test seam).

## Cycles

| Cycle | Title | Status |
| --- | --- | --- |
| 1 | Derived hand strength | Next (not started) |
| 2 | Identity and `HandHistory` foundation | Planned |
| 3 | Betting and dealing transition events | Planned |
| 4 | Showdown and settlement events, full replay/integration, milestone close | Planned |

Cycles 1 and 2 are independent. Cycle 3 depends on Cycle 2, and Cycle 4 on Cycle 3. Cycle 1 must be complete before the milestone closes.

### Cycle 1 — Derived hand strength (ROADMAP Milestone 6 strength decisions)

- **Public:**
  - `BestHand` (the `HandRank`, the five cards, and the derived description);
  - `holdem_hand_strength(hole_cards, board)`, which returns `None` preflop;
  - `hand_strength(hand, seat)`.
- **Unchanged:** `evaluate_best` keeps its contract and results. Strength and `evaluate_best` share one internal evaluation path, so ranks never disagree.
- **Exact best five.** Among equal-rank combinations, prefer the one using the fewest hole cards. Then prefer deal order: board cards in deal order, then hole cards in deal order. When the board plays, return the board.
  - The selection mechanism is internal. There is no public `prefer=` or tie-selection API.
  - The Cycle 1 Brief settles the helper's shape, and whether the description formatter is a separate function.
- **Five-card order** follows significance, consistent with the tiebreakers. The wheel is 5-4-3-2-A.
- **Descriptions** for every category, worded as in `ROADMAP.md`.
- **Inputs.** Requires exactly two hole cards and a board of 0, 3, 4, or 5 cards.
- **`hand_strength`:**
  - works for any participant holding cards, including folded, mucked, and settled seats;
  - rejects an unknown seat (the Brief names the error);
  - never mutates and never stores anything.
- **Tests:**
  - `None` exactly preflop; 5-, 6-, and 7-card evaluation;
  - the equal-rank edge cases: board straight, board two pair, a hole card strictly better, two equal hole cards, equal board cards, swaps in both directions;
  - five-card order and the description for every category, including the wheel and the royal flush;
  - on a complete board, the rank equals every shown seat's settlement rank;
  - no mutation;
  - existing evaluator tests unchanged.
- **`ARCHITECTURE.md`:** a hand-strength section.

### Cycle 2 — Identity and `HandHistory` foundation (ADR 0004 §2, §5–7, §10)

- **`Player`:** `player_id` becomes read-only after creation, and an empty `player_id` is rejected. Uniqueness stays the existing rule for currently seated players. `Table` and `HoldemGame` gain no registry or historical-identifier tracking.
- **`game/hand_history.py`:**
  - `HandHistory`, which holds only `events`;
  - `HandParticipant` and `HandStarted`;
  - derived `number` and `participants`;
  - the engine-internal recording helper.
- **`PokerHand`:**
  - `PokerHand(players, deck, number)` rejects a number that is not a positive integer;
  - it records `HandStarted` at construction;
  - `history` is not a constructor argument, and `number` reads the history.
- **Lifecycle:**
  - `start_game` creates hand 1;
  - `start_next_hand(table, hand_number)`;
  - `HoldemGame.next_hand` passes the current number plus one, stores no counter, and keeps no past histories.
- **Migration:** update the test helpers that construct hands or start hands.
- **Tests:**
  - an empty or reassigned `player_id`;
  - invalid hand numbers;
  - `HandStarted` is `events[0]`, with participants and starting stacks;
  - `HoldemGame` numbers 1..n consecutively, and a rejected `next_hand` consumes no number;
  - durability by value: hand 1's history still equals an independent copy after hand 2 changes the same `Player` objects.
- **`ARCHITECTURE.md`:** participant identity, hand numbering, `HandHistory`, and `PokerHand` ownership.

### Cycle 3 — Betting and dealing transition events (ADR 0004 §1, §3–4, §8)

- **Events:** `BlindsPosted` (with `BlindPost`), `HoleCardsDealt`, `StreetDealt`, `BettingRoundStarted`, `ActionTaken`, `ChipsReturned`, and `BettingRoundCompleted`, each recorded by its operation.
- **Betting:** `collect_round` reports the excess it returns to the operation that records it.
- **Ordering within an operation** follows ADR 0004 §4.
- **Atomicity:** a rejected operation leaves the history equal to its previous value. Derived reads record nothing.
- **Tests:**
  - each event's facts, including short blinds, short calls, all-in commitments, and uncalled returns;
  - the blinds alone completing preflop;
  - a test-local partial fact-replay fold over the board, burns, hole cards, contributions, folds, and pre-payout all-in, through both low-level calls and `hand_flow`.
- **`ARCHITECTURE.md`:** recorded events and their owners.

### Cycle 4 — Showdown and settlement events, full replay/integration, milestone close (ADR 0004 §1, §3–4, §7, §10)

- **Events:** `ShowdownStarted`, `ShowdownDecided`, and `HandSettled`, including the direct contested `ALL_IN` settlement, which records `ShowdownStarted` then `HandSettled` only after every rejectable check.
- **Reads:** `HandHistory.settlement` and `is_complete`, derived from the last event.
- **Tests:**
  - a full fact-replay fold on every history: showdown, settlement, final stacks as starting − committed + returned + payout, and chip conservation;
  - the runout and ordering invariants, asserted only on orchestrated histories;
  - a low-level test that records the direct-settle order faithfully, with no presentation assertion;
  - durability across hands;
  - seeded `HoldemGame` stress asserting replay for every hand.
- **Close out:**
  - `ARCHITECTURE.md`: the history contract, invariants, and `PokerHand` described as owning its history;
  - README capabilities;
  - `ROADMAP.md` status.

A history is deliberately incomplete between Cycles 3 and 4: it has no showdown or settlement events yet. `is_complete` arrives with `HandSettled`, so it is never wrong in between.

## Invariants

All of these use value equality, never object identity (ADR 0004 §2).

- **Bookends.** `events[0]` is the only `HandStarted`. `HandSettled` appears at most once and only last.
- **Appends.** A successful operation appends exactly its events. A rejection appends nothing.
- **Facts.** Every history's facts fold to values equal to the live hand's (ADR 0004 §4).
- **Presentation order.** It is guaranteed only for histories produced through `hand_flow` / `HoldemGame`. Raw low-level histories are faithful, not normalized.
- **History content.** No timestamps, pacing fields, runout flag, or provenance marker. Derived hand strength never appears in history or state.

## Brief-Level Choices

Each Cycle Brief settles these within the approved contracts:

- the error type for an unknown seat in `hand_strength`;
- the name of the invalid hand number error;
- the shape of the internal tie-selection helper;
- whether the description formatter is a separate function.
