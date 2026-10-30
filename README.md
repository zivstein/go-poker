# Go! Poker

A modular No-Limit Texas Hold'em engine built in Python.

Go! Poker is an ongoing software-development project focused on clean domain modeling, poker game logic, algorithms, and automated testing.

The core engine is intentionally independent from presentation and networking layers, allowing the same game logic to later power CLI, web, and mobile clients.

## Current Features

**Cards and hand evaluation**

- Card, rank, and suit models, and a standard 52-card deck with shuffle and draw
- Secure shuffling: `Deck.shuffle()` uses the OS CSPRNG (`random.SystemRandom`), so engine shuffles are not reproducible. Its `_rng` keyword is the only test seam: tests pass a seeded `random.Random` for a known order, and engine code never passes it. The underscore is a naming convention, not a security mechanism; production APIs and clients never control the shuffle RNG
- Five-card hand evaluation across all nine hand categories, including the ace-low straight
- Best-hand evaluation from 5–7 available cards
- Directly comparable hand ranks: category first, then kickers and tie-breakers
- Rejection of duplicate cards and invalid card counts

**Table and players**

- Configurable 2–9 seat tables
- Players with a chip stack and a participation state: `WAITING` (the default), `READY`, or `SITTING_OUT`; running out of chips does not change the state (there is no bust or rebuy policy yet)
- Seats that hold the seated `Player` object, with sit-in and stand-up rules
- Storage of the dealer-button seat (the table does not move the button itself)

**Game lifecycle**

- Explicit game start: `start_game()` starts a game with every seated `WAITING` player who has chips (2–9; `SITTING_OUT` players and players with no chips are excluded, are not offered to the chooser, and keep their status), the first button comes from an injected chooser, and seating alone never starts a game
- Button movement between hands: `start_next_hand()` moves the button clockwise from the previous button seat to the next `READY` player with chips, skipping `WAITING` and `SITTING_OUT` players, players with no chips, and empty seats (the previous button seat anchors the move even if its player has run out of chips); with no `READY` players with chips, it raises `GameNotStartedError` (a game with no `READY` players at all must be started again)
- Both create a fresh 52-card deck, shuffle it securely, and return the new hand as a `PokerHand` that owns its participants, that deck, and an empty community board, on `PREFLOP` with no burned cards; starting a hand deals no cards
- Neither takes an RNG argument: the lifecycle owns the shuffle policy
- Both leave table and player state unchanged if they fail

**Hand setup**

- Position assignment for 2–9 players relative to the button, skipping empty seats
- Small- and big-blind seat assignment, including the heads-up rule where the button holds the small blind
- Per-hand player state (seat, position, blind, and private hole cards) kept separate from the persistent table-level player; hole cards are an empty list until dealt, with no fixed card count
- `PokerHand`, the aggregate for one hand: its participants in order from the button, its own deck (a required constructor argument, `PokerHand(players=..., deck=...)`), the community board, the current street, and the burned cards
- Street progression: a hand moves through `PREFLOP`, `FLOP`, `TURN`, and `RIVER`, starting on `PREFLOP`
- Hand participant setup: `READY` players take part, `SITTING_OUT` players are skipped, and a hand needs at least two participants regardless of table size
- Start-of-hand chip rule: a player with no chips is not dealt into a new hand and cannot receive the button, while a positive stack smaller than a blind still plays
- Waiting-player entry rules: a `WAITING` player joins as the big blind or in a non-blind position, and keeps waiting if they would be the button or small blind

**Texas Hold'em dealing**

- `deal_hole_cards()` deals two hole cards to every participant of a `PokerHand` from the hand's own deck
- Cards go out one at a time in rounds, starting with the player clockwise of the button and ending with the button (heads-up, the big blind gets the first card); no card is burned before hole cards
- Dealing hole cards is rejected without changing the hand if the hand is past preflop, hole cards were already dealt, or the deck has too few cards
- `deal_next_street()` moves a `PokerHand` to its next street: it burns one card into the hand's burned cards, then deals that street's board cards onto the hand's board in draw order (three on the flop, one on the turn, one on the river)
- Board dealing is rejected without changing the hand if any participant does not hold exactly two hole cards (`InvalidHoleCardCountError`), the hand is already on the river, or the deck has too few cards for the burn and the street's board cards
- Card uniqueness holds by construction: every hand has its own fresh deck and dealing only draws from it, so there is no runtime duplicate-card scan

