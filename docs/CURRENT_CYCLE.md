# Current Cycle

**Milestone 6 — Structured Hand History / Event Log** is in progress. Cycles 1 and 2 are complete; Cycle 3 is next.

Milestone status, approved product decisions, and deferred work live in `ROADMAP.md`. The hand history and event contract is in [ADR 0004](adr/0004-hand-history-and-event-contract.md); its numbered decisions are cited below as ADR 0004 §N. Earlier contracts still apply:

- settlement, in [ADR 0001](adr/0001-showdown-settlement-contract.md);
- the hand lifecycle and orchestration, in [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md);
- the showdown, in [ADR 0003](adr/0003-interactive-showdown-and-muck.md).

Implemented behavior is recorded in `ARCHITECTURE.md` as each Cycle lands.

## Planning Gate

Satisfied. ADR 0004 was accepted on 2026-11-01.

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
| 1 | Derived hand strength | Complete |
| 2 | Identity and `HandHistory` foundation | Complete |
| 3 | Betting and dealing transition events | Next (not started) |
| 4 | Showdown and settlement events, full replay/integration, milestone close | Planned |

Cycles 1 and 2 are independent. Cycle 3 depends on Cycle 2, and Cycle 4 on Cycle 3. Cycle 1 must be complete before the milestone closes.

### Cycle 1 — Derived hand strength (ROADMAP Milestone 6 strength decisions)

Delivered:

- `core/best_hand.py`: `BestHand`;
- `texas_holdem/hand_strength.py`: `holdem_hand_strength`, `hand_strength`, and `SeatNotInHandError` (a `ValueError`) for an unknown seat;
- the private `_best_fives` in `core/evaluator.py`, now under `evaluate_best`, whose contract and results are unchanged.

The Brief-level choices:

- Core returns every maximal combination, and the Hold'em reads apply the tie preference.
- The description formatter is a private function beside `BestHand`.
- Two hole cards are required before the preflop `None`, so an undealt hand raises `InvalidHoleCardCountError`.

The contract is in `ARCHITECTURE.md` ([Hand Strength](ARCHITECTURE.md#hand-strength)). Showdown and settlement logic is unchanged. The seeded `HoldemGame` stress test checks that river strength agrees with every shown seat's settlement rank.

### Cycle 2 — Identity and `HandHistory` foundation (ADR 0004 §2, §5–7, §10)

Delivered:

- `Player`: `player_id` must be a non-empty `str` (`InvalidPlayerIdError`, a `ValueError`) and is read-only after creation. The current-table uniqueness rule is unchanged, and there is no registry.
- `game/hand_history.py`: `HandHistory`, `HandStarted`, `HandParticipant`, the `HandEvent` alias (only `HandStarted` so far), and the private `_appended`, which no operation calls yet.
- `PokerHand(players, deck, number)`: records `HandStarted` at construction; `number` reads the history.
- Lifecycle: `start_game` creates hand 1, `start_next_hand(table, hand_number)` takes the number from its caller, and `HoldemGame.next_hand` passes the current number plus one.

The Brief-level choices:

- `InvalidHandNumberError` (a `ValueError`) rejects a `bool`, a non-integer, or a value below 1, through one private rule in `poker_hand.py`.
- `start_next_hand` checks the number before any other check or change.
- `PokerHand` has an explicit constructor. The other state fields (board, street, burned cards, betting, settlement, showdown) are no longer constructor arguments.

The contract is in `ARCHITECTURE.md` ([Hand History](ARCHITECTURE.md#hand-history)). The seeded `HoldemGame` stress test checks every hand's number and `HandStarted` against independently built values, and re-checks earlier histories for durability.

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

None remain open. Each later Cycle Brief settles its own implementation-level choices within the approved contracts.
