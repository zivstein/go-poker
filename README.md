# Go! Poker

A modular No-Limit Texas Hold'em engine written in Python.

Go! Poker is a work-in-progress portfolio project focused on
software design, poker game logic, algorithms, and automated testing.

The core engine is intentionally independent from presentation
layers so it can later power CLI, web, and mobile clients.

## Current Features

- Card and deck domain models
- 2–9 seat poker tables
- Player seating and dealer-button rotation
- Dynamic table positions
- Heads-up position and blind rules
- 5-card poker hand evaluation
- Best-hand evaluation from 5–7 cards
- Complete hand tie-breaking and kicker comparison
- Automated pytest test suite

## Architecture

src/go_poker/
├── core/
│   ├── card.py
│   ├── deck.py
│   ├── hand_rank.py
│   └── evaluator.py
│
└── game/
    ├── seat.py
    ├── table.py
    ├── position.py
    └── position_assignment.py

## Running Tests

uv run pytest

## Code Quality

uv run ruff check .
uv run ruff format --check .

## Roadmap

- Player stack and hand state
- Hand setup and player entry rules
- Betting rounds and legal actions
- All-in handling and side pots
- Showdown and pot distribution
- Computer-controlled players
- CLI game
- FastAPI backend
- WebSocket multiplayer
- Web/mobile clients