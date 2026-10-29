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
| `game/` | Current | Players, seats, table, game lifecycle, hand setup, and the `PokerHand` aggregate | Accounts, persistence, APIs, clients |
| `game/variants/` | Planned (Cycle 2) | Variant-specific poker rules; first implementation in `game/variants/texas_holdem/`, starting with dealing | Accounts, persistence, APIs, clients |
| `game/betting/` | Planned (milestone 2) | Betting-structure–specific rules | Accounts, persistence, APIs, clients |
| Hand history / events | Planned (milestone 6) | Structured raw record of every hand | APIs, clients |
| Accounts, persistence, API, clients | Planned (milestones 10+) | Users, storage, networking, presentation | — (they depend on the engine, never the reverse) |

Paths are relative to `src/go_poker/`. The `game/variants/` and `game/betting/` locations are module-ownership decisions only; neither package is created until its first responsibility appears.

## Core

`core/` is pure card, deck, and hand-evaluation functionality: `Card`, `Rank`, `Suit`, `Deck`, `HandRank`, and the evaluator. It has no knowledge of tables, players, hands in play, accounts, APIs, or clients, and it stays that way.

## Game domain (current)

Persistent runtime state is kept separate from state that belongs to one hand.

**Persistent state**

- `Player` — a poker participant with an id, a chip stack, and a `PlayerStatus` (`WAITING`, `READY`, `SITTING_OUT`).
- `Seat` — one physical seat, holding at most one `Player`.
- `Table` — owns the physical seats, seating rules (sit in, stand up), and the stored button seat. `Table` does **not** own `PlayerStatus` lifecycle policy or button traversal policy; it stores the button but never decides where it moves.

**Rules that operate on that state**

- `hand_setup` — owns hand participation and `WAITING` entry rules: which seated players take part in the next hand, and when a waiting player may enter (big blind or a non-blind position, never button or small blind).
- `game_lifecycle` — owns explicit game start and restart (`start_game`, with an injected button chooser) and button traversal between hands (`start_next_hand`). Both return the new hand as a `PokerHand`. Seating alone never starts a game.
- `position` / `position_assignment` — positions and blinds relative to the button for a given set of seats.

**Per-hand state**

- `PokerHand` — the aggregate for one hand (see [below](#pokerhand)).
- `HandPlayerState` — one player's state for one hand: seat, position, blind, and hand flags. It references the persistent `Player` rather than copying it.

## PokerHand

`PokerHand` is the aggregate for one hand. It owns:

- the participating `HandPlayerState` objects, in the order `setup_hand` produces them (clockwise from the button)
- the hand's own `Deck`: a fresh 52-card deck per hand, never shared between hands
- the community board, empty until board dealing exists

Later hand-level state, such as street, action, and pot state, is added as those responsibilities appear. No cards are dealt yet.

`PokerHand` is a plain container. It does not re-validate participation; `hand_setup` remains the single owner of those rules. The hand-starting lifecycle functions (`start_game`, `start_next_hand`) return a `PokerHand` built from `setup_hand`'s participants.

### Card ownership

- Community board cards belong to `PokerHand`.
- Private (hole) cards belong to each `HandPlayerState` (planned, Cycle 2).
- A player's combined board + hole cards are never stored as separate state. They are derived when needed, for example at evaluation.
- Hole-card storage does not structurally assume exactly two cards. Variant rules decide the count.

## Variants and betting structures

These are separate, independent dimensions.

**Poker variants** — for example Texas Hold'em, Omaha, Pineapple. Variant rules may control:

- private-card counts
- dealing procedure
- discard phases
- community-card behavior
- hand-evaluation constraints (for example, Omaha's "exactly two hole cards")

**Betting structures** — No Limit, Pot Limit, Fixed Limit.

A variant is never coupled to one betting structure. A game is a composition of the two: PLO is Omaha rules + Pot-Limit betting, and No-Limit Hold'em is Texas Hold'em rules + No-Limit betting.

### Extensibility policy

- Do not create abstract base classes or protocols for future variants or betting structures yet.
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
