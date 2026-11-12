# M8 C6.4 — Web Cycle Brief (Work Order)

**Status:** **Approved** by the Product Owner on 2026-11-12 (revision 2, M8 C6.3), together with ADR 0009. Execution starts only on the Owner's instruction, after the preflight. This Brief is for a fresh Lead session in its own worktree. The parallel Backend Brief is [M8_C6_4_BACKEND_BRIEF.md](M8_C6_4_BACKEND_BRIEF.md). The shared dependencies are in the [C6.3 plan](M8_C6_3_WIRE_CONTRACT_PLAN.md) §4.

**Contract:** [ADR 0009](../adr/0009-wire-protocol-v1.md), `go-poker.v1`, and its fixtures. **Architecture:** the approved [C6.2 plan](M8_C6_2_WEB_PLAN.md), W1–W30. Neither is restated here.

## 1. Goal

The C6.2 §6 Priority 1 and 2 Web slice in `web/`. It is built and tested entirely against the ADR 0009 fixtures through the mock transport, and it is ready to drive two real browsers against the Backend once both branches are merged.

## 2. In scope

1. **`protocol/`:**
   - hand-written TypeScript types for every ADR 0009 shape (W6);
   - strict decoders: an unknown type, field or enum value, a missing field, a float or an out-of-range integer, or a card outside the ADR 0009 §3 encoding is a decode error;
   - encoders for `hello` and every command.
2. **`connection/`:**
   - the `Transport` interface with the browser WebSocket and the scripted mock (C6.2 §2.2);
   - the lifecycle of C6.2 §2.4: hello; the first `connected` snapshot as "live"; reconnect with backoff and jitter;
   - the terminal states keyed by ADR 0009 §12's close codes and messages, whichever comes first;
   - command correlation by `request_id`;
   - the uncertain-outcome rule (ADR 0009 §8):
     - a 10 s timeout;
     - actions disabled until a fresh `connected` snapshot;
     - the uncertain command is **never retransmitted**, automatically or through any retry control;
     - after reconciliation, any command is a new one from the user's decision on the fresh state, with a new `request_id` and the current revision;
     - the fresh snapshot is shown as the current state, never as proof of which request caused it;
     - `AUTH_FAILED` after an uncertain `leave` is treated as left;
     - `1009` is reconnectable.
3. **`api/`:** create and join (ADR 0009 §4), with the error body mapped to field errors. Join codes are uppercased and stripped of whitespace before sending.
4. **`session/` store:**
   - apply a snapshot with revision ≥ current, ignore an older one, and replace on equal (private);
   - one poker command in flight;
   - the last rejection;
   - stable cached references (W7).
5. **`presentation/`:** the displayed frame and queue, fast-forward on the hero's decision, and a jump on reconnect (C6.2 §2.3).
6. **`entry/`:** Create, Join with a seat number from 1 to 9, and the credential kept in `sessionStorage` keyed by `table_id` (C6.2 §2.5). `4401` and `4410` delete the stored credential.
7. **`table/`:** the functional table of C6.2 §6, Priority 1 item 3:
   - seats from `settings.max_seats`, using hand-tuned layouts for 2–9 seats with the hero at the bottom;
   - board, pots as given, chips in front, dealer and blinds, the turn indicator;
   - own cards and `strength.description`;
   - **card backs from `hidden_card_count` only**;
   - the dock from `legal_actions` (Min, All-in, input and slider; `short_all_in_target` collapses the sizer to one choice);
   - Show and Muck from `showdown_actions`;
   - the hand result from `settlement` plus the shown participants;
   - "Next hand starting", Leave, and the rejection text from a client table of ADR 0009 §12 codes with a generic fallback.
8. **The visual baseline**, C6.2 §6 Priority 2: Emerald tokens, the dev-only Sapphire toggle, Montserrat and Inter, code-drawn cards and chips, the provisional wordmark, monograms and reduced motion.
9. **Dev serving:** the Vite proxy forwards `/tables`, `/health` and `/ws` (with `ws: true`) to `http://127.0.0.1:8000`, the Backend's dev command (C6.3 plan D5).

   **Dev-only mock mode** (C6.3 plan D9) runs any fixture scenario with no server:
   - it loads fixtures only under `import.meta.env.DEV`, through a dynamic import;
   - `vite.config.ts` adds exactly `../docs/adr/0009-wire-protocol-v1/` to `server.fs.allow`, for the dev server only;
   - **the production build never contains a fixture.** A build-time check in `vite.config.ts` fails `vite build` if any module from that directory enters the bundle.
10. **Priority 3** (dropped first if over budget): motions 2–4, sit out / sit back, pre-actions from `you.pre_action_options`, a simple hand log from `hand.log`, narrower widths.

## 3. Out of scope

- Everything in C6.2 §6 **Out**, and ADR 0009 §16.
- Any poker rule in the client: no pot, call, limit, eligibility, turn order, winner or preset arithmetic. Clamping to the server's range is the only exception (C6.2 §2.3).
- Merging or reinterpreting pots or any other server value.
- New dependencies beyond the preflight's `web/package.json`. A needed one stops the session.
- Any file outside `web/`.

## 4. Architecture and ownership

- **Declared paths (the only ones this Cycle may change):** `web/`. `web/package.json` may change only in its `scripts`, and `web/package-lock.json` not at all (§3).
- **Read-only inputs:** `docs/adr/0009-wire-protocol-v1.md`, `docs/adr/0009-wire-protocol-v1/`, the C6.2 plan and `docs/design/`.
- **Fixtures are read from the repository path** (`../docs/adr/0009-wire-protocol-v1/`, relative to `web/`):
  - by a loader in `web/src/testing/`, through Node `fs`, in Vitest;
  - by the dev-only mock mode (§2.9).

  They are never copied into `web/` and never bundled. No team changes them on its own (P17).
