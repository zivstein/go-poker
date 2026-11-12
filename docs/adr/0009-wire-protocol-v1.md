# 0009: Wire protocol v1

Status: Accepted (2026-11-12), revision 2 (M8 C6.3, with the Product Owner's final decisions after the contract audit). Builds on [ADR 0005](0005-player-view-and-table-session-boundary.md), [ADR 0006](0006-shared-table-revision-and-private-intents.md) and [ADR 0008](0008-fastapi-server-and-single-writer-tables.md); supersedes none of them.

Canonical fixtures: [`0009-wire-protocol-v1/`](0009-wire-protocol-v1/README.md), part of this contract.

## Context

ADR 0005 fixed full per-viewer snapshots, `expected_revision` on every state-changing command, and redaction by allowlist. ADR 0006 made the revision a shared-state revision, with private intents answered at an unchanged revision. ADR 0008 fixed FastAPI, explicit DTO mapping, a single writer per table and ordered delivery of genuine intermediate states. ADR 0005 left the wire itself open: message names, fields, the card encoding, endpoint paths. The [C6.1 plan](../milestones/M8_C6_1_BACKEND_API_PLAN.md) §9 sketched the endpoints and message kinds. The [C6.2 plan](../milestones/M8_C6_2_WEB_PLAN.md) §12 listed seven blockers (B1–B7) that change Web code if left open.

C6.4 builds the Backend (`src/go_poker/server/`) and the Web client (`web/`) at the same time, in two worktrees, with no shared code. This ADR is the only thing they share, together with its fixtures. It is therefore written as a language-independent protocol: JSON over HTTP and WebSocket, with no Python or TypeScript type in it.

The protocol exposes only what `TableSession` and the engine's views already produce. No `TableSession`, engine or `app/` change is needed for v1.

## Decision

### 1. Scope and versioning

1. **Protocol identifier:** `"go-poker.v1"`. It names this ADR's HTTP endpoints, WebSocket messages and fixtures together.
2. **Negotiation:** the client states its identifier in `hello` (§5). A v1 server supports exactly `["go-poker.v1"]`. Any other value is rejected with `PROTOCOL_MISMATCH` and close code `4400`. The client shows a terminal "Please reload" screen. A later server may support several identifiers at once.
3. **v1 is closed.** Both sides decode strictly. A message is a protocol error when it has:
   - an unknown `type`, command `name` or log `event`;
   - an unknown enum value;
   - a missing field or an extra field;
   - a value of the wrong JSON type, or an integer outside its range.

   **Any** change to the wire, including an added optional field or enum value, is a new protocol identifier and a superseding ADR. The client never guesses at an unknown value.
4. **Client reaction to an undecodable server message:** treat it as a protocol failure. Close the connection, show the terminal protocol screen, and never render the message.
5. **Server reaction to an undecodable client message:** see §12 (`MALFORMED_MESSAGE`, `INVALID_COMMAND`). The server never closes an authenticated connection for a malformed frame. The one exception is an oversized frame (§5).
6. **Scope of strictness.** Strict decoding and the single supported identifier are properties of `go-poker.v1`. They hold for C6.4, during which v1 is frozen (§15).

   Long-term compatibility is a separate policy. C7 decides it before any client that cannot simply reload ships (an installed Mobile or desktop client). It covers:
   - backward compatibility;
   - how many protocol identifiers a server accepts at once, and for how long;
   - how the HTTP API is versioned (create and join happen before `hello`, so v1's handshake does not cover them).

   Omaha and Pot-Limit values arrive under a later identifier (§14). No migration framework is designed here.

### 2. Conventions (B7)

- **Encoding:** UTF-8 JSON. WebSocket messages are text frames, one JSON object per frame. Field names are `snake_case`.
- **Presence:** every field in a shape is always present. An absent value is `null`, never an omitted key. The only variable part is a command's `args`, whose shape depends on its `name` (§6).
- **Integers:** money, revisions, seats, counts and hand numbers are JSON integers, never strings or floats; `10.0` is invalid. Every integer is within ±(2⁵³ − 1), so JavaScript reads it exactly. Money is never negative.
- **Money:** whole virtual dollars. There are no cents and no minor units. Clients format, never compute (C6.2 W20).
- **Order:** every array has a defined order (§10). Receivers keep it.
- **Identifiers:**

| Value | Format | Notes |
| --- | --- | --- |
| `table_id` | lowercase UUID string | permanent and opaque; an address only (ADR 0008 §6) |
| `join_code` | 6 characters from `23456789ABCDEFGHJKMNPQRSTUVWXYZ` | unique among active codes; matched case-insensitively |
| `credential` | 1–256 characters from `[A-Za-z0-9_-]`; the POC issues 43 (256 random bits, base64url) | opaque bearer secret (§4) |
| `request_id` | 1–64 characters from `[A-Za-z0-9_-]`, chosen by the client (`crypto.randomUUID()` fits) | a correlation identifier, echoed exactly; never interpreted and never used to deduplicate (§8) |

- **Never on the wire:** `UserId`, the engine `player_id`, the deck, burned cards, any card a viewer may not see, game-node placement, and a credential anywhere except the create or join response body and `hello`.

### 3. Encodings (B7)

- **Card:** two characters, rank then suit. Ranks are `2 3 4 5 6 7 8 9 T J Q K A`, suits `c d h s`. Example: `"Th"` is the ten of hearts. `"10h"`, `"ah"` and `"A♥"` are invalid.
- **Enums** are lowercase `snake_case` strings, mapped explicitly from the engine. They are never the engine's own enum values:

| Enum | v1 values |
| --- | --- |
| variant | `texas_holdem` |
| betting structure | `no_limit` |
| phase | `not_started`, `hand_in_progress`, `hand_complete`, `waiting_for_players` |
| street | `preflop`, `flop`, `turn`, `river` |
| position | `btn`, `sb`, `bb`, `utg`, `utg1`, `mp`, `lj`, `hj`, `co` |
| blind | `small`, `big` (otherwise `null`) |
| occupant status | `waiting_to_join`, `sitting_out` (ready is `null`) |
| turn kind | `betting`, `showdown` |
| action | `fold`, `check`, `call`, `bet`, `raise` |
| showdown kind | `all_in`, `interactive` |
| showdown decision | `show`, `muck` |
| hand category | `high_card`, `one_pair`, `two_pair`, `three_of_a_kind`, `straight`, `flush`, `full_house`, `four_of_a_kind`, `straight_flush` |
| pre-action kind | `check`, `check_or_fold`, `fold`, `call_current` |
| snapshot cause | `connected`, `private`, `command`, `leave_auto_action`, `pre_action`, `hand_boundary`, `resume` |

### 4. HTTP: create and join (B2)

- **Bodies:** JSON with `Content-Type: application/json`. Request bodies are strict: exactly the listed fields, with no unknown or missing field. Every response carries `Cache-Control: no-store`.
- **Defaults:** the POC server applies its own defaults for stakes, buy-in, seat count and the host's seat (C6.2 W28). They are server configuration, not protocol. The fixtures use small blind 5, big blind 10, buy-in 1,000, 6 seats and host seat 1.

**Create:** `POST /tables`

```json
{"display_name": "Alice"}
```
→ `201`
```json
{"table_id": "4f9c2a1e-8d3b-4c5a-9e7f-1a2b3c4d5e6f", "join_code": "K7Q2XM", "seat": 1, "credential": "…"}
```

The creator is seated as host, `waiting_to_join`, with the buy-in.

**Join and sit:** `POST /tables/by-code/{join_code}/members`

```json
{"display_name": "Bob", "seat": 2}
```
→ `201`
```json
{"table_id": "4f9c2a1e-8d3b-4c5a-9e7f-1a2b3c4d5e6f", "seat": 2, "credential": "…"}
```

- **Atomic:** either the player is a member seated at `seat` with the buy-in, or nothing changes. A failed request stores nothing, and a new attempt after an error response is a fresh request.
- **No idempotency key:** create and join have none. A request whose response was lost may still have succeeded, and a repeat then creates a separate table or membership. This is a POC limitation; durable identity is C7 work.
- **Revision:** the server supplies the current revision to `TableSession.join` (C6.1 E4). A join is therefore never `STALE_REVISION`.
- **Field rules:**
  - `display_name`: a string. The server NFC-normalizes and trims it, then requires 1–20 characters and no Unicode category C character. It must be unique at the table, case-insensitively.
  - `seat`: an integer 1–9, the product range. The table's `max_seats` may be lower.
- **Order of checks:** body validation, then the code lookup, then the domain checks in `TableSession` order (display name, then seat).
- **Error body:** for every non-2xx response.

```json
{"error": {"code": "SEAT_TAKEN", "message": "This seat is already occupied", "field": "seat"}}
```

| Status | `code` | `field` | When |
| --- | --- | --- | --- |
| 422 | `VALIDATION_FAILED` | the offending field, or `null` | malformed JSON, a missing, extra or mistyped field, an invalid display name, a seat outside 1–9 |
| 404 | `TABLE_NOT_FOUND` | `null` | no open table has this code, including a malformed code, a failed table and a closed session; never distinguished |
| 409 | `DISPLAY_NAME_TAKEN` | `display_name` | another member has the same name |
| 409 | `SEAT_TAKEN` | `seat` | the seat is occupied |
| 422 | `INVALID_SEAT` | `seat` | the seat is above this table's `max_seats` |
| 409 | `ALREADY_MEMBER`, `LEFT_TABLE` | `null` | mapped for completeness; unreachable in v1, because every join mints a fresh identity |
| 500 | `INTERNAL_ERROR` | `null` | a server defect |

- **The credential:**
  - It is a bearer secret for one membership of one table. It is returned only in these two response bodies.
  - It is valid until that member's departure is applied, then revoked.
  - It is never put in a URL, a cookie or a log.
  - The client keeps it in `sessionStorage`, keyed by `table_id` (C6.2 §2.5).
  - Identity, accounts and durable credentials are C7 work.
- **Non-contract endpoint:** `GET /health` → `200 {"status": "ok"}` is operational and not part of v1.

### 5. WebSocket session

- **URL:** `/ws/tables/{table_id}`, same origin as the HTTP API (in the POC, through the Vite dev proxy). The upgrade is accepted for any `table_id`. Authorization happens only in `hello`.
- **Handshake:**
  - The client's first frame is `hello`:

    ```json
    {"type": "hello", "protocol": "go-poker.v1", "credential": "…"}
    ```

  - The server checks, in this order:
    1. the frame is a well-formed `hello`, otherwise `HELLO_REQUIRED` and close `4400`;
    2. the protocol, otherwise `PROTOCOL_MISMATCH` and close `4400`;
    3. the credential is valid for this `table_id`, otherwise `AUTH_FAILED` and close `4401`.

    An unknown table and a foreign or revoked credential are not distinguished.
  - No `hello` within 10 s gives `HELLO_TIMEOUT` and close `4408`.
- **Success:** the first server message is a `snapshot` with cause `connected` at the current revision. It is the only welcome.
- **Supersede:** when the same credential already has a live connection, that connection receives `superseded` and close `4409` first, in the same atomic step (ADR 0008 §5, C6.1 §8).
  - From that step on, the server reads and executes **no further frame** from the superseded connection, including frames already in transit.
  - A command the superseded connection sent earlier was either executed before the supersede, in arrival order, or is never executed.
- **Liveness (W26):** the server sends WebSocket Ping every 20 s and closes a connection that has not answered within 20 s. Browsers answer automatically. There is no application heartbeat.
- **Limits:**
  - **Frame size:** an inbound text frame is at most 16 KiB (16,384 bytes of UTF-8).
    - A larger frame closes the connection with `1009` (Message Too Big). It is never executed, and the client treats the close as reconnectable (§12).
    - The limit is enforced by the application, so it is testable without a particular transport.
    - A transport may also enforce its own frame limit in deployment, no lower than this one.
  - A binary frame is `MALFORMED_MESSAGE`.
  - The server's per-connection outbox is bounded. Its size is an implementation value, proposed at 256 messages. A connection that overflows it is closed with `4008`, and on reconnect it receives the current snapshot.

### 6. Client → server messages (B7)

Only `hello` (§5) and `command`:

```json
{"type": "command", "request_id": "a-04", "expected_revision": 6, "name": "act", "args": {"action": "raise", "target": 60}}
```

- `expected_revision`: an integer ≥ 1, the revision of the latest snapshot the client has applied. Every command carries it, private ones included (ADR 0005 §8, ADR 0006 §2).

| `name` | `args` | Effect |
| --- | --- | --- |
| `start_game` | `{}` | host only; starts the first hand |
| `act` | `{"action": "fold" \| "check" \| "call", "target": null}` or `{"action": "bet" \| "raise", "target": <int ≥ 1>}` | a betting action, passed to the engine unchanged |
| `showdown_decision` | `{"decision": "show" \| "muck"}` | the current decider's showdown choice |
| `sit_out` | `{}` | pending (private) during the requester's hand, otherwise applied at once |
| `sit_back` | `{}` | cancels a pending sit-out (private), or sits back in from sitting out |
| `leave` | `{}` | pending (private) during the requester's hand, otherwise applied at once (§8) |
| `select_pre_action` | `{"pre_action": {"kind": "<pre-action kind>", "amount": <int ≥ 1> \| null}}` | private; `amount` is set only for `call_current`, and the selection must be one of `you.pre_action_options` exactly |
| `clear_pre_action` | `{}` | private |

**Raise-to semantics.**
- `target` is the requester's **total chips in front on this street after the action** ("bet to", "raise to"). It is never the number of chips added.
- **All-in** is not a separate action. It is:
  - a `call` whose `legal_actions.call_is_all_in` is true; or
  - a `bet` or `raise` to `legal_actions.max_target`; or, when `short_all_in_target` is set, to that value, which is then the only legal target.
- The engine alone judges legality. An out-of-range target is a domain rejection (`ILLEGAL_ACTION`), not an argument error.

**Not client commands.** Create and join are HTTP. Advancing to the next hand is server-only: its timer calls it with the revision the timer was armed at (ADR 0005 §10).

### 7. Server → client messages

| `type` | Fields | Sent |
| --- | --- | --- |
| `snapshot` | `revision`, `cause`, `view` | after hello; after each shared transition, to every connected member; after the requester's private command |
| `accepted` | `request_id`, `revision` | the terminal outcome of an applied command; `revision` is the table's revision after it |
| `rejected` | `request_id`, `code`, `message` | the terminal outcome of a domain rejection; nothing changed |
| `error` | `request_id` (or `null`), `code`, `message` | a protocol or argument error (§12); nothing changed |
| `superseded` | — | terminal; followed by close `4409` |
| `left_table` | — | terminal; this member's departure was applied; followed by close `4410` |
| `table_failed` | — | terminal; the table hit a defect and is gone; followed by close `4500` |

- **`message` is diagnostic.** It is English text for logs. Clients display their own text from `code`, with a generic fallback (C6.2 §2.4). It is not normative.
- **Terminal messages:** the server sends the message, then closes with the matching code. On a clean close the client treats the message and the close code as the same signal, whichever it sees first.

### 8. Command outcomes and delivery (B1)

Several guarantees are often confused here. They are stated separately:
- what the server does with one received frame;
- what `request_id` is;
- what `expected_revision` protects;
- what a client can observe.

**What is not guaranteed.**
- **Exactly-once effects are not guaranteed.** A command lost before the server reads it has no effect at all. A command the server executes may have an outcome its client never receives.
- **There is no outcome cache, no outcome replay and no automatic retransmission**, on either side.

**Server processing.**
1. **At most once per frame.** Every text frame the server reads from an authenticated connection that is neither superseded nor closed is read once. A frame that decodes as a `command` is **executed at most once**:
   - in arrival order for that connection;
   - serialized with every other mutation of the table through `TableRuntime.execute` (ADR 0008 §4).

   No frame is read from a connection after it is superseded (§5) or closed. A frame still in transit when a connection drops is never read.
2. **`request_id` is a correlation identifier, not a deduplication mechanism.** The server copies it into the outcome and never compares it with earlier requests. Two frames carrying the same `request_id` are two independent commands. Scenario `reconnect_and_supersede` shows this.
3. **One outcome, possibly undelivered.** Each executed command produces exactly one terminal outcome, carrying its `request_id`. It is one of:
   - `accepted`;
   - `rejected` (a `TableSession` rejection);
   - `error` with code `INVALID_COMMAND` (the server could not interpret it).

   The outcome may be **undelivered**: when the connection drops first, or when the table fails (`table_failed`).

   A `rejected` or `error` outcome leaves the table, every private intent and the revision unchanged (ADR 0005 §7).
4. **What the requester receives, in this order, on its connection:**
   1. one `snapshot` for each shared transition the command produced, in revision order, each with that transition's cause. One command may produce several: for example `command` then `pre_action`, or a single `leave_auto_action` for a leave on the requester's own turn.
   2. If the command produced **no** shared transition and the requester is still a member: exactly one `snapshot` with cause `private`, at the **unchanged** revision.
   3. The outcome message.
   4. If the requester is no longer a member: `left_table`, then close `4410`.

   For `rejected` and `error` there is no snapshot, only the outcome.
5. **Other connected members** receive one `snapshot` per shared transition, with the transition's cause and no `request_id`. They receive nothing for someone else's private command or rejection. A member whose departure a transition applied (a pending leave at the hand boundary) receives `left_table` instead, then close `4410`.

**What `expected_revision` protects.**
- **It protects against duplicate shared transitions at one revision.** A command passes the guard only when its `expected_revision` equals the current shared revision. A successful shared command increments that revision. So of several commands carrying the same `expected_revision`, **at most one can produce a shared transition**, and a duplicated shared command at the same revision cannot apply twice.
- **It is not an idempotency guarantee for private commands.** A private command leaves the revision unchanged (ADR 0006 §2), so a repeated or reordered private command passes the guard. Today an exact repeat of an applied private command answers `NO_CHANGE` (an already selected pre-action, an already pending leave or sit-out, nothing to clear or cancel). That comes from `TableSession`'s current rules for these commands, **not from the protocol**, and a later private command need not behave that way.
- **It does not say whether a command was applied.** `STALE_REVISION` means only that shared state moved, which may have happened for any reason.
- **It does not protect a command sent with a newer revision.** That is a new command, and the guard treats it as one.

**Client-observed delivery.**
1. **Delivery is not guaranteed across a disconnection.** An outcome arrives only while the connection stays open, and it is never replayed after a reconnect.
2. **An uncertain outcome.** A client that has not received a command's outcome, because the connection dropped or its own timeout expired, treats the outcome as **uncertain**: the server may have executed the command once, or not at all.
3. **An uncertain command is never retransmitted**, neither automatically nor through a retry control. The client then:
   - keeps every gameplay action disabled;
   - reconnects;
   - re-enables actions only from the `connected` snapshot.

   The timeout is client-side behavior, not protocol (provisionally 10 s; C6.2 §2.3 rule 4).
4. **A fresh snapshot proves the current state, not which request caused it.** The client renders that state and makes no claim about the uncertain command's fate. After a `leave` whose outcome was uncertain, `AUTH_FAILED` on reconnect is the expected result of an applied leave. The client treats it as having left.
5. **After reconnection and reconciliation, the user may start a new command** from their own decision on the fresh state, with a **new** `request_id` and the **current** revision. It is a new command, not a retry of the uncertain one.
6. **The client completes a command only on its correlated outcome**, never on a revision change. One poker command is in flight at a time; the server does not enforce this.

### 9. Ordering, revisions and private updates

1. **Per-connection order.** Each connection's messages are queued in processing order and sent first-in, first-out. Revisions never decrease on one connection. Nothing is guaranteed about the relative order of different connections.
2. **No merging or skipping.** A live connection receives a snapshot for every shared transition, with the genuine intermediate state (ADR 0008 §5, C6.1 E7). A client may pace or animate them, but never reorder or alter them.
3. **Equal revision.** Two snapshots for the same member at the same revision differ only in that member's private intents (`you.pending_leave`, `you.pending_sit_out`, `you.pre_action`, `you.pre_action_options`; ADR 0006 §4). A `connected` snapshot may also repeat the current revision. The client applies a snapshot whose revision is ≥ its current one and ignores an older one (C6.2 §2.3 rule 5).
4. **Stale rejections arrive after newer state.** When a command whose `expected_revision` is **lower** than the current revision is rejected with `STALE_REVISION`, the same connection has already received a snapshot at a newer revision: either that transition's own snapshot or the connection's `connected` snapshot. The client keeps that snapshot and shows a quiet "Table updated".
   - An `expected_revision` **higher** than the current revision is also `STALE_REVISION`. No newer snapshot exists then, and it indicates a client defect.
5. **Causes.**

| Cause | Revision | Meaning |
| --- | --- | --- |
| `connected` | current | the first snapshot of a connection, after hello or a reconnect |
| `private` | unchanged | the requester's own private-intent change |
| `command` | +1 | a member's own shared change: a join (HTTP), start, action, showdown decision, an applied sit-out, sit-back or leave |
| `leave_auto_action` | +1 | the automatic check, fold or muck of a member with a pending leave |
| `pre_action` | +1 | a selected pre-action executing on its owner's turn |
| `hand_boundary` | +1 | the next-hand timer: pending leaves and sit-outs applied, then the next hand started or the table waiting |
| `resume` | +1 | a waiting table started a hand, or replaced its engine generation, after a member change |

### 10. The view (B3)

`snapshot.view` is one member's `TableView` (ADR 0005, ADR 0006), mapped field by field (ADR 0008 §2). Each field below is listed with its type, then its meaning. The fixtures show every shape.

**View**
- `table_id`: string.
- `join_code`: string.
- `settings`: Settings.
- `phase`: phase enum.
- `seats`: Seat[], one per seat number from 1 to `max_seats`, ascending.
- `hand`: Hand or `null`. It is the current hand, or the last settled hand until the next one starts. It is `null` before the first hand of an engine generation.
- `you`: You.

**Settings**
- `variant`: variant enum.
- `betting_structure`: betting structure enum.
- `small_blind`, `big_blind`, `buy_in`: integers ≥ 1.
- `max_seats`: integer 2–9.

`variant` and `betting_structure` are for display and client presentation configuration only. In v1 the Backend maps them as constants, because the only engine game is No-Limit Hold'em.

**Seat**
- `seat`: integer.
- `occupant`: Occupant or `null`.

**Occupant**
- `display_name`: string.
- `is_host`: bool.
- `stack`: integer ≥ 0, the chips behind, excluding `in_front`.
- `status`: occupant status, or `null` when ready.

**Hand**
- `number`: integer ≥ 1. It is scoped to one engine generation and may restart (ADR 0005 §11). It is for display only; a new hand is recognized from the cause and the log, never from a number change.
- `street`: street enum.
- `board`: Card[], 0–5 cards in deal order.
- `participants`: Participant[], in hand order, button first.
- `pots`: Pot[], the main pot first. It is empty until chips are first collected, and chips in front are never in a pot.
- `turn`: Turn or `null`.
- `legal_actions`: LegalActions, only in the view of the member who must bet now; otherwise `null`.
- `showdown_actions`: `["show", "muck"]`, only in the view of the current showdown decider; otherwise `null`.
- `showdown`: Showdown or `null`.
- `settlement`: Settlement, once the hand is settled; otherwise `null`.
- `log`: LogEvent[].

**Participant**
- `seat`: integer.
- `position`: position enum.
- `blind`: blind enum or `null`.
- `in_front`: integer ≥ 0, the chips committed this street and not yet collected.
- `folded`, `all_in`: bool.
- `has_live_cards`: bool. Cards were dealt and are neither folded nor mucked. It is the same for every viewer.
- `hole_cards`: Card[] when the viewer may see them, otherwise `null`. The viewer sees its own cards always, including after a fold or a muck, and everyone's shown cards.
- `hidden_card_count`: integer ≥ 0.
- `strength`: Strength, exactly when `hole_cards` is set and cards were dealt; otherwise `null`.

**Hidden cards (B3, W29).**
- `hidden_card_count` is the number of card backs to draw, never card values.
- The Backend maps it as: `0` when `hole_cards` is not `null` or `has_live_cards` is false; otherwise the engine's `HOLE_CARD_COUNT` (`game/variants/texas_holdem/dealing.py`), its single source.
- The client draws exactly `hidden_card_count` backs and the faces in `hole_cards`. Nothing assumes two cards.

**Pot**
- `amount`: integer ≥ 1.
- `eligible_seats`: integer[], ascending.

**Pots are the engine's.** Adjacent pots may have the same eligible seats, because the engine does not merge them. For example, a folded blind's chips form the lowest layer: scenario `three_way_side_pots`, hand 1, shows 30 and 780, both eligible to seats 1 and 2. Each pot is awarded separately (ADR 0001 §1).
- **A known Core defect:** with equivalent layers, the odd chips of a split can differ from those of the merged pot. A reproduced five-player tie over an aggregate 130 pays 66 / 64 instead of 65 / 65. This is accepted for the C6.4 POC only, and it is a mandatory fix before the Friends Alpha (C6.3 plan §3).
- **No fixture presents it as correct.** The one canonical split (`split_pot_and_all_in_calls`) is a single pot with one eligible-seat set.
- **The client renders pots and awards exactly as given.** It never merges or re-splits them.

**Turn**
- `seat`: integer.
- `kind`: turn kind enum.

**Showdown**
- `kind`: showdown kind enum.
- `order`: integer[], the engine's order.
- `decisions`: `{seat, decision}`[], in decision order.

**Settlement**
- `pot_awards`: `{amount, eligible_seats, shares: {seat, amount}[]}`[], in pot order. The shares are in the engine's odd-chip order.
- `shown_ranks`: `{seat, category}`[], the shown seats only.

**Strength**
- `category`: hand category enum.
- `description`: English text, for example "Pair of Kings", derived by the engine.
- `cards`: Card[5], in order of significance.

The client never evaluates hands.

**You**
- `seat`: integer.
- `is_host`, `pending_leave`, `pending_sit_out`: bool.
- `pre_action`: PreAction or `null`, the selection as presented.
- `pre_action_options`: PreAction[], what may be selected now.

**PreAction**
- `kind`: pre-action kind enum.
- `amount`: integer or `null`; set only for `call_current`.

**LogEvent.** The redacted hand history (ADR 0005 §5), one object per engine event, discriminated by `event`. All fields are always present.

| `event` | Fields |
| --- | --- |
| `hand_started` | `number`, `participants: {seat, position, blind, starting_stack}[]` |
| `blinds_posted` | `posts: {seat, blind, chips, all_in}[]` |
| `hole_cards_dealt` | `own_cards`: Card[] or `null` (only the viewer's own cards; `null` for a non-participant) |
| `street_dealt` | `street`, `cards`: the board cards only, never burns |
| `betting_round_started` | `street` |
| `action_taken` | `seat`, `action`, `target` (int for bet and raise, else `null`), `chips` (added by this action), `all_in` |
| `chips_returned` | `seat`, `chips` |
| `betting_round_completed` | `street` |
| `showdown_started` | `kind`, `order` |
| `showdown_decided` | `seat`, `decision` |
| `hand_settled` | `settlement`: Settlement |

Shown cards never appear in the log. They appear only in `participants[].hole_cards`.

### 11. Legal actions (B7)

| Field | Type | Meaning, exactly as the engine's `LegalActions` |
| --- | --- | --- |
| `can_fold`, `can_check`, `can_call`, `can_bet`, `can_raise` | bool | which action types are legal now; bet only when the current bet is zero, raise otherwise |
| `amount_owed` | int ≥ 0 | chips needed to match the call target |
| `call_amount` | int ≥ 0 | chips a `call` commits; less than `amount_owed` for a short call; `0` when calling is not legal |
| `call_is_all_in` | bool | the call uses the whole stack |
| `min_full_target` | int or `null` | the minimum full bet-to or raise-to target; set whenever a bet or raise is legal, even if the actor cannot reach it |
| `max_target` | int or `null` | the highest legal target; set whenever a bet or raise is legal |
| `short_all_in_target` | int or `null` | set only when the actor's all-in target is below `min_full_target`; it then equals `max_target` and is the only legal target |

**Client rules.**
- Action buttons come only from these fields: "Call $`call_amount`", "Raise to $`target`".
- The sizer offers the closed range `[min_full_target, max_target]`, or the single value `short_all_in_target` when it is set. Clamping to that range is a convenience; the server still validates.
- In `no_limit`, `max_target` is the actor's all-in target and may be labelled "All-in". For any other betting structure, a later protocol defines its meaning: the client never labels `max_target` as all-in, and never computes a pot limit or a preset target (C6.2 W21).

### 12. Code catalogue (B4)

Wire codes are `UPPER_SNAKE` strings, mapped explicitly. A code is never derived from a Python enum's value.

**`rejected` (domain, from `RejectionCode`; the connection stays open):**

| Code | Meaning |
| --- | --- |
| `STALE_REVISION` | `expected_revision` is not the current revision; checked before anything else |
| `NOT_A_MEMBER` | the requester is no longer a member, for example in a race with its own departure |
| `NOT_HOST` | `start_game` from a non-host |
| `GAME_ALREADY_STARTED` | `start_game` after the first hand |
| `NOT_ENOUGH_PLAYERS` | `start_game` with fewer than two players able to play |
| `NO_HAND_IN_PROGRESS` | an action with no hand to act in |
| `NOT_YOUR_TURN` | an action or showdown decision from a seat that is not the one to act |
| `ILLEGAL_ACTION` | the engine rejected the action or its target |
| `LEAVE_PENDING` | sit-out, sit-back or a pre-action command while a leave is pending |
| `NO_CHANGE` | the request changes nothing (already pending, already selected, nothing to clear or cancel) |
| `PRE_ACTION_UNAVAILABLE` | the pre-action is not one of `you.pre_action_options` |

`SEAT_TAKEN`, `INVALID_SEAT`, `DISPLAY_NAME_TAKEN`, `ALREADY_MEMBER` and `LEFT_TABLE` occur only on the HTTP join (§4). `NOT_AT_HAND_BOUNDARY` is internal to the server's own `advance_hand` call and never reaches the wire.

**`error` (protocol and arguments):**

| Code | `request_id` | Connection | When |
| --- | --- | --- | --- |
| `MALFORMED_MESSAGE` | `null` | stays open | not JSON, not an object, a binary frame, an unknown `type`, a missing or invalid `request_id`, or a second `hello` |
| `INVALID_COMMAND` | echoed | stays open; **this is the command's outcome** | a `command` with a valid `request_id` but any other defect: a missing or mistyped `expected_revision`, an unknown `name`, invalid `args`, an extra field |
| `HELLO_REQUIRED` | `null` | close `4400` | the first frame is not a well-formed `hello` |
| `PROTOCOL_MISMATCH` | `null` | close `4400` | an unsupported `hello.protocol` |
| `AUTH_FAILED` | `null` | close `4401` | an unknown table, or a credential that is not valid for it |
| `HELLO_TIMEOUT` | `null` | close `4408` | no `hello` within 10 s |

**Close codes and client reaction:**

| Code | Signal | Client |
| --- | --- | --- |
| `4400` | handshake protocol failure | terminal: "Please reload" |
| `4401` | `AUTH_FAILED` | terminal: back to entry; drop the stored credential |
| `4409` | `superseded` | terminal: "Use here", which reconnects and supersedes the other connection |
| `4410` | `left_table` | terminal: back to entry; drop the stored credential |
| `4500` | `table_failed` | terminal: error screen |
| `4008` | outbox overflow | reconnect |
| `4408` | `HELLO_TIMEOUT` | reconnect |
| `1009` | an inbound frame over 16 KiB (§5) | reconnect; the frame was not executed |
| `1001`, `1006`, `1011`, any other | going away, abnormal or server error | reconnect with backoff (C6.2 §2.4) |

### 13. Reconnection

- **Reconnecting** is a new connection to the same URL with a new `hello` and the same credential. The server supersedes any live connection for that credential, then sends `snapshot` with cause `connected` at the current revision.
- **Missed transitions** are not replayed (ADR 0005 §13). The client discards its presentation queue and jumps to the snapshot with no animation (C6.2 §2.3 rule 6).
- **A credential that no longer works** (the member left, the table failed, or a server restart lost it) gives `AUTH_FAILED`.
- **Recovery:** v1 makes no recovery claim. A restart loses every table until the durable mechanisms of ADR 0008 §8 exist (C6.1 E16).

### 14. Future variants and structures

v1 implements only No-Limit Hold'em. Its shapes already fit Omaha and Pot-Limit:
- hole cards are an array of any length, with `hidden_card_count`;
- `variant` and `betting_structure` are sent;
- sizing is a server-given target range;
- hand strength and descriptions come from the server.

What v1 deliberately does **not** do:
- It does not reserve `omaha` or `pot_limit` as enum values (§1.3). Adding them is a new protocol identifier, so a client never renders a variant nobody has tested.
- It does not define the meaning of `max_target` outside `no_limit`, or any preset target (§11).

### 15. Canonical fixtures (B5, W27)

- **Location:** `docs/adr/0009-wire-protocol-v1/`, versioned with this ADR. The layout, scenario format and conformance rules are in its [README](0009-wire-protocol-v1/README.md).
- **Normative:** the fixtures are part of this contract. Where the prose and a fixture disagree, the session stops and the Product Owner decides. The disagreement is never interpreted.
- **Frozen for C6.4:** they are committed on `master` before the Backend and Web worktrees branch, and frozen throughout C6.4. Both Briefs list the path as read-only. **No team may change a canonical fixture on its own.**
- **Controlled evolution after C6.4 (C6.3 P17).** A Core rules correction, such as the pot defect in §10, may change fixture **values** after the parallel Cycle ends. Such a change:
  - is explicitly reviewed;
  - is documented with the Core ADR that makes it;
  - regenerates the affected fixtures from the real engine;
  - re-runs both sides' fixture tests.

  It keeps `go-poker.v1` as long as the wire schema and every field's meaning stay compatible. An incompatible change (a shape, a field meaning, an enum, a code or a delivery rule) needs a new protocol identifier, a superseding ADR and Owner approval.
- **Contents:**
  - the HTTP exchanges and errors;
  - every client message and command;
  - snapshots for:
    - a not-started table;
    - a heads-up preflop, as actor and as waiting viewer;
    - a showdown decision;
    - a settled hand with a muck;
    - a nine-seat table;
    - a short all-in decision;
    - an all-in call decision (`call_is_all_in`);
    - a call-only decision against all-ins;
    - side pots with three participants, settled at an all-in showdown;
    - a split single pot with an odd chip;
    - a private pre-action acknowledgement and an executed pre-action;
    - a leave auto-action;
    - waiting for players, both with the last hand and with `hand: null` after an engine-generation reset, with occupants `sitting_out`;
    - a `resume` transition;
    - a reconnect;
  - `accepted` (shared and private), each kind of `rejected` the scenarios produce, each `error` kind, `superseded`, `left_table` and `table_failed`;
  - eight scenarios;
  - invalid frames for each direction.
- **Equality:** conformance compares parsed JSON values and ignores `message` fields.

### 16. Not in v1

The following are not in v1. Each is a later protocol version, and none is a C6.4 capability:
- spectators, and a pre-join seat view (C6.1 L1, E4);
- buy-in choice, rebuy, top-up and the wallet;
- action, disconnect and next-hand deadlines in the snapshot;
- owner settings and code rotation;
- chat;
- a hand-history API;
- Quick Play;
- multi-tabling;
- an application heartbeat;
- outcome replay;
- any recovery semantics.

## Alternatives considered

- **Tolerant decoding (ignore unknown fields, minor versions):** it lets the server add fields without a version change. It was rejected for v1, because during contract-first parallel work a silently ignored field is undetected drift, and C6.2 already chose exhaustive decoders behind the handshake.
- **The command outcome inside the requester's snapshot** (a `request_id` on the snapshot): it was rejected because one command can produce several transitions, or none, or remove the requester. A separate `accepted` after the command's snapshots has one rule for every case.
- **An outcome cache replayed after reconnect, or `request_id` deduplication:** it would answer the uncertain case directly, and could give exactly-once effects together with retransmission. It was rejected for the POC, because it adds server state, an expiry policy and ordering problems. v1 instead never retransmits an uncertain command and reconciles from authoritative state. A later protocol may add deduplication, for example for clients on unreliable mobile networks.
- **A `welcome` message after `hello`:** it carries nothing the first `connected` snapshot does not.
- **Diffs or an event stream:** rejected by ADR 0005 §13.
- **The protocol version in the URL or `Sec-WebSocket-Protocol`:** a browser cannot read why a handshake failed. A `hello` error gives a specific code.
- **Rejecting the upgrade for an unknown table:** the browser sees only a failed connection, and the answer reveals which table ids exist. `AUTH_FAILED` after `hello` is uniform.
- **The engine's enum values on the wire** (`"Fold"`, `"UTG+1"`, `"Preflop"`): they would tie the protocol to Python naming. Explicit lowercase mappings are stable and language-independent.
- **Leaving the log out of v1:** it is smaller, but the last-action label and the hand log would then need a new protocol version. The log is already redacted by allowlist in the engine, and mapping it is mechanical.
- **A hand-written normative JSON Schema now:** it would be a second source beside the Backend's DTOs (ADR 0008 §2). The prose and the fixtures are normative. The Backend's exported schema is tested against the fixtures, and the Friends Alpha generates TypeScript types from it (W6).
- **Reserving `omaha` and `pot_limit` now:** see §14.

## Consequences

- **Backend (C6.4)** implements:
  - §4–§13 in `src/go_poker/server/`, with explicit mapping and no `TableSession`, engine or `app/` change;
  - test-only injection of the table id, join code, credential generators, the button chooser and the next-hand trigger, so that the scenarios replay exactly;
  - a replay of every fixture scenario.
- **Web (C6.4)** implements:
  - strict decoders and encoders for exactly these shapes;
  - the connection lifecycle of §5, §8, §12 and §13;
  - fixture-driven decoder, render and mock-scenario tests.
- **Neither side** may add, rename or reinterpret a field. A needed change stops the session and goes to the Product Owner. A superseding ADR re-approves both Briefs (`ENGINEERING_PROCESS.md`, Parallel Sessions).
- **`ARCHITECTURE.md`** describes the protocol once it is implemented, and cites this ADR.
- **The known Core pot defect** (§10) is a mandatory Friends Alpha blocker. Its fix is Core work under its own ADR, after C6.4. It updates fixture values under §15 and keeps the protocol identifier.
- **C7** confirms or supersedes v1 (C6.1 E6), together with identity, durable credentials, hosting and origin, deadlines and the other §16 items.
- **Blockers resolved:** B1 by §8; B2 by §4; B3 by §10 (Settings and Hidden cards); B4 by §12; B5 by §15 and the fixtures; B6 by §1; B7 by §2, §3, §6 and §11.
