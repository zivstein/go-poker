import { describe, expect, it } from "vitest";
import type { ScenarioReceiveStep } from "../testing/fixtures";
import {
  listFixtureFiles,
  listScenarioNames,
  readFixtureJson,
  readFixtureText,
  readScenario,
} from "../testing/fixtures";
import {
  decodeCreateTableResponse,
  decodeHttpErrorBody,
  decodeJoinTableResponse,
  decodeServerMessage,
  ProtocolDecodeError,
  parseWireJson,
} from "./decode";

describe("decodeServerMessage", () => {
  for (const file of listFixtureFiles("messages/server")) {
    it(`decodes messages/server/${file}`, () => {
      const raw = readFixtureJson(`messages/server/${file}`);
      expect(() => decodeServerMessage(raw)).not.toThrow();
    });
  }

  it("decodes every receive step of every scenario", () => {
    for (const name of listScenarioNames()) {
      const scenario = readScenario(name);
      for (const step of scenario.steps) {
        if (step.op === "receive") {
          const receive = step as ScenarioReceiveStep;
          expect(
            () => decodeServerMessage(receive.message),
            `${name}: ${JSON.stringify(receive.message).slice(0, 120)}`,
          ).not.toThrow();
        }
      }
    }
  });

  it("rejects every invalid/server_to_client.json case", () => {
    // Parsed with parseWireJson, not plain JSON.parse: `money_float` writes a
    // field as `995.0`, and only parseWireJson preserves that it was a float
    // rather than collapsing it to the integer 995 (ADR 0009 §2).
    const text = readFixtureText("invalid/server_to_client.json");
    const data = parseWireJson(text) as { cases: { case: string; message: unknown }[] };
    for (const c of data.cases) {
      expect(() => decodeServerMessage(c.message), c.case).toThrow(ProtocolDecodeError);
    }
  });
});

describe("parseWireJson (the float-vs-integer sentinel)", () => {
  it("parses an ordinary object with plain integers unaffected", () => {
    const text = '{"a":1,"b":995,"c":-7,"d":0}';
    expect(parseWireJson(text)).toEqual({ a: 1, b: 995, c: -7, d: 0 });
  });

  it("leaves digit-like substrings inside strings untouched", () => {
    const text = '{"table_id":"4f9c2a1e-8d3b-4c5a-9e7f-1a2b3c4d5e6f","note":"5.0 chips"}';
    expect(parseWireJson(text)).toEqual({
      table_id: "4f9c2a1e-8d3b-4c5a-9e7f-1a2b3c4d5e6f",
      note: "5.0 chips",
    });
  });

  it("leaves an escaped quote or backslash inside a string intact", () => {
    const text = '{"note":"she said \\"5.0\\" and left a \\\\ mark"}';
    expect(parseWireJson(text)).toEqual({ note: 'she said "5.0" and left a \\ mark' });
  });

  it("marks a decimal literal so expectInt rejects it, in an array and nested object", () => {
    const text = '{"amounts":[1,995.0,3],"nested":{"stack":1000.5}}';
    const parsed = parseWireJson(text) as { amounts: unknown[]; nested: { stack: unknown } };
    expect(parsed.amounts[0]).toBe(1);
    expect(typeof parsed.amounts[1]).toBe("string"); // the sentinel, not the number 995
    expect(parsed.amounts[2]).toBe(3);
    expect(typeof parsed.nested.stack).toBe("string");
  });

  it("marks a bare-exponent integer-looking literal (1e5) as a float too", () => {
    const text = '{"a":1e5,"b":1E+5,"c":-2e-3}';
    const parsed = parseWireJson(text) as Record<string, unknown>;
    for (const key of ["a", "b", "c"]) {
      expect(typeof parsed[key]).toBe("string");
    }
  });

  it("round-trips every messages/server fixture identically to JSON.parse", () => {
    for (const file of listFixtureFiles("messages/server")) {
      const text = readFixtureText(`messages/server/${file}`);
      expect(parseWireJson(text), file).toEqual(JSON.parse(text));
    }
  });
});

