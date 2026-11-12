# ADR 0009 canonical fixtures (protocol `go-poker.v1`)

**Status: accepted with [ADR 0009](../0009-wire-protocol-v1.md) revision 2 on 2026-11-12, and frozen for C6.4.**

These files are part of the wire contract. Once ADR 0009 is accepted they are **frozen for all of C6.4**. Both the Backend and Web C6.4 Briefs list this directory as a **read-only input**. Neither side keeps a copy, and **no team changes a fixture on its own**: a needed change stops the session and goes to the Product Owner.

After C6.4, a reviewed Core rules correction may change fixture *values* under its Core ADR, with the protocol identifier unchanged while the schema and field meanings stay compatible. An incompatible change needs a new identifier (ADR 0009 §15; C6.3 plan P17).

## Layout

```text
0009-wire-protocol-v1/
  README.md
  messages/                 one canonical example per message shape
    http/                   {request, response} pairs: create, join, and each join error
    client/                 client → server frames: hello, and one command per name and action
    server/                 server → client frames: snapshots by situation, accepted, rejected, error, terminal
  scenarios/                ordered exchanges, end to end, over the real engine
    heads_up_hand.json            entry flow, errors on join, a full heads-up hand, interactive showdown, next hand
    rejections_and_errors.json    domain rejections, invalid command, malformed frame, stale revision
    pre_action_private.json       private updates at an unchanged revision, then a pre_action transition
    three_way_side_pots.json      three players, unequal stacks, short all-in raise, main and side pot
    reconnect_and_supersede.json  missed transitions, supersede, undelivered outcome, request_id not deduplicated,
                                  hello failures
    leave_and_sit_out.json        pending sit-out and cancel, pending leave with auto-fold, left_table
    sit_out_reset_resume.json     applied sit-outs, engine-generation reset (hand null), sit back, resume
    split_pot_and_all_in_calls.json  short all-in calls (call_is_all_in), one pot split with an odd chip
  invalid/
    client_to_server.json   frames the server must answer with a given error
    server_to_client.json   messages a v1 client decoder must reject
```

## Conformance

- **Equality is on parsed JSON values**, not bytes: object key order and whitespace are not significant; array order is.
- **`message` fields are not normative.** They are English diagnostics. Conformance comparisons ignore every `message` field: in `error`, `rejected`, and HTTP error bodies.
- **Credentials, table id and join code** are fixed fake values. A Backend test injects them through test-only generators. They follow the formats in ADR 0009 §2.
- Every `messages/` file is an excerpt of a scenario run, except `snapshot.nine_seats.actor.json` (nine joins and a start) and `table_failed.json` (no engine path produces a defect).

## Scenario format

```json
{
  "protocol": "go-poker.v1",
  "scenario": "…", "summary": "…",
  "setup": {
    "server_defaults": {"small_blind": 5, "big_blind": 10, "buy_in": 1000, "max_seats": 6, "host_seat": 1},
    "ids": {"table_id": "…", "join_code": "…", "credentials": {"alice": "…"}},
    "button": "lowest_starting_seat",
    "hands": [{"button": 1, "hole_cards": {"1": "Ah Kh"}, "board": "…", "draw_order": ["Ah", "…"]}]
  },
  "steps": [ … ]
}
```

- `setup.hands[i].draw_order` is the draw order for the engine's *i*-th deck shuffle, first card first, burns included. In every scenario here the *i*-th shuffle deals the listed hand *i*. A shuffle beyond the list keeps the deck unshuffled: `leave_and_sit_out` has one, a next-hand attempt that fails for lack of players.
- `button: lowest_starting_seat` is the button chooser for the first hand of each engine generation.
- Steps, in one valid causal order:

| `op` | Fields | Meaning |
| --- | --- | --- |
| `http` | `actor`, `request {method, path, body}`, `response {status, body}` | one HTTP exchange |
| `open` | `connection`, `actor`, `path` | the client opens a WebSocket |
| `send` | `connection`, `message` or `raw` | a client text frame (`raw` is sent as is) |
| `receive` | `connection`, `message` | a server text frame |
| `server_close` | `connection`, `code` | the server closes with this close code |
| `drop` | `connection` | the connection is lost abruptly; nothing more reaches that client on it |
| `server_timer` | `timer: "next_hand"` | the server's next-hand pause elapses |
| `note` | `text` | explanation only |

- **Normative order is per connection.** Each connection receives exactly its `receive` steps, in that order, and nothing else. The interleaving between different connections in the file is one valid order, not a requirement.

## How each side uses them

- **Backend:** replays every scenario through the real server (FastAPI test client, the real `TableSession` and engine) with the setup's ids, defaults, button rule and draw orders, and compares each connection's received messages and each HTTP response. Its own decoder answers every `invalid/client_to_server.json` case as stated. Its exported JSON Schema validates every server message here.
- **Web:** decodes every server message here and rejects every `invalid/server_to_client.json` case; encodes the `messages/client/` frames exactly; renders the snapshots (including nine seats, side pots and card backs from `hidden_card_count`); and replays the scenarios through the mock transport, one actor at a time.

## Known engine defect in the values

`three_way_side_pots` hand 1 shows two pots with identical eligible seats (30 and 780). This is the engine's current layering. With a tie it can distribute odd chips differently from a merged pot: a known Core defect, accepted for C6.4 only and fixed before the Friends Alpha (C6.3 plan §7). No fixture presents that outcome as correct. The canonical split, `split_pot_and_all_in_calls` hand 2, is a single pot with one eligible-seat set.

## Provenance

- **Source:** generated on 2026-11-12 from the engine on `master` (`aeea92e`) by a scratch prototype of the ADR 0009 mapping. The generator is not committed (C6.3 Q3). These files are the contract, and the Backend's scenario replay reproduces them from `setup` alone.
- **Checks run on each regeneration:**
  - no hole card or strength outside the viewer's own seat and the shown seats;
  - `hidden_card_count` consistent with `hole_cards` and `has_live_cards`;
  - legal and showdown actions only for the decider;
  - no user id or credential anywhere;
  - per-connection revisions never decreasing;
  - private snapshots at an unchanged revision, differing only in the private `you` fields;
  - settlement awards equal to the pots, shares adding up, winners eligible, odd chips in ADR 0001 order;
  - chips conserved in every hand.
- **Last result:** 188 snapshots, 24 settled, 159 conservation checks, no failure.
