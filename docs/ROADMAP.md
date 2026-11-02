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
| 6 | Structured Hand History / Event Log | Complete |
| 7 | Player view + local table | **In progress** (Cycle 1 of 4 complete) |
| 8 | Private table online | Planned (Friends Alpha) |
| 9 | Friends Alpha v0.1 | Planned (Friends Alpha) |
| 10 | Bots + simulation / large-scale testing | Post-Alpha |
| 11 | Omaha + Pot-Limit / PLO | Post-Alpha |
| 12 | Pineapple | Post-Alpha |
| 13 | Mixed/private-table per-hand variant selection | Post-Alpha |
| 14 | Chinese Poker game family | Post-Alpha |
| 15 | Unified history + stats/analytics | Post-Alpha |
| 16 | Accounts + persistence/database | Post-Alpha |
| 17 | Reconnect + platform scaling | Post-Alpha |
| 18 | Mobile/desktop clients | Post-Alpha |
| 19 | AI analysis/coaching/player assistant | Post-Alpha |
| 20 | Further variants, tournaments, and game modes | Post-Alpha |

Milestones 7–9 are the Roadmap-to-Alpha, approved on 2026-11-02 (see [Reach a Friends Alpha](#reach-a-friends-alpha)). The order of the post-Alpha milestones is provisional and is revisited after the Friends Alpha. The former Backend API, Real-time multiplayer and Web client milestones are absorbed into Milestones 7–9; reconnect beyond rejoining by guest token, and scaling beyond one server process, become Milestone 17.

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
- leaving and sitting out during a hand, as application-level hand-boundary intents with an automatic action for a leaving player (Milestone 7); an action timer (Milestone 9);
- busting, rebuys, and top-ups (a simple play-money rebuy/top-up between hands, Milestone 9);
- blind levels, antes, straddles, dead-button and missed-blind rules (Milestone 20);
- run it twice.

### Change Table Rules Only Between Hands

An active hand captures the effective rules it starts with; a hand already captures its stakes when betting is initialized. Game and table configuration changes take effect only at a hand boundary.

Milestone 5's `HoldemGame` keeps its stakes fixed for its lifetime ([ADR 0002](adr/0002-hand-lifecycle-orchestration-contract.md) §3). That is the Milestone 5 implementation contract, not a permanent product rule. Changing stakes, betting structures (Milestone 11), per-hand variant selection (Milestone 13), antes, straddles, and other house rules are future work. No generic configuration framework is built until a milestone needs one.

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

- serialization: the wire form of player views (Milestone 7); completed-history JSON logs (Milestone 9); history storage formats (Milestone 16);
- the player-view projection and redaction of hidden data (Milestone 7, [ADR 0005](adr/0005-player-view-and-table-session-boundary.md));
- table and session identifiers (application-level, Milestone 7); global hand identifiers and any table-wide hand sequence (a later application/persistence concern); timestamps and clocks, which stay outside the engine (application timers from Milestone 7);
- a replay engine, rebuilding a live `PokerHand` from history, and validating externally supplied histories;
- history query helpers and analytics, including a "board plays" flag (Milestone 15);
- table- and game-level events (sitting down, standing up, status changes);
- guest and display identity (application-level, Milestone 7); accounts and participant uniqueness beyond a table (Milestone 16);
- hand strength for other variants, and localized descriptions.

### Reach a Friends Alpha

Approved on 2026-11-02: the next product checkpoint is a **Friends Alpha**, and Milestones 7–9 are the shortest sound path to it. A user can:

1. open the Go! Poker website;
2. create a private table or join one through a link or code;
3. use a simple guest identity and display name;
4. sit at the table;
5. play with several real human players connected at once;
6. start and play consecutive Texas Hold'em hands;
7. see only the information they are allowed to see;
8. make Fold / Check / Call / Bet / Raise and SHOW / MUCK decisions;
9. see the board, stacks, pots, current actor, action and result feedback, and the hand result;
10. continue into later hands without anyone resetting the engine.

Desktop web is enough, and visual polish can be modest.

Non-goals for the first Alpha:

- native mobile or desktop apps;
- tournaments, clubs, payments, rake, and real money;
- advanced anti-cheat;
- variants beyond Hold'em;
- AI bots or coaching;
- persistent statistics;
- complex accounts or authentication;
- social features, matchmaking, and lobby discovery;
- reconnect perfection;
- a hand-history UI beyond what play and debugging need;
- production-scale traffic.

The boundaries between the engine, the application layer, and the server are in [ADR 0005](adr/0005-player-view-and-table-session-boundary.md) (accepted 2026-11-02). In summary:

- one authoritative server-side game state;
- clients never decide poker legality;
- clients never receive hidden information they may not see;
- the projection is read-only derived state;
- the application layer coordinates the engine and never reimplements poker rules.

#### Milestones

| # | Milestone | Purpose | Ends with |
| --- | --- | --- | --- |
| 7 | Player view + local table | Engine player-view projection; transport-free `TableSession` application layer; real-time WebSocket server; unstyled browser client skeleton | Several local browser tabs play consecutive hands at one table, each seeing only what it may see |
| 8 | Private table online | First remote deployment; private-table link flow, display names, and rejoin by guest token; playable table UI | A friend opens a URL and plays remotely with a legible UI |
| 9 | Friends Alpha v0.1 | Table-life rules (action timer, sit out / back, rebuy and top-up) and hardening (socket drops, logs, limits, cleanup), then a playtest | Friends Alpha v0.1 |

The Milestone 7 Cycle split is in `CURRENT_CYCLE.md`. Milestones 8 and 9 are split into Cycles when they are planned.

#### Approved decisions

Approved on 2026-11-02:

- **Player view.**
  - The poker visibility boundary lives in the engine: `game/visibility.py` plus the Hold'em view layer.
  - Clients receive full per-viewer snapshots plus an allowlist-redacted log of the current hand. There is no diff protocol.
- **Server.**
  - Python with Starlette, uvicorn, and WebSocket.
  - Server dependencies stay outside the dependency-free engine.
  - Python 3.14 compatibility is confirmed before the server Cycle is implemented.
- **Client.** TypeScript with React and Vite.
- **Repository.** `src/go_poker/app/` (application layer), `src/go_poker/server/` (server), and `web/` (client) in this repository.
- **Identity.**
  - A server-issued guest token and an opaque engine `player_id`.
  - The display name is separate, application-level data.
  - The creator of a private table is its host.
- **Next hand.** It starts automatically after a short pause, about 5 seconds as the initial product default. The pause is owned by the application/server, not the engine.
- **Stale commands.**
  - A monotonic application-level revision is the concurrency token.
  - Every snapshot carries it, and every state-changing command carries the revision it expects.
- **Leaving and sitting out during a hand.**
  - These are recorded as pending hand-boundary intents. The current hand's engine state is not changed.
  - When a leaving player's turn comes, the application checks if that is legal, otherwise folds, and mucks at a showdown decision.
  - The leave takes effect after settlement.
- **Engine-generation reset.**
  - At a hand boundary, when the current engine game can no longer progress because no `READY` player with chips remains, the application rebuilds a fresh engine `Table` and `HoldemGame`.
  - The private table, its code, guests, seats, names, and revision persist.
  - This is an application-layer policy. The engine lifecycle contract is unchanged.
- **Rebuy.** Milestone 9 may add a simple play-money rebuy/top-up policy between hands.
- **Browser test.** A minimal Playwright browser smoke test, folded into the Milestone 8 UI Cycle once the playable UI exists.
- **History logs.** Completed-history JSON logs are useful work for Milestone 9.
- **No autoplayer.** No dev-only autoplayer is added unless a later test or load need independently justifies it.
- **Hosting.** The hosting provider is decided at Milestone 8 planning.

### Exercise the Engine at Scale

After the Friends Alpha, Milestone 10 introduces bots and simulation for large-scale validation and experimentation.

### Expand Poker Variants

Omaha + Pot-Limit (Milestone 11) provides the second concrete variant/betting-structure combination and creates the first strong opportunity to extract proven shared abstractions.

Pineapple and mixed/private-table selection follow.

Milestone 13 may select the poker variant at table/session level or per hand. The exact product design remains future work.

Chinese Poker remains a separate game family.

### Grow the Platform

After the Friends Alpha:

- accounts and persistence (Milestone 16) replace guest-only, in-memory tables;
- reconnect and platform scaling (Milestone 17) go beyond rejoining by guest token and beyond one server process.

### Add Clients

The web client is built in Milestones 7–9. Later mobile and desktop clients (Milestone 18) consume the same server protocol and engine contracts rather than recreating poker rules.

### Add Analytics and AI

Structured history, simulation, statistics, and real gameplay data provide the foundation for later analysis, coaching, and player-assistant capabilities.
