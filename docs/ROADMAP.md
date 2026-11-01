# Go! Poker Roadmap

This is the product roadmap: the authoritative source for milestone status and for approved product decisions that are intentionally future and unbuilt.

Current architecture belongs in `ARCHITECTURE.md`.
Active implementation detail belongs in `CURRENT_CYCLE.md`.
AI-organization growth belongs in `docs/company/ORGANIZATION_ROADMAP.md`.

| # | Milestone | Status |
| --- | --- | --- |
| 0 | Engine foundation | Complete |
| 1 | PokerHand + dealing + streets | Complete |
| 2 | Betting engine + legal actions | Complete |
| 3 | All-ins + main/side pots | Complete |
| 4 | Showdown + settlement | Complete |
| 5 | Complete continuous PokerHand/game loop | Complete |
| 6 | Structured Hand History / Event Log | **Current** (Cycles 1–3 complete; Cycle 4 next) |
| 7 | Bots + simulation / large-scale testing | Planned |
| 8 | Omaha + Pot-Limit / PLO | Planned |
| 9 | Pineapple | Planned |
| 10 | Mixed/private-table per-hand variant selection | Planned |
| 11 | Chinese Poker game family | Planned |
| 12 | Unified history + stats/analytics | Planned |
| 13 | Accounts + persistence/database | Planned |
| 14 | Backend API | Planned |
| 15 | Real-time multiplayer/reconnect | Planned |
| 16 | Web client | Planned |
| 17 | Mobile/desktop clients | Planned |
| 18 | AI analysis/coaching/player assistant | Planned |
| 19 | Further variants, tournaments, and game modes | Planned |

## Product Direction

### Complete the Texas Hold'em Engine

Milestones 0–5 produce a complete No-Limit Texas Hold'em hand engine.

Approved for Milestone 4: settling a hand that has reached its end. Each pot is resolved independently among its eligible seats, ties split the pot, odd chips follow an approved rule, and winners are paid while the hand's contributions stay as accounting history. The showdown and settlement contract (odd-chip rule, all live hands competing, the stored settlement record, payout ownership, result shape, module placement, and the `settle_hand(hand)` entry point) is in [ADR 0001](adr/0001-showdown-settlement-contract.md). Also approved:

- only the best five cards count, and suits never break ties;
- there is no rake;
- settlement does not change participation status or handle busting or rebuys.

Board runout, revealing hands, and full-hand orchestration stay in Milestone 5.

Approved for Milestone 5: running a whole Hold'em hand, and one hand after another, with player decisions as the only inputs. Being all-in does not by itself reveal hole cards. The hand lifecycle and orchestration contract (the two usage levels, engine-owned sequencing through `hand_flow` and `HoldemGame`, the game lifecycle, the settled-hand guard, hand start order, and mid-hand table changes staying outside the engine) is in [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md).

Approved for Milestone 5 on 2026-10-31, after Cycle 2: interactive showdown and muck. When all betting is complete and any live player is all-in, every live hand is tabled at once, the board is run out, and the hand settles, with side-pot eligibility exactly as the pots define it. In a non-all-in river showdown, the last river aggressor decides first (with none, the first live seat left of the button), then clockwise; each player may SHOW or MUCK, a muck is not a fold, and a last remaining contender wins without showing. Only shown hands are evaluated or reported. The showdown contract (the two showdown kinds, decision order, SHOW/MUCK, the showdown record, the low-level operations, and the settlement interaction) is in [ADR 0003](adr/0003-interactive-showdown-and-muck.md), which supersedes the affected parts of ADR 0001 and ADR 0002.

Deferred beyond Milestone 5:

- voluntary show by a player not asked to decide (an uncontested winner or a last remaining contender), automatic muck, show/muck preferences, and showdown timers;
- a folded player voluntarily revealing one or both hole cards (a visibility and history feature only; it never changes folded status, pot eligibility, or settlement);
- reporting the best five cards (derived hand strength, Milestone 6);
- leaving, sitting out, timeouts, and auto-fold during a hand (Milestones 14–15);
- busting, rebuys, and top-ups (no milestone assigned yet);
- blind levels, antes, straddles, dead-button and missed-blind rules (Milestone 19);
- run it twice.

### Change Table Rules Only Between Hands

An active hand captures the effective rules it starts with; a hand already captures its stakes when betting is initialized. Game and table configuration changes take effect only at a hand boundary.

Milestone 5's `HoldemGame` keeps its stakes fixed for its lifetime ([ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md) §3). That is the Milestone 5 implementation contract, not a permanent product rule. Changing stakes, betting structures (Milestone 8), per-hand variant selection (Milestone 10), antes, straddles, and other house rules are future work. No generic configuration framework is built until a milestone needs one.

### Build Reconstructable Data

Milestone 6 introduces structured raw hand history/events before persistence, analytics, or AI depend on them.

Raw history/events remain reconstructable source data. Later statistics and analytics are derived from history rather than becoming the only source of truth.

