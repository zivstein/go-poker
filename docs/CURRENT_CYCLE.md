# Current Cycle

**Milestone 4 — Showdown + settlement** is in progress. Cycle 1 is complete; Cycle 2 is next.

Milestone status and approved product decisions live in `ROADMAP.md`. The showdown and settlement contract lives in [ADR 0001](adr/0001-showdown-settlement-contract.md). Implemented behavior is recorded in `ARCHITECTURE.md` as each Cycle lands.

## Goal

Settle a No-Limit Texas Hold'em hand that has reached its end:

- an uncontested hand (one live player) is won without evaluation, on any street;
- a showdown (two or more live players) needs the full board and no possible further betting, and evaluates every live hand;
- each pot is resolved independently among its eligible seats, with ties split and odd chips allocated by the approved rule;
- winners are paid, the immutable settlement is stored on the hand, and contributions and `folded` stay as accounting history.

Out of scope: automatic board runout, revealing hands and show order, full-hand orchestration (Milestone 5); blocking dealing or betting after settlement (Milestone 5 hand lifecycle); reporting the best five cards; rake; bust/rebuy; hi-lo splits.

Tests reach the end of a hand through the real dealing and betting operations, dealing any remaining streets themselves.

## Cycles

| Cycle | Title | Status |
| --- | --- | --- |
| 1 | Showdown strength and pot awards | Complete |
| 2 | Settlement operation and payout | Next (not started) |
| 3 | Integration hardening and milestone close | Planned |

### Cycle 1 — Showdown strength and pot awards

Pure derivations only: no stack changes and no `PokerHand` change.

- `game/settlement.py`: the immutable `PotAward` and `Settlement` types (winners and per-seat totals derived), and a pure function from pots, per-seat hand ranks, and clockwise seat order to pot awards: single-eligible pots, sole winners, ties, splits, odd chips.
- `game/variants/texas_holdem/showdown.py`: each live player's `HandRank` from their hole cards and the full board, through `evaluate_best`.
- Focused tests per rule: a single-eligible pot; a sole winner; 2-way and 3-way ties with 0, 1, and 2 odd chips; odd-chip order wrapping past the button; heads-up order; a side pot won by a different player than the main pot; a short stack winning only the main pot; result types reject mutation.

### Cycle 2 — Settlement operation and payout

- `PokerHand.settlement`.
- Generic settle operation: validate, derive the awards, pay each seat's derived total into its stack, clear `all_in` where the stack becomes positive, and store the record. Rejections leave the hand unchanged; settling twice is rejected.
- Hold'em `settle_hand(hand)`: uncontested settlement, or showdown once the river is dealt and either the river betting round is complete or betting closed earlier.
- Tests: uncontested wins on each street; showdown after a completed river round; showdown after an earlier all-in with the remaining streets dealt; a paid all-in player loses `all_in` and an unpaid one keeps it; each rejection leaves the hand unchanged; double settlement; contributions and `folded` preserved; the post-settlement accounting invariants.

Carried from Cycle 1: `_award_pots(pots, ranks, seats_from_button)` (internal; takes `hand.players` order and owns the odd-chip rotation) and `showdown_ranks(hand)` (returns a dict in hand order; already rejects an incomplete board and a live player without exactly two hole cards). Convert its result to `Settlement.showdown_ranks` pairs.

### Cycle 3 — Integration hardening and milestone close

- End-to-end scenarios through the public dealing, betting, and settlement operations, with a test-local stacked deck (no new production seam): 9-max with many side pots and different winners per layer; a split main pot with a side pot to a third player; odd chips in several pots; folded dead-money layers; an uncontested pot after an unmatched bet is returned.
- Extend the seeded betting stress test to deal the remaining streets, settle, and assert table-wide chip conservation. Fold in the Cycle 1 randomized award test in `tests/game/test_settlement_pots.py`, so a single seeded hand driver remains.
- Close out: `ARCHITECTURE.md` (settlement section and invariants), README capabilities, `ROADMAP.md` status.

## Invariants to establish

- After settlement: `stack == starting_chips - total_contribution + payout`.
- `sum(payouts) == middle_pot == sum(pot.amount)`, and each pot's awards add up to its amount.
- Only eligible, non-folded seats are paid. Awards within a pot differ by at most 1, and the larger ones go to the earliest tied winners clockwise from the button.
- A participant is `all_in` exactly when their stack is zero, before and after payout. This strengthens the current "before payout" scoping in `ARCHITECTURE.md`.

## Risks

- An import cycle between `PokerHand`, the settlement types, and `Pot`. It is resolved in implementation (for example a type-only import) without changing behavior. `settlement.py` already reaches `poker_hand.py` through `pots.py`, so adding `PokerHand.settlement` closes the cycle.

## Open Decisions

None. ADR 0001 is accepted.
