# M8 C6.3 — Shared Wire Contract Plan

**Status:** **Approved** by the Product Owner on 2026-11-12 (revision 2). This completes C6.3.
- [ADR 0009](../adr/0009-wire-protocol-v1.md) revision 2 is accepted, and its canonical fixtures are approved and frozen for C6.4.
- Both C6.4 Briefs are approved.
- P1–P17 and Q1–Q5 are approved as documented (§3, §6).
- **Nothing is implemented.** Next, on the Owner's instruction, is the bounded toolchain preflight.

| Revision | Date | Change |
| --- | --- | --- |
| 1 | 2026-11-12 | Draft for Owner review: ADR 0009, the fixture directory, the Backend and Web Briefs, dependencies, decisions P1–P16 and open questions |
| 2 (approved) | 2026-11-12 | The Owner's final decisions after the contract audit:<br>• §8 command processing corrected;<br>• the known Core pot defect recorded (§7);<br>• P17, controlled fixture evolution;<br>• fixture coverage completed with two scenarios and four message examples;<br>• D3 and D5 and both Briefs updated (toolchains, transport limits, dev fixtures);<br>• the protocol policy for C7;<br>• Q1–Q5 answered |

## 1. Deliverables

| # | Deliverable | Where |
| --- | --- | --- |
| 1 | ADR 0009, protocol `go-poker.v1` (revision 2, accepted 2026-11-12) | [`docs/adr/0009-wire-protocol-v1.md`](../adr/0009-wire-protocol-v1.md) |
| 2 | Canonical fixture directory: 54 message examples, 8 scenarios, 2 invalid-case files | [`docs/adr/0009-wire-protocol-v1/`](../adr/0009-wire-protocol-v1/README.md) |
| 3 | Backend Work Order | [`M8_C6_4_BACKEND_BRIEF.md`](M8_C6_4_BACKEND_BRIEF.md) |
| 4 | Web Work Order | [`M8_C6_4_WEB_BRIEF.md`](M8_C6_4_WEB_BRIEF.md) |
| 5 | Cross-team dependencies, decisions and the known defect | §3–§7 below |

**What was not done:** no dependency installed, no application or Core code, no CI or tooling change, no commit, no C6.4 work.

**How the fixtures were made.**
- A scratch generator, not committed (Q3), applied a prototype of the ADR 0009 mapping to the **real** `TableSession` and engine, with stacked decks through the engine's test-only shuffle seam.
- Every regeneration was then checked independently:
  - no hole card or strength outside the viewer's own seat and the shown seats;
  - `hidden_card_count` consistent with `hole_cards` and `has_live_cards`;
  - legal and showdown actions only for the decider;
  - no `UserId` or credential anywhere;
  - per-connection revisions never decreasing;
  - each private snapshot at an unchanged revision and differing only in the private `you` fields;
  - `accepted.revision` at least the requester's last snapshot;
  - settlement awards equal to the pots, shares adding up to each pot, winners eligible, odd chips in ADR 0001 order;
  - chips conserved in every hand.
- **Result of the last check:** 188 snapshots, 24 settled and 159 conservation checks, with no failure.

## 2. Blockers B1–B7: resolution

| # | Blocker | Resolved in ADR 0009 | Summary |
| --- | --- | --- | --- |
| B1 | Command completion | §8 | **Server:** an authenticated received command frame is executed at most once; `request_id` is correlation only, never deduplication; exactly-once effects are not guaranteed; the one terminal outcome may be undelivered; no frame of a superseded connection is processed. **`expected_revision`:** prevents duplicate shared transitions at one revision; not idempotency for private commands. **Client:** an uncertain command is never retransmitted; reconcile from the `connected` snapshot, which proves the current state, not its cause; then any new command has a new `request_id` and the current revision |
| B2 | Create and join | §4 | Exact bodies; the credential only in the 201 body; `404`, `409`, `422` and `500` with `{error: {code, message, field}}`; the order of checks; the join is atomic and never stale (E4); no idempotency key (a POC limitation) |
| B3 | Variant fields | §10 | `settings.variant` = `texas_holdem` and `settings.betting_structure` = `no_limit`, mapped as constants; `participants[].hidden_card_count` from `HOLE_CARD_COUNT`; no `TableSession` change |
| B4 | Code catalogue | §12 | 11 `rejected` codes, 6 `error` codes, 8 HTTP codes, and close codes (including `1009`) with each one's client reaction |
| B5 | Fixtures | §15 | One versioned path beside the ADR; frozen for C6.4; controlled evolution afterwards (P17) |
| B6 | Versioning | §1 | `hello.protocol = "go-poker.v1"`; a mismatch gives `PROTOCOL_MISMATCH` and close `4400`; strict v1, frozen for C6.4; the long-term compatibility policy belongs to C7 |
| B7 | Encodings | §2, §3, §6, §11 | Safe integers; two-character cards (`"Th"`); explicit lowercase enums; `legal_actions` with `short_all_in_target`; `act.target` is the street total ("to") |

