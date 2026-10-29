# Current Cycle

**Milestone 1: PokerHand + Dealing Foundation** (see [ROADMAP.md](ROADMAP.md)) — **COMPLETE**

All five cycles are complete, so there is no current cycle. The next milestone, **Milestone 2 — Betting Engine + Legal Actions**, is next but not started. It is broken into cycles when it starts.

## Goal

At the end of this milestone, the engine represents a real hand with participants, deck, private cards, board, and street progression. There is still no betting.

Out of scope for this milestone: betting and legal actions, pots, all-in handling, showdown and settlement, variants other than Texas Hold'em, and hand history.

The ownership rules this milestone follows are in [ARCHITECTURE.md](ARCHITECTURE.md#pokerhand).

## Cycles

| Cycle | Title | Status |
| --- | --- | --- |
| 1 | PokerHand aggregate | Complete |
| 2 | Deterministic deck + Texas Hold'em private-card dealing | Complete |
| 3 | Streets + board dealing | Complete |
| 4 | Integration hardening | Complete |
| 5 | Simplification + milestone closeout | Complete |

### Cycle 1 — PokerHand aggregate

- `PokerHand` becomes the aggregate for one hand.
- It owns the participants (`HandPlayerState` objects), the `Deck`, and the board.
- Lifecycle functions return `PokerHand` rather than a bare tuple of `HandPlayerState`.
- No dealing yet.

### Cycle 2 — Deterministic deck + Texas Hold'em private-card dealing

- Make randomness and deck behavior reliably testable. Determinism exists only in tests; engine shuffles are secure and never reproducible (see the randomness rule in [ARCHITECTURE.md](ARCHITECTURE.md#core)).
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
- Duplicate-card protection (removed in Cycle 5; uniqueness holds by construction).
- Invalid transition coverage.
- Deterministic tests.

### Cycle 5 — Simplification + milestone closeout

- Remove the runtime duplicate-card scan (`ensure_unique_cards`, `DuplicateCardError`, `card in deck`). Card uniqueness holds by construction and is proven by one test-only 52-card accounting invariant.
- Simplify the milestone's tests: one focused test per domain rule, representative boundaries, and a small number of strong integration tests.
- Tighten randomness boundaries: `_rng` stays only on `Deck.shuffle` as a test seam and is removed from `start_game` / `start_next_hand`. Lifecycle and dealing tests that need determinism patch `Deck.shuffle` to forward a seeded `_rng`.
- `PokerHand` requires an explicit `deck`; the lifecycle owns the shuffle policy.
- The Texas Hold'em `InvalidHoleCardCountError` (exactly two hole cards before board dealing) replaces `HoleCardsNotDealtError`.
- Keep Texas Hold'em's street transitions variant-owned.
- Document the `PokerHand` family (Texas Hold'em, Omaha, Pineapple) and Chinese Poker as a separate game family in [ARCHITECTURE.md](ARCHITECTURE.md).
- Renumber the [roadmap](ROADMAP.md).
- Use pytest's `importlib` import mode so same-named test modules in different variant directories do not collide.
