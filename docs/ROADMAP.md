# Go! Poker Roadmap

High-level milestones in intended order. This is the single source of truth for the project roadmap; the [README](../README.md) links here rather than repeating it.

The active milestone is broken into cycles in [CURRENT_CYCLE.md](CURRENT_CYCLE.md). Architecture decisions referenced below are in [ARCHITECTURE.md](ARCHITECTURE.md).

| # | Milestone | Status |
| --- | --- | --- |
| 0 | Engine foundation | Complete |
| 1 | PokerHand + dealing + streets | **Current** |
| 2 | Betting engine + legal actions | Planned |
| 3 | All-in + main/side pots | Planned |
| 4 | Showdown + settlement | Planned |
| 5 | Complete continuous game loop | Planned |
| 6 | Structured Hand History / Event Log | Planned |
| 7 | Bots + simulation / large-scale engine testing | Planned |
| 8 | Validate extensibility with Omaha + Pot-Limit | Planned |
| 9 | Stats / analytics engine | Planned |
| 10 | Accounts + persistence/database | Planned |
| 11 | Backend API | Planned |
| 12 | Real-time multiplayer / reconnect | Planned |
| 13 | Web client | Planned |
| 14 | Mobile / desktop clients | Planned |
| 15 | AI analysis / coaching / player assistant | Planned |
| 16 | Further variants, game modes and tournaments | Planned |

## Milestone notes

**0. Engine foundation** — cards, deck, and hand evaluation; players, seats, and table; explicit game start and button movement; positions, blinds, and hand setup.

**1. PokerHand + dealing + streets** — a `PokerHand` aggregate that owns participants, deck, and board; deterministic deck behavior; Texas Hold'em private-card and board dealing; street progression. No betting. See [CURRENT_CYCLE.md](CURRENT_CYCLE.md).

**2. Betting engine + legal actions** — betting-structure behavior under `src/go_poker/game/betting/`, starting with No Limit.

**6. Structured Hand History / Event Log** — raw hand events become the source of truth that later stats, persistence, and AI features build on.

**8. Validate extensibility with Omaha + Pot-Limit** — the second variant and second betting structure. Shared abstractions are extracted here, once two implementations show what is common.

**9–10. Stats, accounts, persistence** — stats are derived from hand history; accounts live outside the engine, and bots and guests still play without one.
