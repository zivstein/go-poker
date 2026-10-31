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
| 5 | Complete continuous PokerHand/game loop | **Current** (Cycle 1 complete; Cycle 2 next) |
| 6 | Structured Hand History / Event Log | Planned |
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

Approved for Milestone 5: running a whole Hold'em hand, and one hand after another, with player decisions as the only inputs. Being all-in does not by itself reveal hole cards. Once betting is closed with at least two live players, hand orchestration reveals the relevant hands, completes the board runout, then proceeds to showdown. The hand lifecycle and orchestration contract (the two usage levels, engine-owned sequencing through `hand_flow` and `HoldemGame`, the game lifecycle, all-in and river-showdown reveals, river show order, the reveal record, the settled-hand guard, hand start order, and mid-hand table changes staying outside the engine) is in [ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md).

Deferred beyond Milestone 5:

- voluntary show, automatic muck, and show/muck preferences;
- reporting the best five cards;
- leaving, sitting out, timeouts, and auto-fold during a hand (Milestones 14–15);
- busting, rebuys, and top-ups (no milestone assigned yet);
- blind levels, antes, straddles, dead-button and missed-blind rules (Milestone 19);
- run it twice.

### Build Reconstructable Data

Milestone 6 introduces structured raw hand history/events before persistence, analytics, or AI depend on them.

Raw history/events remain reconstructable source data. Later statistics and analytics are derived from history rather than becoming the only source of truth.

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
