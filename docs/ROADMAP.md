# Go! Poker Roadmap

This is the product roadmap: the authoritative source for milestone status and for approved product decisions that are intentionally future and unbuilt.

Where the [Friends Alpha Product Contract](product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md) covers the same product scope, it governs any conflicting or stale description in this roadmap (approved on 2026-11-09). Known conflicts are listed for follow-up in `CURRENT_CYCLE.md`.

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
| 7 | Player view + local table | Complete |
| 8 | Multi-Agent Engineering Organization + Product Architecture | **In progress** |
| 10 | Bots + simulation / large-scale testing | Post-Alpha (provisional) |
| 11 | Omaha + Pot-Limit / PLO | Post-Alpha (provisional) |
| 12 | Pineapple | Post-Alpha (provisional) |
| 13 | Mixed/private-table per-hand variant selection | Post-Alpha (provisional) |
| 14 | Chinese Poker game family | Post-Alpha (provisional) |
| 15 | Unified history + stats/analytics | Post-Alpha (provisional) |
| 16 | Accounts + persistence/database | Post-Alpha (provisional) |
| 17 | Reconnect + platform scaling | Post-Alpha (provisional) |
| 18 | Mobile/desktop clients | Post-Alpha (provisional) |
| 19 | AI analysis/coaching/player assistant | Post-Alpha (provisional) |
| 20 | Further variants, tournaments, and game modes | Post-Alpha (provisional) |

