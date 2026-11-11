# 0008: FastAPI server, single-writer tables and scale-ready boundaries

Status: Accepted (2026-11-11); partly supersedes [ADR 0005](0005-player-view-and-table-session-boundary.md)

## Context

ADR 0005 §12–14 fixed the server direction for the Friends Alpha:
- one process holding every table, with exactly one instance;
- restart loss accepted;
- Python ASGI on Starlette and uvicorn.

No server has been built yet. Since then, three things have changed:

- **The Product Contract (2026-11-08)** requires crash and restart recovery of account, wallet and table data for the Friends Alpha (§7, §10). That makes "a restart loses every table" unacceptable beyond the earliest preview.
- **The Product Owner's long-term direction (M8 C6.1, 2026-11-11)** covers:
  - FastAPI;
  - a modular monolith;
  - one authoritative writer per table;
  - future Quick Play pools partitioned for load;
  - scale-out and reliable recovery before a public launch.
- **The C6.1 plan** ([M8 C6.1 Backend/API Plan](../milestones/M8_C6_1_BACKEND_API_PLAN.md)) found the following:
  - `TableSession` already covers the gameplay slice and stays unchanged for the C6.4 POC.
  - The HTTP surface will grow (tables, Quick Play, later accounts and wallet).
  - Web and a later Mobile client both need a machine-readable wire schema.

The wire protocol itself, meaning message names, fields, encodings, errors and versioning, is decided separately in ADR 0009 (M8 C6.3).

## Decision

1. **Framework.**
   - The server is Python ASGI on **FastAPI and uvicorn**. FastAPI is built on Starlette, so WebSocket handling is Starlette's.
   - Server dependencies (`fastapi`, `uvicorn`, `websockets`; `httpx` for tests) stay outside the dependency-free engine.
   - Python 3.14 compatibility, including `pydantic-core`, is confirmed before the server is implemented.
2. **Wire DTOs by explicit mapping.**
   - Views reach the wire only as pydantic wire DTOs, each built from a frozen view value by an explicit, field-by-field mapping function.
   - Automatic bulk copying from domain or view objects is forbidden: `model_validate` on a view, `from_attributes`, `asdict`, `__dict__` or any equivalent. Such copying would bypass the visibility allowlist.
   - Normal pydantic validation of the explicitly mapped DTO data is permitted.
   - Engine and application objects are never serialized directly.
   - The DTOs are the single wire schema, and their JSON Schema is exported for clients.
3. **Handlers.**
   - Network handlers (HTTP and WebSocket) are `async def`.
   - `async def` alone does not serialize table mutations. Serialization is guaranteed by `TableRuntime` and its synchronous transition boundary (decision 4).
   - A synchronous handler would run in a thread pool, outside that boundary.
4. **Single writer per table.**
   - Every table has exactly one authoritative writer, its `TableRuntime`, which wraps that table's `TableSession`.
   - Every mutation goes through `TableRuntime.execute(command)`, whatever its source: HTTP, WebSocket or timers.
   - A command is a frozen data value from a small, closed set. No generic command framework is built.
   - Read-only queries go through a separate, controlled read interface on the runtime that never mutates.
   - A command and the queuing of its resulting messages run to completion with no `await` in between.
   - Each table has isolated authoritative gameplay state: no gameplay state is shared between tables, and there is no synchronous transaction across tables.
   - Shared identity, wallet and bankroll systems are separate cross-table concerns, decided in later milestones and ADRs.
5. **Delivery.**
   - The server sends genuine intermediate states: one snapshot per shared transition, mapped from the view captured at that transition, never re-read later.
   - Each client's messages are delivered in revision order, through a bounded queue per connection and a writer task per connection. No lock is held across a network send.
   - A slow client that fills its queue is disconnected, and on reconnect it receives the current snapshot.
   - Client animation pacing is a client concern: clients may pace or animate received states, but they never change their order or content.
   - The client-visible semantics are specified in ADR 0009.
6. **Identities are separate concepts.**
   - **Table id:** permanent, a globally unique opaque id.
   - **Join code:** a rotating invitation, unique among active codes. A revoked or expired code, or one from a closed session, never grants access.
   - **Player identity:** `UserId`, never on the wire.
   - **Game-node ownership:** which instance hosts a table's runtime. It is internal to the backend and never exposed to clients.
   - Every table-bound message is addressed by table id. Routing to the owner is internal to the backend; a client never addresses an instance.
   - The bearer token never appears in a URL (ADR 0005 §6, unchanged).