**Intermediate snapshots (audit item, not a blocker).** `TableSession` already returns `Accepted.transitions`: one `Transition(revision, cause, views)` per shared change, each with every member's frozen view captured in `_record`. The `app/` tests assert distinct intermediate states (the pre-action cascade, leave cascades, and `check_every_transition_view`). ADR 0008 §5 is satisfied with no `app/` or Core change.

## 3. Decisions (approved by the Product Owner on 2026-11-12)

| # | Decision | Outcome |
| --- | --- | --- |
| P1 | Protocol identity and strictness | **Approved.** `"go-poker.v1"`; v1 is closed and strictly decoded both ways; frozen for C6.4. The long-term compatibility policy is C7's (§5, ADR 0009 §1.6) |
| P2 | Command outcome shape | **Approved.** `accepted {request_id, revision}` after the command's snapshots; a `private` snapshot for a private command; `rejected` and `error` carry no snapshot |
| P3 | Outcome replay and deduplication | **Approved, amended.** No outcome cache, no replay, no `request_id` deduplication, no retransmission of an uncertain command. Exactly-once effects are not guaranteed. `expected_revision` prevents duplicate shared transitions at one revision and is not an idempotency guarantee for private commands. The claim that a manual retry is safe is withdrawn |
| P4 | HTTP contract | **Approved.** ADR 0009 §4, including that create and join have no idempotency key |
| P5 | Variant fields | **Approved.** Constants plus `hidden_card_count`; no reserved `omaha` or `pot_limit` values in v1 |
| P6 | Code catalogue and close codes | **Approved, amended.** ADR 0009 §12, plus `1009` for an oversized frame |
| P7 | Fixture location | **Approved.** `docs/adr/0009-wire-protocol-v1/` (Q1) |
| P8 | Encodings | **Approved.** Two-character cards; explicit lowercase enums; integers within ±(2⁵³ − 1) |
| P9 | The log in v1 | **Approved.** Included |
| P10 | Pots | **Approved, amended.** The engine-derived pot representation is accepted for the C6.4 POC only. The odd-chip defect is a known Core correctness defect and a mandatory Friends Alpha blocker (§7, Q2) |
| P11 | Liveness and limits | **Approved, amended.** Ping 20 s / timeout 20 s, set explicitly on the transport; hello timeout 10 s; 16 KiB inbound, enforced in the application with close `1009`; a bounded outbox |
| P12 | POC server defaults | **Approved.** Stakes 5/10, buy-in 1,000, **6 seats**, host seat 1, a 5 s next-hand pause; nine seats covered by fixtures (Q4) |
| P13 | Credential | **Approved.** One membership of one table, revoked on departure; `sessionStorage` per table; dropped on `4401` and `4410` |
| P14 | Normative schema | **Approved.** The ADR prose and the fixtures are normative; the Backend's exported schema is tested against them; FA codegen |
| P15 | Sizing | **Approved.** Each Brief keeps its Cycle whole, with an explicit order of steps |
| P16 | Success targets | **Approved.** The M8 Plan's C6 targets, unchanged (§5) |
| P17 | Controlled fixture evolution | **Added and approved.** See below |

**P17 in full.**
- **The freeze:** the canonical fixtures are frozen throughout C6.4. No team changes a canonical fixture on its own; a needed change stops the session and goes to the Owner.
- **Value changes afterwards:** after the parallel Cycle, a Core rules correction may update fixture **values** through an explicitly reviewed and documented change. That change:
  - is made under the Core ADR;
  - regenerates the fixtures from the real engine;
  - re-runs both sides' fixture tests.

  It keeps `go-poker.v1` as long as the wire schema and every field's meaning stay compatible.
- **Incompatible changes:** a change to a shape, a field meaning, an enum, a code or a delivery rule needs explicit versioning (a new identifier and a superseding ADR) and Owner approval.

## 4. Cross-team dependencies

