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
| `game/` | Current | Players, seats, table, game lifecycle, hand setup, streets, and the `PokerHand` aggregate | Accounts, persistence, APIs, clients |
| `game/variants/` | Current | Variant-specific poker rules; first implementation in `game/variants/texas_holdem/`: hole-card and board dealing | Accounts, persistence, APIs, clients |
| `game/betting/` | Planned (milestone 2) | Betting-structure–specific rules | Accounts, persistence, APIs, clients |
| Hand history / events | Planned (milestone 6) | Structured raw record of every hand | APIs, clients |
| Accounts, persistence, API, clients | Planned (milestones 10+) | Users, storage, networking, presentation | — (they depend on the engine, never the reverse) |

Paths are relative to `src/go_poker/`. The `game/variants/` and `game/betting/` locations are module-ownership decisions; a package is created only when its first responsibility appears. `game/variants/` exists (Texas Hold'em dealing); `game/betting/` does not exist yet.

## Core

`core/` is pure card, deck, and hand-evaluation functionality: `Card`, `Rank`, `Suit`, `Deck`, `HandRank`, and the evaluator. It has no knowledge of tables, players, hands in play, accounts, APIs, or clients, and it stays that way.

**Randomness rule.** A new `Deck()` is in creation order until shuffled. `Deck.shuffle()` uses the OS CSPRNG (`random.SystemRandom`, which cannot be seeded), so engine shuffles are never reproducible. `Deck.shuffle()`, `start_game`, and `start_next_hand` accept an underscored `_rng` keyword (a `random.Random`) that is test-only: tests pass a seeded generator to get a reproducible deck order, and engine code must never pass it.

## Game domain (current)

Persistent runtime state is kept separate from state that belongs to one hand.

**Persistent state**

- `Player` — a poker participant with an id, a chip stack, and a `PlayerStatus` (`WAITING`, `READY`, `SITTING_OUT`).
- `Seat` — one physical seat, holding at most one `Player`.
- `Table` — owns the physical seats, seating rules (sit in, stand up), and the stored button seat. `Table` does **not** own `PlayerStatus` lifecycle policy or button traversal policy; it stores the button but never decides where it moves.

**Rules that operate on that state**

- `hand_setup` — owns hand participation and `WAITING` entry rules: which seated players take part in the next hand, and when a waiting player may enter (big blind or a non-blind position, never button or small blind).
- `game_lifecycle` — owns explicit game start and restart (`start_game`, with an injected button chooser) and button traversal between hands (`start_next_hand`). Both return the new hand as a `PokerHand` with a fresh deck, shuffled before hand setup with the OS CSPRNG (or the test-only `_rng`). Seating alone never starts a game. The lifecycle is variant-agnostic: it deals no cards, so the new hand starts on `PREFLOP` with an empty board and no burned cards; the caller applies variant dealing (for example `texas_holdem.dealing.deal_hole_cards`, then `deal_next_street`) to the returned `PokerHand`.
- `position` / `position_assignment` — positions and blinds relative to the button for a given set of seats.

**Per-hand state**

- `PokerHand` — the aggregate for one hand (see [below](#pokerhand)).
- `HandPlayerState` — one player's state for one hand: seat, position, blind, hand flags, and hole cards. It references the persistent `Player` rather than copying it.

## PokerHand

`PokerHand` is the aggregate for one hand. It owns:

- the participating `HandPlayerState` objects, in the order `setup_hand` produces them (clockwise from the button)
- the hand's own `Deck`: a fresh 52-card deck per hand, never shared between hands. `PokerHand`'s default deck is unshuffled (in creation order); only the lifecycle shuffles it, so engine code creates hands through `start_game` / `start_next_hand`
- the community board, empty until variant rules deal it
- the current `Street` (`PREFLOP`, `FLOP`, `TURN`, `RIVER`), starting on `PREFLOP`
- the burned cards, empty until variant rules burn cards before dealing the board, kept so every card drawn from the deck stays accounted for

`Street` lives in `game/` (`game/street.py`), not in a variant, because `PokerHand` owns the street and `game/` must not depend on `game/variants/`. Variant rules decide how the hand moves between streets.

Later hand-level state, such as action and pot state, is added as those responsibilities appear. Hole cards, burned cards, and the board are dealt by variant rules from the hand's deck, and the same rules advance the street.

`PokerHand` is a plain container. It does not re-validate participation; `hand_setup` remains the single owner of those rules. The hand-starting lifecycle functions (`start_game`, `start_next_hand`) return a `PokerHand` built from `setup_hand`'s participants.

### Card ownership

- Community board cards belong to `PokerHand`.
- Burned cards belong to `PokerHand`.
- Private (hole) cards belong to each `HandPlayerState`, as a list that is empty until dealt.
- A player's combined board + hole cards are never stored as separate state. They are derived when needed, for example at evaluation.
- Hole-card storage does not structurally assume exactly two cards. Variant rules decide the count: Texas Hold'em (`game/variants/texas_holdem/dealing.py`) deals two, one card at a time starting clockwise of the button and ending with the button, with no burn card. Hole cards are dealt only on `PREFLOP`.
- Texas Hold'em board dealing (`deal_next_street`) moves the hand from `PREFLOP` to `FLOP`, `TURN`, and `RIVER`. Entering each street burns one card and then deals that street's board cards in draw order: three on the flop, one on the turn, one on the river. The board is dealt only after every participant holds their hole cards, and there is no street after `RIVER`.

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
