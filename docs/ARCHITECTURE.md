# Go! Poker Architecture

This document is the source of truth for the engine's current architecture, ownership boundaries, state meanings, and durable invariants.

Implementation examples belong in tests.
Development history belongs in Git.
Future product capabilities belong in `ROADMAP.md`.

## Principles

- The poker engine is independent from persistence, APIs, networking, and clients.
- Clients consume poker rules rather than reimplementing them.
- Every rule and state value has one owner.
- Persistent player/table state is separate from per-hand state.
- Poker variant and betting structure are independent dimensions.
- Extract abstractions only when concrete implementations prove what is shared.

## Layers

Paths are under `src/go_poker/`.

| Area | Responsibility |
| --- | --- |
| `core/` | cards, deck, hand ranks, hand evaluation |
| `game/` | players, seats, table, lifecycle, hand setup, per-hand state, settlement |
| `game/variants/` | poker-variant-specific rules |
| `game/betting/` | betting-structure rules, currently No-Limit |

`core/` never depends on `game/`.

`game/` never depends on `game/variants/`. Shared concepts that `game/` needs belong in `game/`, not in a concrete variant; for example, `Street` lives in `game/street.py`.

The engine never depends on persistence, accounts, networking, API, or UI layers.

## Core Cards and Evaluation

`core/` owns:

- `Card`, `Rank`, and `Suit`;
- `Deck`;
- comparable `HandRank`;
- five-card evaluation;
- best-of-5–7 evaluation.

### Randomness

A fresh `Deck` begins in creation order.

Production `Deck.shuffle()` uses `random.SystemRandom`.

Production engine code never controls or seeds the RNG.

`Deck.shuffle(_rng=...)` is the single deterministic test seam.

Tests may pass a seeded `random.Random`; engine code must not.

### Card Integrity

Legal engine-generated state keeps cards unique by construction:

- each hand receives a fresh deck;
- shuffling only reorders it;
- drawing removes cards from the deck;
- dealing moves drawn cards into hand-owned locations.

Runtime engine play therefore does not rescan the hand for duplicate cards.

Validation of future externally loaded or reconstructed state belongs at that external boundary.

## Persistent Game State

### Player

`Player` owns:

- player id;
- stack;
- participation status: `WAITING`, `READY`, or `SITTING_OUT`.

`Player` is a poker participant, not an account or user identity. Accounts and authentication stay outside the engine, and bots and guests must be able to participate without an account.

Running out of chips does not automatically change participation status.

Bust/rebuy/top-up policy is not implemented.

### Seat

A `Seat` represents one physical table seat and holds at most one `Player`.

### Table

`Table` owns:

- physical seats;
- seating operations;
- the stored button seat.

It does not own:

- hand participation;
- player-status lifecycle;
- button traversal policy;
- dealing;
- betting rules.

## Hand Setup and Lifecycle

### Hand Setup

`hand_setup` decides which seated players participate in the next hand.

A player with `stack == 0` does not participate and cannot receive the button.

A player with a positive stack smaller than a blind still participates.

`READY` players participate.

`SITTING_OUT` players do not.

A `WAITING` player may enter when their computed position is:

- big blind; or
- a non-blind position.

They remain waiting if they would enter as:

- button;
- small blind.

At least two participants are required.

### Game Lifecycle

`game_lifecycle` owns:

- explicit game start;
- button traversal between hands;
- creation and secure shuffle of each hand's fresh deck.

The lifecycle is variant-agnostic and betting-agnostic.

It deals no cards and posts no blinds.

`start_game` selects the first button from eligible starting players.

`start_next_hand` moves clockwise from the stored previous button seat to the next `READY` player with chips.

It skips:

- empty seats;
- `WAITING`;
- `SITTING_OUT`;
- zero-stack players.

The old button seat remains the traversal anchor even if its player can no longer participate.

The lifecycle returns a new `PokerHand`.

## Per-Hand State

### PokerHand

`PokerHand` is the aggregate for one community-card hand.

It owns:

- ordered `HandPlayerState` participants;
- the hand's `Deck`;
- community board;
- current `Street`;
- burned cards;
- optional `BettingState`;
- optional immutable `Settlement`, present only once the hand is settled.

