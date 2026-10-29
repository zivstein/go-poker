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
| `game/betting/` | Current (milestone 2 in progress) | Betting-structure–specific rules; first implementation: No-Limit betting. Current: stakes, betting state, chip commitment, betting initialization with blind posting, the action model, No-Limit sizing, and legal actions. Planned: applying actions and betting-round progression (see [Betting](#betting-milestone-2-in-progress)) | Accounts, persistence, APIs, clients |
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

Betting rules live in the betting layer, not on `PokerHand` (see [Betting](#betting-milestone-2-in-progress)). Pot state beyond what player contributions already record arrives with all-ins and side pots (milestone 3). Hole cards, burned cards, and the board are dealt by variant rules from the hand's deck, and the same rules advance the street.

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

## Betting (milestone 2, in progress)

This section records the approved Milestone 2 design. Cycle 1 is implemented: `Stakes`, `BettingState`, the player contributions, chip commitment, and betting initialization with blind posting (the [Stakes](#stakes), [BettingState](#bettingstate), and [Betting initialization](#betting-initialization) sections, and the round-start pending and first-actor rules they use). Cycle 2 is implemented: the action model, No-Limit sizing, and legal-action calculation (the [Actions](#actions), [No-Limit sizing](#no-limit-sizing), and [Legal actions](#legal-actions) sections, and the no-opponent rule for bets and raises). Applying actions, round progression, and later betting rounds are planned; progress is tracked in [CURRENT_CYCLE.md](CURRENT_CYCLE.md).

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
- the current bet: the street contribution every remaining player must match
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

Betting relies on hands containing only players who started the hand with chips (see the start-of-hand chip rule); the betting layer adds no stack checks of its own. Eligibility to act comes from the hand flags (`folded`, `all_in`), and `commit_chips` sets `all_in` when a stack reaches zero.

Posting a blind is not an action, so the blinds still owe an action in the preflop round. This is what gives the big blind its option when everyone calls.

### Actions

The normal action set is `FOLD`, `CHECK`, `CALL`, `BET`, and `RAISE` (`ActionType` in `game/betting/actions.py`). There is no separate `ALL_IN` action.

`BET` and `RAISE` carry a **target** amount: the player's street contribution after the action ("bet to" / "raise to"), never the number of chips added. If a player has contributed 100 on this street and raises to 500, the action amount is `500`, not the additional 400. This semantic is used consistently in engine APIs, tests, and future history and API design. `FOLD`, `CHECK`, and `CALL` carry no amount; the call amount is the current bet minus the player's street contribution.

An action is an `Action(type, amount=None)` value. Construction checks only its shape and raises `InvalidActionError` otherwise: `BET` and `RAISE` need a positive target amount, and `FOLD`, `CHECK`, and `CALL` must have none. Whether a target is in range for the current hand is decided by the legal actions, and validating a requested action against them belongs to applying actions (Cycle 3, planned).

### No-Limit sizing

The sizing rules are small No-Limit helpers in `game/betting/no_limit.py` (`min_bet_target`, `min_raise_target`, `max_target`), used by the legal-action calculation.

- `BET` is used when `current_bet == 0`; the minimum bet target is the big blind.
- `RAISE` is used when `current_bet > 0`; the minimum raise target is `current_bet + last_full_raise_size`.
- The maximum target is `street_contribution + stack`. There is no artificial cap to keep a stack above zero.
- After a full bet or raise, `last_full_raise_size = new_current_bet - previous_current_bet` (applied when actions are applied; Cycle 3, planned).

Preflop starts with `current_bet = big_blind` and `last_full_raise_size = big_blind`, so the first minimum raise target is two big blinds.

### All-in boundary

A normal `CALL`, `BET`, or `RAISE` may use the player's entire remaining stack when it otherwise satisfies the ordinary full-action rules: a call of the full call amount, or a bet or raise to at least the minimum target. When a supported action (or a blind posted in full) leaves `Player.stack == 0`, the player's `all_in` flag becomes true and they owe no further actions in the hand.

Milestone 2 supports only these full-action all-ins. Because short all-ins are deferred, a call the player cannot cover in full is not legal in Milestone 2, and neither is a bet or raise when the player's maximum target is below the minimum target. Milestone 3 adds those actions together with pots.

### Legal actions

Legal actions are derived state, calculated from the current hand state on request. No mutable list of legal actions is stored on `PokerHand` or `BettingState`. The calculation communicates:

- whether fold, check, and call are legal
- the call amount
- whether bet or raise is legal
- the minimum and maximum target amounts

`legal_actions(hand)` (`game/betting/legal_actions.py`) returns a frozen `LegalActions` value for the current actor: `can_fold`, `can_check`, `can_call`, `call_amount`, `can_bet`, `can_raise`, and `min_target` / `max_target`, which are set only when a bet or raise is legal. When the round has no current actor, nothing is legal (every flag false, a call amount of zero, no targets). A hand without a betting state raises `BettingNotInitializedError` (`game/betting/state.py`).

`FOLD` is legal whenever a live, eligible player is the current actor, including when `CHECK` is also available. `CHECK` is legal when the call amount is zero, and `CALL` when it is positive and the player can cover it. `BET` and `RAISE` additionally require at least one other player who can respond: someone who has not folded, is not all-in, and can still take a future betting action. "Can respond" reuses the round-start eligibility predicate (`is_eligible`: not folded, not all-in); like the rest of the betting layer it adds no stack checks. When every other non-folded player is all-in, the actor may only resolve the outstanding bet (see [No opponent can respond](#no-opponent-can-respond)). The exact representation is an implementation choice within these boundaries.

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

A betting round is complete only when every eligible player has responded to the current bet and no action remains pending. Two special cases end a round early: everyone else folding, and no opponent being able to respond (both below).

**Everyone else folds.** When only one non-folded player remains, the betting round ends immediately: the current actor becomes `None` and no players are pending. No chips are awarded and no pot is created; settlement and payout belong to milestone 4.

### No opponent can respond

When at most one player can still act (every other non-folded player is all-in), there is no further betting, but the hand is not over: unlike when everyone else folds, it can still continue through later streets toward showdown.

- `BET` and `RAISE` are never legal, because no opponent could respond.
- If that player still owes chips to the current bet, they must resolve it with a supported action: in Milestone 2, `CALL` if they can cover the complete call amount, or `FOLD`. The betting round is complete after that response. If they cannot cover the complete call, that short all-in call is unsupported until milestone 3; Milestone 2 has no partial-call behavior.
- If that player owes nothing, the betting round completes automatically, with no current actor and nobody pending. No meaningless `CHECK` is required to close it.

The same rule applies when a round starts, including a later street's round, so such a round is complete as soon as it starts.

### Later betting rounds

Dealing stays independent from betting. After the variant dealing layer advances the street (for example `deal_next_street`), a separate betting-layer operation starts the new `FLOP`, `TURN`, or `RIVER` betting round. It:

- requires the previous betting round to be complete
- requires `hand.street` to differ from `betting_state.street`, then sets `betting_state.street = hand.street`, so the same street's round cannot be started twice
- resets every player's `street_contribution` to zero and preserves `total_contribution`
- sets `current_bet = 0` and restores the normal minimum-bet context: `last_full_raise_size` returns to the big blind
- builds the pending players from the eligible (non-folded, non-all-in) players
- chooses the first eligible player clockwise after the button, so heads-up postflop starts with the big blind

A rejected round start leaves the hand and its betting state unchanged.

The betting layer does not encode `PREFLOP` → `FLOP` → `TURN` → `RIVER` as a generic betting rule: variant dealing code owns street progression. Starting a later round only checks that the hand has moved to a different street; it does not detect a caller who skipped a variant street through lower-level APIs. There is no hand or street orchestration yet. The later orchestration layer (milestone 5) will enforce the complete deal-and-bet sequence.

### Pot

There is no `Pot` abstraction in Milestone 2; it would only hold one number. The chips committed to the hand are derived from the players' `total_contribution` values. Main pots, side pots, and pot eligibility belong to milestone 3.

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