**Betting (No-Limit)**

- `Stakes`: a small and a big blind, both positive, with `small_blind <= big_blind` (equal blinds are valid)
- Per-hand player contributions: `street_contribution` (the chips in front, committed in the current round and not yet collected) and `total_contribution` on `HandPlayerState`; committing chips moves them from the player's stack into both, and a player whose stack reaches zero is marked all-in. A commitment that is not positive or exceeds the player's stack is rejected without changes
- Returning chips (`return_chips`) is the only reverse movement: it moves chips still in front back to the stack, lowers both contributions, and clears the player's all-in flag. A return that is not positive or exceeds the player's chips in front is rejected without changes
- `initialize_betting(hand, stakes)` posts the small and big blinds as real chips and attaches a preflop `BettingState` to the `PokerHand` (`hand.betting`, `None` until then): the current bet and last full raise size start at the full big blind, posting a blind is not an action so nobody has acted yet, every player who has not folded or gone all-in is pending (blinds included, which gives the big blind its option), and the first pending player clockwise after the big blind acts first (the button heads-up)
- Short blinds: a blind player whose stack is smaller than their blind posts their whole stack and is all-in for less, while the current bet stays the full big blind (the others still owe it, and the minimum raise is two full big blinds)
- The call target: when no opponent can respond (every other live player is all-in), a player owes only what those all-in players can contest, the largest street contribution among them, never above the current bet, which keeps its nominal value (heads-up 50/100 against a big blind all-in for 70, the small blind calls 20); only a player still below their call target is pending, so a round in which nobody can respond and nothing is owed is complete as soon as it starts
- Initialization is rejected without changing the hand if betting is already initialized or the hand is no longer on `PREFLOP`; a blind that uses a player's last chips, in full or short, puts them all-in
- Betting relies on hands containing only players who started with chips: it adds no zero-stack or eligibility stack checks of its own (eligibility comes from the folded and all-in flags)
- The intended hand start is `start_game` / `start_next_hand` → `initialize_betting` → `deal_hole_cards`; the lifecycle itself knows nothing about betting
- Actions: `Action(type, amount)` with `ActionType` `FOLD`, `CHECK`, `CALL`, `BET`, and `RAISE` (no separate all-in action); `BET` and `RAISE` carry a positive target amount, the street contribution after the action ("bet to" / "raise to"), and the others carry none
- `BettingState.current_bet` is the nominal betting target a fully funded player must match (no street contribution is ever above it, but a short blind or short call stays below it), and `last_full_raise_size` is the size of the last full bet or raise (the big blind when a round starts; a short all-in never changes it)
- No-Limit sizing: a bet's minimum full target is the big blind, a raise's is the current bet plus the last full raise size, and the maximum is the player's all-in target, their street contribution plus their whole stack
- Raise rights, derived separately from who still owes an action: a player may bet or raise only when they have not acted in the current round, or when the current bet has risen by at least the last full raise size since their latest action (a check counts as acting; posting a blind does not). So a single short all-in below a full raise does not reopen raising for players who already acted, while cumulative short all-ins that together reach a full raise do. `BettingState.acted_at_bet` records the current bet right after each seat's latest action and is cleared when a round starts
- `legal_actions(hand)` derives the current actor's options on request (never stored): fold always, check with nothing owed, call whenever chips are owed (a call the stack cannot cover is a short all-in call of the whole stack), and bet or raise when the player has raise rights, chips beyond the current bet, and another player who has not folded or gone all-in can respond. It reports `amount_owed` (measured against the call target), `call_amount` (the chips a call commits, the whole stack for a short call, 0 when calling is not legal), `call_is_all_in`, `min_full_target` (the normal minimum full bet or raise), `max_target` (the all-in target), and `short_all_in_target` (set when the all-in target is below the full minimum, and then the only legal target, such as a short opening bet below the big blind or a short raise below the minimum raise); nothing is legal when no one is to act
- `apply_action(hand, seat_number, action)` applies the current actor's action after checking the turn and the legal actions, rejecting out-of-turn or illegal actions (including any target but the short all-in target when that is the only legal one) without changing the hand: fold, check, call (the call amount, which never changes the current bet), and bet or raise to a target (adding the target minus the player's street contribution and making it the current bet; a full bet or raise sets the next minimum raise, while a short all-in leaves the last full raise size unchanged); every action records the current bet right after it for raise rights, and any action that uses the whole stack puts the player all-in
- Betting rounds progress until nobody owes an action: a bet or raise makes every other player who can still act owe a response, the action passes to the next pending player clockwise, and the round ends early when everyone else folds (the uncalled chips are returned and nothing is awarded yet) or when nobody could respond and nothing is owed
- End-of-round collection: the operation that completes a round (`apply_action`, or `initialize_betting` when the posted blinds already complete the preflop round) collects it in the same call. If exactly one player has the highest total contribution, the chips above the next-highest total of any other player, folded players included, are uncalled and go back to that player's stack (UTG raises to 30 and everyone folds: 20 go back); then every player's chips in front move into the middle. The current bet, the last full raise size, and the recorded actions keep the completed round's values until the next round starts, and a rejected action never collects
- `start_betting_round(hand)` starts the flop, turn, or river betting round once dealing has moved the hand to a new street and the previous round is complete: the previous round was already collected, so nobody has chips in front (totals are kept), there is no bet, the minimum bet is the big blind, and the first player after the button acts (the big blind heads-up)
- `is_betting_closed(hand)` derives that no further betting is possible: the round is complete and at most one player has neither folded nor gone all-in (every live player all-in, one player with chips owing nothing against all-in opponents, or everyone else folded)
- `middle_pot(hand)` derives the chips collected into the middle from completed rounds (every player's total minus their chips in front), never counting chips still in front: the displayed pot and the boundary a future rake takes its share from, not the pot-sizing base of a future Pot-Limit structure
- `pots(hand)` derives the main pot and side pots, of any depth, as `Pot(amount, eligible_seats)` values from the players' collected contributions: every distinct contribution, folded players' included, is a layer boundary, each layer's amount includes folded players' dead money, and its eligible seats are the players who have not folded and reach it (all-in players included). Adjacent layers may have the same eligible seats; nothing is stored, and the pots always add up to the middle pot

**Tooling**

- Automated test suite with pytest (`importlib` import mode, so same-named test modules in different variant directories do not collide); deterministic shuffles come from a seeded `random.Random` passed to `Deck.shuffle(_rng=...)`, the only randomness seam; tests above the `Deck` layer patch `Deck.shuffle` to forward a seeded `_rng`
- Texas Hold'em tests for heads-up and multiway deal order, street progression, invalid transitions, deck-size boundaries, a complete hand from game start to the river, and a 52-card accounting invariant
- Betting tests for stakes validation, chip commitment and return, heads-up, three-handed and multiway blind posting and first actor, atomic rejection, blinds that put a player all-in, short small and big blinds (including heads-up blinds all-in for less than the other blind, which complete and collect the round at once, returning the unmatched part), and the game start → betting initialization → hole-card dealing sequence; action shape; and legal actions preflop, for the big blind's option, in an unopened round (including a short opening bet), facing a raise, at stack boundaries (a call of exactly the whole stack, a short all-in call, and a short all-in raise), when no opponent can respond (including the amount owed measured against the larger of two all-in opponents), and with nobody to act; raise rights (the reopening rule at its boundaries and a limper who faces a full raise); applying actions (turn and legality checks, target chip movement, raise sizing, reopening after a bet, short calls, opening bets, and raises that keep the last full raise size, atomic rejection of illegal short all-in actions, recording the current bet after each action, all-in through a full action, early round endings, including the uncalled chips returned when everyone else folds), the end-of-round collection (a sole top contributor gets back only what nobody else matched, folded contributions included; a matched top contribution returns nothing; every player's chips in front are collected; a rejected action by the last pending player neither returns nor collects), starting later rounds (including heads-up order, clearing the recorded actions, and atomic rejections), detecting that no further betting is possible, the middle pot (only collected chips), and pot layering (folded dead money, a folded layer boundary with unchanged eligibility, all-in eligibility, and eight layers from nine distinct contributions)
- Betting integration scenarios driven through the public dealing and betting operations, on hands built the way hand setup builds them (one scenario starts from a real game start), with the betting and accounting invariants (stack plus total contribution, all-in exactly when the stack is empty, no street contribution above the current bet, pending and actor consistency, recorded actions only for participants and never above the current bet, the middle pot plus the chips in front equal to the total contributions, pots that add up to the middle pot with at least two contributors, eligible seats that have not folded and reach their pot, a completed round with nothing in front and a matched highest total, and derived legal actions and pots) asserted after every step: multiway preflop with a limp and a raise, a bet after checks, a raise, re-raise and four-bet, heads-up order across streets, full-action all-ins skipped on later streets, everyone folding to a raise, a round closed by calling all-in opponents with later rounds completing automatically, play through the river, and atomic rejections mid-hand; and short all-in scenarios: a short call, a short opening bet, a short raise that does not reopen raising, cumulative short all-ins that do, a check followed by a short opening bet, a multiway short big blind, a heads-up short big blind called for what it can contest, and a short all-in player skipped while deeper players keep betting through the river, each asserting the collected totals, returned chips, and derived pots at round completion; and accounting scenarios: chips in front joining the middle pot only at collection (after a matched call, and after a short all-in call whose unmatched 30 go back), and a player who folds after contributing to three pot layers, keeping their chips in every layer but eligible for none, while all-in players stay eligible and the uncalled excess above the folded contribution goes back to the raiser
- Linting and formatting with Ruff, static type checking with mypy
- GitHub Actions CI running all of the above

