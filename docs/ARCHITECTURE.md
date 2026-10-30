# Go! Poker Architecture

This document records the engine's architecture decisions and ownership boundaries. It describes both what exists today and the agreed direction for planned work; each section says which is which.

For the module tree and feature list, see the [README](../README.md). For planned work, see the [roadmap](ROADMAP.md) and the [current cycle](CURRENT_CYCLE.md).

## Principles

- The poker engine is independent from accounts, persistence, APIs, and clients. Clients consume the engine; they never reimplement poker rules.
- Poker rules and game-state decisions live in the engine.
- Each piece of state has exactly one owner. No duplicate sources of truth.
- The engine evolves incrementally toward multiple poker variants and betting structures, without introducing abstractions before a second implementation shows what is shared.

## Layers

| Layer | Status | Responsibility | Must not depend on |
| --- | --- | --- | --- |
| `core/` | Current | Cards, deck, hand evaluation | Tables, players, accounts, APIs, clients |
| `game/` | Current | Players, seats, table, game lifecycle, hand setup, streets, and the `PokerHand` aggregate | Accounts, persistence, APIs, clients |
| `game/variants/` | Current | Variant-specific poker rules; first implementation in `game/variants/texas_holdem/`: hole-card and board dealing | Accounts, persistence, APIs, clients |
| `game/betting/` | Current | Betting-structure–specific rules; first implementation: No-Limit betting (milestone 2): stakes, betting state, chip commitment, betting initialization with blind posting, the action model, No-Limit sizing, legal actions, applying actions, betting-round progression, and later-street round starts (see [Betting](#betting-milestone-2)). Milestone 3 (planned) adds short all-ins and short blinds, raise reopening, the end-of-round collection, and derived main and side pots (see [All-ins and pots](#all-ins-and-pots-milestone-3-planned)) | Accounts, persistence, APIs, clients |
| Hand history / events | Planned (milestone 6) | Structured raw record of every hand | APIs, clients |
| Accounts, persistence, API, clients | Planned (milestones 13+) | Users, storage, networking, presentation | — (they depend on the engine, never the reverse) |

Paths are relative to `src/go_poker/`. The `game/variants/` and `game/betting/` locations are module-ownership decisions; a package is created only when its first responsibility appears. `game/variants/` exists (Texas Hold'em dealing); `game/betting/` exists (No-Limit betting, built up through milestone 2).

## Core

`core/` is pure card, deck, and hand-evaluation functionality: `Card`, `Rank`, `Suit`, `Deck`, `HandRank`, and the evaluator. It has no knowledge of tables, players, hands in play, accounts, APIs, or clients, and it stays that way.

**Randomness rule.** A new `Deck()` is in creation order until shuffled. `Deck.shuffle()` uses the OS CSPRNG through the module-private `random.SystemRandom` instance `_SYSTEM_RANDOM` (it cannot be seeded), so engine shuffles are never reproducible.

- The security boundary is that production APIs and clients never control the shuffle RNG. No lifecycle or dealing function takes an RNG argument; `start_game` and `start_next_hand` always call `Deck.shuffle()` with no arguments.
- The only RNG input is the test seam `Deck.shuffle(*, _rng=None)`: tests pass a seeded `random.Random` to get a reproducible deck order. Engine code never passes it.
- The leading underscore on `_rng` and `_SYSTEM_RANDOM` is a naming convention that marks test-only or private use. It is not a security mechanism.
- Tests that need deterministic (or failing) shuffles above the `Deck` layer, for example through the lifecycle, patch `Deck.shuffle` inside the test to forward a seeded (or failing) `_rng` to the original method, so `_rng` stays the only seam. Only `Deck`'s own tests replace `_SYSTEM_RANDOM`, to check the deck's default generator at the layer that owns it.

## Game domain (current)

Persistent runtime state is kept separate from state that belongs to one hand.

**Persistent state**

- `Player` — a poker participant with an id, a chip stack, and a `PlayerStatus` (`WAITING`, `READY`, `SITTING_OUT`).
- `Seat` — one physical seat, holding at most one `Player`.
- `Table` — owns the physical seats, seating rules (sit in, stand up), and the stored button seat. `Table` does **not** own `PlayerStatus` lifecycle policy or button traversal policy; it stores the button but never decides where it moves.

**Rules that operate on that state**

- `hand_setup` — owns hand participation and `WAITING` entry rules: which seated players take part in the next hand (`READY` or `WAITING`, with chips; see the start-of-hand chip rule below), and when a waiting player may enter (big blind or a non-blind position, never button or small blind).
- `game_lifecycle` — owns explicit game start and restart (`start_game`, with an injected button chooser) and button traversal between hands (`start_next_hand`). Both create a fresh `Deck()`, shuffle it securely before hand setup (so a shuffle failure is rolled back like any other), and pass it to the new `PokerHand`. The lifecycle owns the shuffle policy. Seating alone never starts a game. Only players with chips count: `start_game`'s starters are the seated `WAITING` players with chips (only they are counted, offered to the button chooser, and made `READY`), while its game-already-started guard still looks at every seated `READY` player; `start_next_hand` moves the button among `READY` players with chips, anchored clockwise on the previous button seat even when that player has no chips left. The lifecycle is variant-agnostic: it deals no cards, so the new hand starts on `PREFLOP` with an empty board and no burned cards; the caller applies variant dealing (for example `texas_holdem.dealing.deal_hole_cards`, then `deal_next_street`) to the returned `PokerHand`.
- `position` / `position_assignment` — positions and blinds relative to the button for a given set of seats.

**Start-of-hand chip rule.** A player with no chips (`stack == 0`) at the start of a new hand does not take part in it and cannot receive the button; a player with a positive stack smaller than a blind does take part. The rule is defined once in `hand_setup` (`has_chips_for_hand`) and reused by `game_lifecycle`. Running out of chips does not change `PlayerStatus`: a player with no chips may stay seated and `READY` (or `WAITING`) and is simply not dealt into new hands. There is no bust, rebuy, reload, or top-up policy yet.

**Known deferred case: every `READY` player has no chips.** `start_next_hand` cannot continue (`GameNotStartedError`), and `start_game` cannot restart while those `READY` players remain seated (`GameAlreadyStartedError`). Today the caller must stand those players up or change their status. An automatic bust, rebuy, or status-transition policy is intentionally deferred: it is not part of Milestone 2 and will be decided when such a policy is planned.

**Per-hand state**

- `PokerHand` — the aggregate for one hand (see [below](#pokerhand)).
- `HandPlayerState` — one player's state for one hand: seat, position, blind, hand flags (`folded`, `all_in`), betting contributions (`street_contribution`, `total_contribution`), and hole cards. It references the persistent `Player` rather than copying it.

## PokerHand

`PokerHand` is the aggregate for one hand. It owns:

- the participating `HandPlayerState` objects, in the order `setup_hand` produces them (clockwise from the button)
- the hand's own `Deck`, a required constructor argument (`PokerHand(players=..., deck=...)`, with no default). `PokerHand` owns the deck's state for the hand but not its shuffle policy. The lifecycle creates a fresh 52-card deck per hand, shuffles it securely, and passes it in, so engine code creates hands through `start_game` / `start_next_hand`. Tests that want a known order pass an unshuffled `Deck()` explicitly
- the community board, empty until variant rules deal it
- the current `Street` (`PREFLOP`, `FLOP`, `TURN`, `RIVER`), starting on `PREFLOP`
- the burned cards, empty until variant rules burn cards before dealing the board, kept so every card drawn from the deck stays accounted for
- an optional reference to the hand's `BettingState` (`betting`), `None` until the betting layer initializes betting

`Street` lives in `game/` (`game/street.py`), not in a variant, because `PokerHand` owns the street and `game/` must not depend on `game/variants/`. Variant rules decide how the hand moves between streets.

Betting rules live in the betting layer, not on `PokerHand` (see [Betting](#betting-milestone-2)). Milestone 3 adds no pot state to `PokerHand`: the middle pot and the main and side pots are derived from the players' contributions (see [All-ins and pots](#all-ins-and-pots-milestone-3-planned)). Hole cards, burned cards, and the board are dealt by variant rules from the hand's deck, and the same rules advance the street.

`PokerHand` is a plain container. It does not re-validate participation; `hand_setup` remains the single owner of those rules. The hand-starting lifecycle functions (`start_game`, `start_next_hand`) return a `PokerHand` built from `setup_hand`'s participants.

### Card ownership

- Community board cards belong to `PokerHand`.
- Burned cards belong to `PokerHand`.
- Private (hole) cards belong to each `HandPlayerState`, as a list that is empty until dealt.
- A player's combined board + hole cards are never stored as separate state. They are derived when needed, for example at evaluation.
- Hole-card storage does not structurally assume exactly two cards. Variant rules decide the count: Texas Hold'em (`game/variants/texas_holdem/dealing.py`) deals two, one card at a time starting clockwise of the button and ending with the button, with no burn card. Hole cards are dealt only on `PREFLOP`.
- Texas Hold'em board dealing (`deal_next_street`) moves the hand from `PREFLOP` to `FLOP`, `TURN`, and `RIVER`. Entering each street burns one card and then deals that street's board cards in draw order: three on the flop, one on the turn, one on the river. The board is dealt only once every participant holds exactly two hole cards; otherwise `deal_next_street` raises the Hold'em-owned `InvalidHoleCardCountError` (for zero, one, or three or more cards) without changing the hand. There is no street after `RIVER`. Texas Hold'em owns its street transitions (the `PREFLOP` → `FLOP` → `TURN` → `RIVER` mapping in `dealing.py`); `Street` itself only names the streets.

### Card integrity

Legal engine-generated state keeps every card unique by construction:

- each hand gets a fresh deck of 52 distinct cards;
- shuffling only reorders the deck;
- drawing removes the card from the deck;
- dealing moves cards only by drawing them.

There is therefore no runtime duplicate-card scan. A test-only card-accounting invariant proves the guarantee: after a legal complete Texas Hold'em deal, the remaining deck plus every hole card, burned card, and board card are exactly the original 52 distinct cards. Externally deserialized, reconstructed, or network-provided state is not engine-generated. Validating it belongs at that external boundary, once such a boundary exists.

## Betting (milestone 2)

This section records the Milestone 2 design, which is fully implemented under `game/betting/`: `Stakes`, `BettingState`, the player contributions and chip commitment, betting initialization with blind posting, the action model, No-Limit sizing, legal-action calculation, applying actions (`apply_action`), round progression and completion with its early endings, and starting later betting rounds (`start_betting_round`). The behavior it defers (short all-ins, pots, showdown, orchestration, and other betting structures) is listed under [Scope](#scope).

Milestone 3 is planned to change parts of this design: the meaning of the current bet, short all-ins and short blinds, raise reopening, the end-of-round collection that replaces the street-contribution reset, and pots. Those planned changes are recorded in [All-ins and pots](#all-ins-and-pots-milestone-3-planned). Until each one is implemented, this section describes the engine's current behavior.

### Scope

Milestone 2 adds normal No-Limit betting and legal-action calculation to `PokerHand`. It supports a player going all-in only through an ordinary full action (see [All-in boundary](#all-in-boundary)).

Deferred to later milestones:

- calls the player cannot cover in full (short all-in calls), raises below the normal minimum because the player lacks chips, short-raise reopening rules, short blind all-ins (a player whose stack is below their blind posts it all and is all-in for less), main and side pots, and pot eligibility (milestone 3)
- showdown, settlement, and payout (milestone 4)
- automatic complete-hand and street orchestration (milestone 5)
- Pot-Limit (milestone 8) and Fixed-Limit (not yet scheduled)

### Ownership

- Betting rules live under `src/go_poker/game/betting/`, not in `PokerHand` methods.
- `PokerHand` holds a reference to the hand's current `BettingState`. Until betting is initialized, the hand has no active `BettingState`.
- Each `HandPlayerState` owns that player's hand-specific betting data: `street_contribution` (chips committed in the current betting round), `total_contribution` (chips committed in the whole hand), and the existing `folded` and `all_in` flags.
- `Player.stack` stays the single source of truth for the player's remaining chips.
- `Table` owns no betting rules. There is no `GameConfig` or `TableConfig`.
- There are no base classes, protocols, factories, or speculative betting abstractions.
- Chinese Poker remains a separate game family and does not use this betting model.

### Betting structures

Poker variant and betting structure stay separate dimensions (see [Variants and betting structures](#variants-and-betting-structures)). Milestone 2 implements only No-Limit. The first structure is implemented directly, and common abstractions are extracted only when a second betting structure (Pot-Limit, milestone 8) proves what is shared.

### Stakes

A focused hand/betting-level `Stakes` model (`game/betting/stakes.py`) holds the small blind and the big blind. Both are positive integers and `small_blind <= big_blind`; equal blinds such as 1/1 are valid. Invalid stakes raise `InvalidStakesError` at construction. It is not a table or game configuration object.

### BettingState

Betting progress is held in one explicit `BettingState` (`game/betting/state.py`), not in unrelated variables spread across modules. It tracks:

- the `Street` its current or completed betting round belongs to
- the hand's `Stakes`, so later rounds can restore the big-blind minimum-bet context
- the current bet: the street contribution every remaining player must match (milestone 3 redefines it as a nominal betting target; see [The current bet](#the-current-bet))
- the last full raise size
- the current actor, or none when the round has ended
- the players still pending action in the current betting round

Players are identified by seat number, which is stable and unique within a hand.

`BettingState` never stores legal actions; they are derived (see [Legal actions](#legal-actions)).

### Betting initialization

The lifecycle signatures are unchanged: `start_game(table, choose_button) -> PokerHand` and `start_next_hand(table) -> PokerHand` are betting-agnostic and know nothing about betting. They do apply the [start-of-hand chip rule](#game-domain-current), so a hand contains only players who start it with chips. Betting initialization is a separate betting-layer operation, `initialize_betting(hand, stakes)` (`game/betting/initialization.py`), that the caller applies to the returned hand. It:

- creates the hand's preflop `BettingState` (`street = PREFLOP`) and attaches it to the `PokerHand`
- posts the blinds as real chip commitments: the small blind (identified by `HandPlayerState.blind`, which `hand_setup` assigns; heads-up, the button holds it) commits the small-blind amount and the big blind commits the big-blind amount
- sets the current bet to the big blind
- sets the last full raise size to the big blind
- selects the first actor: the first pending player clockwise after the big blind, following `PokerHand.players`
- builds the pending players: every eligible player, blinds included, subject to [No opponent can respond](#no-opponent-can-respond)

The intended hand-start sequence is: start the hand → initialize betting (post blinds) → variant hole-card dealing. There is no orchestration abstraction for this sequence yet (milestone 5).

Initialization is rejected, leaving the hand and every stack unchanged, when the hand already has betting initialized (`BettingAlreadyInitializedError`), when the hand is no longer on `PREFLOP` (`BettingNotPreflopError`), or when a blind player's stack is smaller than their blind (`ShortBlindAllInNotSupportedError`), checked in that order. The last case is not an invalid player: in poker that player posts their whole stack and is all-in for less than the blind, while the nominal big blind stays the current bet. That short blind all-in needs unmatched chips and side pots, so it is deferred to milestone 3 and the error is a temporary Milestone 2 rejection. Both blinds are validated before either is posted. Initialization does not check variant dealing state such as whether hole cards were dealt; enforcing the deal-and-bet sequence belongs to the later orchestration layer. A blind posted in full that uses the player's last chips marks them all-in, like any other commitment that empties a stack. Chips are committed through the single `commit_chips` operation (`game/betting/chips.py`).

Betting relies on hands containing only players who started the hand with chips (see the start-of-hand chip rule); the betting layer adds no zero-stack or eligibility stack checks of its own (the short-blind check at initialization remains). Eligibility to act comes from the hand flags (`folded`, `all_in`), and `commit_chips` sets `all_in` when a stack reaches zero.

Posting a blind is not an action, so the blinds still owe an action in the preflop round. This is what gives the big blind its option when everyone calls.

### Actions

The normal action set is `FOLD`, `CHECK`, `CALL`, `BET`, and `RAISE` (`ActionType` in `game/betting/actions.py`). There is no separate `ALL_IN` action.

`BET` and `RAISE` carry a **target** amount: the player's street contribution after the action ("bet to" / "raise to"), never the number of chips added. If a player has contributed 100 on this street and raises to 500, the action amount is `500`, not the additional 400. This semantic is used consistently in engine APIs, tests, and future history and API design. `FOLD`, `CHECK`, and `CALL` carry no amount; the call amount is the current bet minus the player's street contribution.

An action is an `Action(type, amount=None)` value. Construction checks only its shape and raises `InvalidActionError` otherwise: `BET` and `RAISE` need a positive target amount, and `FOLD`, `CHECK`, and `CALL` must have none. Whether a target is in range for the current hand is decided by the legal actions, and `apply_action` validates a requested action against them.

### No-Limit sizing

The sizing rules are small No-Limit helpers in `game/betting/no_limit.py` (`min_bet_target`, `min_raise_target`, `max_target`), used by the legal-action calculation.

- `BET` is used when `current_bet == 0`; the minimum bet target is the big blind.
- `RAISE` is used when `current_bet > 0`; the minimum raise target is `current_bet + last_full_raise_size`.
- The maximum target is `street_contribution + stack`. There is no artificial cap to keep a stack above zero.
- After a full bet or raise, `last_full_raise_size = new_current_bet - previous_current_bet` (set by `apply_action`).

Preflop starts with `current_bet = big_blind` and `last_full_raise_size = big_blind`, so the first minimum raise target is two big blinds.

### All-in boundary

A normal `CALL`, `BET`, or `RAISE` may use the player's entire remaining stack when it otherwise satisfies the ordinary full-action rules: a call of the full call amount, or a bet or raise to at least the minimum target. When a supported action (or a blind posted in full) leaves `Player.stack == 0`, the player's `all_in` flag becomes true and they owe no further actions in the hand.

Milestone 2 supports only these full-action all-ins. Because short all-ins are deferred, a call the player cannot cover in full is not legal in Milestone 2, and neither is a bet or raise when the player's maximum target is below the minimum target. Milestone 3 adds those actions together with pots (see [All-ins and pots](#all-ins-and-pots-milestone-3-planned)).

### Legal actions

Legal actions are derived state, calculated from the current hand state on request. No mutable list of legal actions is stored on `PokerHand` or `BettingState`. The calculation communicates:

- whether fold, check, and call are legal
- the call amount
- whether bet or raise is legal
- the minimum and maximum target amounts

`legal_actions(hand)` (`game/betting/legal_actions.py`) returns a frozen `LegalActions` value for the current actor: `can_fold`, `can_check`, `can_call`, `call_amount`, `can_bet`, `can_raise`, and `min_target` / `max_target`, which are set only when a bet or raise is legal. When the round has no current actor, nothing is legal (every flag false, a call amount of zero, no targets). A hand without a betting state raises `BettingNotInitializedError` (`game/betting/state.py`).

`FOLD` is legal whenever a live, eligible player is the current actor, including when `CHECK` is also available. `CHECK` is legal when the call amount is zero, and `CALL` when it is positive and the player can cover it. `BET` and `RAISE` additionally require at least one other player who can respond: someone who has not folded, is not all-in, and can still take a future betting action. "Can respond" reuses the betting eligibility predicate (`is_eligible` in `game/betting/rounds.py`: not folded, not all-in); like the rest of the betting layer it adds no zero-stack checks. When every other non-folded player is all-in, the actor may only resolve the outstanding bet (see [No opponent can respond](#no-opponent-can-respond)). The exact representation is an implementation choice within these boundaries.

### Action order

- **Multiway preflop:** the first eligible player clockwise after the big blind acts first.
- **Heads-up preflop:** the button, who is the small blind, acts first. This is the same rule as multiway, because heads-up the player clockwise after the big blind is the button.
- **Postflop:** the first eligible player clockwise after the button acts first. Heads-up, the big blind acts before the button.

Betting reuses the existing ordering: `PokerHand.players` is already clockwise from the button (built by `hand_setup` through `order_seats_from_button`), so betting does not re-derive seat order or duplicate circular traversal rules. An eligible player is one who has neither folded nor gone all-in.

### Pending actors and round completion

A betting round is not complete when "everyone has acted once", because a bet or raise reopens action. Instead, the betting state tracks which eligible players still owe an action:

- When a round starts, every eligible player is pending.
- A check or call removes the actor from the pending players.
- A bet or raise removes the actor and makes every other eligible player pending again.
- A fold, or an action that puts the player all-in, removes them from the pending players and from eligibility.
- The next actor is the next pending player clockwise from the current actor.

Example: A checks, B checks, C bets; A and B now owe an action again.

`apply_action(hand, seat_number, action)` (`game/betting/apply.py`) implements these rules. Before changing anything it rejects a hand without betting (`BettingNotInitializedError`), a seat that is not the current actor, including any action once the round is complete (`NotPlayersTurnError`), and an action that the current legal actions do not allow, including a `BET` or `RAISE` target outside the legal minimum and maximum (`IllegalActionError`); legality comes from `legal_actions`, not a second implementation. It then applies the action: `FOLD` sets `folded`; `CALL` commits the call amount; `BET` or `RAISE` to a target commits the target minus the actor's street contribution and updates the current bet and last full raise size. Chips move only through `commit_chips`, which marks a player who empties their stack all-in. Finally it settles the pending players with the early endings below and passes the action to the next pending player clockwise. `is_round_complete(betting)` (`game/betting/rounds.py`) reports whether nobody is pending, so nobody is to act.

A betting round is complete only when every eligible player has responded to the current bet and no action remains pending. Two special cases end a round early: everyone else folding, and no opponent being able to respond (both below).

**Everyone else folds.** When only one non-folded player remains, the betting round ends immediately: the current actor becomes `None` and no players are pending. No chips are awarded and no pot is created; settlement and payout belong to milestone 4. In milestone 3 the [end-of-round collection](#end-of-round-collection) also returns the last player's uncalled chips.

Both early endings live in one helper (`settle_pending` in `game/betting/rounds.py`), used after every action and, through `pending_at_round_start`, whenever a round starts.

### No opponent can respond

When at most one player can still act (every other non-folded player is all-in), there is no further betting, but the hand is not over: unlike when everyone else folds, it can still continue through later streets toward showdown.

- `BET` and `RAISE` are never legal, because no opponent could respond.
- If that player still owes chips to the current bet, they must resolve it with a supported action: in Milestone 2, `CALL` if they can cover the complete call amount, or `FOLD`. The betting round is complete after that response. If they cannot cover the complete call, that short all-in call is unsupported until milestone 3; Milestone 2 has no partial-call behavior.
- If that player owes nothing, the betting round completes automatically, with no current actor and nobody pending. No meaningless `CHECK` is required to close it.

The same rule applies when a round starts, including a later street's round, so such a round is complete as soon as it starts.

### Later betting rounds

Dealing stays independent from betting. After the variant dealing layer advances the street (for example `deal_next_street`), a separate betting-layer operation, `start_betting_round(hand)` (`game/betting/rounds.py`), starts the new `FLOP`, `TURN`, or `RIVER` betting round. It:

- requires the previous betting round to be complete
- requires `hand.street` to differ from `betting_state.street`, then sets `betting_state.street = hand.street`, so the same street's round cannot be started twice
- resets every player's `street_contribution` to zero and preserves `total_contribution` (in milestone 3 the [end-of-round collection](#end-of-round-collection) takes over this reset)
- sets `current_bet = 0` and restores the normal minimum-bet context: `last_full_raise_size` returns to the big blind
- builds the pending players from the eligible (non-folded, non-all-in) players
- chooses the first eligible player clockwise after the button, so heads-up postflop starts with the big blind

A rejected round start leaves the hand and its betting state unchanged. The rejections, checked in this order, are a hand without betting (`BettingNotInitializedError`), a previous round that is not complete (`BettingRoundNotCompleteError`), and a hand still on the betting state's street (`BettingRoundAlreadyStartedError`). The button is the first entry of `PokerHand.players`.

The betting layer does not encode `PREFLOP` → `FLOP` → `TURN` → `RIVER` as a generic betting rule: variant dealing code owns street progression. Starting a later round only checks that the hand has moved to a different street; it does not detect a caller who skipped a variant street through lower-level APIs. There is no hand or street orchestration yet. The later orchestration layer (milestone 5) will enforce the complete deal-and-bet sequence.

### Pot

There is no `Pot` abstraction in Milestone 2; it would only hold one number. The chips committed to the hand are derived from the players' `total_contribution` values. Main pots, side pots, and pot eligibility belong to milestone 3 (see [Pots](#pots)).

### Betting-state invariants

- Rejected betting operations are atomic: a rejected initialization, action, or round start leaves the hand, its betting state, and every stack unchanged.
- `street_contribution` resets to zero at the start of each new betting round.
- `total_contribution` accumulates for the whole hand.
- Chips a player commits are removed from `Player.stack`. Committing chips is one operation (`commit_chips`) that subtracts from the stack and adds to both contributions. It enforces its own local invariants before changing anything: the amount must be positive (`InvalidChipAmountError`) and no larger than the player's stack (`InsufficientChipsError`). Operations that commit chips still validate their whole request first, so a rejection never leaves a partial commitment.
- Before settlement, a player's remaining stack plus total contribution equals their chip total at the start of the hand. Only future payout and settlement change this.
- Folded and all-in players are never pending actors.
- A bet or raise makes every other eligible player owe another response.
- A bet or raise is legal only when at least one other player can respond.
- `BettingState` belongs to exactly one street, and a street's betting round is started at most once.
- Legal actions are always derived, never stored.

## All-ins and pots (milestone 3, planned)

This section records the approved Milestone 3 design. None of it is implemented yet; the cycle plan is in [CURRENT_CYCLE.md](CURRENT_CYCLE.md). It extends the [Milestone 2 betting design](#betting-milestone-2) so that No-Limit betting and chip accounting are correct for every realistic all-in case, including deep 9-max side pots, and so that future UI, hand history, rake, analytics, and AI can read the state directly without reconstructing poker rules.

### Milestone 3 scope

Milestone 3 adds:

- short all-in calls, short all-in opening bets, short all-in raises, and short small and big blinds
- No-Limit reopening rules, including cumulative short all-ins that reopen raising
- the return of unmatched (uncalled) chips and the end-of-round collection of chips in front into the middle
- the derived middle pot, and derived main and side pots of any depth with their eligible seats
- a derived way to detect that no further betting is possible

Out of scope: evaluating cards at showdown, choosing pot winners, pot payout, split pots, odd-chip rules, automatic card reveal, automatic board runout, complete-hand orchestration, rake, the tournament rebuy and bust lifecycle, Pot-Limit, and Fixed-Limit.

### Milestone 3 ownership

- All of it stays in `game/betting/`. `PokerHand`, `Table`, `Player`, and the lifecycle gain no betting or pot state.
- `HandPlayerState.total_contribution` stays the single source of truth for pots. No pot is stored or updated after each action. There is no `MainPot`, `SidePot`, or `PotManager` class and no fixed side-pot slots.
- Chips move only through two small operations in `game/betting/chips.py`: `commit_chips` (stack to chips in front) and a new `return_chips` (chips in front back to the stack). `commit_chips` never runs backwards. Keeping chip movement in these two functions keeps it centralized and auditable.
- The No-Limit reopening rule joins the sizing helpers in `game/betting/no_limit.py`. The end-of-round collection and the pot derivation each get a focused module (planned: `collection.py` and `pots.py`). File names are forecasts, not commitments.
- No base classes, protocols, or speculative abstractions are added for other betting structures.

### Where chips are

| Location | Source of truth | Meaning |
| --- | --- | --- |
| Stack | `Player.stack` | Chips behind the player, still available to wager |
| Chips in front | `HandPlayerState.street_contribution` | Chips committed in the current betting round and not yet collected. They stay associated with that player until the round completes |
| Middle pot | Derived: `middle_pot(hand) = sum(p.total_contribution - p.street_contribution for p in hand.players)` | Only chips collected from completed betting rounds |

Example: a player who starts the round with 500 and bets 100 has a stack of 400 and 100 in front. Those 100 chips are not part of the middle pot until the round completes and they are collected.

`total_contribution` is everything a player has committed to the hand and not had returned: their collected chips plus their chips in front. There is no mutable pot-size field. Rake is out of scope and not yet scheduled, but when it is added it must take its share from collected pot chips only, never from chips still in front of players.

`middle_pot` is the engine and display value, and the future rake boundary. It is not necessarily the number a future Pot-Limit implementation (milestone 8) uses as its pot-sizing base: Pot-Limit sizing may need to count current wagers and chips in front according to Pot-Limit rules. That calculation belongs to the Pot-Limit betting structure when it is built. `middle_pot` keeps its meaning and is not changed to anticipate Pot-Limit.

### The current bet

`BettingState.current_bet` is the **nominal betting target**: the street contribution that a fully funded player must currently match. No street contribution is ever above it, but it is not guaranteed to equal the highest one, because a short blind or a short call leaves a player below it.

Example: blinds 50/100 and the big blind has 30. The big blind posts 30 and is all-in; `current_bet` stays 100, and the full-raise context (`last_full_raise_size`) stays based on the full 100 big blind.

The Milestone 2 invariant `current_bet == max(street_contribution)` is removed. It is replaced by `max(street_contribution) <= current_bet`. After a round completes, `current_bet` and `last_full_raise_size` keep that round's final values until the next round starts.

### Amount owed and the call target

The engine derives what the current actor must match, so a client can show it without knowing betting rules.

- `amount_owed` is the additional amount a fully funded current player would need to match what the remaining live opponents can actually contest: `amount_owed = max(0, call_target - street_contribution)`.
- The **call target** is normally `current_bet`. When no opponent can respond (every other live player is all-in) and the nominal target is above every opponent's actual street contribution, the call target is the largest street contribution among the other live players. The player is never asked to commit chips that would be returned at collection straight away. The call target is never above `current_bet`, and `current_bet` itself keeps its nominal value for the betting context.
- `call_amount` is the number of chips a `CALL` actually commits: `min(amount_owed, stack)` when `CALL` is legal.
- A `CALL` commits `call_amount`. When that uses the whole stack the call is all-in, and when it is less than the amount owed the player stays below the target (a short call). A short call never changes `current_bet`.

Examples:

- Current bet 300, 100 in front: the player owes 200. The client shows `CALL 200`.
- Current bet 500, 100 in front, stack 150: `amount_owed = 400`, `call_amount = 150`, and `call_is_all_in` is true. The current bet stays 500. The client shows `CALL 150 — ALL IN`.
- Heads-up 50/100, the big blind is all-in with 70 in front, and the small blind has 50 in front: the small blind owes 20 and the client shows `CALL 20`, not `CALL 50` followed by 30 coming back. `current_bet` stays 100. If the big blind were all-in for 30 instead, the small blind would owe nothing: they are not pending, the round completes, and their extra 20 is returned at collection.
- Multiway, the big blind is all-in for 30 of a 100 blind: the other players still owe the full 100, because other live players can still contest it.

The same call target decides who stays pending: when no opponent can respond, an eligible player stays pending only while they are below the call target.

`BET` and `RAISE` keep their Milestone 2 target semantics: the amount is the player's street contribution after the action. A player with 100 in front who raises to 300 sends the amount `300` and adds `300 - 100 = 200` chips. Every legal-action API stays consistent with this.

### Legal actions with short all-ins

`LegalActions` keeps its flat, frozen shape and gains the fields a client needs for all-ins. There is still no `ALL_IN` action.

| Field | Meaning |
| --- | --- |
| `can_fold` | Unchanged: always legal for the current actor |
| `can_check` | Nothing is owed |
| `can_call` | Chips are owed. A short all-in call is legal |
| `amount_owed` (new) | Chips needed to reach the call target; 0 when nothing is owed |
| `call_amount` (changed) | Chips a `CALL` commits: `min(amount_owed, stack)`; 0 when `CALL` is not legal. In Milestone 2 this field held the amount owed |
| `call_is_all_in` (new) | The call uses the actor's whole stack, whether it is short or exactly enough |
| `can_bet`, `can_raise` | Some bet (current bet zero) or raise (otherwise) is legal, either a full one or a short all-in; conditions below |
| `min_full_target` (replaces `min_target`) | The normal minimum **full** bet or raise target: the big blind for a bet, `current_bet + last_full_raise_size` for a raise. Set whenever a bet or raise is legal, even when the actor cannot reach it |
| `max_target` | The actor's maximum target, which in No-Limit is always their all-in target (`street_contribution + stack`). Set whenever a bet or raise is legal |
| `short_all_in_target` (new) | Set only when the actor's all-in is below `min_full_target`. It then equals `max_target` and is the only legal target. `None` when a full bet or raise is possible |

Each field has one meaning, so the aggressive options are never ambiguous:

- A **full** bet or raise is legal when `can_bet` or `can_raise` is true and `short_all_in_target` is `None`. The legal targets are `min_full_target` through `max_target`.
- A **short all-in** bet or raise is legal when `short_all_in_target` is set. That target is the only legal one, and `min_full_target` still shows what a full bet or raise would have needed.
- Example: the current bet is 100, the last full raise size is 100, and the actor can reach 170. Then `can_raise` is true, `min_full_target = 200`, `max_target = 170`, and `short_all_in_target = 170`. The client shows `RAISE TO 170 — ALL IN` and knows a full minimum raise would have been to 200.

A client shows `CALL <call_amount>` and adds `ALL IN` when `call_is_all_in` is true. It treats a bet or raise to `max_target` as all-in.

A bet or raise is legal when all of these hold:

- another player can respond (not folded, not all-in), as in Milestone 2
- the actor has raise rights (see [Raise rights and reopening](#raise-rights-and-reopening))
- the actor has chips beyond the call: `max_target > current_bet`

The full minimum target (`min_full_target`) keeps its Milestone 2 values. When the actor's `max_target` reaches it, the legal range is `min_full_target` through `max_target`. When it does not, the only legal target is `short_all_in_target`.

- **Short opening bet.** Big blind 100, the current bet is 0, and the player's stack is 30: `BET` to 30 is legal and puts them all-in (`min_full_target = 100`, `short_all_in_target = 30`). The full minimum bet stays 100. The current bet becomes 30 and the last full raise size stays 100, so the next minimum raise is to 130.
- **Short raise.** The current bet is 100, the last full raise size is 100, and the player's maximum target is 170: `RAISE` to 170 is legal and puts them all-in (`min_full_target = 200`, `short_all_in_target = 170`). The current bet becomes 170 and the last full raise size stays 100, so the next minimum raise is to 270.

When `apply_action` applies a bet or raise to a target, the bet or raise is **full** when the target reaches the full minimum target. A full bet or raise sets `last_full_raise_size = target - previous current_bet`; a short all-in leaves it unchanged. Either way `current_bet` becomes the target and every other eligible player owes a response again, so a short all-in raise may create new pending responses without reopening raising.

### Raise rights and reopening

`pending_actors` answers only "who still owes an action?". Whether a player may raise is a separate, derived question.

`BettingState` gains one piece of per-round state: `acted_at_bet: dict[int, int]`, which maps the seat of each player who has acted in the current round to the `current_bet` right after their latest action. Every applied action records it. It is cleared whenever a betting round starts. Posting a blind is not an action, so the blinds start the preflop round without an entry. There is no second mutable raise-eligible set.

A player has **raise rights** when either:

- they have not acted in the current round, or
- `current_bet - acted_at_bet[seat] >= last_full_raise_size`

Consequences:

- A full bet or raise reopens raising for everyone who already acted, because the increase since any earlier action is at least the new full raise size.
- A short all-in below a full raise makes earlier actors owe a response but does not let them raise. Example: A bets 50 and B goes all-in to 70. A may call the extra 20 or fold, but may not raise.
- Cumulative short all-ins reopen raising. Example: A bets 100 (so A acted at 100), B goes all-in to 160, and C goes all-in to 220. A now faces 120 more than A's last action, which is at least the full raise size of 100, so A may raise. If A had called 160 in between, A would have last acted at 160 and would face only 60 more, so A could only call or fold.
- A check is an action. A player who checked and then faces a short all-in opening bet may call or fold but not raise. Example: big blind 100; on the flop A checks and B bets all-in for 30.
- Preflop the big blind has not acted, because posting is not an action, so a short all-in raise never takes away the big blind's option to raise.
- The minimum new full raise stays `current_bet + last_full_raise_size`, and individual short all-ins never change `last_full_raise_size`.

### Short blinds

A player with a positive stack takes part in the hand even when they cannot cover their blind (the existing [start-of-hand chip rule](#game-domain-current)). `initialize_betting` posts `min(blind, stack)` for each blind, and posting the last chips marks the player all-in. `ShortBlindAllInNotSupportedError` is removed. `current_bet` and `last_full_raise_size` start at the full big blind regardless of what the blinds actually posted.

Example: blinds 50/100 and the big blind has 30. The big blind posts 30 and is all-in, with a stack of 0, a street contribution of 30 and a total contribution of 30. The current bet stays 100, and the next minimum raise is to 200.

Heads-up, when the small blind (the button) posts 50 and the big blind is all-in for 30, nobody can act: the preflop round is complete as soon as betting is initialized, and the small blind's extra 20 is returned at collection.

### End-of-round collection

When a betting round completes, the betting operation that completed it collects the round in the same call: `apply_action` for the round's last action, or `initialize_betting` when the preflop round is complete as soon as it starts. There is no separate public collection step, and no round is ever complete but not yet collected. A later-street round that starts complete has no chips in front, so there is nothing to collect.

The collection:

1. **Returns unmatched chips.** If exactly one participant has the highest total contribution, the amount above the next-highest total contribution of any other participant (folded players included) is uncalled. It is returned to that player's stack through `return_chips`, which also lowers their street and total contributions by the same amount. There is never a one-player pot for unmatched chips.
2. **Collects the chips in front.** Every `street_contribution` is reset to zero, so the remaining chips in front become part of the middle pot.
3. **Keeps the normalized totals.** `total_contribution` keeps the normalized amounts and stays the source of truth for pots.

Because earlier rounds were already normalized, the unmatched amount always comes from the top player's chips in front. `return_chips` therefore only ever returns chips in front: the amount must be positive and no larger than the player's `street_contribution`, and the player's stack becomes positive again, so `return_chips` clears `all_in`.

Examples:

- A has 100 in front and B calls all-in for 70: 30 returns to A, A and B have each committed 70, 140 is collected into the middle, and both have nothing in front.
- A commits 1000 and B can only call 300 all-in: 700 returns to A. A has 700 behind and is no longer all-in, but no further betting is possible.
- UTG raises to 30 and everyone folds, with 5 and 10 from the blinds: 20 returns to UTG and the middle holds 25. Awarding it belongs to milestone 4.
- Everyone folds to the big blind: the big blind's 5 above the small blind is returned and the middle holds 10.

After collection the round has no chips in front, and the highest total contribution is matched by at least one other participant. `start_betting_round` no longer resets street contributions, because collection owns that. It still sets the current bet to zero, restores the big-blind minimum, and clears `acted_at_bet`.

### Pots

A pot is a small frozen value object: `Pot(amount: int, eligible_seats: frozenset[int])`. `pots(hand) -> tuple[Pot, ...]` derives the pot layers from each player's **collected contribution** (`total_contribution - street_contribution`). The pots therefore always add up to the middle pot and never include chips in front. During the preflop round nothing has been collected yet, so there are no pots.

Derivation:

1. The **levels** are the distinct positive collected contributions of **all** participants, folded players included, in ascending order. A folded player's contribution is dead money, but it still marks a layer boundary.
2. Each level `L`, with `P` the previous level (0 for the first), defines one contribution layer:
   - its **contributors** are every participant whose collected contribution `c` reaches the layer (`c > P`), folded players included
   - its **amount** is the sum over all participants of `min(c, L) - min(c, P)`
   - its **eligible seats** are the non-folded participants with `c >= L`

The first pot is the main pot and the later pots are side pots. The derivation is generic: it encodes no player count and no fixed side-pot numbers. Contributors are derived from the contributions whenever needed, so `Pot` stores only the amount and the eligible seats.

- **Contributors vs eligibility.** A folded player's chips stay in the amount of every layer they reach, but the player is eligible for no pot. An all-in player is eligible for every layer their contribution reaches. Every pot names the live seats that can win that specific layer, so a future showdown can evaluate each pot independently.
- **Folded thresholds.** A folded player's contribution can add a layer boundary without changing the eligible seats. Example after collection: A is live with 100, B folded with 150, and C and D are live with 200 each. The layers are 400 (A, C and D eligible), 150 (C and D eligible, including B's 50 between 100 and 150), and 100 (C and D eligible). The last two layers have the same eligible seats and stay separate, deterministic contribution layers. A client may merge adjacent layers with identical eligibility for presentation later if there is a concrete reason, but the core derivation never relies on eligibility shrinking from one layer to the next.
- **No one-contributor top layer.** Collection always returns an unmatched top contribution that only one player funded, so the highest level is reached by at least two participants and never becomes a one-contributor pot. Example: A is live with 100, B folded with 150, and C is live with 200 and nobody else reached 200. C's 50 above B's 150 is unmatched and returns to C at collection. The pots are 300 (A and C eligible) and 100 (only C eligible, made of B's 50 between 100 and 150 and C's matching 50).
- **Depth.** There is at most one pot per distinct level. After collection the top level is shared by at least two participants, so 9 players produce at most 8 pots: the main pot and up to 7 side pots. Example: nine contributions of 100, 200, …, 900. Collection returns 100 to the 900 player, and the pots are 900, 800, 700, 600, 500, 400, 300, and 200, with 9, 8, …, 2 eligible seats when nobody folded. If some of those players had folded, the same eight layers remain and only their eligible seats change.
- **Folded dead money.** A is all-in for 100 preflop, and B and C have each put in 300 by the end of the flop. On the turn B bets and C folds. B's turn bet is returned at collection. The pots are a main pot of 300 (A and B eligible) and a side pot of 400 (only B eligible, including C's 200 of dead money).
- **Properties.** Every pot has a positive amount. Every pot has at least one eligible seat, because after collection the highest contribution always belongs to a live player. Eligible seats are never folded. Each pot's eligible seats are a subset of the previous pot's, but not necessarily a strict one.

### No further betting

`is_betting_closed(hand)` (planned name) is derived, never stored. It is true when the current round is complete and at most one live player can still act (has not folded and is not all-in). From then on, no later round can ask anyone to act. This covers:

- every remaining live player is all-in
- one live player still has chips, owes nothing, and faces only all-in opponents
- everyone else has folded (the caller tells this apart from an all-in by counting live players)

If an actionable player still owes chips to an all-in wager, the round is not complete, so betting is not closed and that player must still act. On the river, with two or more players still able to act, it is false: the betting layer does not know the variant's street sequence, and orchestration does.

### An all-in does not end the hand

If A is all-in preflop while B and C still have chips, B and C keep betting normally on later streets and may build side pots. A stays eligible for the pot layers that A's contribution reaches. If B or C later folds, their committed chips stay in the pot amounts and they become ineligible for every pot.

### Future reveal and board runout (documented, not implemented)

- Hole cards are not exposed just because a player is all-in.
- While other players still have betting action against one another, play continues normally.
- Once at least one player is all-in and betting is closed with two or more live players, future orchestration (milestone 5) will table the live hands, deal all remaining board cards, and proceed to showdown (milestone 4).

Milestone 3 only exposes the state needed to detect this (`is_betting_closed` and the folded and all-in flags). It does not reveal cards or deal the board.

### Milestone 3 invariants

These extend the [Milestone 2 betting-state invariants](#betting-state-invariants):

- For every participant, stack plus total contribution equals their chips at the start of the hand, including after returned chips, until payout (milestone 4).
- The middle pot plus every street contribution equals the sum of total contributions, and the pot amounts add up to the middle pot.
- `all_in` is true exactly when a participant's stack is zero.
- No street contribution is above `current_bet` (this replaces `current_bet == max(street_contribution)`).
- A completed round has no chips in front and no unmatched chips: the highest total contribution belongs to at least two participants.
- `last_full_raise_size` is the big blind when a round starts and changes only on a full bet or raise.
- `acted_at_bet` holds exactly the seats that have acted in the current round, and it is empty when a round starts.
- Every pot has a positive amount and at least one eligible seat, no eligible seat has folded, and each pot's eligible seats are a subset (not necessarily strict) of the previous pot's. Pot levels come from every participant's collected contribution, folded players included.
- Chips move only through `commit_chips` and `return_chips`. Rejected operations stay atomic, and the collection itself never fails.

## Variants and betting structures

These are separate, independent dimensions.

### The PokerHand family

`PokerHand` is the normal (default) community-card poker hand abstraction. It serves Texas Hold'em, the default product variant, and later Omaha and Pineapple. All three may reuse shared hand infrastructure (participants, deck, board, streets, burned cards, and later betting and pots). Rules that differ between them, such as hole-card counts, discards, and evaluation constraints, stay variant-owned under `game/variants/`. There are no premature base classes, protocols, or factories for the family; shared abstractions are extracted when the second implementation shows what is shared (see [Extensibility policy](#extensibility-policy)).

A future private-table or session layer may choose the variant per table or per hand, for example by rotation, explicit request, or voting (roadmap milestone 10). It is not implemented.

### Chinese Poker (separate game family)

Chinese Poker is not a `PokerHand` variant. A future implementation uses a distinct model, such as `ChinesePokerHand`, with its own:

- hand state and player state
- placement / round lifecycle
- scoring, multipliers, and royalties
- rules

It may reuse `core/` card and evaluation primitives, and later platform infrastructure such as accounts, history, and persistence. `PokerHand`, `Street`, blinds, betting, the board, and the folded / all-in flags are not made universal to fit Chinese Poker. No source-tree refactor is made for it now (roadmap milestone 11).

### Variant rules

**Poker variants** — for example Texas Hold'em, Omaha, Pineapple. Variant rules may control:

- private-card counts
- dealing procedure
- discard phases
- community-card behavior
- hand-evaluation constraints (for example, Omaha's "exactly two hole cards")

**Betting structures** — No Limit, Pot Limit, Fixed Limit.

A variant is never coupled to one betting structure. A game is a composition of the two: No-Limit Hold'em is Texas Hold'em rules + No-Limit betting, PLO is Omaha rules + Pot-Limit betting, and Pineapple pairs Pineapple rules with an appropriate betting structure.

### Extensibility policy

- Do not create abstract base classes, protocols, factories, or registries for future variants, betting structures, or game families yet.
- Variant-specific poker rules live under `src/go_poker/game/variants/`, with the first implementation in `src/go_poker/game/variants/texas_holdem/`. Betting-structure–specific rules live under `src/go_poker/game/betting/`.
- These boundaries are namespaces only: no abstract base classes, protocols, factories, or speculative implementations.
- Extract common abstractions only when a second implementation (planned: Omaha + Pot-Limit, milestone 8) proves what is shared.

## Engine vs accounts and persistence

- The engine's `Player` is a poker participant, not a user account.
- Account, authentication, profile, and history concerns belong outside the poker engine.
- Bots and guests must be able to participate as `Player`s without an account.

## Data, history, and AI (planned)

- Structured raw hand history / events become the source of truth before persistence or statistics are built.
- Persist enough raw information to reconstruct each hand and each decision point.
- Statistics are derived from hand-history / event data rather than being the only stored source of truth.

This data is meant to support:

- player-facing hand and session history and stats
- analytics
- AI coaching and analysis
- querying similar decision spots
- simulation and training datasets
