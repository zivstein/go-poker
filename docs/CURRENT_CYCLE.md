# Current Cycle

**Milestone 5 — Complete continuous PokerHand/game loop** is in progress. Cycles 1–3 are complete; Cycle 4 is next.

Milestone status, approved product decisions, and deferred work live in `ROADMAP.md`. The hand lifecycle and orchestration contract lives in [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md), and the showdown contract in [ADR 0003](adr/0003-interactive-showdown-and-muck.md), which supersedes parts of ADR 0002 and [ADR 0001](adr/0001-showdown-settlement-contract.md). Their numbered decisions are cited below as ADR 0002 §N and ADR 0003 §N. Implemented behavior is recorded in `ARCHITECTURE.md` as each Cycle lands.

## Goal

Run a No-Limit Texas Hold'em hand from creation to settlement, then the next hand, with player decisions as the only external inputs:

- every public hand-level mutation entry point rejects a settled hand;
- once showdown is certain, a showdown starts: an `ALL_IN` showdown tables every live hand at once; an `INTERACTIVE` river showdown asks players in decision order to SHOW or MUCK until it is complete; settlement evaluates only shown hands;
- `begin_hand` / `act` advance a hand automatically until a betting or showdown decision is required or it is settled;
- `HoldemGame` owns the table, stakes, and current hand, and starts the next hand only after settlement.

Out of scope: the items deferred in `ROADMAP.md`.

Tests drive whole hands through public operations, using the existing `stacked_hand` fixture and the `shuffle_decks_with` monkeypatch pattern (no new production test seam).

## Cycles

| Cycle | Title | Status |
| --- | --- | --- |
| 1 | Post-settlement boundary | Complete |
| 2 | Reveal and show order | Complete |
| 3 | Interactive showdown and muck | Complete |
| 4 | Single-hand orchestration | Next (not started) |
| 5 | Continuous `HoldemGame` and milestone close | Planned |

Cycle 3 depends on Cycles 1 and 2; Cycle 4 depends on Cycle 3; Cycle 5 depends on Cycle 4.

### Cycle 1 — Post-settlement boundary (ADR 0002 §7)

- Move the settled check and `HandAlreadySettledError` to `game/poker_hand.py`; `settlement.py` keeps exporting the error.
- Guard `initialize_betting`, `deal_hole_cards`, `deal_next_street`, `start_betting_round`, `apply_action`, and `settle_hand`; the check runs before any other validation. Internal helpers get no guard. Later entry points get the same guard in the Cycles that add them.
- Tests: each entry point rejects a settled hand and leaves it unchanged; the settled check wins over each entry point's other errors; existing import path still works.

### Cycle 2 — Reveal and show order (ADR 0002 §4–6, §8 direct settlement)

Delivered `Reveal`, `RevealKind`, `reveal_hands`, `PokerHand.reveal`, `BettingState.last_aggressor`, canonical seat order, the show-order helper, and the shared classification rule. Cycle 3 replaces the reveal record and API (ADR 0003 §11); `last_aggressor`, canonical order, and the classification rule carry over.

### Cycle 3 — Interactive showdown and muck (ADR 0003)

Delivered `game/showdown.py` (`Showdown`, `ShowdownKind`, `ShowdownAction`, `NotShowdownTurnError`, the derived showdown state, `Showdown.decide`, canonical order, `decision_order`), `PokerHand.showdown`, `start_showdown`, `apply_showdown_action`, interactive `settle_hand`, and contender-based settlement with both pot invariants (`SettlementInvariantError`). `game/reveal.py` and the public `showdown_ranks` are gone (Hold'em ranks shown seats through a private helper). `apply_showdown_action` rejects a non-`ShowdownAction` with `TypeError` before any change; `apply_action` rejects a non-`Action` before any change only incidentally (an `AttributeError` from its legality check, kept by a regression test), so Cycle 4's `act` dispatches by type.

### Cycle 4 — Single-hand orchestration (ADR 0002 §1–2, §8 hand start; ADR 0003 §9)

- `texas_holdem/hand_flow.py`: `begin_hand` (blinds, then hole cards, then advance), `act(hand, seat, action)` taking an `Action` or a `ShowdownAction`, a derived `current_actor(hand)` (the betting actor, else the showdown decider, else `None`), and private `_advance` (below).
- `act` sends a `ShowdownAction` to `apply_showdown_action` and any other action to `apply_action`, then advances. An action of the wrong kind is rejected by that operation, so `act` stays atomic.
- Tests, only through `begin_hand` / `act`: fold-out on each street; interactive river showdown with shows, mucks, and an unshown winner; all-in on each street with runout; blinds completing preflop at once; one player with chips against all-ins; multi-way side pots; wrong-kind and out-of-turn actions; atomic rejections. Extend the seeded stress test to drive hands only through `act`.

### Cycle 5 — Continuous `HoldemGame` and milestone close (ADR 0002 §2–3, §9)

- `texas_holdem/game.py`: `HoldemGame` with `act(seat, action)` taking either action kind, and `HandInProgressError`. Stakes stay fixed for the game's lifetime as the Milestone 5 contract (see `ROADMAP.md`).
- Tests: `start` / `next_hand` return a hand awaiting a decision or settled; button movement; busted players skipped; waiting players entering; `next_hand` rejected mid-hand, including during a showdown, without changes; the game cannot continue below two players; seeded multi-hand stress with chip conservation across hands.
- Close out: `ARCHITECTURE.md` (lifecycle, orchestration, invariants, §9 caller precondition, fixed stakes as a Milestone 5 limitation), README capabilities, `ROADMAP.md` status.

## `_advance` contract

Private to `hand_flow`; runs after `begin_hand` and after every successful `act`. Each pass:

1. hand settled → stop;
2. one live (non-folded) player → `settle_hand` (it owns the uncontested case) → stop;
3. a betting actor is to act → stop;
4. a showdown has started:
   - not complete → stop (a showdown decision is required);
   - complete → deal any remaining streets without starting their betting rounds → `settle_hand` → stop;
5. no showdown yet; ask the shared Hold'em classification rule:
   - ready (`ALL_IN` or `INTERACTIVE`) → `start_showdown` → next pass;
   - not ready → `deal_next_street` + `start_betting_round` → next pass (at most once per street).

Postcondition: the hand is settled, has a betting actor, or has a showdown decider. A failure after a valid action is an engine defect and is raised, never swallowed.

## Invariants to establish

- A settled hand rejects every public mutation entry point, and its own state is not changed by further operations on it. Shared `Player` objects still change in later hands, so a settled `PokerHand` is not a historical snapshot.
- `hand.showdown` is `None` or its `order` is exactly the non-folded seats; an `ALL_IN` showdown has its seats in canonical order and no decisions; decisions are only added, one at a time, never once complete; a mucked seat is never folded.
- A settled contested hand has a complete showdown; an uncontested hand has none.
- `Settlement.showdown_ranks` holds exactly the shown seats.
- Every pot has at least one final contender among its eligible seats; a pot with more than one has a showdown rank for each; only contenders are paid.
- Under `hand_flow`, every call ends with a betting actor, a showdown decider, or a settlement.
- Across a `HoldemGame`, `sum(player.stack)` is conserved from hand to hand.

## Risks

- Migrating the Cycle 2 and Milestone 4 tests that settle a non-all-in river directly must change how they reach settlement, never weaken what they assert.
- The pot invariants are unreachable through public operations, so their tests target the internal settlement function; they must not grow into tests of impossible states elsewhere.

## Open Decisions

None. The Cycle 4 Brief is next.