## Architecture

```text
src/go_poker/
├── core/                       # cards and hand evaluation
│   ├── card.py                 # Card, Rank, Suit
│   ├── deck.py                 # 52-card deck: secure shuffle and draw
│   ├── hand_rank.py            # HandCategory and comparable HandRank
│   └── evaluator.py            # five-card and best-of-5–7 evaluation
│
└── game/                       # table and per-hand state
    ├── player.py               # Player and PlayerStatus
    ├── seat.py                 # Seat holding a Player
    ├── table.py                # seating and the stored button seat
    ├── game_lifecycle.py       # game start and button movement between hands
    ├── position.py             # positions by player count, blinds
    ├── position_assignment.py  # position and blind per seat for one hand
    ├── hand_state.py           # HandPlayerState, per-hand player state
    ├── hand_setup.py           # setup_hand, selects a hand's participants
    ├── street.py               # Street: PREFLOP, FLOP, TURN, RIVER
    ├── poker_hand.py           # PokerHand: participants, deck, board, street, burned cards, and betting state
    ├── betting/                # betting-structure rules (No-Limit)
    │   ├── stakes.py           # Stakes: small and big blind
    │   ├── state.py            # BettingState: street, stakes, current bet, raise size, actor, pending, acted-at bets
    │   ├── chips.py            # commit_chips and return_chips: chips between the stack and the contributions
    │   ├── rounds.py           # eligibility, call target, pending players, first actor, round completion, is_betting_closed, start_betting_round
    │   ├── initialization.py   # initialize_betting: blind posting and the preflop betting state
    │   ├── actions.py          # ActionType and Action with "bet to" / "raise to" targets
    │   ├── no_limit.py         # No-Limit minimum and maximum targets, raise rights
    │   ├── legal_actions.py    # LegalActions and legal_actions for the current actor
    │   ├── apply.py            # apply_action: validate and apply the current actor's action
    │   ├── collection.py       # collect_round: return unmatched chips, collect chips in front at round end
    │   └── pots.py             # middle_pot, Pot, and pots: the derived middle pot and main and side pots
    └── variants/               # variant-specific poker rules
        └── texas_holdem/
            └── dealing.py      # Texas Hold'em hole-card, burn, and board dealing
```