describe("boundary values decoders must reject or accept exactly", () => {
  function baseSnapshot(): {
    type: string;
    revision: number;
    cause: string;
    view: { settings: { max_seats: number }; you: { seat: number } } & Record<string, unknown>;
  } {
    return readFixtureJson("messages/server/snapshot.connected.not_started.json");
  }

  it.each([
    [1, false],
    [2, true],
    [9, true],
    [10, false],
  ])("max_seats = %i is accepted: %s", (value, accepted) => {
    const message = baseSnapshot();
    message.view.settings.max_seats = value;
    if (accepted) {
      expect(() => decodeServerMessage(message)).not.toThrow();
    } else {
      expect(() => decodeServerMessage(message)).toThrow(ProtocolDecodeError);
    }
  });

  it.each([
    [0, false],
    [1, true],
    [9, true],
    [10, false],
  ])("a seat number of %i is accepted: %s", (value, accepted) => {
    const message = baseSnapshot();
    message.view.you.seat = value;
    if (accepted) {
      expect(() => decodeServerMessage(message)).not.toThrow();
    } else {
      expect(() => decodeServerMessage(message)).toThrow(ProtocolDecodeError);
    }
  });

  it.each([
    [0, false],
    [1, true],
    [-1, false],
  ])("revision = %i is accepted: %s", (value, accepted) => {
    const message = baseSnapshot();
    message.revision = value;
    if (accepted) {
      expect(() => decodeServerMessage(message)).not.toThrow();
    } else {
      expect(() => decodeServerMessage(message)).toThrow(ProtocolDecodeError);
    }
  });
});

describe("HTTP fixtures", () => {
  it("decodes the create table response", () => {
    const fixture = readFixtureJson<{ response: { body: unknown } }>(
      "messages/http/create_table.json",
    );
    expect(() => decodeCreateTableResponse(fixture.response.body)).not.toThrow();
  });

  it("decodes the join table response", () => {
    const fixture = readFixtureJson<{ response: { body: unknown } }>(
      "messages/http/join_table.json",
    );
    expect(() => decodeJoinTableResponse(fixture.response.body)).not.toThrow();
  });

  for (const file of [
    "join_table.error.display_name_taken.json",
    "join_table.error.invalid_seat.json",
    "join_table.error.seat_taken.json",
  ]) {
    it(`decodes the error body of ${file}`, () => {
      const fixture = readFixtureJson<{ response: { body: unknown } }>(`messages/http/${file}`);
      expect(() => decodeHttpErrorBody(fixture.response.body)).not.toThrow();
    });
  }
});

describe("strict string decoding", () => {
  const joinBody = (joinCode: string) =>
    `{"table_id":"t","join_code":${joinCode},"seat":1,"credential":"c"}`;

  it("still decodes a real string join_code", () => {
    expect(() => decodeCreateTableResponse(parseWireJson(joinBody('"ABC123"')))).not.toThrow();
  });

  for (const literal of ["1.5", "10.0", "1e3", "-2.5", "7", "true", "null", "[]", "{}"]) {
    it(`rejects ${literal} where join_code must be a string`, () => {
      expect(() => decodeCreateTableResponse(parseWireJson(joinBody(literal)))).toThrow(
        ProtocolDecodeError,
      );
    });
  }

  it("rejects a float where a string is required in a server message", () => {
    const raw = readFixtureJson<Record<string, unknown>>(
      "messages/server/snapshot.connected.not_started.json",
    );
    const text = JSON.stringify(raw).replace(/"join_code":"[^"]*"/, '"join_code":1.5');
    expect(text).toContain('"join_code":1.5');
    expect(() => decodeServerMessage(parseWireJson(text))).toThrow(ProtocolDecodeError);
  });
});