Approved for Milestone 6 on 2026-11-01: a structured, immutable hand history for every hand.

- Each hand gets a number. Numbers are consecutive and scoped to a `HoldemGame`, starting at 1.
- `Player.player_id` becomes the stable logical identity of an engine participant. It is opaque and distinct from any platform, account or display identity.
  - The same `player_id` in different hand histories means the same logical participant.
  - A caller must not reuse an existing `player_id` for a different logical participant in histories intended to be linked.
  - The engine enforces only that a `player_id` is non-empty when the `Player` is created, immutable afterwards, and unique among the players currently seated at a table (the existing rule).
  - Milestone 6 adds no registry or historical-identifier tracking. Longer-lived identity consistency is the caller's, and later the platform's, responsibility.
- The low-level operations record each transition as it happens. It is a record, not event sourcing, and rules never read it.
- Every history reconstructs the hand's poker and game facts.
- Only histories produced through `hand_flow` / `HoldemGame` guarantee presentation and runout order. Raw low-level histories are faithful but not normalized.
- History stores hidden authoritative data. Projection and redaction are later work.
- `HoldemGame` does not retain past histories.

The hand history and event contract is in [ADR 0004](adr/0004-hand-history-and-event-contract.md).

Approved for Milestone 6: derived player hand strength for client display. From the flop onward, Hold'em derives for a seat its current hand category and rank, the exact best five cards, and a human-readable description (for example "Eights full of Aces" or "Ace-high flush"):

- preflop: no five-card result;
- flop: the five available cards;
- turn: the best five of six;
- river: the best five of seven.

It is derived, read-only data. It is not stored on `PokerHand` and is not part of showdown or settlement state. A future API projection exposes anything derived from hidden hole cards only to that seat's player until those cards are shown.

Approved for Milestone 6 on 2026-11-01, extending that decision:

- **Never stored.** Strength is never stored: not on `PokerHand`, the showdown, the settlement, or the hand history.
- **Who can be evaluated.** It can be computed for any participant who holds hole cards, including a folded, mucked, or settled seat. Who may see it is the projection's concern.
- **Public surface.**
  - `BestHand` holds the `HandRank`, the five cards, and the derived description.
  - `holdem_hand_strength(hole_cards, board)` returns a `BestHand`, or `None` preflop.
  - `hand_strength(hand, seat)` reads it for a seat of a hand.
  - `evaluate_best` keeps its current contract and results.
  - There is no public tie-selection or `prefer=` API.
- **Exact best five.** When several five-card combinations share the best `HandRank`, the one using the fewest hole cards is chosen. Among those, cards are preferred in deal order: board cards in the order dealt, then hole cards in the order dealt. When the board plays, the board's five cards are returned. This rule changes which cards are reported, never the rank. The selection mechanism is internal to the evaluator and the Hold'em strength code.
- **Card order.** The five cards are listed by significance, consistent with the rank's tiebreakers. The wheel is 5-4-3-2-A.
- **Descriptions.** English only, with no kickers:

| Category | Description |
| --- | --- |
| High card | "Ace high" |
| One pair | "Pair of Eights" |
| Two pair | "Two pair, Kings and Fours" |
| Three of a kind | "Three of a kind, Sevens" |
| Straight | "Nine-high straight"; the wheel is "Five-high straight" |
| Flush | "Ace-high flush" |
| Full house | "Eights full of Aces" |
| Four of a kind | "Four of a kind, Queens" |
| Straight flush | "Nine-high straight flush"; Ace-high is "Royal flush" |

Deferred beyond Milestone 6:

- serialization, wire and storage formats (Milestone 13);
- the API projection and redaction of hidden data (Milestone 14);
- global hand, table, and session identifiers; timestamps and clocks;
- a replay engine, rebuilding a live `PokerHand` from history, and validating externally supplied histories;
- history query helpers and analytics, including a "board plays" flag (Milestone 12);
- table- and game-level events (sitting down, standing up, status changes);
- account and display identity, and participant uniqueness beyond a table (platform milestones);
- hand strength for other variants, and localized descriptions.

### Exercise the Engine at Scale

Milestone 7 introduces bots and simulation for large-scale validation and experimentation.

### Expand Poker Variants

Omaha + Pot-Limit provides the second concrete variant/betting-structure combination and creates the first strong opportunity to extract proven shared abstractions.

Pineapple and mixed/private-table selection follow.

Milestone 10 may select the poker variant at table/session level or per hand. The exact product design remains future work.

Chinese Poker remains a separate game family.

### Build the Platform

Accounts/persistence, backend APIs, and real-time multiplayer are added after the engine and history contracts are stable.

### Add Clients

Web and later mobile/desktop clients consume platform and engine contracts rather than recreating poker rules.

### Add Analytics and AI

Structured history, simulation, statistics, and real gameplay data provide the foundation for later analysis, coaching, and player-assistant capabilities.
