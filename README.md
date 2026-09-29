# Go! Poker

A modular No-Limit Texas Hold'em engine built in Python.

Go! Poker is an ongoing software-development project focused on clean domain modeling, poker game logic, algorithms, and automated testing.

The core engine is intentionally independent from presentation and networking layers, allowing the same game logic to later power CLI, web, and mobile clients.

## Current Features

- Card, rank, suit, and standard 52-card deck models
- Configurable 2–9 seat poker tables
- Player seating and dealer-button rotation
- Dynamic table-position assignment
- Heads-up position and blind handling
- Five-card poker hand evaluation
- Best-hand evaluation from 5–7 available cards
- Full hand comparison with category ranking, kickers, and tie-breaking
- Automated test suite with pytest
- Static type checking and linting with mypy and Ruff

## Architecture

```text
src/go_poker/
├── core/
│   ├── card.py
│   ├── deck.py
│   ├── hand_rank.py
│   └── evaluator.py
│
└── game/
    ├── position.py
    ├── position_assignment.py
    ├── seat.py
    └── table.py
```

The project separates pure card and hand-evaluation logic from table and game-state logic. Future APIs and clients will consume the engine rather than reimplement poker rules.

## Development

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

- Player stack and lifecycle state
- Hand setup and player-entry rules
- Preflop, flop, turn, and river game state
- Betting actions and legal-action validation
- All-in handling
- Main and side-pot calculation
- Showdown and pot distribution
- Computer-controlled players
- Playable CLI
- FastAPI backend
- WebSocket multiplayer
- Web and mobile clients

## Project Status

**Work in progress.**

The current focus is completing the core No-Limit Texas Hold'em game engine before adding networking and presentation layers.