`core` holds pure card and hand-evaluation logic. `game` holds table state and the rules that turn it into the participants of one hand. `game_lifecycle` owns game start and button movement, while `Table` only stores the button seat and stays unaware of player status. Game start and each next hand return a `PokerHand`, the aggregate for one hand, which owns the participants, a fresh securely shuffled deck, the community board, the current street, and the burned cards. Persistent player state lives in `Player`; anything that belongs to a single hand lives in `PokerHand` and its `HandPlayerState` participants, including each player's hole cards. `Street` lives in `game` because `PokerHand` owns it. The lifecycle is variant-agnostic: variant rules such as Texas Hold'em hole-card and board dealing live in `game/variants/`, are applied by the caller to the returned `PokerHand`, and advance its street. It is also betting-agnostic: betting-structure rules live in `game/betting/`, and the caller initializes betting (posting the blinds) on the returned `PokerHand`, which then holds its `BettingState`. Future APIs and clients will consume the engine rather than reimplement poker rules.

`PokerHand` is the default community-card hand for Texas Hold'em and, later, Omaha and Pineapple; Chinese Poker is planned as a separate game family with its own model. Ownership boundaries and the planned direction for hands, variants, game families, betting structures, and hand history are documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Usage Example

Evaluate and compare two players' best hands on the same board:

