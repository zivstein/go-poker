# Current Cycle

**Milestone 2: Betting Engine + Legal Actions** (see [ROADMAP.md](ROADMAP.md)) — **CURRENT** (planned for implementation)

The milestone plan is approved and Cycle 1 is next; no cycle has started. The previous milestone, Milestone 1 (PokerHand + Dealing Foundation), is complete.

## Goal

At the end of this milestone, `PokerHand` supports normal No-Limit betting: betting is initialized with real blinds, the engine calculates the legal actions for the current actor, applies actions, tracks each betting round to completion, and starts the betting round for each later street.

Out of scope for this milestone: short all-in calls, raises below the minimum because the player lacks chips, short-raise reopening rules, blinds that cannot be posted in full, main and side pots, pot eligibility, showdown and settlement, automatic complete-hand orchestration, Pot-Limit, and Fixed-Limit. All-ins are supported only when they are otherwise normal full actions.

The approved design, ownership rules, invariants, and boundaries this milestone follows are in [ARCHITECTURE.md](ARCHITECTURE.md#betting-milestone-2-planned).

## Cycles

| Cycle | Title | Status |
| --- | --- | --- |
| 1 | Betting state, stakes and blind posting | Next (not started) |
| 2 | Action model + legal actions | Planned |
| 3 | Apply actions + betting-round progression | Planned |
| 4 | Integration hardening | Planned |

### Cycle 1 — Betting state, stakes and blind posting

- Create `src/go_poker/game/betting/`.
- `Stakes` model: positive integer small and big blinds, `small_blind <= big_blind` (equal blinds are valid).
- `BettingState`: street, current bet, last full raise size, current actor, pending players.
- `street_contribution` and `total_contribution` on `HandPlayerState`, and the single chip-commitment operation (stack down, both contributions up).
- `PokerHand` holds an optional reference to its `BettingState`; there is none until betting is initialized.
- Betting initialization (conceptually `initialize_betting(hand, stakes)`):
  - creates the preflop `BettingState` (`street = PREFLOP`)
  - posts SB / BB in full as real chips, deducted from the stacks
  - sets the initial current bet and last full raise size to the big blind
  - selects the first actor (first eligible player clockwise after the BB, so the button heads-up)
  - builds the pending players from the eligible players, blinds included
  - marks a player all-in if posting their blind in full uses their last chips
- Initialization is rejected atomically when the hand is already initialized or a blind cannot be posted in full.
- `start_game` and `start_next_hand` stay unchanged.

No user betting actions yet.

### Cycle 2 — Action model + legal actions

- `FOLD`, `CHECK`, `CALL`, `BET`, `RAISE`; no `ALL_IN` action.
- Action representation, with target ("bet to" / "raise to") street-contribution amounts for `BET` and `RAISE`.
- Call amount.
- No-Limit sizing: `BET` when the current bet is zero with a big-blind minimum, `RAISE` otherwise with a `current_bet + last_full_raise_size` minimum, and a `street_contribution + stack` maximum.
- Legal-action calculation: `FOLD` for any current actor (even when `CHECK` is available), `CHECK` with nothing to call, `CALL` when the player can cover the full amount, `BET` / `RAISE` when the player's maximum target reaches the minimum and at least one other player (not folded, not all-in) can respond. Short all-in calls and raises are not legal in this milestone.
- Focused tests include: no `BET` / `RAISE` when every other non-folded player is all-in, with only `CALL` (if fully covered) or `FOLD` offered when the player still owes chips.

Do not apply actions yet.

### Cycle 3 — Apply actions + betting-round progression

- Apply an action.
- Validate the current actor.
- Validate the requested action.
- Move chips.
- Fold / check / call / bet / raise behavior, including full actions that use the player's whole stack and mark them all-in.
- Update the current bet and last full raise size.
- Update pending actors: a bet or raise makes every other eligible player pending; folded and all-in players are never pending.
- Select the next actor.
- Determine round completion.
- End the round immediately when only one non-folded player remains (no actor, no pending players, no chips awarded).
- When no opponent can respond (every other non-folded player is all-in): the round completes after the remaining player resolves any outstanding bet with `CALL` or `FOLD`, and completes automatically, with no actor and nobody pending, if they owe nothing. This also applies when a round starts.
- Start the `FLOP` / `TURN` / `RIVER` betting round after the dealing layer advances the street:
  - requires the previous round to be complete
  - requires `hand.street` to differ from `betting_state.street`, then records the new street, so a street's round cannot start twice; rejection is atomic
  - does not validate the variant's street sequence, which dealing owns
  - resets street contributions and preserves total contributions
  - sets the current bet to zero and the last full raise size to the big blind
  - builds the pending players from eligible players
  - chooses the first eligible player clockwise after the button (the big blind heads-up)

Dealing stays independent from betting, and there is no hand or street orchestration.

### Cycle 4 — Integration hardening

Cover representative high-value behavior, including:

- heads-up preflop order
- heads-up postflop order
- representative multiway betting
- a bet after checks reopening action
- multiple raises
- folds, including everyone else folding
- an all-in through a normal full action
- round completion and starting a later street's round
- every opponent all-in: the remaining player calls (or folds) to close the round, and a later street's round completes automatically with no actor
- rejected repeated initialization, a rejected second round start on the same street, and a blind that cannot be posted in full
- invalid and out-of-turn actions
- atomic failure behavior
- stack / contribution invariants

Do not create Cartesian-product tests for every combination when the behavior is already proven.

## Testing principle

`distinct rule -> focused test`

Use representative boundaries and a small number of integration tests. Avoid:

- tests that only assert constants
- duplicated coverage across layers
- large combinatorial matrices without distinct behavior
- defensive tests for impossible state created only by manually corrupting internals

## Decisions

All Milestone 2 architecture, product, and domain decisions (1–10) are resolved and recorded in [ARCHITECTURE.md](ARCHITECTURE.md#betting-milestone-2-planned). No decisions remain open before Cycle 1. Milestone 2 is not yet implemented.