- **Not touched:** `docs/ARCHITECTURE.md`, `CURRENT_CYCLE.md`, `ROADMAP.md`, `scripts/` and CI. The Web architecture section is recorded after integration.
- **Directory and dependency direction:** C6.2 §2.2, enforced by one Vitest test.

## 5. Behavior and invariants

1. **The server is the only source of game state** (C6.2 §2.3 rules 1–7).
2. **A command is complete only on its `accepted`, `rejected` or `error` (`INVALID_COMMAND`) with the same `request_id`.** It is never complete on a revision change. A `private` snapshot at an unchanged revision precedes the `accepted` of a private command.
   - `request_id` is only a correlation identifier.
   - Exactly-once effects are not guaranteed: an outcome can be lost with its connection, which is why the uncertain-outcome rule exists (§2.2).
3. **`STALE_REVISION` is not an error:** keep the newer snapshot and show "Table updated".
4. **An undecodable server message** closes the connection and shows the terminal "Please reload" (ADR 0009 §1.4).
5. **No card value is rendered** for a participant whose `hole_cards` is `null`. The DOM must not contain one.
6. **Seat numbers are the server's.** Rotation is presentational only.
7. **Amounts** are formatted as whole dollars with grouping (W20).

## 6. Test strategy

**Required, in Vitest:**

1. **Decoders:**
   - every server message in `messages/server/` and every `receive` in `scenarios/` decodes;
   - every `invalid/server_to_client.json` case fails to decode;
   - the HTTP fixture responses decode.
2. **Encoders:** every `messages/client/` frame is produced exactly (parsed equality) from its typed value. The commands of every scenario `send` step are encodable.
3. **Connection state machine** (fake timers, fake transport):
   - hello first;
   - the live state on the first snapshot;
   - correlation, including several snapshots before `accepted`, and a `private` snapshot then `accepted`;
   - the 10 s timeout → uncertain → actions stay disabled until the next `connected` snapshot, with **no frame re-sent**; after reconciliation, the next user command carries a new `request_id` and the current revision;
   - every ADR 0009 §12 close code mapped to terminal or reconnect;
   - backoff with jitter bounds;
   - supersede and "Use here".
4. **Store:** revision ordering, equal-revision replacement, and reference stability.
5. **Mock scenario replay:** for each scenario and each actor, the mock transport answers that actor's `send` steps with its `receive` steps, and the store reaches the expected final state.
6. **Rendering from fixtures:**
   - nine seats with no overlap;
   - every hero rotation for 2–9 seats (layout data);
   - side pots, with main and side shown separately, from `three_way_side_pots`;
   - pots rendered exactly as given, including hand 1's two layers with identical eligible seats (the known Core defect is not "fixed" by merging in the client);
   - a split single pot with its odd chip (1,463 / 1,462), from `split_pot_and_all_in_calls`;
   - an all-in call (`call_is_all_in`) labelled as all-in;
   - `sitting_out` occupants, and waiting for players with `hand: null`, from `sit_out_reset_resume`;
   - `short_all_in_target` collapsing the sizer;
   - a call-only dock;
   - Show and Muck;
   - a settled hand;
   - card backs equal `hidden_card_count`, with no hidden card value in the DOM;
   - controls queried by role and accessible name ("Call $5", "Raise to $20").
7. **Formatting:** money and card names.

All four gates — `tsc --noEmit`, `biome ci`, `vitest run` and `vite build`, the last including the fixture-exclusion check — pass inside `uv run scripts/verify.py` (preflight), together with the Python gates. Before the first run, the worktree has **both** toolchains installed: `npm ci` in `web/` and `uv sync --locked` at the root (C6.3 plan D3). They are part of worktree setup, not a dependency change.

**After both merges (not in this Cycle's gates):** the recorded two-browser demonstration of C6.2 §2.5, against the real server on `master`.

## 7. Risks and deferred decisions

| Risk | Mitigation |
| --- | --- |
| Hand-written types drift from the Backend DTOs | Both sides are tested against the same fixtures; codegen comes in the FA (W6) |
| A fixture seems wrong | Stop and go to the Owner. Never patch around it in the client |
| Visual work crowds out integration | Priority order of C6.2 §6; Priority 3 is dropped first |
| Adjacent pots with identical eligible seats look odd ("Side pot" with the same players) | Rendered as given (ADR 0009 §10). A known Core defect, accepted for the POC and fixed in Core before the Friends Alpha (C6.3 plan §7); fixture values then change under P17 |

Deferred: W21 presets, the FA items in C6.2 §7, and ADR 0009 §16.

## 8. Execution plan and sizing

**Sizing decision: keep the Cycle whole.** C6.2 estimated it at **M–L**, with several surfaces: protocol, connection, store and presentation, and table UI. Splitting would serialize what the contract has made independent, and the M8 Plan's C6.4 is one Web Cycle. The Priority 3 items absorb overrun. The Engineer works in this order, each step green before the next:

1. Protocol types, decoders and encoders against every fixture.
2. Connection and the mock transport, with the state-machine tests.
3. The store and presentation.
4. Entry and API.
5. Table components and the seat layout, with the render tests.
6. The visual baseline.
7. Priority 3, if within budget.

**Integration:** this branch merges second. Before the merge the Owner brings `master` (with the Backend) into this branch, and the session re-runs verification.

**Success targets:** as confirmed in the C6.3 plan §5.

Telemetry: per session, as in `ENGINEERING_PROCESS.md` (Usage Measurement).
