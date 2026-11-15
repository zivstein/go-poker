# `go_poker.server`

The FastAPI server that hosts private tables in memory and speaks [`go-poker.v1`](../../../docs/adr/0009-wire-protocol-v1.md). It imports `app`, `game` and `core`; nothing imports it.

## Dev command

```bash
uv run uvicorn go_poker.server.app:create_app --factory --host 127.0.0.1 --port 8000 --ws websockets --ws-ping-interval 20 --ws-ping-timeout 20 --ws-max-size 16384
```

`GET /health` answers `{"status": "ok"}`. The Web client reaches both surfaces through the Vite dev proxy, same origin.

The WebSocket options are stated explicitly because they are **transport** behavior, not application behavior:

- `--ws-ping-interval 20 --ws-ping-timeout 20` is the liveness rule of ADR 0009 §5: the server pings every 20 s and closes a connection that has not answered within 20 s. Browsers answer automatically, and there is no application heartbeat.
- `--ws-max-size 16384` is the transport's own inbound frame limit. A deployment may enforce its own, never lower than the contract's.

FastAPI's `TestClient` runs neither of them: it drives the ASGI application directly, with no WebSocket protocol implementation. So

- the **application** enforces the 16 KiB inbound limit itself (`ws.py`), which is what the tests check, and
- **ping and pong are checked by hand** in the demonstration, against this command.

## Modules

| Module | Responsibility |
| --- | --- |
| `app.py` | `create_app(config=None)`: the routes, the error handlers, the `Cache-Control: no-store` middleware, and one `TableDirectory` on `app.state` |
| `config.py` | `ServerConfig`: the table defaults, the timings, the limits, and the test-only seams, each defaulting to the production behavior |
| `directory.py` | `TableDirectory`: table id → runtime and active join code → table id; table creation and the identifiers it mints |
| `http.py` | `POST /tables`, `POST /tables/by-code/{join_code}/members`, `GET /health`, and the contract's error body |
| `ws.py` | `/ws/tables/{table_id}`: the handshake, the inbound limit, and phase 2 (one reader and one writer task per connection) |
| `runtime.py` | `TableRuntime`: phase 1, the single authoritative writer of one table, with no `await` |
| `timers.py` | the next-hand pause, behind a scheduler seam |
| `decode.py` | strict parsing of inbound frames into frozen command values |
| `dto.py` | the wire models, and the JSON Schema export |
| `mapping.py` | views and results → wire models, with the explicit enum, card and code tables |
| `ids.py` | the table id, join code, credential and user id generators |

## Invariants

- **Phase 1 is synchronous.** Between a `TableSession` call and the last outbox put there is no `await`, and no lock is held across a send. `tests/server/test_runtime_isolation.py` checks that on the source.
- **Explicit mapping only.** No wire field exists unless a function in `mapping.py` names it; `tests/server/test_mapping_is_an_allowlist.py` checks that on the source.
- **One writer per connection.** After the handshake, nothing sends except that connection's writer task, so the per-connection order of ADR 0009 §9 holds.
- **The engine decides legality.** `decode.py` checks shapes only; an out-of-range target comes back from the engine as `ILLEGAL_ACTION`.
