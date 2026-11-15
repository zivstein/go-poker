import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ClosedReason } from "../connection/closeCodes";
import type { Scenario, ScenarioReceiveStep, ScenarioStep } from "./fixtures";
import { listScenarioNames, readScenario } from "./fixtures";
import { driveScenarioConnection, scenarioConnectionIds } from "./scenarioPlayer";

/**
 * Fixture `send` steps that a correct client does not (or cannot) put on the
 * wire exactly as written. Each exists in the scenarios only to exercise the
 * Backend's decoder or revision guard. The set is closed: any other
 * difference between the client's frame and the fixture's frame fails the
 * test. Keys are `scenario|connection|request_id` for a command and
 * `scenario|connection|raw#<n>` (n-th raw send step of the connection).
 *
 * - `not_producible`: the client has no API that builds this frame; it is not
 *   driven, and the test asserts the client never sends it.
 * - `stale_in_fixture`: the fixture deliberately carries a stale
 *   `expected_revision`; the client IS driven and must send the same command
 *   with its current revision (`clientRevision`), proving it does not copy
 *   the stale one.
 * - `hello_protocol`: keyed `scenario|connection|hello`; the fixture's hello
 *   names a protocol this client does not speak. The client IS driven and
 *   must send the same hello with protocol `go-poker.v1`.
 */
type Divergence =
  | { kind: "not_producible"; reason: string }
  | { kind: "hello_protocol"; reason: string }
  | { kind: "stale_in_fixture"; clientRevision: number; reason: string };

const DIVERGENCES: Readonly<Record<string, Divergence>> = {
  "rejections_and_errors|alice-1|a-03": {
    kind: "not_producible",
    reason: "act raise with target null: ActArgs requires a number for bet/raise",
  },
  "rejections_and_errors|alice-1|a-04": {
    kind: "not_producible",
    reason: "the `rebuy` command does not exist in protocol v1; CommandName has no such command",
  },
  "rejections_and_errors|alice-1|raw#0": {
    kind: "not_producible",
    reason: "truncated JSON frame: the client only sends encoded messages",
  },
  "rejections_and_errors|alice-1|raw#1": {
    kind: "not_producible",
    reason: "second hello frame: the client sends hello once, as the first frame of a connection",
  },
  "rejections_and_errors|bob-1|b-02": {
    kind: "stale_in_fixture",
    clientRevision: 4,
    reason:
      "models a command sent before Alice's revision-4 snapshot arrived; the replay delivers that snapshot first, so the client correctly carries revision 4",
  },
  "reconnect_and_supersede|alice-2|hello": {
    kind: "hello_protocol",
    reason:
      "provokes PROTOCOL_MISMATCH with a hello for protocol go-poker.v0; this client only speaks go-poker.v1",
  },
  "reconnect_and_supersede|bob-4|b-01": {
    kind: "stale_in_fixture",
    clientRevision: 5,
    reason:
      "a byte-identical duplicate of b-01 as a faulty client might send; the client's command after the connected snapshot (revision 5) carries revision 5",
  },
};

const usedDivergences = new Set<string>();

/** The terminal reason a connection must end in, from the scenario's last
 * step for it (spelled out here, not taken from the production table). */
const TERMINAL_CLOSE_CODES: Readonly<Record<number, ClosedReason>> = {
  4400: "protocol_mismatch",
  4401: "auth_failed",
  4409: "superseded",
  4410: "left_table",
  4500: "table_failed",
};
const TERMINAL_MESSAGES: Readonly<Record<string, ClosedReason>> = {
  superseded: "superseded",
  left_table: "left_table",
  table_failed: "table_failed",
};

function expectedTerminalReason(
  lastStep: (ScenarioStep & { connection: string }) | undefined,
): ClosedReason | null {
  if (lastStep === undefined) return null;
  if (lastStep.op === "server_close") return TERMINAL_CLOSE_CODES[lastStep.code] ?? null;
  if (lastStep.op === "receive") {
    return TERMINAL_MESSAGES[(lastStep.message as { type?: string }).type ?? ""] ?? null;
  }
  return null;
}

function parseFrame(frame: string | undefined): unknown {
  if (frame === undefined) throw new Error("no frame was sent");
  return JSON.parse(frame);
}