```python
from go_poker.core.card import Card, Rank, Suit
from go_poker.core.evaluator import evaluate_best

board = [
    Card(Rank.KING, Suit.SPADES),
    Card(Rank.KING, Suit.DIAMONDS),
    Card(Rank.SEVEN, Suit.CLUBS),
    Card(Rank.FOUR, Suit.HEARTS),
    Card(Rank.TWO, Suit.SPADES),
]

pocket_aces = evaluate_best([Card(Rank.ACE, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS), *board])
king_seven = evaluate_best([Card(Rank.KING, Suit.HEARTS), Card(Rank.SEVEN, Suit.DIAMONDS), *board])

print(pocket_aces.category.name)  # TWO_PAIR
print(king_seven.category.name)  # FULL_HOUSE
print(king_seven > pocket_aces)  # True
```

`evaluate_best` accepts 5–7 cards and returns a `HandRank`, which compares by category and then by tie-breakers.

## Development

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

Install the project and development dependencies:

```bash
uv sync
```

Run the test suite:

```bash
uv run pytest
```

Run linting:

```bash
uv run ruff check .
```

Check formatting:

```bash
uv run ruff format --check .
```

Run static type checking:

```bash
uv run mypy src
```

Run tests with coverage:

```bash
uv run pytest --cov=go_poker
```

## Roadmap

The milestone roadmap is in [docs/ROADMAP.md](docs/ROADMAP.md), and the active milestone's cycle plan is in [docs/CURRENT_CYCLE.md](docs/CURRENT_CYCLE.md).

## Project Status

**Work in progress.**

The engine currently covers cards, hand evaluation, table state, game startup, button movement between hands, hand setup into a `PokerHand` with its participants, securely shuffled deck, board, street, and burned cards, and Texas Hold'em hole-card dealing, burn cards, and flop, turn, and river dealing with street progression. It also covers No-Limit betting rounds: stakes and blind posting, the action model, derived legal actions, applying actions, and betting-round progression across streets. It also covers short all-ins: short calls, bets, raises, and blinds, the call target when no opponent can respond, and detecting that no further betting is possible. It also covers chip accounting: uncalled chips returned and chips in front collected when a round completes, the derived middle pot, and derived main and side pots with their eligible seats. It does not yet play out a complete hand: there is no showdown or settlement, no orchestration of the full deal-and-bet sequence, and no CLI, API, or client.

The current focus is completing the core No-Limit Texas Hold'em game engine before adding networking and presentation layers. Milestone 1, PokerHand + Dealing Foundation, and Milestone 2, Betting Engine + Legal Actions, are complete. Milestone 3 — All-ins + main/side pots is in progress: its first three cycles (short-all-in state and raise rights; short calls, bets, raises and blinds; accounting, collection and pots) are complete and its fourth (extreme integration hardening) is next (see the [current cycle](docs/CURRENT_CYCLE.md)).