It is a state container rather than the owner of participation, variant dealing, or betting rules.

The settlement marker's presence makes every public hand-level mutation entry point reject the hand first with `HandAlreadySettledError` (see [Settled-Hand Guard](#settled-hand-guard)).

### HandPlayerState

Per-hand player state owns:

- reference to the persistent `Player`;
- seat;
- position;
- blind;
- hole cards;
- `folded`;
- `all_in`;
- `street_contribution`;
- `total_contribution`.

Persistent stack remains on `Player`.

## Texas Hold'em Dealing

Texas-specific dealing lives under `game/variants/texas_holdem/`.

It owns:

- exactly two hole cards;
- hole-card deal order;
- burn cards;
- flop/turn/river board counts;
- Hold'em street progression.

Hole cards are dealt one at a time beginning with the player clockwise from the button and ending with the button.

Board progression is:

    PREFLOP
    → burn + FLOP(3)
    → burn + TURN(1)
    → burn + RIVER(1)

The lifecycle does not know these rules.

## Betting Ownership

No-Limit betting lives under `game/betting/`.

`PokerHand` holds the current `BettingState`.

`Table` owns no betting configuration or betting rules.

`HandPlayerState` owns per-player hand contributions and flags.

`Player.stack` is the source of truth for chips behind.

### Betting Modules

| Module | Responsibility |
| --- | --- |
| `stakes.py` | blind values |
| `state.py` | betting-round state |
| `chips.py` | chip movement |
| `initialization.py` | blind posting / initial betting state |
| `actions.py` | action value model |
| `no_limit.py` | No-Limit sizing and raise rights |
| `legal_actions.py` | derived legal actions |
| `apply.py` | action validation/application |
| `rounds.py` | actors, pending actions, call target, round lifecycle |
| `collection.py` | unmatched return and round collection |
| `pots.py` | derived middle/main/side pots |

## Betting State

`BettingState` owns:

- street;
- stakes;
- `current_bet`;
- `last_full_raise_size`;
- `current_actor`;
- `pending_actors`;
- `acted_at_bet`.

`current_bet` is the nominal target a fully funded player normally matches.

A short blind or call may leave all actual contributions below it.

Invariant:

`street_contribution <= current_bet`

`last_full_raise_size` changes only after a full bet or raise.

`acted_at_bet[seat]` stores the `current_bet` immediately after that player's latest action in the round.

Posting a blind is not an action.

## Actions and Legal Actions

Actions are:

- `FOLD`
- `CHECK`
- `CALL`
- `BET`
- `RAISE`

There is no separate `ALL_IN` action.

`BET` and `RAISE` carry target street contributions ("bet to" / "raise to"), not chip deltas.

`legal_actions(hand)` is derived on request and is never stored.

It exposes enough information for a caller to present valid choices without recreating betting rules.

Rejected actions are atomic.

## No-Limit Sizing and All-Ins

The normal minimum opening bet is the big blind.

The normal minimum raise target is:

`current_bet + last_full_raise_size`

A player may call for less when their entire remaining stack cannot cover the call.

When a player's maximum aggressive target is below the normal full minimum, the only short aggressive target is that exact all-in target.

A short all-in does not change `last_full_raise_size`.

### Raise Rights

Pending action and raise rights are separate concepts.

A player may raise when:

- they have not acted this round; or
- `current_bet` has increased by at least `last_full_raise_size` since their latest action.

Conceptually:

`current_bet - acted_at_bet[seat] >= last_full_raise_size`

A check counts as acting.

Therefore:

- one insufficient short raise does not reopen raising for earlier actors;
- cumulative short all-ins can reopen raising once their combined increase reaches a full raise.

## Blind All-Ins

A blind posts:

`min(required_blind, stack)`

If that consumes the stack, the player becomes all-in.

The nominal `current_bet` and initial `last_full_raise_size` remain the full big blind even when the big blind posts short.

## Contestable Call Target

When every other live opponent is all-in, a player is not required to commit chips above what those opponents can contest.

The call target is capped by the highest actual street contribution among relevant live all-in opponents, never above the nominal `current_bet`.

With several all-in opponents, the largest contestable contribution matters.

The nominal `current_bet` is not rewritten.

## Betting Rounds

