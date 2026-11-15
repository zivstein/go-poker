/**
 * Drives one connection of a committed scenario through a
 * {@link ConnectionController} and {@link TableStore}, using a
 * {@link MockTransport} (C6.2 plan §2.6). Used only by the mock-scenario-replay
 * test, which asserts the client's real behavior against the trace this
 * player records; it is not used by the dev mock mode.
 *
 * The player emits every `receive`, `server_close` and `drop` step as the
 * server's side of the scenario. For each `send` step it makes the client
 * produce its own frame (`connect()` for `hello`, `sendCommand` for a
 * command) and records what the client actually put on the wire, so the test
 * can compare it with the fixture's frame. It never writes the fixture's
 * frame to the transport on the client's behalf.
 */

import { ConnectionController } from "../connection/ConnectionController";
import { MockTransport } from "../connection/MockTransport";
import type { CommandName } from "../protocol/types";
import { TableStore } from "../session/store";
import { wireStore } from "../session/wireStore";
import type { Scenario, ScenarioStep } from "./fixtures";

export interface ScenarioIds {
  table_id: string;
  join_code: string;
  credentials: Record<string, string>;
}

/** What the client did at one `open` or `send` step of the connection. */
export type TraceEvent =
  | {
      kind: "open";
      /** The connection's `hello` send step message, if the scenario has one. */
      expectedHello: unknown;
      /** Frames the client sent while the connection opened. */
      frames: string[];
    }
  | {
      kind: "command";
      /** `request_id` of the fixture's command. */
      requestId: string;
      /** The fixture's command message. */
      expected: unknown;
      /** False when the step was listed in `notDriven`: the client was not asked to send it. */
      driven: boolean;
      /** What `sendCommand` returned (null when not driven, or refused). */
      returned: string | null;
      /** Frames the client sent for this step. */
      frames: string[];
      /** The controller's revision when the command was issued. */
      revisionAtSend: number;
    }
  | {
      kind: "raw";
      /** Index of this raw frame among the connection's raw send steps. */
      index: number;
      raw: string;
    };

export interface ScenarioPlayer {
  controller: ConnectionController;
  store: TableStore;
  transport: MockTransport;
  trace: TraceEvent[];
}

export interface DriveOptions {
  /** `request_id`s of command send steps the client is not asked to send
   * (a frame a correct client cannot produce). They are recorded, not driven. */
  notDriven?: ReadonlySet<string>;
}

interface CommandLikeMessage {
  type: string;
  request_id?: string;
  name?: string;
  args?: unknown;
}

function isCommandMessage(
  value: unknown,
): value is CommandLikeMessage & { request_id: string; name: CommandName } {
  return (
    typeof value === "object" && value !== null && (value as { type?: unknown }).type === "command"
  );
}

/** Plays one connection's `send`/`receive`/`server_close`/`drop` steps,
 * in the exact order the scenario gives for that connection. */
export function driveScenarioConnection(
  scenario: Scenario,
  connectionId: string,
  options: DriveOptions = {},
): ScenarioPlayer {
  const steps = scenario.steps.filter(
    (s): s is ScenarioStep & { connection: string } =>
      "connection" in s && s.connection === connectionId,
  );
  const openStep = steps.find((s) => s.op === "open");
  if (openStep === undefined || openStep.op !== "open") {
    throw new Error(`no "open" step for connection ${connectionId}`);
  }
  const ids = (scenario.setup as { ids: ScenarioIds }).ids;
  const helloStep = steps.find(
    (s) => s.op === "send" && (s.message as { type?: string } | undefined)?.type === "hello",
  );
  const helloMessage =
    helloStep !== undefined && helloStep.op === "send" ? helloStep.message : undefined;
  const helloCredential = (helloMessage as { credential?: string } | undefined)?.credential;
  // A hostile or unregistered actor (for example "mallory") sends its own
  // (invalid) credential directly in `hello`, with no `setup.ids` entry.
  const credential = helloCredential ?? ids.credentials[openStep.actor];
  if (credential === undefined) throw new Error(`no credential for actor ${openStep.actor}`);

  // The fixture's request_id for the command about to be sent, so the frame
  // the client builds carries the same correlation id.
  let nextRequestId = "";

  const transport = new MockTransport();
  const controller = new ConnectionController(transport, {
    tableId: ids.table_id,
    credential,
    requestIdFactory: () => nextRequestId,
  });
  const store = new TableStore();
  wireStore(store, controller);
  const trace: TraceEvent[] = [];
  let rawIndex = 0;

  for (const step of steps) {
    switch (step.op) {
      case "open": {
        const before = transport.sentFrames.length;
        controller.connect();
        transport.emitOpen();
        trace.push({
          kind: "open",
          expectedHello: helloMessage,
          frames: transport.sentFrames.slice(before),
        });
        break;
      }
      case "send": {
        if (step.raw !== undefined) {
          // The client has no way to send an arbitrary frame.
          trace.push({ kind: "raw", index: rawIndex++, raw: step.raw });
          break;
        }
        const message = step.message as CommandLikeMessage | undefined;
        // A `hello` send is performed by `connect()`'s open handler and
        // recorded at the `open` step.
        if (!isCommandMessage(message)) break;
        const before = transport.sentFrames.length;
        const revisionAtSend = controller.currentRevision;
        let returned: string | null = null;
        const driven = options.notDriven?.has(message.request_id) !== true;
        if (driven) {
          nextRequestId = message.request_id;
          returned = controller.sendCommand({ name: message.name, args: message.args } as never);
        }
        trace.push({
          kind: "command",
          requestId: message.request_id,
          expected: message,
          driven,
          returned,
          frames: transport.sentFrames.slice(before),
          revisionAtSend,
        });
        break;
      }
      case "receive":
        transport.emitMessage(step.message);
        break;
      case "server_close":
        transport.emitClose(step.code);
        break;
      case "drop":
        transport.emitClose(1006);
        break;
      case "server_timer":
      case "note":
        break;
    }
  }

  return { controller, store, transport, trace };
}

/** Every distinct connection id a scenario opens. */
export function scenarioConnectionIds(scenario: Scenario): string[] {
  const ids = new Set<string>();
  for (const step of scenario.steps) {
    if (step.op === "open") ids.add(step.connection);
  }
  return [...ids];
}
