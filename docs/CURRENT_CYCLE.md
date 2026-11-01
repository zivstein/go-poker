# Current Cycle

**Milestone 6 — Structured Hand History / Event Log** is complete. All four Cycles are complete. The next milestone (Milestone 7) has not been planned yet.

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
| 3 | Betting and dealing transition events | Complete |
| 4 | Showdown and settlement events, full replay/integration, milestone close | Complete |

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

Delivered:

- `game/hand_history.py`: `BlindsPosted` (with `BlindPost`), `HoleCardsDealt` (with `SeatHoleCards`), `StreetDealt`, `BettingRoundStarted`, `ActionTaken`, `ChipsReturned`, and `BettingRoundCompleted`, all in the closed `HandEvent` union.
- Recording: `initialize_betting`, `deal_hole_cards`, `deal_next_street`, `start_betting_round`, and `apply_action` each record their own events in the same call, after every mutation. `hand_flow`, `HoldemGame`, helpers, and derived reads record nothing.
- `collect_round` returns the excess it returned as `(seat, chips)`, or `None`, and imports no history; the calling operation records `ChipsReturned`.

The Brief-level choices:

- Hole cards are a tuple of `SeatHoleCards(seat, cards)` in hand order, since Python 3.14 has no immutable mapping.
- `BlindsPosted` marks the preflop round start; there is no `BettingRoundStarted(PREFLOP)`.
- `HandHistory.number` and `participants` read `events[0]` through a private narrowing that raises `TypeError` when it is not a `HandStarted`.
- A round that `start_betting_round` starts already complete records `BettingRoundStarted` then `BettingRoundCompleted` for the same street (user-approved resolution of the Brief's open issue).

The contract is in `ARCHITECTURE.md` ([Hand History](ARCHITECTURE.md#hand-history)). A test-local `replay_facts` fold (`tests/game/conftest.py`) reconstructs the pre-payout facts and is checked against the live hand after every step of the betting suites and the `hand_flow` and `HoldemGame` stress tests; a seeded event-grammar stress walks 400 orchestrated hands. Cycle 4 extends the replay with showdown, settlement, and payout.

### Cycle 4 — Showdown and settlement events, full replay/integration, milestone close (ADR 0004 §1, §3–4, §7, §10)

Delivered:

- `game/hand_history.py`: `ShowdownStarted(kind, order)`, `ShowdownDecided(seat, action)` and `HandSettled(settlement)`, completing the closed `HandEvent` union; `HandHistory.is_complete` and `HandHistory.settlement`, derived from the last event.
- Recording: `start_showdown` records `ShowdownStarted` for both kinds, `apply_showdown_action` one `ShowdownDecided` per decision, and `settle_hand` `HandSettled` once, last. A direct contested `ALL_IN` settlement records `ShowdownStarted` then `HandSettled` in one assignment after the settlement succeeds. `hand_flow`, `HoldemGame`, helpers, and derived reads still record nothing, and no rule reads history.

The Brief-level choices:

- `Settlement` is imported under `TYPE_CHECKING` in `hand_history.py`, avoiding the runtime cycle through `poker_hand.py`.
- `_settle` returns the `Settlement` it stores, and still records nothing.
- `HandHistory.settlement` is `None` while the history is incomplete.
- The decision field is `ShowdownDecided.action`.

The contract is in `ARCHITECTURE.md` ([Hand History](ARCHITECTURE.md#hand-history)).

Tests:

- The test-local replay (`tests/game/conftest.py`) folds every history to its full facts, final stacks and settlement included. It checks the pot layering and awards independently, and runs after every step of the betting, `hand_flow`, and `HoldemGame` suites.
- `assert_orchestrated_order` checks the kind-specific presentation order on orchestrated histories only. Low-level tests check the faithful direct-settle order, which is not normalized.
- The seeded `HoldemGame` stress retains every completed history and re-folds each one after later hands that reuse the same `Player` objects.

## Invariants

All of these use value equality, never object identity (ADR 0004 §2).

- **Bookends.** `events[0]` is the only `HandStarted`. `HandSettled` appears at most once and only last.
- **Appends.** A successful operation appends exactly its events. A rejection appends nothing.
- **Facts.** Every history's facts fold to values equal to the live hand's (ADR 0004 §4).
- **Presentation order.** It is guaranteed only for histories produced through `hand_flow` / `HoldemGame`. Raw low-level histories are faithful, not normalized.
- **History content.** No timestamps, pacing fields, runout flag, or provenance marker. Derived hand strength never appears in history or state.

## Brief-Level Choices

None remain open. Each later Cycle Brief settles its own implementation-level choices within the approved contracts.