`pending_actors` represents only players who still owe an action.

A bet or raise makes every other eligible actor who owes a response pending.

Action moves clockwise through hand order.

A round completes when nobody remains pending.

`start_betting_round` starts a later-street round after the previous round has already been collected.

It starts with:

- `current_bet = 0`;
- `last_full_raise_size = big blind`;
- empty `acted_at_bet`;
- first eligible actor clockwise after the button.

### Betting Closed

`is_betting_closed(hand)` is derived.

It is true when the current round is complete and at most one live player can still act.

Examples:

- all remaining live players are all-in;
- one player has chips but owes nothing against all-in opponents;
- every opponent has folded.

All-in players remain live and eligible for pots.

## Chip Accounting

Before settlement, there are three relevant chip locations.

### Behind

`Player.stack`

### In Front

`HandPlayerState.street_contribution`

These chips are committed in the current betting round but not yet collected.

### Collected

`total_contribution - street_contribution`

Summed across players, this is the derived `middle_pot`.

`total_contribution` is the hand-wide source of truth for chips committed and not returned.

### After Settlement

After settlement, [payout](#payout) has moved the contested chips into stacks. The contributions, the collected amounts, and the middle pot are unchanged history of what was contested, and `hand.settlement` records that they were paid. They are not additional physical chips and must not be added to stacks: the chips on the table are then the stacks alone.

### Chip Movement

Betting moves chips between stack and contributions only through `commit_chips` and `return_chips`.

`commit_chips` moves chips from stack into contributions.

`return_chips` moves unmatched chips still in front back to the stack.

A commitment that empties the stack sets `all_in`.

A return that makes the stack positive clears `all_in`.

Settlement payout, owned by `game/settlement.py` (see [Payout](#payout)), is the other stack movement.

## End-of-Round Collection

When a betting round completes:

1. if exactly one participant has the highest `total_contribution`, return unmatched excess above the next-highest participant total;
2. folded participants still count when determining how much was matched;
3. reset every `street_contribution` to zero;
4. preserve normalized `total_contribution`.

This prevents creation of an unmatched one-contributor pot.

Collection happens when the operation completing the round runs.

Starting the next round does not perform collection.

## Pots

Pots are derived values rather than mutable stored state.

`Pot(amount, eligible_seats)`

`middle_pot(hand)` contains collected chips only. For `pots(hand)` and `middle_pot(hand)` after settlement, see [After Settlement](#after-settlement).

`pots(hand)` derives layers from each participant's collected contribution.

For every distinct positive contribution level:

- folded and live contributions both fund the amount;
- folded players are never eligible;
- live/all-in players are eligible for every layer their contribution reaches.

Folded contributions may introduce a layer boundary without changing the eligible seats.

Adjacent pots may therefore have identical eligible sets.

Every pot has at least one eligible seat.

Eligibility is nested by depth: each later pot's eligible seats are a subset, not necessarily strict, of the previous pot's.

Pot depth is generic and does not encode a fixed number of side pots.

## Showdown and Settlement

Settlement turns the contested pots into stack payouts and records the result. The contract is in [ADR 0001](adr/0001-showdown-settlement-contract.md).

| Module | Responsibility |
| --- | --- |
| `game/settlement.py` | variant- and betting-structure-agnostic: `PotAward`, `Settlement`, pot awarding (winners, ties, odd chips), the internal `_settle` operation and payout; re-exports `HandAlreadySettledError` (see [Settled-Hand Guard](#settled-hand-guard)) |
| `game/variants/texas_holdem/showdown.py` | Hold'em hand strength (`showdown_ranks`), readiness rules, the public `settle_hand`, `ShowdownNotReadyError` |

`settle_hand(hand)` is the only public settle entry. `_settle(hand, ranks)` is shared engine implementation for variant entry points and is not a client-facing API.

`PotAward` holds a `Pot` and the exact chips each winning seat receives, ordered clockwise from the button. Odd chips make amounts unequal.

`Settlement` holds the pot awards and each live player's showdown `HandRank`, empty when uncontested. Per-seat payouts and winners are derived, never stored.

Every non-folded player competes for each pot they are eligible for.

Each pot is split independently: each tied winner gets `amount // winners`, and the remainder goes one chip at a time to tied winners clockwise from the first seat left of the button.

### Settling a Hold'em Hand

`settle_hand(hand)` validates in this order, and a rejection leaves the hand unchanged:

1. the hand is already settled: `HandAlreadySettledError`; this comes first because a payout can clear `all_in` and make betting look open again;
2. the hand has no betting state: `BettingNotInitializedError`;
3. exactly one player has not folded: the hand is settled uncontested on any street, with nothing evaluated;
4. the board is incomplete: `IncompleteBoardError`;
5. further betting is possible: `ShowdownNotReadyError`;
6. otherwise every live hand is evaluated and the hand is settled.

A contested hand is ready when the current betting round is complete and either that round belongs to the river or `is_betting_closed(hand)`. A river dealt without its round started, while two players can act, is not ready. Remaining streets after an all-in need to be dealt, but their betting rounds need not be started.

### Payout

`_settle` derives the pots, awards, and settlement before changing anything. It then adds each seat's payout to its stack, clears `all_in` for every paid seat, and stores the settlement on the hand.

`total_contribution`, `street_contribution`, `folded`, the board, the betting state, and the derived pots keep describing what was contested; `hand.settlement` records that it was paid.

### Settled-Hand Guard

`HandAlreadySettledError` ("this hand is settled") and `_require_unsettled(hand)` live in `game/poker_hand.py`, which does not import settlement at runtime. `settlement.py` re-exports the same error class, so importing it from either module gives the same class.

`_require_unsettled` is the first validation, before any other state validation, in each public hand-level mutation entry point:

- `initialize_betting`
- `deal_hole_cards`
- `deal_next_street`
- `start_betting_round`
- `apply_action`
- `settle_hand` (the internal `_settle` also keeps its own check)

A rejection leaves the hand unchanged. The guard comes first because a payout can clear `all_in` and make a settled hand look open to further dealing or betting.

Internal helpers (`commit_chips`, `return_chips`, `collect_round`, payout) and derived reads (`legal_actions`, `is_betting_closed`, `pots`, `middle_pot`) are not guarded. This is a guard, not immutability: the `Player` objects are shared with the table, so their stacks still change in later hands.

## Durable Invariants

Before settlement:

`player.stack + player.total_contribution`

equals that player's chips at hand start.

After settlement:

`player.stack == starting_chips - total_contribution + payout`

`sum(payouts) == middle_pot == sum(pot.amount)`, each pot's shares add up to its amount, and only eligible, non-folded seats are paid.

Across the hand:

`middle_pot + sum(street_contribution) == sum(total_contribution)`

and:

`sum(pot.amount) == middle_pot`

These remain true after settlement as accounting identities over the unchanged contributions, not as physical chip conservation. After settlement, current chips are conserved as `sum(player.stack) == sum(starting_chips)`.

Other invariants:

- a participant is `all_in` exactly when their stack is zero, before and after payout;
- a settled hand (`hand.settlement is not None`) is rejected first by every public hand-level mutation entry point, leaving it unchanged;
- settlement is stored once; contributions, `folded`, hole cards, board, burned cards, the deck, the betting state, and derived pots are unchanged by it;
- betting moves chips between stacks and contributions only through `commit_chips` and `return_chips`;
- no street contribution exceeds `current_bet`;
- completed rounds have no chips in front;
- unmatched top excess is returned before pot derivation;
- `last_full_raise_size` changes only after a full bet/raise;
- `acted_at_bet` contains exactly players who acted this round;
- folded players are never pot-eligible;
- every pot has at least one eligible seat, and each pot's eligible seats are a subset of the previous pot's;
- rejected operations do not partially mutate state.

## Variant and Betting-Structure Strategy

Variant and betting structure are separate dimensions.

Examples:

- Texas Hold'em + No Limit
- Omaha + Pot Limit
- Pineapple + an appropriate betting structure

Texas Hold'em, Omaha, and Pineapple may share community-card hand infrastructure where concrete implementations prove it useful.

Variant-specific dealing and evaluation rules remain under `game/variants/`.

Do not create variant base classes, protocols, factories, or registries before multiple implementations demonstrate the shared abstraction.

Chinese Poker is a separate game family and should not be forced into the `PokerHand` community-card model.