7. **Modular monolith.**
   - The logical boundaries are transport, table runtime, table directory, matchmaking, capacity and persistence/recovery.
   - The C6.4 POC implements only the transport, `TableRuntime` and an in-memory table dictionary.
   - The other boundaries are **planned designs, not implemented guarantees**, and none becomes a service or an abstract interface before it has a second implementation.
   - Matchmaking and capacity will reach a table only through runtime commands.
8. **Instances and restart.**
   - Exactly one instance runs until a later ADR approves leases, fencing and internal routing.
   - Losing every table on restart is accepted only through the Playable Preview.
   - The Friends Alpha requires durable table state and a consistent ledger, including the reduced crash policy approved for it (void an interrupted hand and restore its starting stacks). That policy may be relied on only once it is implemented and tested.
   - The public product requires accurate recovery of hands in progress.
   - Each mechanism is decided by its own later ADR. Recovery is expected to need `TableSession` export and restore and, for hands in progress, a Core change.

### Supersession of ADR 0005

| ADR 0005 clause | Effect |
| --- | --- |
| §12, "A single server process holds every live `TableSession` in memory. It is the only authority for its tables, so exactly one instance runs." | **Superseded** by decisions 4 and 8: one authoritative writer per table; one instance until a later ADR |
| §12, "Engine and application calls are synchronous. Each command runs to completion before another command for the same table starts…" | **Stands**, made concrete by decision 4 |
| §12, timers re-check the revision | **Stands** |
| §12, "A restart loses every table. That is accepted for the Friends Alpha." | **Superseded** by decision 8: accepted only through the Playable Preview |
| §14, "The server is Python ASGI on Starlette and uvicorn." | **Superseded** by decision 1: FastAPI and uvicorn |
| §14, "Views are serialized to JSON at the server boundary, by explicit serializers from view values." | **Refined** by decision 2: explicit mapping into wire DTOs |
| §14, engine and application objects never serialized directly; the engine has no serialization; Python 3.14 confirmed first | **Stand** |
| §13 | **Stands**, as amended by ADR 0006; decision 5 adds the server's delivery rules, and ADR 0009 the wire semantics |
| §1–11, and ADR 0006 | **Unchanged** |

## Alternatives considered

- **Starlette only (ADR 0005 §14):** sufficient for WebSocket, but its validation, auth injection and schema generation would have to be built by hand for a growing HTTP surface. Adopting FastAPI later stays possible, but the Owner preferred to decide now.
- **Pydantic models built automatically from view dataclasses:** less code, but a field added to a view would reach the wire by default, which is the leak the explicit allowlist exists to prevent.
- **One global writer, or a lock around all tables:** simpler, but it serializes unrelated tables and cannot be spread across instances.
- **Splitting into services now:** premature. The boundaries are kept as modules until load or ownership proves a split.
- **Exposing instance addresses to clients, or routing by URL alone:** ties clients to placement and breaks on failover. Routing stays internal.
- **A generic command or event-sourcing framework:** no demonstrated need. Plain command values through one `execute` keep logging and routing possible without one.

## Consequences

- **The C6.4 Backend** builds `src/go_poker/server/` with FastAPI, `TableRuntime`, an in-memory table dictionary, DTO mapping with JSON Schema export, and delivery as in decision 5. `TableSession`, the engine and `app/` are unchanged.
- **A bounded preflight** (Small-Change Path Meta work) adds the server dependencies and the Web toolchain to `verify.py` and CI before C6.4.
- **Later ADRs** decide each of these as its milestone arrives:
  - durable state and the Friends Alpha crash policy;
  - accurate in-hand recovery (expected to include a Core ADR on hand serialization or deterministic replay);
  - leases, fencing and internal routing;
  - partitioned Quick Play matchmaking;
  - capacity and admission.
- **`ARCHITECTURE.md`** describes the server only once it is implemented.
- **`ROADMAP.md`'s** approved server line is updated to cite this ADR.
- **ADR 0005's** status line records the partial supersession by this ADR, as it does for ADR 0006.
