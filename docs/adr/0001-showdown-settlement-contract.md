# 0001: Showdown and settlement contract

Status: Accepted (2026-10-30)

## Context

Milestone 3 derives the main and side pots (`pots(hand)`, `middle_pot(hand)`) from preserved player contributions, but nothing decides who wins them or pays anyone. Milestone 4 adds showdown and settlement.

The result of settlement is a durable contract. Milestone 5 hand orchestration, Milestone 6 hand history, later variants such as Omaha, and the future API and clients all build on it. Settlement also changes the meaning of existing chip and `all_in` state once a hand is paid, so those rules must be explicit.

Automatic board runout, revealing hands, and full-hand orchestration stay in Milestone 5.

## Decision

1. **Odd chips.** Each pot is split independently. Every tied winner of a pot gets `amount // winners`. The `amount % winners` remainder chips go one at a time to the tied winners in clockwise order, starting with the first seat left of the button (heads-up, the big blind first). No tied winner gets a second odd chip in the same pot before every earlier tied winner in that order has one.

2. **All live hands compete.** At showdown every non-folded player competes for each pot they are eligible for. There is no voluntary muck or concession at showdown. Which hands are revealed to others, and in what order, is outside this decision.

3. **Settlement record and state after payout.** Settlement stores an immutable `Settlement` on `PokerHand` (`hand.settlement`). It is also what marks the hand as settled, so a hand is settled at most once.
   - `total_contribution`, `street_contribution`, and `folded` are preserved as the hand's accounting history.
   - `pots(hand)` and `middle_pot(hand)` keep describing what was contested; `hand.settlement` records that it was paid.
   - `all_in` stays current state, not history. A payout that makes a stack positive clears `all_in`; an all-in player paid nothing keeps a zero stack and `all_in`. A participant is therefore `all_in` exactly when their stack is zero, before and after payout. Knowing that a player was all-in earlier in the hand belongs to hand history/events.

4. **Payout ownership.** Settlement owns the payout transition from contested-pot accounting back to player stacks, including clearing `all_in`. `game/betting/chips.py` keeps owning only stack ↔ betting-contribution movement (`commit_chips`, `return_chips`). No further abstraction is introduced unless implementation proves one necessary.

5. **Result representation.** All settlement result types are immutable.
   - `PotAward` holds its `Pot` and the exact amount awarded to each winning seat, ordered clockwise from the button. Odd chips can make those amounts unequal. The winners are derived from these amounts and are not stored separately.
   - `Settlement` holds the pot awards in pot order and each live player's `HandRank` at showdown (empty when the hand is uncontested). Each seat's total payout is derived from the pot awards and is not stored.

6. **Module placement and public entry.**
   - `game/settlement.py` owns variant- and betting-structure-agnostic settlement: the result types, pot awarding (winners, splits, odd chips), and the generic settle operation with its payout.
   - `game/variants/texas_holdem/showdown.py` owns Hold'em showdown: hand strength as the best five of the two hole cards and five board cards, and when a Hold'em hand is ready to settle.
   - `settle_hand(hand)` in the Hold'em showdown module is the public entry point. A hand with one live player is settled uncontested without evaluating anything; otherwise it needs a complete board and no possible further betting.

## Alternatives considered

- **Odd chip to the highest card by suit** (stud-style): needs a suit order the engine does not have, and is not the convention for flop games.
- **Odd chip to a random winner:** adds randomness to settlement and makes results harder to test and to replay from history.
- **Allowing a player to concede at showdown:** needs a new showdown action and turn order. Not needed for a correct engine result.
- **Returning the result without storing it:** the hand would need a separate "settled" flag, and history would have to capture the return value to know who won.
- **Keeping `all_in` set after payout as history:** leaves current state stale and breaks "`all_in` exactly when the stack is zero". History belongs to the event log.
- **A payout function in `chips.py`:** would widen that module beyond betting contributions and give the payout transition two owners.
- **Storing winners next to per-seat amounts, or storing per-seat totals:** duplicate sources of truth that can disagree.
- **Settlement under `game/betting/` or inside the Hold'em variant only:** splitting pots does not depend on the betting structure, and hand strength depends on the variant, so neither place fits both parts.

## Consequences

- Milestone 5 orchestration calls `settle_hand(hand)` once the hand has reached its end. Blocking dealing and betting operations after settlement is part of Milestone 5's hand lifecycle.
- Milestone 6 hand history can read winners, amounts, and showdown ranks from `hand.settlement`, and must itself record facts that current state no longer shows, such as a player having been all-in.
- Omaha adds its own showdown hand strength (exactly two hole cards) and reuses the generic settlement unchanged. Hi-lo splits would need a new decision.
- After settlement, `stack == starting_chips - total_contribution + payout`, and the payouts add up to the middle pot (no rake).
- Reporting the best five cards is not part of this contract.
