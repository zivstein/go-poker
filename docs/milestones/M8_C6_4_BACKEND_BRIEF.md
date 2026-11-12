# M8 C6.4 — Backend Cycle Brief (Work Order)

**Status:** **Approved** by the Product Owner on 2026-11-12 (revision 2, M8 C6.3), together with ADR 0009. Execution starts only on the Owner's instruction, after the preflight. This Brief is for a fresh Lead session in its own worktree. The parallel Web Brief is [M8_C6_4_WEB_BRIEF.md](M8_C6_4_WEB_BRIEF.md). The shared dependencies are in the [C6.3 plan](M8_C6_3_WIRE_CONTRACT_PLAN.md) §4.

**Contract:** [ADR 0009](../adr/0009-wire-protocol-v1.md), `go-poker.v1`, and its fixtures. The ADR number is the contract version.

## 1. Goal

A FastAPI server that hosts private tables in memory. It implements ADR 0009 exactly over the real `TableSession` and engine, and it proves that by replaying every canonical scenario.

## 2. In scope

1. **App factory** `go_poker.server.app:create_app(config=None) -> FastAPI`.
   - **Dev command** (C6.3 plan D5), with the transport's WebSocket options set explicitly:

     ```bash
     uv run uvicorn go_poker.server.app:create_app --factory --host 127.0.0.1 --port 8000 --ws websockets --ws-ping-interval 20 --ws-ping-timeout 20 --ws-max-size 16384
     ```

   - The command is documented in a module docstring or `src/go_poker/server/README.md`.
2. **HTTP** (ADR 0009 §4):
   - `POST /tables`;
   - `POST /tables/by-code/{join_code}/members`;
   - the strict request bodies and the error body. FastAPI's default `422 {"detail": …}` is replaced by the contract shape.
   - Also `GET /health`.
3. **WebSocket** `/ws/tables/{table_id}` (ADR 0009 §5, §7–§9, §12–§13):
   - hello and its timeout; the strict client decoder; commands; every server message; the close codes;
   - **supersede**, after which no frame of the superseded connection is read or executed;
   - **the 16 KiB inbound limit, enforced in the application:** the UTF-8 length of each received text frame is checked before it is decoded, and a larger frame closes with `1009` without being executed.
   - **Transport and application are distinct.** Ping and pong, and uvicorn's own `--ws-max-size`, are uvicorn behavior that FastAPI's `TestClient` does not run. The application limit is therefore what tests check. Ping is a dev-command setting, checked manually in the demonstration.
4. **`TableRuntime`**, one per table (ADR 0008 §4, C6.1 §8):
   - **phase 1**, synchronous and with no `await`: execute → map each captured view → put each message on its recipient's outbox in transition order → update the connection registry (`left_table` for departed members, credential revocation) → arm or re-arm the next-hand timer;
   - **phase 2**, one writer task per connection: drain the bounded FIFO outbox; on overflow, close with `4008`.
5. **Next-hand timer.** While the phase is `hand_complete`, `advance_hand(expected_revision)` runs after the pause (default 5 s), with the revision the timer was armed at. Any transition re-arms it. A stale timer does nothing.
6. **Table directory:** an in-memory dictionary from table id to runtime, and from active join code to table id. Join codes use the ADR 0009 §2 alphabet and are unique among active codes.
7. **Credentials:** `secrets.token_urlsafe(32)`. The server keeps credential → (table id, `UserId`), with `UserId` minted as a UUID per membership. A credential is revoked when its member's departure is applied.
8. **DTOs:** pydantic models for every message in ADR 0009. They are built by explicit field-by-field mapping functions from `TableView`, `Accepted`, `Rejected` and `Transition`, with explicit enum, card and code tables (ADR 0008 §2). The hidden-card count reads `HOLE_CARD_COUNT`. JSON Schema is exported through a function used by a test.
9. **Failure isolation:** an unexpected exception inside `execute` marks the table failed. Every connection of that table receives `table_failed` and close `4500`, the table and its code leave the directory, and other tables are unaffected.
10. **Configuration**, a frozen dataclass:
    - default stakes 5/10, buy-in 1,000, 6 seats, host seat 1;
    - next-hand pause 5 s, hello timeout 10 s, outbox size 256, inbound frame limit 16,384 bytes (ping is a transport setting of the dev command, not app configuration);
    - **test-only seams**, which default to the secure behavior: generators for the table id, join code and credential; the button chooser (default `secrets.choice`); and a way for tests to fire the next-hand timer.

