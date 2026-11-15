import { describe, expect, it } from "vitest";
import type { ScenarioSendStep } from "../testing/fixtures";
import {
  listFixtureFiles,
  listScenarioNames,
  readFixtureJson,
  readScenario,
} from "../testing/fixtures";
import { decodeClientMessage, ProtocolDecodeError } from "./decode";
import { encodeCommand, encodeHello } from "./encode";
import type { ClientMessage, CommandMessage } from "./types";

describe("encodeHello", () => {
  it("produces the canonical hello frame", () => {
    const fixture = readFixtureJson<{ credential: string }>("messages/client/hello.json");
    expect(encodeHello(fixture.credential)).toEqual(fixture);
  });
});

describe("encodeCommand", () => {
  for (const file of listFixtureFiles("messages/client")) {
    if (file === "hello.json") continue;
    it(`produces messages/client/${file} exactly from its typed value`, () => {
      const fixture = readFixtureJson<CommandMessage>(`messages/client/${file}`);
      // Re-derive the typed command from the fixture's own fields, then re-encode:
      // the test is that encoding a typed value is parsed-equal to the fixture,
      // not merely that the fixture round-trips through JSON.
      const encoded = encodeCommand(fixture.request_id, fixture.expected_revision, {
        name: fixture.name,
        args: fixture.args,
      } as never);
      expect(encoded).toEqual(fixture);
    });
  }
});

describe("scenario send steps are encodable", () => {
  // Every well-formed `command` a legitimate client could construct from our
  // typed model is produced exactly by our encoder. A handful of scenario
  // `send` steps are deliberately malformed (an unknown command name, a
  // raise with no target, a raw non-JSON frame) to exercise the Backend's
  // own decoder (the fixtures' README); those are not constructible from our
  // types at all, and are skipped here rather than guessed at.
  for (const name of listScenarioNames()) {
    it(`replays ${name}`, () => {
      const scenario = readScenario(name);
      let checked = 0;
      for (const step of scenario.steps) {
        if (step.op !== "send") continue;
        const send = step as ScenarioSendStep;
        if (send.message === undefined) continue; // a `raw` frame: not a typed message
        let message: ClientMessage;
        try {
          message = decodeClientMessage(send.message);
        } catch (e) {
          if (e instanceof ProtocolDecodeError) continue; // deliberately malformed
          throw e;
        }
        if (message.type === "hello") {
          expect(encodeHello(message.credential)).toEqual(send.message);
        } else {
          expect(
            encodeCommand(message.request_id, message.expected_revision, {
              name: message.name,
              args: message.args,
            } as never),
          ).toEqual(send.message);
        }
        checked += 1;
      }
      expect(checked).toBeGreaterThan(0);
    });
  }
});
