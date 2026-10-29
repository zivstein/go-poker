# Go! Poker Roadmap

High-level milestones in intended order. This is the single source of truth for the project roadmap; the [README](../README.md) links here rather than repeating it.

The active milestone is broken into cycles in [CURRENT_CYCLE.md](CURRENT_CYCLE.md). It currently records the completed milestone 1; milestone 2's cycles are planned when it starts. Architecture decisions referenced below are in [ARCHITECTURE.md](ARCHITECTURE.md).

| # | Milestone | Status |
| --- | --- | --- |
| 0 | Engine foundation | Complete |
| 1 | PokerHand + dealing + streets | **COMPLETE** |
| 2 | Betting engine + legal actions | **Next** (not started) |
| 3 | All-ins + main/side pots | Planned |
| 4 | Showdown + settlement | Planned |
| 5 | Complete continuous PokerHand/game loop | Planned |
| 6 | Structured Hand History / Event Log | Planned |
| 7 | Bots + simulation / large-scale testing | Planned |
| 8 | Omaha + Pot-Limit support / PLO | Planned |
| 9 | Pineapple support | Planned |
| 10 | Mixed/private-table per-hand variant selection | Planned |
| 11 | Chinese Poker game family | Planned |
| 12 | Unified history + stats/analytics | Planned |
| 13 | Accounts + persistence/database | Planned |
| 14 | Backend API | Planned |
| 15 | Real-time multiplayer/reconnect | Planned |
| 16 | Web client | Planned |
| 17 | Mobile/desktop clients | Planned |
| 18 | AI analysis/coaching/player assistant | Planned |
| 19 | Further variants, tournaments and game modes | Planned |

## Milestone notes

**0. Engine foundation** — cards, deck, and hand evaluation; players, seats, and table; explicit game start and button movement; positions, blinds, and hand setup.

**1. PokerHand + dealing + streets** — a `PokerHand` aggregate that owns participants, deck, and board; secure engine shuffling with deterministic deck behavior in tests only; Texas Hold'em private-card and board dealing; street progression; integration tests including heads-up and multiway. Card uniqueness holds by construction and is proven by a test-only 52-card accounting invariant. No betting. See [CURRENT_CYCLE.md](CURRENT_CYCLE.md).

**2. Betting engine + legal actions** — betting-structure behavior under `src/go_poker/game/betting/`, starting with No Limit.

**6. Structured Hand History / Event Log** — raw hand events become the source of truth that later stats, persistence, and AI features build on.

**8. Omaha + Pot-Limit support / PLO** — the second variant and second betting structure, composed as PLO. Shared `PokerHand`-family abstractions are extracted here, once two implementations show what is common.

**9. Pineapple support** — a third `PokerHand`-family variant, paired with an appropriate betting structure.

**10. Mixed/private-table per-hand variant selection** — a private-table or session layer chooses the variant per table or per hand. Concepts it should eventually support:

- a fixed Texas Hold'em table
- PLO-only or Pineapple-only tables
- periodic Omaha hands
- manually requested variant changes
- voting for the next special hand
- variant rotations

**11. Chinese Poker game family** — Chinese Poker is a separate game family, not a `PokerHand` variant. It uses a distinct model such as `ChinesePokerHand`, with its own state, lifecycle, scoring, and rules, and may reuse `core/` primitives. See [ARCHITECTURE.md](ARCHITECTURE.md#chinese-poker-separate-game-family).

**12. Unified history + stats/analytics** — stats are derived from hand history rather than stored as the only source of truth.

**13. Accounts + persistence/database** — accounts live outside the engine, and bots and guests still play without one.
