# Go! Poker

A modular poker engine and AI-engineering lab built in Python.

The current product focus is a clean, fully tested No-Limit Texas Hold'em engine.

The engine is intentionally independent from persistence, networking, and presentation so the same rules can later power APIs, web, mobile, desktop, bots, simulation, and analysis.

## Current Capabilities

### Core

- Cards, ranks, suits, and a 52-card deck
- Secure production shuffling with a deterministic test seam
- Comparable poker hand ranks
- Five-card and best-of-5–7 evaluation

### Table and Hand Lifecycle

- 2–9 seat tables
- Players, seats, participation states, positions, and blinds
- Explicit game start and button movement
- Waiting/sitting-out participation rules
- `PokerHand` aggregate with per-hand player state

### Texas Hold'em

- Two-card private dealing
- Burn cards
- Flop, turn, and river dealing
- Street progression

### No-Limit Betting

- Blind posting
- Fold / check / call / bet / raise
- Derived legal actions
- Full and short all-ins
- Raise reopening, including cumulative short all-ins
- Multi-street betting
- Unmatched-chip return
- Collected middle pot
- Derived main and side pots with eligibility

### Showdown and Settlement

- Hold'em hand strength from two hole cards and the board
- Uncontested wins and showdowns
- Per-pot winners, ties, and odd-chip allocation
- Chip payout and an immutable stored settlement

### Quality

- Unit and integration tests
- Deterministic randomized betting stress tests
- Ruff linting and formatting
- mypy type checking
- GitHub Actions CI

## Architecture

    src/go_poker/
    ├── core/                  cards, deck, hand evaluation
    └── game/
        ├── player / seat / table
        ├── hand setup + lifecycle
        ├── PokerHand state
        ├── betting/           No-Limit betting + pots
        ├── settlement         pot awards + payout
        └── variants/
            └── texas_holdem/  Hold'em-specific dealing + showdown

The engine owns poker rules.

Future APIs and clients consume those rules rather than reimplementing them.

Detailed ownership, state semantics, and invariants are documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Example

    from go_poker.core.card import Card, Rank, Suit
    from go_poker.core.evaluator import evaluate_best

    board = [
        Card(Rank.KING, Suit.SPADES),
        Card(Rank.KING, Suit.DIAMONDS),
        Card(Rank.SEVEN, Suit.CLUBS),
        Card(Rank.FOUR, Suit.HEARTS),
        Card(Rank.TWO, Suit.SPADES),
    ]

    rank = evaluate_best(
        [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            *board,
        ]
    )

    print(rank)

## Development

Requires Python 3.14+ and [`uv`](https://docs.astral.sh/uv/).

    uv sync

    uv run pytest
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy src

Coverage:

    uv run pytest --cov=go_poker

## Project Status

The Current Capabilities above describe what the engine supports today. Automatic board runout and a complete automatic hand loop, structured history, persistence, API, networking, and clients are not implemented yet.

- [`docs/ROADMAP.md`](docs/ROADMAP.md) — authoritative milestone status
- [`docs/CURRENT_CYCLE.md`](docs/CURRENT_CYCLE.md) — active work
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture and invariants
