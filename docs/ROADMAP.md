# Go! Poker Roadmap

This is the product roadmap: the authoritative source for milestone status and for the planned work tracks. It was rewritten on 2026-11-19 from verified GitHub and repository state. The previous roadmap, with all of its approved decisions, is preserved unchanged in [`milestones/ROADMAP_ARCHIVE_2026-11-19.md`](milestones/ROADMAP_ARCHIVE_2026-11-19.md).

Precedence, unchanged:

- Where the [Friends Alpha Product Contract](product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md) covers the same product scope, it governs any conflicting description here (approved 2026-11-09).
- The approved decisions in the [archive](milestones/ROADMAP_ARCHIVE_2026-11-19.md) stay in force unless this roadmap, an accepted ADR or the Contract supersedes them. Their text has not been moved; the archive is their home until the Owner decides where they live permanently.
- Current architecture belongs in `ARCHITECTURE.md`, the active Cycle working state in `CURRENT_CYCLE.md`, and AI-organization growth in `docs/company/ORGANIZATION_ROADMAP.md`.
- GitHub Issues are the task list, the Project Board (<https://github.com/users/zivstein/projects/4>) is a view of them, and a merged PR plus a closed Issue is the evidence that work is done. A Board status of Done is not evidence.

## Milestones

| # | Milestone | Status |
| --- | --- | --- |
| 0–7 | Engine foundation through Player view + local table | Complete |
| 8 | Multi-Agent Engineering Organization + Product Architecture (carries the road to the Friends Alpha) | **In progress** |
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

Milestone numbers and names are unchanged from the archived roadmap; those after 8 stay provisional until M8 Cycle C7 replans them. Milestones 11, 12 and 14 are the formal home of the variants that the Offline Variant Lab explores informally (below).

## Verified state (2026-11-19)

| Item | Evidence |
| --- | --- |
| A1 Betting & Action Safety | PR #16 merged 2026-11-17 (`35aa41a`) |
| Core pot settlement (odd chips across equivalent pot layers) | PR #21 merged 2026-11-17 (`033f945`); Issue #2 closed 2026-11-19 as completed, with a comment linking the PR |
| `master` | Equal to `origin/master` at `033f945`; the worktree is clean |
| Open pull requests | None |
| GitHub milestones | None defined; all work is tracked by Issue, label and Board Track |

## Track 1 — Friends Alpha

Goal: a reliable, hosted Friends Alpha for friends' evenings, as the [Product Contract](product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md) defines it. A playable local prototype is not a Friends Alpha.

| Cycle | Scope | Status |
| --- | --- | --- |
| R0 Core Correctness | #2 | **Complete** (PR #21, Issue #2 closed) |
| R1 Backend Stability | #3, #4, #5, #6, #7 | Planned; not started. **Primary next engineering cycle**, starting with #3 and #4 |
| R2 Web Connectivity & Secure Hosting | #10, #11, #12, #13 | Planned; not started. #10 first needs the hosting-origin decision |
| F0 Friends Session Contracts | #22 (design phase) | Planned as a design cycle that can run in parallel with R1; not started |
| Friends Session implementation | #22 (decomposed after F0) | Not decomposed: #22 requires approved contracts first, then Core/App, persistence, Backend, Web and integration issues |
| Friends Alpha release validation (proposed name R3) | The Contract's [release gate](product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md) | Not started; needs R1, R2 and the Friends Session first |

Friends Session (#22): configurable buy-in, top-up credited between hands, a durable idempotent ledger, cash-out, and a host-facing Settle Up that reports and proposes external settlement only (no in-app transfers). Chip units and currency conversion are defined separately. The Contract's wallet model (persistent play-money wallet, grants) is wider than #22's session ledger; F0 must reconcile the two before decomposition.

Release validation is the end-to-end proof, on the real hosting origin over HTTPS/WSS, that the Contract's acceptance criteria hold: a multi-hand private game with side pots, reconnect, leave and settlement, no open release blockers, and no developer intervention.

### Release blockers

Open Issues labelled `release-blocker` ("must be resolved or explicitly re-approved before Friends Alpha"):

| Issue | Priority | Cycle |
| --- | --- | --- |
| #3 Cancel and await WebSocket reader/writer tasks | p1 | R1 |
| #4 Do not re-arm next-hand timer on private commands | p1 | R1 |
| #5 Handle disconnects during WebSocket sends | p2 | R1 |
| #6 Log unexpected `TableRuntime` failures safely | p2 | R1 |
| #7 Contract error bodies for malformed join-code paths | p2 | R1 |
| #10 Request IDs in the Friends Alpha hosting environment | p1 | R2 |
| #11 Recoverable Create/Join network errors | p2 | R2 |
| #12 Exit from indefinite reconnect screens | p2 | R2 |

Also required for the Friends Alpha although not labelled `release-blocker`: #22 (`priority:p1`, Product Contract P0 scope). #2 was a release blocker and is resolved. #13 is a defensive follow-up in R2, not a blocker.

## Track 2 — Premium Poker Experience

Goal: a table that feels clear and premium. Work here never delays the Friends Alpha release gate and starts only after the Owner schedules it.

| Cycle | Scope | Status |
| --- | --- | --- |
| A1 Betting & Action Safety | PR #16 | **Complete** |
| A2 Player Action Feedback | #23, with #17 and #20 folded in | Planned; not started. The Owner prioritized it ahead of pre-actions and keyboard shortcuts. #23 depends on the motion contracts before any timed transition |
| B0 Motion contracts and showdown experience | #24, with #14 and #19 folded in | Planned; not started. Defines ordered presentation contracts before any animation |
| Server-authoritative 3-second Show/Muck timer | #25 | **Planned, not implemented.** The server owns the deadline and auto-Shows on timeout only where legal. It needs an approved design and protocol contract first (ADR 0009 is `go-poker.v1`, frozen). It relates to the deferred C6.1 decision E3 (the showdown-timeout rule) |

Sequencing inside the track: motion contracts (B0) come before timed feedback transitions in A2; the Show/Muck timer's contract also touches the Backend and the protocol, so it is not a Web-only cycle.

## Track 3 — Offline Variant Lab

A learning and experimentation track. It is **not** a Friends Alpha release blocker, does not change production, API or wire contracts, and nothing in it counts as implementation progress until a tested, reviewed integration lands.

| Topic | Notes |
| --- | --- |
| #26 | Tracking issue for the lab; exercise order and deliverables are there |
| Omaha High | Exactly two hole cards and three board cards. Formal home: Milestone 11 |
| Pot-Limit betting | A betting structure, separate from the variant. Formal home: Milestone 11 |
| Pineapple Hold'em | Discard phase. Formal home: Milestone 12 |
| Classic Chinese Poker | A separate game family (arrangement and scoring), not a Hold'em parameter. Formal home: Milestone 14 |
| OFC / Pineapple OFC | Separate again from Classic; incremental placement. Formal home: Milestone 14 |

The practical guide is [`company/OFFLINE_DEVELOPMENT_GUIDE.md`](company/OFFLINE_DEVELOPMENT_GUIDE.md).

## Not placed in a track

| Issue | Note |
| --- | --- |
| #8 `[Meta]` pytest `faulthandler_timeout` | Meta maintenance; not a Friends Alpha gate unless reliability requires it. Board Track: Meta |
| #18 Reject unsafe integer values in bet drafts | Latent Web reliability bug, `priority:p2`, not a blocker. The Board puts it in Friends Alpha; no cycle was assigned. Owner to place it (the issue itself suggests a small Web reliability pass) |

## Execution rules

- One primary engineering Cycle at a time. At most one parallel design or experiment track beside it. The parallel-session limits in `ENGINEERING_PROCESS.md` still apply.
- No Cycle is marked In Progress before work on it has started.
- A bug belongs to a Cycle, a release gate or the backlog; it does not get its own milestone.
- Each Cycle follows the engineering process: Brief, tests, implementation, QA, independent review, PR with green CI, merge, Issue closed, records updated.
- The approved Backend, Web and wire-protocol architecture is in `ARCHITECTURE.md`, [ADR 0008](adr/0008-fastapi-server-and-single-writer-tables.md) and [ADR 0009](adr/0009-wire-protocol-v1.md).
- Later platform work (accounts, Quick Play, multi-instance scale, recovery hardening, mobile, analytics, AI) stays post-Alpha and provisional, as in the archived roadmap.
