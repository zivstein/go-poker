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
- Dealer-button placement and rotation across occupied seats

**Hand setup**

- Position assignment for 2–9 players relative to the button, skipping empty seats
- Small- and big-blind seat assignment, including the heads-up rule where the button holds the small blind
- Per-hand player state (seat, position, blind) kept separate from the persistent table-level player
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
    ├── table.py                # seating and dealer button
    ├── position.py             # positions by player count, blinds
    ├── position_assignment.py  # position and blind per seat for one hand
    ├── hand_state.py           # HandPlayerState, per-hand player state
    └── hand_setup.py           # setup_hand, selects a hand's participants
```

`core` holds pure card and hand-evaluation logic. `game` holds table state and the rules that turn it into the participants of one hand. Persistent player state lives in `Player`; anything that belongs to a single hand lives in `HandPlayerState`. Future APIs and clients will consume the engine rather than reimplement poker rules.

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

Planned work, in intended order. None of it is implemented yet.

1. Game startup and button lifecycle
2. PokerHand / hand lifecycle
3. Hole-card and board dealing
4. Betting engine and legal actions
5. All-in handling
6. Main and side pots
7. Showdown
8. Complete game loop
9. Bots
10. Backend/API
11. Real-time multiplayer
12. Web/mobile clients
13. Analytics / coaching features

## Project Status

**Work in progress.**

The engine currently covers cards, hand evaluation, table state, and hand setup. It does not yet start or play a hand: there is no dealing, betting, pot handling, or showdown, and no CLI, API, or client.

The current focus is completing the core No-Limit Texas Hold'em game engine before adding networking and presentation layers.