## 3. Out of scope

- Any change to `src/go_poker/core/`, `game/` or `app/`, or to `pyproject.toml` and `uv.lock`.
- Dependencies beyond the preflight's (`fastapi`, `uvicorn`, `websockets`, dev `httpx`).
- Persistence, recovery, more than one instance, leases, matchmaking, capacity limits beyond the frame and outbox limits.
- The seat summary (C6.1 L1), spectators, the action and disconnect timers, CORS, `Origin` checks, TLS, rate limits, serving the Web build.
- Anything in ADR 0009 §16.

## 4. Architecture and ownership

- **Declared paths (the only ones this Cycle may change):** `src/go_poker/server/` and `tests/server/`.
- **Read-only inputs:**
  - `docs/adr/0009-wire-protocol-v1.md`;
  - `docs/adr/0009-wire-protocol-v1/`;
  - the engine and `app/`.
- **Not touched:** `docs/ARCHITECTURE.md`, `CURRENT_CYCLE.md` and `ROADMAP.md`. Their server and status text is written after integration (`ENGINEERING_PROCESS.md`, Parallel Sessions).
- **Layering:** the server imports `app`, `game` and `core`; nothing imports the server. `tests/test_layering.py` already covers this and is not changed.
- **Suggested modules** (the Engineer may adjust them inside the declared paths):
  - `app.py`: the factory and configuration;
  - `http.py`;
  - `ws.py`;
  - `runtime.py`;
  - `directory.py`;
  - `dto.py`: the wire models;
  - `mapping.py`: views and results → DTOs, and the enum, card and code tables;
  - `decode.py`: the strict client-frame parser → command values or `MALFORMED_MESSAGE` / `INVALID_COMMAND`;
  - `ids.py`.
- **No generic command framework.** Commands are the closed set of frozen values parsed by `decode.py` (C6.1 E13).

## 5. Behavior and invariants

ADR 0009 is the specification. These are the points most easily got wrong:

1. **Explicit mapping only.** No `model_validate` on a view, no `from_attributes`, `asdict` or `__dict__`. A field added to a view never reaches the wire unless the mapper names it.
2. **The requester's order:** its transition snapshots → a `private` snapshot only when there was no transition → `accepted` → `left_table` and close, when it is no longer a member. Rejections and errors carry no snapshot (§8).
3. **One snapshot per transition** per connected member, mapped from the view captured in that transition. A later state is never re-read and used instead.
4. **Atomic steps.**
   - Supersede plus the first `connected` snapshot happen in one phase-1 step, and the superseded connection's reader stops at that step. A frame it had not yet read is never executed.
   - `left_table` and revocation are one step too.
5. **No `await`** between `execute` and the last outbox put. No lock is held across a send. A slow client never delays others.
6. **`expected_revision` passes through unchanged** to `TableSession`. The server never substitutes the current revision, except for the HTTP join (E4).
7. **Join failures store nothing:** no credential is minted and no membership created before an `Accepted` join.
8. **Strict inbound decoding:**
   - booleans are not integers;
   - floats are not integers;
   - integers are within ±(2⁵³ − 1);
   - an unknown or extra field is an error.
9. **The engine decides legality.** The decoder checks only shapes. An out-of-range target goes to the engine and comes back `ILLEGAL_ACTION`.
10. **At most once, with no deduplication** (ADR 0009 §8):
    - each read command frame is executed at most once;
    - `request_id` is only copied into the outcome. It is never stored or compared, so a repeated `request_id` is a new command;
    - there is no outcome cache and no replay;
    - an outcome that cannot be delivered, because the connection closed or the table failed, is dropped.

## 6. Test strategy

**Required, all in `tests/server/`:**

1. **Scenario replay (the conformance test).** One parametrized test per `scenarios/*.json`. Each:
   - builds the app with the scenario's ids, defaults, button rule and stacked draw orders (through `Deck.shuffle`'s `_rng` test seam, as `tests/app/conftest.py` does);
   - drives every step with the FastAPI `TestClient`;
   - asserts every HTTP response and each connection's exact message sequence, comparing parsed JSON and ignoring `message`.

   - Fixtures are read from the repository path, never copied.
   - **Reproducible without the scratch generator (Q3):** the harness uses only the scenario's `setup`:
     - `server_defaults` → configuration;
     - `ids` → the id, join-code and credential generators, in creation order;
     - `button` → the button chooser;
     - `hands[].draw_order` → the deck seam, one order per engine shuffle; a shuffle beyond the list keeps the unshuffled deck.
     - `server_timer` steps fire the next-hand trigger, and `drop` steps close the client socket without a close handshake.