| # | Dependency | Owner | Before |
| --- | --- | --- | --- |
| D1 | ADR 0009 accepted; its fixtures and both Briefs committed on `master` | Product Owner (C6.3 closeout) | the preflight |
| D2 | **Preflight** (Meta, Small-Change Path, C6.1 §13):<br>• the server dependencies (`fastapi`, `uvicorn`, `websockets`, dev `httpx`) with Python 3.14 and the `pydantic-core` wheel confirmed;<br>• mypy passing on a minimal pydantic and FastAPI import;<br>• a `web/` skeleton: `package.json` with every C6.2 §2.1 dependency, the lockfile, `tsconfig`, `vite.config.ts`, `biome.json`, one trivial test;<br>• the four Web gates in `verify.py` (a missing Node or `node_modules` is a FAIL);<br>• Node and `npm ci` in CI;<br>• `.gitignore` for `web/node_modules` and `web/dist` | Lead (Meta), Owner approval | both worktrees |
| D3 | **Worktrees:**<br>• both branch from the same `master` SHA, containing D1 and D2, and each Cycle Report records it;<br>• **each worktree installs both toolchains before its first `verify.py`:** `uv sync --locked` at the root **and** `npm ci` in `web/`, because the combined `verify.py` runs the Python and the Web gates in both worktrees;<br>• the installs are part of the Owner's worktree setup, and add no dependency | Owner (worktree setup) | C6.4 start |
| D4 | **Disjoint paths:**<br>• Backend: `src/go_poker/server/` and `tests/server/`;<br>• Web: `web/`, with no dependency changes;<br>• fixtures read-only for both;<br>• neither edits `ARCHITECTURE.md`, `CURRENT_CYCLE.md`, `ROADMAP.md`, `pyproject.toml`, `uv.lock`, `scripts/` or CI | Both Leads; the Reviewers check | throughout |
| D5 | **The runtime interface** (not wire protocol):<br>• the Backend dev command is `uv run uvicorn go_poker.server.app:create_app --factory --host 127.0.0.1 --port 8000 --ws websockets --ws-ping-interval 20 --ws-ping-timeout 20 --ws-max-size 16384`, with `/tables`, `/ws/tables/{id}` and `/health` at the root;<br>• the Web Vite proxy forwards these;<br>• same origin, no CORS, no `Origin` check in the POC (C7);<br>• **transport and application are distinct:** ping and pong, and uvicorn's own frame limit, are uvicorn behavior, which FastAPI's `TestClient` does not run. The ADR's 16 KiB limit and `1009` are therefore enforced in the application and tested with `TestClient`; ping is configured on uvicorn and checked manually in the demonstration | Backend provides; Web consumes | the demonstration |
| D6 | **Integration order:**<br>1. The Backend PR merges first.<br>2. The Owner brings `master` into the Web branch, and the Web session re-runs verification.<br>3. The Web PR merges.<br>4. The two-browser demonstration runs on `master` (Q5) | Owner | C6.5 |
| D7 | **Contract questions:** a session that finds an ambiguity or a fixture it believes wrong stops and reports to the Owner. The Owner rules as a **clarification** (recorded in §9, with no signature or fixture change) or a **superseding ADR** (both Briefs re-approved). The target is at most one clarification | Owner | throughout |
| D8 | **Shared engine facts:** both sides rely on, and neither changes, `HOLE_CARD_COUNT`, the rejection set, the `LegalActions` semantics and the current pots rule. A Core change during C6.4 is out of scope for both | — | throughout |
| D9 | **Development-only fixture loading in Web:**<br>• Vitest reads the fixtures with Node `fs` from `../docs/adr/0009-wire-protocol-v1/`;<br>• the dev mock mode loads them only under `import.meta.env.DEV`, through a dynamic import;<br>• `vite.config.ts` adds exactly that directory to `server.fs.allow` for the dev server only;<br>• the production build never includes a fixture: a build-time check in `vite.config.ts` fails `vite build` if a fixture module enters the bundle | Web | C6.4 |

**No other coupling.** Web never needs the server to pass its gates, and Backend never needs Web. Each side's stand-in for the other is the fixture set.

## 5. Success targets (P16) and the protocol policy

The M8 Plan's C6 success criteria are approved **unchanged**:

| Dimension | Target |
| --- | --- |
| Contract | No superseding ADR; at most one clarification, with no signature change |
| Integration | The Backend's scenario replay on `master` (the integration test: the real `TableSession` and engine, no doubles in production code); Web passing against the fixtures; the two-browser demonstration |
| Tests | `VERIFY: PASS` in each worktree and on `master` after both merges |
| Path isolation | No file changed outside each Brief's paths |
| Elapsed time | At most 75% of the sum of both Cycles' own elapsed times |
| Session context | Engineer and QA under 150k; no session over 300k |
| Usage | No window reaches its limit during C6.4 |
| Rework | At most two fix rounds per Cycle; no cross-session rework beyond the pre-merge update |
| Owner intervention | At most two unplanned per Cycle |

