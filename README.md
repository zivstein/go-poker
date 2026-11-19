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
- Interactive SHOW / MUCK showdown on the river, with automatic all-in showdowns

### Hand History

- Structured, immutable hand history with full fact replay: participants, blinds, deals, betting, showdown decisions, and the settlement, with the final stacks derivable from the history alone

### Hand and Game Orchestration

- Automatic hand orchestration: after each action the engine collects betting rounds, deals streets, runs out the board, starts the showdown, and settles
- Continuous `HoldemGame` loop: start the game once, play a hand through `act`, then `next_hand`, with busted players skipped and new players entering between hands

### Quality

- Unit and integration tests
- Deterministic randomized hand stress tests, from betting through settlement
- Ruff linting and formatting
- mypy type checking
- GitHub Actions CI

## Architecture

    src/go_poker/
    ├── core/                  cards, deck, hand evaluation
    └── game/
        ├── player / seat / table
        ├── hand setup + lifecycle
        ├── PokerHand state + immutable hand history
        ├── betting/           No-Limit betting + pots
        ├── settlement         pot awards + payout
        └── variants/
            └── texas_holdem/  Hold'em dealing, showdown, hand_flow (one hand), game (continuous HoldemGame)

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

Requires Python 3.14+ and [`uv`](https://docs.astral.sh/uv/), plus Node 26 LTS with npm for the Web toolchain in `web/` (the exact version is pinned in `web/.nvmrc`).

    uv sync

    (cd web && npm ci)

    uv run scripts/verify.py

This runs Ruff check, Ruff format check, mypy, and pytest, then the Web gates in `web/` (`tsc --noEmit`, `biome ci`, `vitest run`, `vite build`), and ends with `VERIFY: PASS` or `VERIFY: FAIL`. A missing Node or missing Web dependencies fail verification.

Coverage:

    uv run pytest --cov=go_poker

### Local development bot

`scripts/dev_bot.py` is a developer-only bot for playing and testing locally. It uses only the public `go-poker.v1` surface and talks to `127.0.0.1` by default. It joins a table by code, takes the lowest free seat and plays whatever the server offers it: Check, otherwise Call, otherwise Fold, and Show at showdown. It never bets or raises.

**One human, one bot** (two terminals and the browser, all from the repository root; a third terminal runs the bot):

    uv run uvicorn go_poker.server.app:create_app --factory --host 127.0.0.1 --port 8000 --ws websockets --ws-ping-interval 20 --ws-ping-timeout 20 --ws-max-size 16384

    (cd web && npm run dev)

1. Open the Web address Vite prints (normally <http://localhost:5173>), enter your name, press **Create**, and read the table code in the header.
2. Join a bot with that code:

       uv run scripts/dev_bot.py join CODE

3. Press **Start game** in the Web client. You are the host and the bot is never the host, so you always start the game. Two players are enough.

**More bots** are independent processes, each its own guest. Give each a distinct `--name`; `--seat N` picks a seat (default: the lowest free one, 1 to the table's seat count, 6 by default):

    uv run scripts/dev_bot.py join CODE --name "Bot A"
    uv run scripts/dev_bot.py join CODE --name "Bot B"
    uv run scripts/dev_bot.py join CODE --name "Bot C" --seat 5

Join the bots before pressing Start game. `--base-url` points at another server (default `http://127.0.0.1:8000`).

**Smoke test.** Two bots play three hands against a throwaway server on a free local port, so nothing needs to be running. It prints `SMOKE: PASS` or `SMOKE: FAIL` with the reasons and exits 0 or 1. Options: `--hands N`, `--timeout SECONDS`, `--verbose` (every bot log line).

    uv run scripts/dev_bot.py smoke

**Stopping.** Ctrl+C or `kill` (SIGTERM) makes the bot leave the table first, then exit 0. Before the game starts the seat is freed at once; during a hand the server folds for the bot when its turn comes and frees the seat when the hand ends, so the table does not stall. The attempt is bounded by 3 seconds. A second Ctrl+C abandons it and exits immediately. A bot ends by itself, with exit 1 and a reason, when the server ends its membership (AUTH_FAILED, superseded, table failed) or sends something the protocol does not allow.

**Offline.** Nothing is downloaded or called at run time. The bot needs only the packages `uv sync --locked` installs (`websockets` and `uvicorn` come with the dev dependencies), so run that once with internet. Then:

    UV_OFFLINE=1 uv run scripts/dev_bot.py smoke

**Known limitations.**

- The leave on Ctrl+C is best effort. SIGKILL (`kill -9`), a crash or a lost machine cannot run it, and then the seat stays occupied and the table waits whenever it is that bot's turn (v1 has no action timers). To go on, create a new table or restart the server.
- A bot that has no connection when stopped (the server is down, or it is waiting to reconnect) exits at once without leaving. A bot never leaves because of a temporary disconnect, and a leave whose answer is lost is not sent again.
- Restarting the server loses every table; a running bot then stops with AUTH_FAILED.
- The bot cannot see the table before joining, so it finds a free seat by trying seats in order. A join whose reply is lost is reported, not repeated, and may leave a seat taken.
- A bot never bets, raises or sits out.

**Troubleshooting.**

- `nothing is listening at …`: the server is not running on that address. Start it with the command above, or pass the right `--base-url`.
- `404 TABLE_NOT_FOUND`: wrong code, or the server was restarted since the table was created. Codes are six characters from `23456789ABCDEFGHJKMNPQRSTUVWXYZ`.
- `409 DISPLAY_NAME_TAKEN`: another player has that name; use `--name`.
- `joining failed: no free seat` or `409 SEAT_TAKEN`: the table is full or that seat is taken.
- `connection failed … reconnecting`: the server went away; the bot retries with backoff until it is back or the table is gone.
- `uv` tries to download packages: run `uv sync --locked` once online, then use `UV_OFFLINE=1`.

## Project Status

The Current Capabilities above describe what the engine supports today. Persistence, API, networking, and clients are not implemented yet.

- [`docs/ROADMAP.md`](docs/ROADMAP.md) — authoritative milestone status
- [`docs/CURRENT_CYCLE.md`](docs/CURRENT_CYCLE.md) — active work
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture and invariants