2. **Message examples:** every `messages/server/*.json` appears in a scenario replay or is produced by its own focused test (nine seats; `table_failed`).
3. **Inbound decoder:** every `invalid/client_to_server.json` case produces the stated error; the handshake cases close with the stated code.
4. **Leak test, per viewer, on every emitted snapshot of every replay** (ADR 0005 Consequences):
   - no card outside the viewer's own seat and the shown seats;
   - no `UserId`, `player_id` or credential anywhere in any server message.
5. **DTOs and schema:**
   - every server message fixture parses with the DTO models in strict mode and re-serializes to an equal JSON value;
   - the JSON Schema export runs;
   - no JSON Schema validator library is added: that would be a new dependency.
6. **Concurrency and delivery:**
   - two clients racing the same revision: one `accepted`, one `STALE_REVISION`;
   - per-connection revision order;
   - outbox overflow closes `4008` and leaves others unaffected;
   - a stale next-hand timer does nothing.
7. **Lifecycle:**
   - hello timeout (short config);
   - supersede, including a frame sent on the superseded connection after the supersede, which is never executed;
   - a 16 KiB + 1 byte frame closes with `1009` and changes nothing; a 16 KiB frame is decoded;
   - a reconnect gets only the current snapshot;
   - a revoked credential gets `AUTH_FAILED`;
   - failure isolation: an injected defect fails only its own table, with `table_failed` and `4500`.
8. **Integration on `master` after merge:** the scenario replays are the two-client integration test of the M8 Plan, with no doubles reachable from production code.

`uv run scripts/verify.py` passes: Ruff, format, mypy (the project configuration, `disallow_untyped_defs` included), pytest, and the four Web gates of the preflight. Before the first run, the worktree has **both** toolchains installed: `uv sync --locked` at the root and `npm ci` in `web/` (C6.3 plan D3). They are part of worktree setup, not a dependency change.

## 7. Risks and deferred decisions

| Risk | Mitigation |
| --- | --- |
| A fixture and the engine disagree | The fixtures were generated from this engine. A real disagreement stops the session and goes to the Owner. It is never "fixed" in either place: no team changes a canonical fixture on its own (P17) |
| The known pot-layer odd-chip defect (C6.3 plan §7) | Out of scope. The server maps the engine's pots and awards unchanged. The Core fix comes after C6.4 |
| An `await` or a thread-pool handler inside phase 1 | `async def` handlers; the race test; a Reviewer check (ADR 0008 §3) |
| `TestClient` timing makes the timer and timeout tests flaky | Test seams: a manual next-hand trigger and a short hello timeout; no `sleep`-based assertions |
| pydantic in mypy strict | The preflight confirms the configuration; a needed `pyproject.toml` change stops the session |
| Scope creep into Web or C7 items | §3; the Reviewer checks the diff against §4's paths |

Deferred: everything in ADR 0009 §16; C6.1 E3, E5 and E16.

## 8. Execution plan and sizing

**Sizing decision: keep the Cycle whole.** Signals present: two surfaces (HTTP and WebSocket transport, plus the runtime and mapping), and a conformance harness next to the production code. The M8 Plan's C6.4 is one Backend Cycle, and the harness *is* the acceptance test of this slice: splitting it out would leave the first half without its proof. The expected diff is roughly 12–18 paths. The Engineer works in this order, each step green before the next:

1. `mapping.py` and `dto.py` against the snapshot fixtures. These are pure functions, tested by building views from a real `TableSession` with stacked decks.
2. `decode.py` against the invalid and client fixtures.
3. `runtime.py` with fake outboxes: delivery order, private updates, departures, the timer.
4. HTTP, WebSocket and directory, then the scenario replay harness.
5. Failure isolation, overflow and the lifecycle tests.

Then the normal Cycle Flow: QA, Reviewer, final verification and the Cycle Report.

**Integration:** this branch merges first (C6.1 §12).

**Success targets:** as confirmed in the C6.3 plan §5.

Telemetry: per session, as in `ENGINEERING_PROCESS.md` (Usage Measurement).