**Protocol policy.**
- **Now:** strict `go-poker.v1` is frozen for C6.4.
- **Before any installed client ships** that cannot simply reload, C7 defines:
  - backward compatibility;
  - how many protocol versions a server accepts at once;
  - HTTP API versioning.
- **Not now:** no migration framework is designed (ADR 0009 §1.6).

## 6. Owner answers (2026-11-12)

| # | Question | Answer |
| --- | --- | --- |
| Q1 | Fixture location | The ADR-adjacent directory `docs/adr/0009-wire-protocol-v1/` |
| Q2 | Pot layers | The known defect is accepted for the C6.4 POC; a mandatory fix before the Friends Alpha (§7) |
| Q3 | The fixture generator | Not committed. The Backend conformance replay harness makes the scenarios reproducible from the committed fixtures |
| Q4 | POC seat count | Six default seats; nine-seat coverage by fixture |
| Q5 | The two-browser demonstration | Recorded by the Owner and the Web Lead; its durable metrics and findings are kept in the C6.5 documentation |

## 7. Known Core correctness defect: equivalent pot layers (mandatory before the Friends Alpha)

**The defect.**
- **Cause:** `pots()` (`game/betting/pots.py`) builds one layer per distinct collected contribution and never merges layers. Settlement splits each pot independently (ADR 0001 §1).
- **Effect:** equivalent adjacent layers with **identical eligible-seat sets** can produce an odd-chip distribution that differs from the merged pot.
- **Reproduced with the real engine:**
  - five players, stakes 5/10;
  - UTG raises to 25 and two players call; the blinds fold;
  - on the flop UTG bets 20, the cut-off folds and the button calls;
  - UTG and the button tie on a board straight.

  The layers are 25, 20, 45 and 40, all eligible to {1, 4}. The aggregate 130 pays **66 / 64 instead of 65 / 65**.
- **What stays correct:** chips are conserved, and winner eligibility is correct.
- **Scope of the impact:** the result follows ADR 0001 literally, but it deviates from a single pot's split.

**Status:** accepted for the C6.4 POC only. It is a **mandatory blocker before the Friends Alpha**, not a cosmetic improvement. Core is not changed now.

**Planned Core work** (its own Core Cycle and ADR, after C6.4):
1. **Clarify ADR 0001:** "each pot" means each set of chips with one eligible-seat set.
2. **Merge equivalent adjacent layers in Core.** Eligibility only shrinks as the level rises, so identical sets are always adjacent.
3. **Regression tests:**
   - ties and odd chips, including the 66/64 case, which becomes 65/65;
   - eligibility;
   - conservation;
   - the existing side-pot suites.
4. **Update the affected fixtures** after the C6.4 freeze ends, under P17: `three_way_side_pots` hand 1 shows one 810 pot instead of 30 + 780. The protocol identifier is unchanged.

**Fixture rule now.** No canonical fixture presents the defect as correct behavior.
- The one canonical split, `split_pot_and_all_in_calls`, is a single 2,925 pot with one eligible-seat set, split 1,463 / 1,462 under ADR 0001's odd-chip order.
- `three_way_side_pots` hand 1 shows the layered representation with a single winner, where the defect cannot change any award.

## 8. Closeout (2026-11-12)

Accepted by the Product Owner on 2026-11-12, with no remaining contract blocker. C6.3 is documentation only: no application, Core, server or Web code, dependency, CI or tooling changed. The Owner commits through `/finish-cycle`.

Recorded with the closeout:
1. **ADR 0009** revision 2: accepted (2026-11-12).
2. **The fixture directory:** approved and frozen for C6.4, its values unchanged from revision 2.
3. **This plan and the two C6.4 Briefs:** approved.
4. **`CURRENT_CYCLE.md`:**
   - C6.3 complete;
   - B1–B7 resolved;
   - the known pot defect recorded as a mandatory Friends Alpha blocker;
   - next, the preflight.
5. **`M8_PLAN.md`:** the status line and the C6.3 row; the C6 success targets confirmed (P16).
6. **`ROADMAP.md`:** the approved C6.3 decisions, including the Core pot fix before the Friends Alpha. The requirement of full in-hand recovery before the public release is unchanged.
7. **`ARCHITECTURE.md`:** unchanged until the protocol is implemented.

## 9. Clarifications log (C6.4)

Empty. A clarification the Owner rules during C6.4 is recorded here with its date. A change to a shape is a superseding ADR, not a clarification.