describe("mock scenario replay", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  for (const scenarioName of listScenarioNames()) {
    const scenario: Scenario = readScenario(scenarioName);
    for (const connectionId of scenarioConnectionIds(scenario)) {
      it(`${scenarioName}: ${connectionId} sends what the scenario shows and reaches its expected final state`, () => {
        const keyOf = (id: string) => `${scenarioName}|${connectionId}|${id}`;
        const notDriven = new Set<string>();
        for (const [key, divergence] of Object.entries(DIVERGENCES)) {
          const [s, c, id] = key.split("|");
          if (s === scenarioName && c === connectionId && divergence.kind === "not_producible") {
            if (id !== undefined && !id.startsWith("raw#")) notDriven.add(id);
          }
        }

        const { store, controller, transport, trace } = driveScenarioConnection(
          scenario,
          connectionId,
          { notDriven },
        );

        // What the client sent, step by step.
        for (const event of trace) {
          if (event.kind === "open") {
            expect(event.frames, `${scenarioName}/${connectionId} open: hello frames`).toHaveLength(
              1,
            );
            const helloKey = keyOf("hello");
            const sentHello = parseFrame(event.frames[0]);
            if (DIVERGENCES[helloKey]?.kind === "hello_protocol") {
              usedDivergences.add(helloKey);
              const fixtureHello = event.expectedHello as { protocol: string };
              expect(fixtureHello.protocol, `${helloKey}: fixture protocol`).not.toBe(
                "go-poker.v1",
              );
              expect(sentHello, `${helloKey}: client speaks go-poker.v1`).toEqual({
                ...fixtureHello,
                protocol: "go-poker.v1",
              });
            } else {
              expect(sentHello, `${helloKey}: hello equals the fixture's`).toEqual(
                event.expectedHello,
              );
            }
            continue;
          }
          if (event.kind === "raw") {
            const key = keyOf(`raw#${event.index}`);
            const divergence = DIVERGENCES[key];
            expect(divergence?.kind, `${key} must be an allowlisted raw frame`).toBe(
              "not_producible",
            );
            usedDivergences.add(key);
            expect(transport.sentFrames, `${key}: the client must never send it`).not.toContain(
              event.raw,
            );
            continue;
          }

          const key = keyOf(event.requestId);
          const divergence = DIVERGENCES[key];
          if (divergence !== undefined) usedDivergences.add(key);

          if (divergence?.kind === "not_producible") {
            expect(event.driven, `${key}: not driven`).toBe(false);
            expect(
              transport.sentFrames.map((f) => JSON.parse(f)),
              `${key}: the client must never send this frame`,
            ).not.toContainEqual(event.expected);
            continue;
          }

          expect(event.driven, `${key}: driven`).toBe(true);
          expect(event.returned, `${key}: sendCommand returned a request_id`).not.toBeNull();
          expect(event.frames, `${key}: exactly one frame sent`).toHaveLength(1);
          const sent = parseFrame(event.frames[0]);
          if (divergence?.kind === "stale_in_fixture") {
            const fixtureMessage = event.expected as { expected_revision: number };
            expect(fixtureMessage.expected_revision, `${key}: fixture is stale`).not.toBe(
              divergence.clientRevision,
            );
            expect(event.revisionAtSend, `${key}: client's own revision`).toBe(
              divergence.clientRevision,
            );
            expect(sent, `${key}: client carries its current revision`).toEqual({
              ...fixtureMessage,
              expected_revision: divergence.clientRevision,
            });
          } else {
            expect(sent, `${key}: frame equals the fixture's message`).toEqual(event.expected);
          }
        }

        // The terminal status of a connection that ends terminally.
        const connectionSteps = scenario.steps.filter(
          (s): s is ScenarioStep & { connection: string } =>
            "connection" in s && s.connection === connectionId,
        );
        const lastStep = connectionSteps[connectionSteps.length - 1];
        const terminalReason = expectedTerminalReason(lastStep);
        if (terminalReason !== null) {
          expect(controller.currentStatus.phase).toBe("closed");
          expect(controller.currentStatus.reason).toBe(terminalReason);
        } else {
          expect(controller.currentStatus.phase).not.toBe("closed");
        }

        // The final store state.
        const receives = connectionSteps.filter(
          (s): s is ScenarioReceiveStep & { connection: string } => s.op === "receive",
        );
        const lastSnapshot = [...receives]
          .reverse()
          .find((s) => (s.message as { type?: string }).type === "snapshot");
        if (lastSnapshot !== undefined) {
          const expected = lastSnapshot.message as { revision: number; view: unknown };
          expect(store.getSnapshot().revision).toBe(expected.revision);
          expect(store.getSnapshot().view).toEqual(expected.view);
        }
      });
    }
  }

  it("lists no allowlisted divergence that no scenario step exercises", () => {
    expect([...usedDivergences].sort()).toEqual(Object.keys(DIVERGENCES).sort());
  });
});
