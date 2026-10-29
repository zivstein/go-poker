# Current Cycle

**Milestone 1: PokerHand + Dealing Foundation** (see [ROADMAP.md](ROADMAP.md))

## Goal

At the end of this milestone, the engine represents a real hand with participants, deck, private cards, board, and street progression. There is still no betting.

Out of scope for this milestone: betting and legal actions, pots, all-in handling, showdown and settlement, variants other than Texas Hold'em, and hand history.

The ownership rules this milestone follows are in [ARCHITECTURE.md](ARCHITECTURE.md#pokerhand-planned-cycle-1).

## Cycles

| Cycle | Title | Status |
| --- | --- | --- |
| 1 | PokerHand aggregate | Not started |
| 2 | Deterministic deck + Texas Hold'em private-card dealing | Not started |
| 3 | Streets + board dealing | Not started |
| 4 | Integration hardening | Not started |

### Cycle 1 — PokerHand aggregate

- `PokerHand` becomes the aggregate for one hand.
- It owns the participants (`HandPlayerState` objects), the `Deck`, and the board.
- Lifecycle functions return `PokerHand` rather than a bare tuple of `HandPlayerState`.
- No dealing yet.

### Cycle 2 — Deterministic deck + Texas Hold'em private-card dealing

- Make randomness and deck behavior reliably testable.
- Add Hold'em-specific dealing under `src/go_poker/game/variants/texas_holdem/`.
- Add private cards to `HandPlayerState` without structurally assuming two cards.
- Texas Hold'em rules deal two cards per player.

### Cycle 3 — Streets + board dealing

- `PREFLOP` / `FLOP` / `TURN` / `RIVER` progression.
- Texas Hold'em burn / flop / turn / river dealing.
- The board remains owned by `PokerHand`.

### Cycle 4 — Integration hardening

- Deal-order and deck-consumption invariants.
- Heads-up and 2–9 player coverage.
- Duplicate-card protection.
- Invalid transition coverage.
- Deterministic tests.