Milestone 7 is complete (2026-11-03). Milestone 8 is in progress: its plan was approved on 2026-11-08 ([M8 Plan](milestones/M8_PLAN.md)) and amended on 2026-11-10, and its Cycle status is in `CURRENT_CYCLE.md`. The rest of the road to the Friends Alpha is an unnumbered planning section, [Road to Friends Alpha after M8](#road-to-friends-alpha-after-m8), replanned during Milestone 8. The milestones after 8 remain provisional future direction: their numbers and order are not authoritative until Milestone 8 replans the road to the Alpha, and they may be renumbered then. ADRs accepted before 2026-11-03 use the earlier numbering, in which Milestone 8 was "Private table online" and Milestone 9 was "Friends Alpha v0.1"; that work is now in the road to the Friends Alpha after Milestone 8.

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
- leaving and sitting out during a hand, as application-level hand-boundary intents with an automatic action for a leaving player (Milestone 7); an action timer ([Road to Friends Alpha after M8](#road-to-friends-alpha-after-m8));
- busting, rebuys, and top-ups (a simple play-money rebuy/top-up between hands, [Road to Friends Alpha after M8](#road-to-friends-alpha-after-m8));
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

- serialization: the wire form of player views and completed-history JSON logs ([Road to Friends Alpha after M8](#road-to-friends-alpha-after-m8)); history storage formats (Milestone 16);
- the player-view projection and redaction of hidden data (Milestone 7, [ADR 0005](adr/0005-player-view-and-table-session-boundary.md));
- table and session identifiers (application-level, Milestone 7); global hand identifiers and any table-wide hand sequence (a later application/persistence concern); timestamps and clocks, which stay outside the engine (application or server timers, with the real-time server work);
- a replay engine, rebuilding a live `PokerHand` from history, and validating externally supplied histories;
- history query helpers and analytics, including a "board plays" flag (Milestone 15);
- table- and game-level events (sitting down, standing up, status changes);
- guest and display identity (application-level, Milestone 7); accounts and participant uniqueness beyond a table (Milestone 16);
- hand strength for other variants, and localized descriptions.

### Reach a Friends Alpha

Since M8 C0 (approved 2026-11-08), the authoritative Friends Alpha scope and requirements are in the [Friends Alpha Product Contract](product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md), as the [M8 Plan](milestones/M8_PLAN.md) records. This section predates the contract; the precedence rule at the top of this roadmap applies to it.

Approved on 2026-11-02: the next product checkpoint is a **Friends Alpha**. On 2026-11-03 the road to it was replanned: Milestone 7 ends with the transport-free application layer, Milestone 8 builds the multi-agent engineering organization and the product architecture, and the remaining Alpha work is replanned during Milestone 8 (see [Road to Friends Alpha after M8](#road-to-friends-alpha-after-m8)). At the Alpha, a user can:

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

The boundaries between the engine, the application layer, and the server are in [ADR 0005](adr/0005-player-view-and-table-session-boundary.md) (accepted 2026-11-02), partly superseded by [ADR 0006](adr/0006-shared-table-revision-and-private-intents.md) (accepted 2026-11-03) for the shared revision and private intents. In summary:

- one authoritative server-side game state;
- clients never decide poker legality;
- clients never receive hidden information they may not see;
- the projection is read-only derived state;
- the application layer coordinates the engine and never reimplements poker rules.

#### Milestones

| # | Milestone | Purpose | Ends with |
| --- | --- | --- | --- |
| 7 | Player view + local table | Engine player-view projection; transport-free `TableSession` application layer; betting pre-actions | Scripted multi-user `TableSession` tests play consecutive hands, including an engine-generation reset and pre-actions, and each user's views hold only what that user may see |
| 8 | Multi-Agent Engineering Organization + Product Architecture | Product and UX design; the engineering organization and a native-first parallel workflow, proven by a Backend + Web proof of concept; the Backend/API and Web architecture with a shared Core–Backend–Web contract; replanning the road to the Friends Alpha | The [M8 exit gates](milestones/M8_PLAN.md#m8-exit-gates) |

Milestone 7's implemented behavior is recorded in `ARCHITECTURE.md` and its Cycle history in Git. Milestone 8's Cycle split is in the [M8 Plan](milestones/M8_PLAN.md), and its Cycle status in `CURRENT_CYCLE.md`.

Approved on 2026-11-10, at M8 C5.4:

- **Enforcement.** C5.4a (the ownership map and the CI `ownership` check) stays complete and in force. C5.4b (the custom guard hook) is stopped and superseded. Its guard was registered locally, caused a lockout and was removed, and it was never committed. The custom guard and mandatory multi-lane enforcement are not prerequisites for product development ([retrospective](company/C5_4_ENFORCEMENT_RETROSPECTIVE.md)).
- **Workflow.** Development is native-first and manually coordinated by the Product Owner: separate Claude Code sessions in Git worktrees, focused Cycles with QA and Reviewer, and Owner approval and merge. No autonomous orchestrator is built.
- **Sequence.**
  1. Backend/API architecture planning.
  2. Web planning, coordinated with Core and Backend.
  3. A shared Core–Backend–Web contract.
  4. A first parallel iteration with Backend and Web (amended 2026-11-11, below).
  5. Its measured evaluation.
  6. Later parallel iterations across Core, Backend and Web.

  The detail is in the [M8 Plan](milestones/M8_PLAN.md#c6-parallel-development-poc).

Approved on 2026-11-11, at M8 C6.1 ([C6.1 plan](milestones/M8_C6_1_BACKEND_API_PLAN.md), [ADR 0008](adr/0008-fastapi-server-and-single-writer-tables.md), accepted):

- **Backend architecture.** FastAPI and uvicorn; a modular monolith; WebSocket with snapshots per player; one authoritative writer per table (`TableRuntime`). The Python Core and `TableSession` are preserved. The wire protocol is ADR 0009 (C6.3).
- **POC.** C6.4 is Backend ∥ Web, small and local (one process, in memory, private tables), after a bounded preflight for dependencies and the Web toolchain.
- **Seats.** The POC may join without a pre-join seat view. Friends Alpha shows the available seats before the player chooses one (Contract §2).
- **Table categories.** Private tables now. Later, Quick Play public pools grouped by variant, stakes and table configuration, with partitioned matchmaking:
  - fill suitable existing tables first;
  - create a new table only when at least two players are waiting and no suitable capacity exists;
  - no forced mid-hand transfers, and consolidation is deferred;
  - a completely empty table may close after a configurable grace period (initially 60 s);
  - a table is never closed only because one seated player remains.
- **Recovery.** The public product requires full recovery of hands in progress. The Friends Alpha policy is in the [Product Contract](product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md) §7.
- **Scale.** A public launch requires validated multi-instance scale-out, recovery, monitoring and capacity planning. 10,000 concurrent connections is an initial load-test milestone, not a capacity claim or an architectural limit; final targets come from measurement. Scaling, matchmaking and recovery mechanisms are planned, not implemented.
- **Dependencies.**
  1. M8: C6.2 → C6.3 → preflight → C6.4 → C6.5 → C7.
  2. Playable Preview: one instance, in memory.
  3. Friends Alpha: durable state and ledger.
  4. After it, Quick Play, in-hand recovery hardening and multi-instance, in parallel.
  5. Load and recovery validation.
  6. The public launch gate.

  C7 assigns milestone numbers.

#### Road to Friends Alpha after M8

To be replanned during Milestone 8. These are the remaining capability areas expected on the way to the Friends Alpha. They have no milestone numbers yet, and their order and grouping are decided in Milestone 8 Cycle C7 ([M8 Plan](milestones/M8_PLAN.md)):

- **Real-time API/server:** the server that owns live tables, real-time delivery of per-viewer snapshots, serialization of views, and command transport.
- **Web poker experience:** the browser client and a playable, legible table UI.
- **Deployment and private tables:** the first remote deployment, hosting, and the private-table link or code flow.
- **Reconnect and table-life policy:** rejoining after a transport drop, the next-hand pause and other timers, the action timer, and rebuy and top-up.
- **Alpha hardening and playtests:** socket drops, logs (including completed-history JSON logs), limits, cleanup, and playtests ending in Friends Alpha v0.1.

This work is delivered in parallel iterations across Core, Backend and Web against versioned shared contracts, building on the M8 C6 proof of concept, in which Backend and Web are the first parallel pair.

#### Approved decisions

Approved on 2026-11-02. Milestone references after 8 below follow the provisional numbering. The server, client and repository decisions remain the accepted direction ([ADR 0005](adr/0005-player-view-and-table-session-boundary.md) §12–14), which Milestone 8 may revisit when it plans the API architecture.

- **Player view.**
  - The poker visibility boundary lives in the engine: `game/visibility.py` plus the Hold'em view layer.
  - Clients receive full per-viewer snapshots plus an allowlist-redacted log of the current hand. There is no diff protocol.
- **Server.**
  - Python with FastAPI, uvicorn, and WebSocket (FastAPI replaced Starlette on 2026-11-11, [ADR 0008](adr/0008-fastapi-server-and-single-writer-tables.md)).
  - Server dependencies stay outside the dependency-free engine.
  - Python 3.14 compatibility, including FastAPI, `pydantic-core` and uvicorn, is confirmed before the server is implemented.
- **Client.** TypeScript with React and Vite.
- **Repository.** `src/go_poker/app/` (application layer), `src/go_poker/server/` (server), and `web/` (client) in this repository.
- **Identity.**
  - A server-issued guest token and an opaque engine `player_id` (refined on 2026-11-03, below).
  - The display name is separate, application-level data.
  - The creator of a private table is its host.
- **Next hand.** It starts automatically after a short pause, about 5 seconds as the initial product default. The pause is owned by the application/server, not the engine.
- **Stale commands.**
  - A monotonic application-level revision is the concurrency token (refined by [ADR 0006](adr/0006-shared-table-revision-and-private-intents.md), below).
  - Every snapshot carries it, and every state-changing command carries the revision it expects.
- **Leaving and sitting out during a hand.**
  - These are recorded as pending hand-boundary intents. The current hand's engine state is not changed.
  - When a leaving player's turn comes, the application checks if that is legal, otherwise folds, and mucks at a showdown decision.
  - The leave takes effect after settlement.
- **Engine-generation reset.**
  - At a hand boundary, when the current engine game can no longer progress because no `READY` player with chips remains, the application rebuilds a fresh engine `Table` and `HoldemGame`.
  - The private table, its code, guests, seats, names, and revision persist.
  - This is an application-layer policy. The engine lifecycle contract is unchanged.
- **Rebuy.** A simple play-money rebuy/top-up policy between hands may be added on the road to the Alpha.
- **Browser test.** A minimal Playwright browser smoke test, added with the playable UI once it exists.
- **History logs.** Completed-history JSON logs are useful Alpha hardening work.
- **No autoplayer.** No dev-only autoplayer is added unless a later test or load need independently justifies it.
- **Hosting.** The hosting provider is decided when deployment is planned.

Approved on 2026-11-03, for Milestone 7 Cycles 2 and 3 (implemented behavior in `ARCHITECTURE.md`):

- **One logical identity.**
  - A table receives two identity facts from its caller: an opaque, stable `UserId` and a table-visible display name. The `UserId` is authoritative; the display name is what other players see.
  - The engine receives the `UserId` value as `Player.player_id`. There is no second application id. It never appears in a client-facing view.
  - Commands are authorized by `UserId`. Where bearer tokens map to a `UserId` is decided with the future API architecture.
- **Display names.** A table display policy: NFC-normalized and trimmed, 1–20 characters, no control characters, and no two current members of a table with names that differ only by case. Accounts, account usernames, authentication and persistence are a separate future capability. The application layer defines no user or account entity and decides none of their rules.
- **Shared revision and private intents.** The revision is the shared table-state revision ([ADR 0006](adr/0006-shared-table-revision-and-private-intents.md)). Pre-action selections and pending leave, sit-out and sit-back requests are private intents: they still carry the expected revision, but never increment it.
- **Sitting back** returns a player to waiting, so they re-enter through the engine's existing waiting rule.
- **Host.** When the host leaves, the earliest-joined remaining member becomes host.
- **Leave.** An explicit Leave removes the user from the table session, and that user cannot rejoin the same table session. Transport reconnect is separate, and rebuy/top-up stays deferred.
- **Privacy of intents.** Pending leave and sit-out requests and pre-actions are visible only to their owner until applied.
- **Automatic actions.** A leaving player's automatic action, a pre-action executing, and a resumed hand start are each a separate shared transition when they change shared state.
- **Pre-actions.** `CHECK` and `CHECK_OR_FOLD` while nothing is owed; `FOLD` and `CALL_CURRENT` (bound to the exact amount owed) once chips are owed. A `CHECK_OR_FOLD` selected earlier survives later betting and presents as `FOLD`. `CHECK` clears when check becomes unavailable, and `CALL_CURRENT` clears when the amount owed changes. There is no `CALL_ANY`. Once it is the player's turn, they get their full legal actions.
- **Engine read.** `call_obligation(hand, seat)` is the one new, read-only engine API pre-actions need. It shares its calculation with `legal_actions`.

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

The web client is built on the road to the Friends Alpha (see [Road to Friends Alpha after M8](#road-to-friends-alpha-after-m8)). Later mobile and desktop clients (Milestone 18) consume the same server protocol and engine contracts rather than recreating poker rules. The shared Core–Backend–Web contract from M8 C6 is designed so that a Mobile client can be added as another consumer, without changing Core or Backend ownership.

### Add Analytics and AI

Structured history, simulation, statistics, and real gameplay data provide the foundation for later analysis, coaching, and player-assistant capabilities.
