# Go! Poker

A modular No-Limit Texas Hold'em engine built in Python.

Go! Poker is an ongoing software-development project focused on clean domain modeling, poker game logic, algorithms, and automated testing.

The core engine is intentionally independent from presentation and networking layers, allowing the same game logic to later power CLI, web, and mobile clients.

## Current Features

**Cards and hand evaluation**

- Card, rank, and suit models, and a standard 52-card deck with shuffle and draw
- Five-card hand evaluation across all nine hand categories, including the ace-low straight
- Best-hand evaluation from 5–7 available cards
- Directly comparable hand ranks: category first, then kickers and tie-breakers
- Rejection of duplicate cards and invalid card counts

**Table and players**

- Configurable 2–9 seat tables
- Players with a chip stack and a participation state: `WAITING` (the default), `READY`, or `SITTING_OUT`
- Seats that hold the seated `Player` object, with sit-in and stand-up rules
- Storage of the dealer-button seat (the table does not move the button itself)

**Game lifecycle**

- Explicit game start: `start_game()` starts a game with every seated `WAITING` player (2–9; `SITTING_OUT` players are excluded), the first button comes from an injected chooser, and seating alone never starts a game
- Button movement between hands: `start_next_hand()` moves the button clockwise from the previous button seat to the next `READY` player, skipping `WAITING` and `SITTING_OUT` players and empty seats; with no `READY` players, the game must be started again
- Both return the new hand as a `PokerHand` that owns its participants, a fresh 52-card deck, and an empty community board (no cards are dealt yet)
- Both leave table and player state unchanged if they fail

**Hand setup**

- Position assignment for 2–9 players relative to the button, skipping empty seats
- Small- and big-blind seat assignment, including the heads-up rule where the button holds the small blind
- Per-hand player state (seat, position, blind) kept separate from the persistent table-level player
- `PokerHand`, the aggregate for one hand: its participants in order from the button, its own deck, and the community board
- Hand participant setup: `READY` players take part, `SITTING_OUT` players are skipped, and a hand needs at least two participants regardless of table size
- Waiting-player entry rules: a `WAITING` player joins as the big blind or in a non-blind position, and keeps waiting if they would be the button or small blind

**Tooling**

- Automated test suite with pytest
- Linting and formatting with Ruff, static type checking with mypy
- GitHub Actions CI running all of the above

## Architecture

```text
src/go_poker/
├── core/                       # cards and hand evaluation
│   ├── card.py                 # Card, Rank, Suit
│   ├── deck.py                 # 52-card deck: shuffle and draw
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
    └── poker_hand.py           # PokerHand: participants, deck, and board of one hand
```

`core` holds pure card and hand-evaluation logic. `game` holds table state and the rules that turn it into the participants of one hand. `game_lifecycle` owns game start and button movement, while `Table` only stores the button seat and stays unaware of player status. Game start and each next hand return a `PokerHand`, the aggregate for one hand, which owns the participants, a fresh deck, and the community board. Persistent player state lives in `Player`; anything that belongs to a single hand lives in `PokerHand` and its `HandPlayerState` participants. Future APIs and clients will consume the engine rather than reimplement poker rules.

Ownership boundaries and the planned direction for hands, variants, betting structures, and hand history are documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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

The engine currently covers cards, hand evaluation, table state, game startup, button movement between hands, and hand setup into a `PokerHand` with its participants, deck, and empty board. It does not yet play out a hand: there is no dealing, betting, pot handling, or showdown, and no CLI, API, or client.

The current focus is completing the core No-Limit Texas Hold'em game engine before adding networking and presentation layers. The active milestone is PokerHand + Dealing Foundation.
