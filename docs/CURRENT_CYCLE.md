# Current Cycle

**Milestone 3: All-ins + Main/Side Pots** (see [ROADMAP.md](ROADMAP.md)) — **CURRENT** (planned for implementation)

The milestone plan is documented and Cycle 1 is next; no cycle has started. The previous milestone, Milestone 2 (Betting Engine + Legal Actions), is complete, and its design is recorded in [ARCHITECTURE.md](ARCHITECTURE.md#betting-milestone-2).

## Goal

At the end of this milestone, No-Limit betting and chip accounting are correct for every realistic all-in case, including deep 9-max side pots:

- short all-in calls, opening bets, raises, and blinds
- No-Limit reopening rules, including cumulative short all-ins
- the return of unmatched chips and the end-of-round collection of chips in front into the middle
- the derived middle pot and main and side pots with their eligible seats
- a derived signal that no further betting is possible

The state stays explicit enough for future UI, hand history, rake, analytics, and AI to consume directly.

Out of scope for this milestone: card evaluation at showdown, choosing pot winners, pot payout, split pots, odd-chip rules, automatic card reveal, automatic board runout, complete-hand orchestration, rake, the tournament rebuy and bust lifecycle, Pot-Limit, and Fixed-Limit.

The approved design, ownership rules, invariants, and boundaries this milestone follows are in [ARCHITECTURE.md](ARCHITECTURE.md#all-ins-and-pots-milestone-3-planned).

## Cycles

| Cycle | Title | Status |
| --- | --- | --- |
| 1 | Short-all-in state and raise rights | Next (not started) |
| 2 | Short calls, bets, raises and blinds | Planned |
| 3 | Accounting, collection and pots | Planned |
| 4 | Extreme integration hardening | Planned |

### Cycle 1 — Short-all-in state and raise rights

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

### Cycle 2 — Short calls, bets, raises and blinds

- Short `CALL`: legal whenever chips are owed; it commits `min(amount_owed, stack)`, and a call that empties the stack is all-in. `current_bet` is unchanged.
- Call target: when no opponent can respond, `amount_owed` is measured against the largest street contribution of the other live players, so nobody commits chips that collection would return straight away. `current_bet` keeps its nominal value. The same rule settles the pending players. Heads-up 50/100 with the small blind's 50 in front: against a big blind all-in for 30, the small blind is not pending; against one all-in for 70, the small blind owes 20.
- Short opening `BET`: when the actor's maximum target is below the big blind, `short_all_in_target` is set and is the only legal target. `min_full_target` still reports the big blind, and `last_full_raise_size` is unchanged.
- Short `RAISE`: when the actor's maximum target is above the current bet but below the minimum raise, `short_all_in_target` is set and is the only legal target, while `min_full_target` still reports the full minimum raise. `current_bet` becomes the target, `last_full_raise_size` is unchanged, and every other eligible player owes a response.
- A bet or raise that reaches the full minimum target is full and sets `last_full_raise_size`; a short all-in never does.
- Cumulative short all-ins reopen raising through `acted_at_bet`; a single short all-in below a full raise does not.
- Short small and big blinds: remove `ShortBlindAllInNotSupportedError` and post `min(blind, stack)`. `current_bet` and `last_full_raise_size` start at the full big blind.
- All-in state transitions: every commitment that empties a stack marks the player all-in, through the existing `commit_chips` rule.
- No-further-betting detection: `is_betting_closed(hand)` (planned name) is true when the round is complete and at most one live player can still act.
- Known interim gap until Cycle 3: unmatched chips stay committed, and `start_betting_round` still resets street contributions as in Milestone 2.

### Cycle 3 — Accounting, collection and pots

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

### Cycle 4 — Extreme integration hardening

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

## Testing principle

`distinct rule -> focused test`

Use representative boundaries and a small number of integration tests. Avoid:

- tests that only assert constants
- duplicated coverage across layers
- large combinatorial matrices without distinct behavior
- defensive tests for impossible state created only by manually corrupting internals

Property-based testing (Hypothesis) is not used in planning or Cycles 1–3.

## Decisions

All Milestone 3 architecture, product, and domain decisions are resolved and recorded in [ARCHITECTURE.md](ARCHITECTURE.md#all-ins-and-pots-milestone-3-planned):

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

No decisions remain open before Cycle 1. Whether to add Hypothesis is decided with the user at Cycle 4.
