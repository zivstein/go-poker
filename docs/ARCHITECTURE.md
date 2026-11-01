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
| `game/` | players, seats, table, lifecycle, hand setup, per-hand state, hand history, showdown, settlement |
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
- best-of-5–7 evaluation;
- `BestHand` (see [Hand Strength](#hand-strength)).

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

- `player_id`, the participant's stable logical identity (see below);
- stack;
- participation status: `WAITING`, `READY`, or `SITTING_OUT`.

`Player` is a poker participant, not an account or user identity. Accounts and authentication stay outside the engine, and bots and guests must be able to participate without an account.

`player_id` is an opaque, caller-assigned string ([ADR 0004](adr/0004-hand-history-and-event-contract.md) §6). It must be a non-empty `str` (whitespace is allowed and kept as given), is read-only after creation, and is validated before the stack (`InvalidPlayerIdError`). The engine enforces only the existing `Table.sit_in` rule that it is unique among the players currently seated, by equality. `Table` and `HoldemGame` keep no registry of past ids, so keeping an id consistent beyond the current table is the caller's duty. It is not a display name or an account or platform identity.

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

Hand numbers come from the caller: `start_game` creates hand 1, and `start_next_hand(table, hand_number)` numbers the hand as given and keeps no counter. A number that is not a positive integer raises `InvalidHandNumberError` before any other check or change, so a rejected number never leaves a promoted entrant behind.

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
- optional immutable `Settlement`, present only once the hand is settled;
- optional immutable `Showdown`, present only once the hand's showdown has started (see [Showdown](#showdown)); decisions replace it with a new record, never mutate it;
- its immutable `history` (see [Hand History](#hand-history)).

It is created as `PokerHand(players, deck, number)`. The number must be a positive integer (`InvalidHandNumberError`), the hand starts preflop with an empty board, and `history` is not a constructor argument. `number` is a read-only property that reads the history.

It is a state container rather than the owner of participation, variant dealing, or betting rules.

The settlement marker's presence makes every public hand-level mutation entry point reject the hand first with `HandAlreadySettledError` (see [Settled-Hand Guard](#settled-hand-guard)).

The showdown record is separate from the settlement, is started at most once, and afterwards changes only by adding one decision at a time, never once complete.

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

### Hand History

`game/hand_history.py` holds the variant-agnostic, immutable record of a hand. The contract is in [ADR 0004](adr/0004-hand-history-and-event-contract.md); this section describes only what is implemented.

- `HandHistory(events)` holds only `events`; `number` and `participants` read `events[0]`, which must be a `HandStarted` (`TypeError` otherwise). It does not validate on construction.
- `HandParticipant(seat, player_id, position, blind, starting_stack)` takes its values from the hand's players when `PokerHand` is constructed. The participants follow the hand's player order, button first, and `starting_stack` is the stack before any blind is posted.
- Recording appends through the private `_appended`, which returns a new history and leaves the old one unchanged. Each public low-level operation builds its events from locals and assigns `hand.history` once, after every mutation, so a rejected operation leaves the history equal to its previous value. Derived reads, internal helpers, `hand_flow` and `HoldemGame` record nothing.

`HandEvent` is the closed union of the eleven event types below: no base class, protocol, or registry. `PokerHand` owns its history, and a hand's completed history, not the settled hand, is the durable snapshot of it. It is immutable, compares by value, and does not change when the live `Player` objects or later hands do.

The events, each recorded by the operation that causes it, in the same call:

| Event | Recorded by | Facts |
| --- | --- | --- |
| `HandStarted` | `PokerHand` construction | `number`; `participants` |
| `BlindsPosted` | `initialize_betting` | `stakes`; `posts`, `BlindPost(seat, blind, chips, all_in)` for the small then the big blind, `chips` the amount actually posted, `all_in` right after that post |
| `HoleCardsDealt` | `deal_hole_cards` | `hole_cards`, `SeatHoleCards(seat, cards)` in hand order, each seat's cards in the order it received them |
| `StreetDealt` | `deal_next_street` | `street`; the `burned` cards and board `cards` of this call only |
| `BettingRoundStarted` | `start_betting_round` | `street`; never recorded for the preflop, whose start is `BlindsPosted` |
| `ActionTaken` | `apply_action` | `seat`; the `action` as requested (a bet or raise keeps its target); `chips` actually committed (0 for a fold or check); `all_in` right after the commit |
| `ChipsReturned` | the operation that completes a round | `seat`; the uncalled `chips` returned |
| `BettingRoundCompleted` | the operation that completes a round | `street` |
| `ShowdownStarted` | `start_showdown`; `settle_hand` when it builds the `ALL_IN` showdown itself | `kind`; `order`, equal to `hand.showdown.order` at the start: the decision order for `INTERACTIVE`, the canonical storage order (not a sequence) for `ALL_IN` |
| `ShowdownDecided` | `apply_showdown_action` | `seat`; `action`, SHOW or MUCK |
| `HandSettled` | `settle_hand` | `settlement`, equal to `hand.settlement`; always the last event |

Order within one operation: `ActionTaken`, then any `ChipsReturned`, then `BettingRoundCompleted`; when the blinds alone complete the preflop round, `BlindsPosted`, then any `ChipsReturned`, then `BettingRoundCompleted(PREFLOP)`. `start_betting_round` records `BettingRoundStarted`, and when nobody is pending the round is complete as it starts, so it also records `BettingRoundCompleted` for the same street in the same call; it never records `ChipsReturned`, because a new round has nothing in front to collect. `settle_hand` records `HandSettled` once, after the payout, in a single history assignment. An uncontested hand records `HandSettled` alone, with no showdown event. A contested hand with a started showdown (complete, by decisions or because it is `ALL_IN`) records `HandSettled` alone, so its start is never recorded twice. A contested `ALL_IN` hand with no started showdown records `ShowdownStarted` and then `HandSettled` in that one assignment, made only after the settlement succeeded, so a rejected settlement never leaves a lone `ShowdownStarted`; every contested hand's history therefore holds its showdown start even when no showdown action ever happens.

Two levels of order guarantee. Across low-level operations events follow the order of the successful calls and are not normalized: `begin_hand` (blinds, then hole cards) and a caller who deals first produce different, equally valid, histories, and a caller who deals the whole board and then settles an `ALL_IN` hand directly has `StreetDealt` ×3, then `ShowdownStarted`, then `HandSettled`, which makes no runout claim. Through `begin_hand` and `act` the presentation order is guaranteed:

- an `INTERACTIVE` showdown starts right after the river round completes, then come the decisions in decision order (the last contender is never asked, so it has no `ShowdownDecided`), then `HandSettled`;
- an `ALL_IN` showdown starts right after the betting that decided the hand (after the hole cards when the blinds alone decide it), before any runout street; then come the remaining streets with no `BettingRoundStarted`, then `HandSettled`. No `ShowdownDecided` is ever recorded for it;
- a hand decided by the river round has no runout streets; an uncontested hand has neither showdown event.

`HandHistory.is_complete` is true exactly when the last event is `HandSettled`, and `HandHistory.settlement` is that event's settlement, or `None` while the history is incomplete. A history taken mid-hand stays incomplete after the hand completes. Both are derived reads: nothing is stored or validated.

The history alone replays every M6 fact: the participants and starting stacks, the board and burned cards, every betting action, the showdown kind, order and decisions, the settlement, and the final stacks, per seat, as `starting_stack − blind chips − action chips + returned chips + the shares in the settlement's pot awards`. A paid seat is no longer all-in; an unpaid all-in seat keeps a zero stack. Reading a history, never the live hand, is how a client sees the hand once later hands have moved the stacks.

It is a record, not event sourcing: no rule reads it. Its fields are immutable values and it is compared by value equality, never by identity, so it does not change when the live `Player` objects do.

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
- `acted_at_bet`;
- `last_aggressor`.

`current_bet` is the nominal target a fully funded player normally matches.

A short blind or call may leave all actual contributions below it.

Invariant:

`street_contribution <= current_bet`

`last_full_raise_size` changes only after a full bet or raise.

`acted_at_bet[seat]` stores the `current_bet` immediately after that player's latest action in the round.

Posting a blind is not an action.

`last_aggressor` is the seat of the last bet or raise in the current round, including a short all-in bet or raise, or `None`. Checks, calls, and folds never change it. It is `None` when the blinds are posted and whenever a betting round starts, so an earlier street's aggressor never carries into a later round. It exists for the river decision order (see [Showdown](#showdown)).

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

`apply_action` applies one action and collects the round it completes; it never deals, starts the next round or a showdown, or settles. Those steps are the caller's with the low-level operations, and `hand_flow` performs them (see [Hand Flow](#hand-flow)).

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
- no `last_aggressor`;
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

Collection happens when the operation completing the round runs. `collect_round` records nothing: it reports the returned excess as the seat and chips to the calling operation (`initialize_betting` or `apply_action`), or nothing when none was returned, and that operation records the `ChipsReturned` event and the `BettingRoundCompleted` event (see [Hand History](#hand-history)).

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

Settlement turns the contested pots into stack payouts and records the result. The contracts are in [ADR 0001](adr/0001-showdown-settlement-contract.md) and [ADR 0003](adr/0003-interactive-showdown-and-muck.md), which supersedes parts of ADR 0001 and [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md).

| Module | Responsibility |
| --- | --- |
| `game/settlement.py` | variant- and betting-structure-agnostic: `PotAward`, `Settlement`, pot awarding among the final contenders (winners, ties, odd chips), the internal `_settle` operation and payout, `SettlementInvariantError`; re-exports `HandAlreadySettledError` (see [Settled-Hand Guard](#settled-hand-guard)). It never interprets a showdown action |
| `game/showdown.py` | variant-agnostic: `Showdown`, `ShowdownKind`, `ShowdownAction`, the derived showdown state, the turn rule `Showdown.decide` and `NotShowdownTurnError`, canonical seat order and the decision-order helper (see [Showdown](#showdown)); imports neither `settlement.py` nor `poker_hand.py` |
| `game/variants/texas_holdem/showdown.py` | Hold'em: the internal showdown classification and readiness rule, the internal `_showdown_ranks`, the public `start_showdown`, `apply_showdown_action` and `settle_hand`, `IncompleteBoardError`, `ShowdownNotReadyError`, `UncontestedHandError`, `ShowdownAlreadyStartedError`, `ShowdownNotStartedError`, `ShowdownIncompleteError` |
| `game/variants/texas_holdem/hand_strength.py` | Hold'em: the public derived reads `holdem_hand_strength` and `hand_strength`, and `SeatNotInHandError` (see [Hand Strength](#hand-strength)) |
| `game/variants/texas_holdem/hand_flow.py` | Hold'em: single-hand orchestration over the operations above (see [Hand Flow](#hand-flow)) |
| `game/variants/texas_holdem/game.py` | Hold'em: `HoldemGame`, the continuous game over the lifecycle and `hand_flow`, and `HandInProgressError` (see [Hold'em Game](#holdem-game)) |

`settle_hand(hand)` is the only public settle entry; `start_showdown(hand)` and `apply_showdown_action(hand, seat, action)` are the only public showdown entries. `_settle(hand, ranks, contenders)` is shared engine implementation for variant entry points and is not a client-facing API; it returns the `Settlement` it stored and records no history, which `settle_hand` does. `_showdown_ranks(hand, seats)` is internal; the public derived read is [Hand Strength](#hand-strength).

`PotAward` holds a `Pot` and the exact chips each winning seat receives, ordered clockwise from the button. Odd chips make amounts unequal. The pot is the pot as derived and contested: its eligible seats can include a seat that mucked and won nothing.

`Settlement` holds the pot awards and the showdown `HandRank` of each shown player, in hand order, empty when nobody showed: an uncontested hand, or a contested hand whose last contender won without showing. Per-seat payouts and winners are derived, never stored.

Each pot is awarded among its final contenders: its eligible seats that are showdown contenders. A pot with one final contender goes wholly to it without consulting ranks. Otherwise the best rank among the final contenders wins and equal ranks split the pot independently of other pots: each tied winner gets `amount // winners`, and the remainder goes one chip at a time to tied winners clockwise from the first seat left of the button.

Two pot invariants hold for every settlement and are checked for every pot before anything changes: every pot has at least one final contender, and a pot with more than one has a rank for each of them. A violation raises `SettlementInvariantError`, an engine defect with no fallback payout. No public sequence produces one, so it is tested against the internal settlement function.

### Settling a Hold'em Hand

`settle_hand(hand)` validates in this order, and a rejection leaves the hand unchanged:

1. the hand is already settled: `HandAlreadySettledError`; this comes first because a payout can clear `all_in` and make betting look open again;
2. the hand has no betting state: `BettingNotInitializedError`;
3. exactly one player has not folded: the hand is settled uncontested on any street, with nothing evaluated and no showdown recorded;
4. the board is incomplete: `IncompleteBoardError`;
5. further betting is possible: `ShowdownNotReadyError`;
6. the showdown is not complete: an `INTERACTIVE` hand with no started showdown raises `ShowdownNotStartedError`, and a started showdown with pending decisions raises `ShowdownIncompleteError`. A contested `ALL_IN` hand with no showdown yet is not rejected: its complete showdown is built from the hand as it is before the payout;
7. only the shown hands are evaluated, and only their hole cards are checked (`InvalidHoleCardCountError`);
8. `_settle` awards each pot among its final contenders, checks the pot invariants and pays;
9. only after the settlement succeeds is a built `ALL_IN` showdown stored on `hand.showdown`, and the history is extended in one assignment: `HandSettled`, preceded by `ShowdownStarted` only when settlement built the showdown. An existing showdown is kept as the same object, and its start was already recorded.

A contested hand is ready by the showdown classification (see [Showdown](#showdown)), which `start_showdown` and `settle_hand` share. A river dealt without its round started, while two players can act, is not ready. Remaining streets after an all-in need to be dealt, but their betting rounds need not be started.

`Settlement`, `_settle`, and the settlement's odd-chip order do not depend on the showdown module; the two orders happen to rotate seats the same way but are separate contracts.

### Showdown

A showdown records which live seats reach showdown, of which kind, and the SHOW or MUCK decisions made so far. It records seats and decisions, not cards: hole cards, including mucked and unshown ones, stay in engine state, and who may see them is a matter for a future API projection. The contract is in [ADR 0003](adr/0003-interactive-showdown-and-muck.md).

`Showdown(kind, order, decisions)` is immutable. `ShowdownKind` is `ALL_IN` or `INTERACTIVE`; `ShowdownAction` is `SHOW` or `MUCK`. `order` holds the live seats when the showdown starts and never changes; folded seats never appear and the winner of an uncontested hand has no showdown. `decisions[i]` is the decision of `order[i]`, and an `ALL_IN` showdown has none.

Shown seats, mucked seats, contenders, the current decider and completion are derived from `order` and `decisions`, never stored:

- `ALL_IN`: every live hand is tabled at once. Every seat is shown and a contender, none is mucked, the showdown is complete from the start and nobody decides. `order` is canonical seat order, which is storage order only and not a sequence.
- `INTERACTIVE`: `shown` and `mucked` are the seats in `order` whose decision is SHOW or MUCK; `contenders` are the seats in `order` that have not mucked, undecided seats included. The showdown is complete when every seat has decided or only one contender remains; that last contender is not asked to decide and wins without showing. The current decider is `order[len(decisions)]` until complete, then `None`.

`Showdown.decide(seat, action)` is the turn rule: it returns a new record with the decision appended and leaves the old one unchanged, and raises `NotShowdownTurnError` when the showdown is complete (an `ALL_IN` showdown always is) or `seat` is not the current decider, then `TypeError` when `action` is not a `ShowdownAction`, so an unsupported action is never stored. A muck is showdown state only: the seat is not `folded`, and its contributions and the betting state are unchanged. The decider may always SHOW or MUCK; the engine does not judge whether a shown hand already beats theirs.

`Showdown` does no validation when constructed. Engine-owned showdown state produced through the supported operations is well-formed: `start_showdown` creates the initial valid record and `decide` produces each later valid immutable record. Directly constructing a record or manually injecting invalid hand state is outside the supported engine-operation contract; validating externally reconstructed or persisted state belongs at that external boundary when there is one.

`game/showdown.py` provides canonical seat order (clockwise starting with the first seat left of the button, the button last; heads-up the big blind first) and a decision-order helper: the live seats in canonical order, rotated to start at the last aggressor when one is given. The helpers take seat sequences, so they know nothing about streets or kinds of showdown.

One engine-internal Hold'em rule in `showdown.py` classifies a hand with at least two live players as not ready, `ALL_IN`, or `INTERACTIVE`:

- ready: the current betting round is complete and either it is the river round or `is_betting_closed(hand)`;
- `ALL_IN` when any live player is all-in, else `INTERACTIVE`. A closed round before the river with two or more live players always has a live all-in player.

All-in is read after the river round is collected and before payout.

- `ALL_IN`: every live seat in canonical order, ignoring the last aggressor, including when a player all-in from an earlier street faces two others who bet the river. The remaining board is then run out.
- `INTERACTIVE`: the river decision order. The river round's `last_aggressor` decides first, then clockwise; with no river bet or raise, the first live seat left of the button decides first.

`start_showdown(hand)` validates in this order, and a rejection leaves the hand unchanged:

1. the hand is already settled: `HandAlreadySettledError`;
2. the hand has no betting state: `BettingNotInitializedError`;
3. the showdown has already started: `ShowdownAlreadyStartedError`;
4. fewer than two players have not folded: `UncontestedHandError`;
5. further betting is possible: `ShowdownNotReadyError`.

Otherwise it sets only `hand.showdown` and records `ShowdownStarted` (the showdown's kind and order) after it, for both kinds. Completing the river round does not start the showdown. It checks neither the board nor hole cards, so betting closed before the board is run out starts its showdown at once.

`apply_showdown_action(hand, seat, action)` validates in this order, and a rejection leaves the hand unchanged:

1. the hand is already settled: `HandAlreadySettledError`;
2. the showdown has not started: `ShowdownNotStartedError`;
3. the showdown is complete or `seat` is not its current decider, including any decision on an `ALL_IN` showdown: `NotShowdownTurnError`;
4. `action` is not a `ShowdownAction`: `TypeError`. Only `ShowdownAction` is accepted; the check is made once, in `Showdown.decide`, after the turn.

Otherwise it sets only `hand.showdown`, to the record with the decision added, and records one `ShowdownDecided` after it.

### Hand Flow

`game/variants/texas_holdem/hand_flow.py` runs one Hold'em hand so that the caller never collects, deals, starts a betting round or a showdown, or settles. It only coordinates the existing operations: it stores no phase (each next step is derived from the hand) and contains no poker rules. The contract is in [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md) and [ADR 0003](adr/0003-interactive-showdown-and-muck.md).

The low-level operations stay public with unchanged contracts. Mixing both levels within one hand is not supported.

Entry points:

- `begin_hand(hand, stakes)`: posts the blinds, deals the hole cards, then advances;
- `act(hand, seat, action)`: applies a betting `Action` or a `ShowdownAction`, then advances; returns `None`;
- `current_actor(hand)`: a derived, unguarded read of who must act next.

`current_actor(hand)` is `None` for a settled hand; otherwise `hand.betting.current_actor` when betting exists and has an actor; otherwise `hand.showdown.current_decider` when a showdown exists; otherwise `None`, which includes a hand that has not begun.

After a successful `begin_hand` or `act`, `_advance` repeats these steps until one says stop:

1. the hand is settled: stop;
2. exactly one player has not folded: `settle_hand` (which owns the uncontested path), stop. This precedes the showdown classification, which assumes at least two live players;
3. a betting actor exists: stop. The operation that completed a betting round has already collected it; `_advance` never collects;
4. a showdown exists: stop while it is incomplete (only `INTERACTIVE`); once complete, deal the remaining streets up to the river without starting their betting rounds, then `settle_hand`, stop;
5. the hand's showdown is certain (the classification of [Showdown](#showdown)): `start_showdown`, then the next pass (an `ALL_IN` showdown is complete at once and runs out and settles; an `INTERACTIVE` one stops at its first decider);
6. otherwise deal the next street and start its betting round, then the next pass.

Every pass stops or makes progress, so `_advance` always ends; it has no iteration cap or fallback.

`act` validates in this order, and a rejection leaves the hand unchanged and does not advance:

1. the hand is already settled: `HandAlreadySettledError`, whatever the action is;
2. `action` is neither an `Action` nor a `ShowdownAction`: `TypeError`, before any turn check;
3. the errors of `apply_showdown_action` or `apply_action`, unchanged: a showdown action during betting raises `ShowdownNotStartedError`, a betting action during a showdown `NotPlayersTurnError`, a wrong decider `NotShowdownTurnError`, a wrong betting seat `NotPlayersTurnError`, an illegal action `IllegalActionError`.

`begin_hand` validates in this order, before anything changes:

1. the hand is already settled: `HandAlreadySettledError`;
2. the checks of `initialize_betting`: `BettingAlreadyInitializedError`, then `BettingNotPreflopError`;
3. the checks of `deal_hole_cards`: `HandPastPreflopError`, `HoleCardsAlreadyDealtError`, `DeckEmptyError`.

Each low-level operation and `begin_hand` share one private validator per operation, so the checks have one source.

Atomicity is narrow. The expected public precondition and validation rejections of `begin_hand` and `act` leave the hand unchanged. Once valid execution begins, an unexpected internal engine defect raised later, for example while advancing, propagates; there is no rollback or transaction guarantee.

### Hold'em Game

`game/variants/texas_holdem/game.py` runs a table hand after hand. `HoldemGame(table, stakes)` composes `game_lifecycle` and `hand_flow` and holds only the table, the stakes and the current hand. The contract is in [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md); the constructor changes nothing.

It owns no button, participation, turn, legal-action or settlement rule, and stores no phase, actor or "started" flag. `hand is None` is the only sign that the instance has not started, and a hand is finished exactly when `hand.settlement is not None`. The stakes are fixed for the instance's lifetime, as current behavior; any change is a future decision tracked in the [roadmap](ROADMAP.md).

Public surface:

- `start(choose_button)`: `start_game`, then `begin_hand`; sets and returns the first hand;
- `next_hand()`: `start_next_hand` with the current hand's number plus one, then `begin_hand`; sets and returns the next hand;
- `act(seat, action)`: `hand_flow.act` on the current hand, unchanged; returns `None`;
- `hand`: the current `PokerHand`, read-only, `None` before `start`.

Hands are numbered 1, 2, 3, … consecutively. The next number is derived from the current hand; the game keeps no counter and no past histories (a caller who wants them keeps the `hand.history` values). A rejected `next_hand` consumes no number, because `hand` is replaced only on success.

A returned hand is settled (the blinds alone can end it) or waits for a betting actor or showdown decider (see `current_actor` under [Hand Flow](#hand-flow)).

Rejections, checked in this order, each leaving the table, the players, `game.hand` and the hand unchanged:

- `start`: a game that already has a hand, settled or not, raises `GameAlreadyStartedError`, before anything else; then the errors of `start_game` pass through. `start` is a one-time operation per instance, never a reset or restart, even when no `READY` player is seated any more;
- `next_hand`: `GameNotStartedError` before `start`; `HandInProgressError` while the current hand is not settled; then the errors of `start_next_hand` pass through unchanged;
- `act`: `GameNotStartedError` before `start`; then the errors of `hand_flow.act`, including `HandAlreadySettledError` for a settled hand.

`game.hand` is replaced only after both the lifecycle call and `begin_hand` succeed. Atomicity is narrow, as in [Hand Flow](#hand-flow): the lifecycle rolls back its own changes, but an unexpected engine defect raised after it returned propagates with no rollback.

There is no game-over state. With busts only, `next_hand` fails with `InvalidPlayerCount` when fewer than two players can play, and nothing changes; seating a new player with chips lets it succeed. The lifecycle's `GameNotStartedError` arises from `next_hand` only when status or seating changes (for example sitting out or standing up the remaining `READY` players with chips) leave no `READY` player with chips. If `next_hand` cannot proceed because of seating or status configuration, the caller corrects that configuration; `start` is not the recovery path.

Caller precondition, not enforced ([ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md) §9): during a hand, do not stand up a hand participant or directly change a participant's stack. A status change during a hand affects only later hands. Mixing this level with low-level calls on `game.hand` is not supported.

A `Table` is not locked to one `HoldemGame`. Driving the same table through multiple `HoldemGame` instances is unsupported; exclusive table/session ownership is deferred to a later session/platform boundary.

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
- `start_showdown`
- `apply_showdown_action`
- `settle_hand` (the internal `_settle` also keeps its own check)
- `begin_hand`
- `act`

`HoldemGame.act` is guarded through `hand_flow.act`.

A rejection leaves the hand unchanged. The guard comes first because a payout can clear `all_in` and make a settled hand look open to further dealing or betting.

Internal helpers (`commit_chips`, `return_chips`, `collect_round`, payout) and derived reads (`legal_actions`, `is_betting_closed`, `pots`, `middle_pot`, `hand_strength`) are not guarded. This is a guard, not immutability: the `Player` objects are shared with the table, so their stacks still change in later hands.

## Hand Strength

A seat's current hand strength is derived on demand and never stored: not on `PokerHand`, the showdown, or the settlement. `core/best_hand.py` owns `BestHand`; `game/variants/texas_holdem/hand_strength.py` owns the Hold'em reads. The product decisions are in [ROADMAP.md](ROADMAP.md).

`BestHand` is a frozen dataclass of `rank: HandRank` (not a `Card.rank`) and `cards`, exactly five. Its `description` is a read-only property derived from `rank`, so the two cannot disagree. It has no ordering: compare strengths through `rank`. It is built by the engine and not validated on construction.

- `holdem_hand_strength(hole_cards, board)` returns a `BestHand`, or `None` for an empty board.
- `hand_strength(hand, seat)` reads it for a seat of a hand: `holdem_hand_strength` of the seat's hole cards and the hand's board.

### Evaluation and Selection

There is one evaluation path. The private `_best_fives` in `core/evaluator.py` validates 5–7 cards as `evaluate_best` does, evaluates each five-card combination once, and returns the best `HandRank` with every combination that achieves it; `evaluate_best` is its rank. `holdem_hand_strength` evaluates the same hole-then-board cards `_showdown_ranks` gives `evaluate_best`, so a river strength always equals the seat's settlement rank. Core knows nothing of hole cards and the board, and there is no public tie-selection parameter.

When several combinations share the best rank, the one using the fewest hole cards is chosen, then the one whose deal positions are earliest, comparing the sorted positions lexicographically. A card's position is its index in the board in dealt order followed by the hole cards in dealt order. A board that plays on the river is therefore returned as it is. The choice changes which cards are reported, never the rank.

The five cards are ordered by significance: those whose rank occurs more often in the five first, then by rank high to low, with the Ace low in the wheel. This gives quads then kicker, trips then pair, trips then kickers, two pair high then low then kicker, a pair then kickers, straights high to low (the wheel is 5-4-3-2-A), and flush and high-card hands high to low. Cards of equal rank keep deal order, board cards first.

### Descriptions

English only, derived from the category and tiebreakers, with no kickers. The wording is in [ROADMAP.md](ROADMAP.md); the rank names are Two to Ten, Jack, Queen, King and Ace, with an explicit plural table ("Sixes"), and `Rank.__str__` is unchanged. A wheel straight or straight flush is "Five-high", and an Ace-high straight flush is "Royal flush".

### Inputs and Errors

`holdem_hand_strength` validates in this order, before evaluating anything:

1. not exactly two hole cards: `InvalidHoleCardCountError`, even preflop;
2. a board of other than 0, 3, 4 or 5 cards: `WrongCardAmountError`;
3. a duplicate card among the hole cards and the board: `DuplicateCardsError`, even preflop;
4. an empty board: `None`.

`None` therefore means a valid hand with two hole cards and no board. `hand_strength` first rejects a seat that does not play in the hand with `SeatNotInHandError`; a seat whose hole cards are not yet dealt then raises `InvalidHoleCardCountError`.

`hand_strength` is a read and not guarded against a settled hand. It consults neither the betting, the showdown, the street, the deck, nor the settlement, so it works for folded, mucked and settled seats. It never changes the hand, and a `BestHand` holds fresh tuples, never the hand's lists. Who may see a seat's strength is the concern of a future API projection.

## Durable Invariants

Before settlement:

`player.stack + player.total_contribution`

equals that player's chips at hand start.

After settlement:

`player.stack == starting_chips - total_contribution + payout`

`sum(payouts) == middle_pot == sum(pot.amount)`, each pot's shares add up to its amount, and only eligible showdown contenders are paid (a mucked seat is never paid).

Across the hand:

`middle_pot + sum(street_contribution) == sum(total_contribution)`

and:

`sum(pot.amount) == middle_pot`

These remain true after settlement as accounting identities over the unchanged contributions, not as physical chip conservation. After settlement, current chips are conserved as `sum(player.stack) == sum(starting_chips)`.

Other invariants:

- a participant is `all_in` exactly when their stack is zero, before and after payout;
- a settled hand (`hand.settlement is not None`) is rejected first by every public hand-level mutation entry point, leaving it unchanged;
- across a `HoldemGame`, `sum(player.stack)` over the seated players is conserved from hand to hand, absent caller seating changes (a player who sits down or stands up takes their chips with them);
- under `hand_flow`, every successful `begin_hand` or `act` ends with a betting actor, a showdown decider, or a settlement;
- `hand.showdown` is `None` or its `order` is exactly the non-folded seats; an `ALL_IN` showdown has its seats in canonical order and no decisions; decisions are only added, one at a time, never once complete; a mucked seat is never folded;
- a settled contested hand has a complete showdown; an uncontested hand has none;
- `Settlement.showdown_ranks` holds exactly the shown seats;
- every pot has at least one final contender among its eligible seats, and a pot with more than one has a showdown rank for each;
- every completed hand has a complete history: `hand.history.is_complete` holds exactly when `hand.settlement is not None`, and `hand.history.settlement == hand.settlement`; a history starts with exactly one `HandStarted`, ends with exactly one `HandSettled` when complete, and holds a `ShowdownStarted` exactly when the hand was contested, whose `ShowdownDecided` events are the showdown's decisions in order;
- the final stacks folded from a completed history alone equal the live stacks at settlement, and they conserve chips; its pot awards are the pots layered from the replayed contributions;
- settlement is stored once; contributions, `folded`, hole cards, board, burned cards, the deck, the betting state, and derived pots are unchanged by it;
- betting moves chips between stacks and contributions only through `commit_chips` and `return_chips`;
- no street contribution exceeds `current_bet`;
- completed rounds have no chips in front;
- unmatched top excess is returned before pot derivation;
- `last_full_raise_size` changes only after a full bet/raise;
- `acted_at_bet` contains exactly players who acted this round;
- `last_aggressor` is `None` until someone bets or raises in the round, then the last bettor or raiser;
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
