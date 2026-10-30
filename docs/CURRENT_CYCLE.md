# Current Cycle

**Milestone 3: All-ins + Main/Side Pots** (see [ROADMAP.md](ROADMAP.md)) — **COMPLETE**

All four cycles are complete, so there is no current cycle. **Milestone 4 — Showdown + settlement** is next and has not started. It is broken into cycles when it starts. The previous milestone, Milestone 2 (Betting Engine + Legal Actions), is also complete, and its design is recorded in [ARCHITECTURE.md](ARCHITECTURE.md#betting-milestone-2).

## Goal

At the end of this milestone, No-Limit betting and chip accounting are correct for every realistic all-in case, including deep 9-max side pots:

- short all-in calls, opening bets, raises, and blinds
- No-Limit reopening rules, including cumulative short all-ins
- the return of unmatched chips and the end-of-round collection of chips in front into the middle
- the derived middle pot and main and side pots with their eligible seats
- a derived signal that no further betting is possible

The state stays explicit enough for future UI, hand history, rake, analytics, and AI to consume directly.

Out of scope for this milestone: card evaluation at showdown, choosing pot winners, pot payout, split pots, odd-chip rules, automatic card reveal, automatic board runout, complete-hand orchestration, rake, the tournament rebuy and bust lifecycle, Pot-Limit, and Fixed-Limit.

The approved design, ownership rules, invariants, and boundaries this milestone follows are in [ARCHITECTURE.md](ARCHITECTURE.md#all-ins-and-pots-milestone-3).

## Cycles

| Cycle | Title | Status |
| --- | --- | --- |
| 1 | Short-all-in state and raise rights | Complete |
| 2 | Short calls, bets, raises and blinds | Complete |
| 3 | Accounting, collection and pots | Complete |
| 4 | Extreme integration hardening | Complete |

### Cycle 1 — Short-all-in state and raise rights (complete)

- `BettingState`: document `current_bet` as the nominal betting target that a fully funded player must match; it is never below a street contribution but may be above the highest one.
- Add the per-round action context `acted_at_bet: dict[int, int]` (seat → `current_bet` right after that seat's latest action). Every applied action records it, and it is empty when betting is initialized and whenever a betting round starts. Posting a blind is not an action.
- Refine `LegalActions`:
  - add `amount_owed` and `call_is_all_in`
  - `call_amount` becomes the chips a `CALL` commits (`min(amount_owed, stack)`, 0 when `CALL` is not legal)
  - rename `min_target` to `min_full_target` (the normal minimum full bet or raise target) and keep `max_target` (the all-in target)
  - add `short_all_in_target`, which stays `None` in this cycle because short all-ins are not legal yet
- Derive raise rights separately from `pending_actors`. A player has them when they have not acted this round, or when `current_bet - acted_at_bet[seat] >= last_full_raise_size` (the No-Limit reopening rule, next to the sizing helpers). `BET` and `RAISE` need raise rights.
- Replace the test invariant `current_bet == max(street_contribution)` with `max(street_contribution) <= current_bet`.
- Preserve the existing full-action behavior. Short all-ins are still not legal in this cycle, so every bet or raise is full and raise rights never yet deny a pending player. Existing tests change only for the new fields and the new `BettingState` state.

Delivered: `BettingState.acted_at_bet` (recorded by `apply_action` for every action, empty after `initialize_betting`, cleared by `start_betting_round`) with the documented `current_bet` and `last_full_raise_size` meanings; `has_raise_rights` in `no_limit.py`, required by `legal_actions` for `BET` and `RAISE`; and the refined `LegalActions` fields (`amount_owed`, `call_amount` as the chips a legal call commits, `call_is_all_in`, `min_full_target`, `max_target`, and `short_all_in_target`, always `None`). Short calls, bets, raises, and blinds stay rejected as in Milestone 2. Tests cover the new fields, the recording and clearing of `acted_at_bet`, the reopening rule at its boundaries (`test_no_limit.py`), a limper who regains raise rights after a full raise, and the gate on a hand-built state with a short all-in raise; the integration invariant is now `max(street_contribution) <= current_bet`.

### Cycle 2 — Short calls, bets, raises and blinds (complete)

- Short `CALL`: legal whenever chips are owed; it commits `min(amount_owed, stack)`, and a call that empties the stack is all-in. `current_bet` is unchanged.
- Call target: when no opponent can respond, `amount_owed` is measured against the largest street contribution of the other live players, so nobody commits chips that collection would return straight away. `current_bet` keeps its nominal value. The same rule settles the pending players. Heads-up 50/100 with the small blind's 50 in front: against a big blind all-in for 30, the small blind is not pending; against one all-in for 70, the small blind owes 20.
- Short opening `BET`: when the actor's maximum target is below the big blind, `short_all_in_target` is set and is the only legal target. `min_full_target` still reports the big blind, and `last_full_raise_size` is unchanged.
- Short `RAISE`: when the actor's maximum target is above the current bet but below the minimum raise, `short_all_in_target` is set and is the only legal target, while `min_full_target` still reports the full minimum raise. `current_bet` becomes the target, `last_full_raise_size` is unchanged, and every other eligible player owes a response.
- A bet or raise that reaches the full minimum target is full and sets `last_full_raise_size`; a short all-in never does.
- Cumulative short all-ins reopen raising through `acted_at_bet`; a single short all-in below a full raise does not.
- Short small and big blinds: remove `ShortBlindAllInNotSupportedError` and post `min(blind, stack)`. `current_bet` and `last_full_raise_size` start at the full big blind.
- All-in state transitions: every commitment that empties a stack marks the player all-in, through the existing `commit_chips` rule.
- No-further-betting detection: `is_betting_closed(hand)` is true when the round is complete and at most one live player can still act.
- Known interim gap until Cycle 3: unmatched chips stay committed, and `start_betting_round` still resets street contributions as in Milestone 2.

Delivered: `call_target` in `rounds.py`, the single call-target rule used by `legal_actions` (`amount_owed`) and `settle_pending` (who stays pending when no opponent can respond); `legal_actions` with short all-in calls (`call_amount = min(amount_owed, stack)`), aggression whenever the actor has raise rights, chips beyond the current bet, and an opponent who can respond, and `short_all_in_target` as the only legal target when the all-in is below `min_full_target`; `apply_action` accepting exactly that target, setting `last_full_raise_size` only for a full bet or raise, and committing `call_amount` for a call; short small and big blinds posting `min(blind, stack)` with `ShortBlindAllInNotSupportedError` removed; and `is_betting_closed(hand)` in `rounds.py`. As planned, a completed round keeps its chips in front and returns no unmatched chips until Cycle 3. Tests replace the Milestone 2 short-blind rejection with short-blind posting tests, and add focused tests for the short-call, short-bet, and short-raise legal shapes and their application, the call target against the larger of two all-in opponents, atomic rejection of illegal short all-in actions (including a raise without raise rights after a short all-in), and `is_betting_closed`. The integration checker moved into the betting `conftest.py` and now also asserts that a player is all-in exactly when their stack is empty; `test_all_in_integration.py` adds eight short all-in scenarios, with the Milestone 2 scenarios unchanged. They are the single place for the interactions they prove: a short raise or a short opening bet that does not reopen raising for earlier actors, including a checker (which replaces the hand-built raise-rights gate test), cumulative short all-ins that do, the heads-up short big blind called for what it can contest, and the multiway short big blind that leaves the full big blind owed.

### Cycle 3 — Accounting, collection and pots (complete)

- `return_chips` in `chips.py` is the explicit chip-return path. The amount must be positive and no larger than the player's chips in front. It raises the stack, lowers both contributions, and clears `all_in`.
- End-of-round collection, run by `apply_action` (and `initialize_betting` when the preflop round starts complete) when a round completes:
  - return the unmatched chips of a sole top contributor (above the next-highest total contribution, folded players included)
  - collect the chips in front into the middle by resetting every `street_contribution` to zero
  - keep the normalized `total_contribution`
- `start_betting_round` no longer resets street contributions.
- `middle_pot(hand)`: the sum of `total_contribution - street_contribution`.
- `Pot(amount, eligible_seats)` and `pots(hand)`: main and side pots derived from collected contributions.
  - Layer boundaries come from every participant's contribution, folded players included.
  - Each layer's amount includes the chips of all its contributors, folded dead money included.
  - Eligibility is limited to non-folded seats that reach the layer.
  - Adjacent layers may have identical eligibility.
  - Depth is arbitrary.
- Update the Milestone 2 tests whose expectations change: chips in front after a completed round, and the raiser's committed chips after everyone folds.

Delivered: `return_chips` in `chips.py`, the only reverse chip movement, rejecting a non-positive amount (`InvalidChipAmountError`) or more than the chips in front (the new `InsufficientChipsInFrontError`) without changes, and clearing `all_in`; `collect_round` in the new `collection.py`, run by `apply_action` when an action leaves nobody pending and by `initialize_betting` when the posted blinds already complete the preflop round: a sole top contributor gets back the chips above every other participant's highest total contribution (folded players included), then every street contribution resets to zero, while `current_bet`, `last_full_raise_size`, and `acted_at_bet` keep the round's final values; `start_betting_round` no longer resets street contributions; and the new `pots.py` with `middle_pot(hand)` and the frozen `Pot(amount, eligible_seats)` layers from `pots(hand)`, both derived from collected contributions only. Betting decisions are unchanged. Tests cover `return_chips` and its atomic rejections, the collection through real actions (a return measured against a folded total rather than a smaller all-in call, a matched top contribution that returns nothing, and an atomic rejection by the last pending player), the middle pot, and pot layering on hand-built collected contributions (folded dead money, a folded boundary with unchanged eligibility, all-in eligibility, and eight layers from nine contributions). The shared `CheckedHand.check` now also asserts the chip-location and pot invariants after every step: the middle pot plus the chips in front equal the total contributions, the pots add up to the middle pot, each pot has at least two contributors, a positive amount, and eligible seats that have not folded, reach its level, and are a subset of the previous pot's, a completed round has nothing in front and a highest total shared by at least two participants, and the middle pot and pots change nothing. The Milestone 2 and Cycle 2 tests that asserted chips still in front or an uncalled excess still committed now assert the collected state, the returned chips, and the derived pots, and `test_all_in_integration.py` adds a chips-in-front versus middle-pot scenario (a matched call and a short all-in call) and a player who folds after contributing to three pot layers.

### Cycle 4 — Extreme integration hardening (complete)

Representative high-value scenarios, driven through the public dealing and betting operations, each asserting the betting and accounting invariants after every step:

1. 9-max with many distinct all-in levels and the deepest meaningful pot layering (main pot plus 7 side pots)
2. an early all-in while deeper players keep betting across later streets
3. a player who folds after contributing to several pot layers, including a folded contribution that adds a layer boundary without changing eligibility
4. different eligible-seat sets for the main and side pots
5. one short all-in that does not reopen raising
6. several cumulative short all-ins that do reopen raising
7. short small and big blinds
8. a short `CALL`
9. a short opening `BET`
10. a short `RAISE`
11. unmatched chips returned
12. chips in front vs the middle pot, before and after collection
13. chip conservation across stacks, street contributions, total contributions, returned chips, and pots

Do not build Cartesian-product matrices. At the end of this cycle, evaluate whether property-based testing would materially improve confidence in chip conservation, pot layering, eligibility, unmatched returns, and reopening sequences. Hypothesis is a new dependency, so it is added only with user approval.

Delivered: tests only; no production code changed, and no scenario exposed a bug. The shared `CheckedHand` now also asserts, after every step, that `acted_at_bet` holds exactly the seats that acted in the round, that a round starts at the full big blind preflop and unopened with the big-blind minimum later, that only a bet or raise moves the current bet and only a full one changes the last full raise size (which never shrinks within a round), that what each live player can win, the pots whose eligible seats include them, adds up to as many collected chips from every participant as that player has collected (an independent check of pot amounts and eligibility that does not re-derive the layers), and that a completed round leaves every player who can still bet at the highest total. The new `test_side_pot_integration.py` covers nine players all-in preflop at nine levels (the unmatched top excess goes back and the eight remaining levels make a main pot and seven side pots, items 1 and 11), all-ins on successive streets that give the main pot and each side pot a different eligible set, with the stacks, chips in front, middle pot, and amount owed during a round and after its collection (items 2, 4, 8, 11, and 12), a player who folds after funding three layers, leaving every eligible set and adding a folded layer boundary with unchanged eligibility (item 3), and the last player able to act owing what the largest of three all-in opponents can contest. In `test_all_in_integration.py`, the short-raise scenario is now four-handed so both the bettor and a caller face the short raise and may only call or fold (item 5), the cumulative scenario asserts the pending players after each short all-in (item 6), a compact parametrized scenario covers a short small blind, a big blind below the small blind, one between the blinds, and one of exactly the whole stack (item 7), the skipped short all-in scenario asserts the pots after every street (item 2), and the fold-and-return scenario asserts the chips in front, stacks, and middle pot around the fold (items 3 and 11); items 9, 10, and 13 are covered by the existing short-bet and short-raise scenarios and by the checker. The new `test_betting_stress.py` plays 200 fixed seeds of 2–9 players with uneven stacks through random legal actions, street by street, with every step checked and the end-of-hand state checked (nothing in front, chip conservation across stacks and pots, the main pot contested by every live player, and later rounds that ask nobody to act once betting is closed); a companion test fails if the seed set stops reaching short blinds, short calls, short bets and raises, raise rights denied by a short all-in, returned chips, river betting, all-in run-outs, a folded player's dead money in a side pot, or a main pot with seven side pots. Cumulative short all-ins that reopen raising are too rare in random play to require there, and stay covered by their deterministic scenario. Hypothesis was evaluated and not adopted (see [Decisions](#decisions)).

## Testing principle

`distinct rule -> focused test`

Use representative boundaries and a small number of integration tests. Avoid:

- tests that only assert constants
- duplicated coverage across layers
- large combinatorial matrices without distinct behavior
- defensive tests for impossible state created only by manually corrupting internals

Property-based testing with Hypothesis is not used (see [Decisions](#decisions)); the seeded stress test in `test_betting_stress.py` is the randomized check.

## Decisions

All Milestone 3 architecture, product, and domain decisions (1–9) are resolved and recorded in [ARCHITECTURE.md](ARCHITECTURE.md#all-ins-and-pots-milestone-3), and all of them are implemented:

1. Three chip locations: the stack (`Player.stack`), chips in front (`street_contribution`), and the derived middle pot (collected chips only). There is no mutable pot-size state. The middle pot is the display value and the future rake boundary. It is not the future Pot-Limit sizing base, which belongs to the Pot-Limit structure.
2. `current_bet` is the nominal betting target; `current_bet == max(street_contribution)` is no longer an invariant.
3. `LegalActions` keeps its flat shape:
   - it adds `amount_owed`, `call_is_all_in`, and `short_all_in_target`
   - `call_amount` is the chips a call commits
   - `min_target` becomes `min_full_target`, which always means the normal minimum full bet or raise
   - `max_target` is the all-in target

   There is no `ALL_IN` action, and `BET` / `RAISE` keep target amounts.
4. When no opponent can respond, the amount owed is measured against what the all-in players can contest (heads-up 50/100, small blind 50 in, big blind all-in for 70: `CALL 20`), while `current_bet` stays nominal.
5. Raise rights are derived from `acted_at_bet` and `last_full_raise_size`, separately from pending actors. A check counts as acting, and short all-ins never change `last_full_raise_size`.
6. Short blinds post the whole stack; the nominal current bet and full-raise context stay at the big blind.
7. The end-of-round collection runs automatically when a round completes, returns unmatched chips through `return_chips` (which clears `all_in`), and resets chips in front.
8. Pots are derived from collected contributions as `Pot(amount, eligible_seats)` layers, with boundaries from every participant's contribution (folded included). Eligibility need not shrink strictly from one layer to the next. No pot classes or managers are stored.
9. `is_betting_closed(hand)` derives that no further betting is possible. Card reveal and board runout stay in future orchestration.

No decisions remain open.

Hypothesis outcome: not adopted. The gap in what the tests can detect is the oracle, not the generator: a property-based generator would explore more hands, but each would still be judged by the same invariants, and the seeded stress test already generates varied hands quickly and deterministically, with no new dependency. Revisit it at milestone 4 (split pots and odd chips) or milestone 7 (simulation), as a dedicated tooling change that needs user approval.
