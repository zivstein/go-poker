# Current Cycle

**Milestone 5 — Complete continuous PokerHand/game loop** is in progress. Cycles 1 and 2 are complete; Cycle 3 is next.

Milestone status, approved product decisions, and deferred work live in `ROADMAP.md`. The hand lifecycle and orchestration contract lives in [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md); its numbered decisions are cited below as ADR 0002 §N. Implemented behavior is recorded in `ARCHITECTURE.md` as each Cycle lands.

## Goal

Run a No-Limit Texas Hold'em hand from creation to settlement, then the next hand, with player decisions as the only external inputs:

- every public hand-level mutation entry point rejects a settled hand;
- live hands are revealed once showdown is certain: an all-in reveal, or, when the river betting round completes with no live all-in player, a river showdown in show order;
- `begin_hand` / `act` advance a hand automatically until a decision is required or it is settled;
- `HoldemGame` owns the table, stakes, and current hand, and starts the next hand only after settlement.

Out of scope: the items deferred in `ROADMAP.md`.

Tests drive whole hands through public operations, using the existing `stacked_hand` fixture and the `shuffle_decks_with` monkeypatch pattern (no new production test seam).

## Cycles

| Cycle | Title | Status |
| --- | --- | --- |
| 1 | Post-settlement boundary | Complete |
| 2 | Reveal and show order | Complete |
| 3 | Single-hand orchestration | Next (not started) |
| 4 | Continuous game loop and milestone close | Planned |

Cycles 1 and 2 are independent. Cycle 3 depends on both; Cycle 4 depends on Cycle 3.

### Cycle 1 — Post-settlement boundary (ADR 0002 §7)

- Move the settled check and `HandAlreadySettledError` to `game/poker_hand.py`; `settlement.py` keeps exporting the error.
- Guard `initialize_betting`, `deal_hole_cards`, `deal_next_street`, `start_betting_round`, `apply_action`, and `settle_hand`; the check runs before any other validation. Internal helpers get no guard. `reveal_hands`, `begin_hand`, and `act` get the same guard in the Cycles that add them.
- Tests: each entry point rejects a settled hand and leaves it unchanged; the settled check wins over each entry point's other errors; existing import path still works.

### Cycle 2 — Reveal and show order (ADR 0002 §4–6, §8 direct settlement)

- `game/reveal.py`: `Reveal`, `RevealKind`, canonical seat order, generic show-order helper (seat order + last aggressor), with no street or showdown-kind knowledge.
- `BettingState.last_aggressor`; `PokerHand.reveal`.
- Hold'em `showdown.py`: the single classification rule (not ready / `ALL_IN` / `SHOWDOWN`), refactoring `settle_hand`'s readiness onto it; `reveal_hands`; contested direct `settle_hand` records the reveal with the settlement after all rejectable checks.
- Tests: early all-in reveal on each street; river round with an all-in player is `ALL_IN`; river showdown with a river aggressor, with none, and wrapping past the button; folded never revealed; uncontested not revealed; `reveal_hands` rejections; a rejected direct settlement leaves the reveal unset; an existing reveal is kept.

### Cycle 3 — Single-hand orchestration (ADR 0002 §1–2, §8 hand start)

- `texas_holdem/hand_flow.py`: `begin_hand` (blinds, then hole cards, then advance), `act`, and private `_advance` (below).
- Tests, only through `begin_hand` / `act`: fold-out on each street; river showdown; all-in on each street with runout; blinds completing preflop at once; one player with chips against all-ins; multi-way side pots; atomic rejections. Extend the seeded stress test to drive hands only through `act`.

### Cycle 4 — Continuous game loop and milestone close (ADR 0002 §2–3, §9)

- `texas_holdem/game.py`: `HoldemGame`, `HandInProgressError`.
- Tests: `start` / `next_hand` return a hand awaiting a decision or settled; button movement; busted players skipped; waiting players entering; `next_hand` rejected mid-hand without changes; the game cannot continue below two players; seeded multi-hand stress with chip conservation across hands.
- Close out: `ARCHITECTURE.md` (lifecycle, reveal, orchestration, invariants, §9 caller precondition), README capabilities, `ROADMAP.md` status.

## `_advance` contract

Private to `hand_flow`; runs after `begin_hand` and after every successful `act`. Each pass:

1. hand settled → stop;
2. one live player → `settle_hand` (it owns the uncontested case) → stop;
3. a player is to act → stop;
4. ask the shared Hold'em classification rule:
   - ready (`ALL_IN` or `SHOWDOWN`) → `reveal_hands` → deal any remaining streets without starting their betting rounds → `settle_hand` → stop;
   - not ready → `deal_next_street` + `start_betting_round` → next pass (at most once per street).

Postcondition: the hand is settled or has a current actor. A failure after a valid action is an engine defect and is raised, never swallowed.

## Invariants to establish

- A settled hand rejects every public mutation entry point, and its own state is not changed by further operations on it. Shared `Player` objects still change in later hands, so a settled `PokerHand` is not a historical snapshot.
- `hand.reveal` is `None` or covers exactly the live seats, and is set at most once; a settled contested hand has a reveal; `ALL_IN` seats are in clockwise-left-of-button storage order.
- Under `hand_flow`, every call ends with a current actor or a settlement.
- Across a `HoldemGame`, `sum(player.stack)` is conserved from hand to hand.

## Risks

- Import cycles from moving the settled check into `poker_hand.py` or from `BettingState` gaining state; resolved in implementation without behavior change.
- Refactoring `settle_hand`'s readiness onto the shared classification must keep every Milestone 4 test passing unchanged.

## Open Decisions

None. ADR 0002 is accepted.
