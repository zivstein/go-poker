import { afterEach, describe, expect, it, vi } from "vitest";
import { ProtocolDecodeError } from "../protocol/decode";
import { readFixtureJson } from "../testing/fixtures";
import { createTable } from "./createTable";
import { mapHttpError } from "./errors";
import { joinTable, normalizeJoinCode } from "./joinTable";

interface HttpFixture {
  request: { method: string; path: string; body: unknown };
  response: { status: number; body: unknown };
}

function mockFetchFor(fixture: HttpFixture) {
  const spy = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(
      new Response(JSON.stringify(fixture.response.body), { status: fixture.response.status }),
    );
  return spy;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("createTable", () => {
  it("decodes the canonical create response", async () => {
    const fixture = readFixtureJson<HttpFixture>("messages/http/create_table.json");
    const spy = mockFetchFor(fixture);
    const result = await createTable("Alice");
    expect(result).toEqual({ ok: true, data: fixture.response.body });
    expect(spy).toHaveBeenCalledWith("/tables", expect.objectContaining({ method: "POST" }));
  });
});

describe("joinTable", () => {
  it("decodes the canonical join response", async () => {
    const fixture = readFixtureJson<HttpFixture>("messages/http/join_table.json");
    mockFetchFor(fixture);
    const result = await joinTable("k7q2xm", "Bob", 2);
    expect(result).toEqual({ ok: true, data: fixture.response.body });
  });

  it("uppercases and strips whitespace from the join code before sending", async () => {
    const fixture = readFixtureJson<HttpFixture>("messages/http/join_table.json");
    const spy = mockFetchFor(fixture);
    await joinTable(" k7 q2xm ", "Bob", 2);
    expect(spy).toHaveBeenCalledWith("/tables/by-code/K7Q2XM/members", expect.anything());
  });

  it("maps SEAT_TAKEN to a seat field error", async () => {
    const fixture = readFixtureJson<HttpFixture>("messages/http/join_table.error.seat_taken.json");
    mockFetchFor(fixture);
    const result = await joinTable("K7Q2XM", "Bob", 1);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.field).toBe("seat");
  });

  it("maps INVALID_SEAT to a seat field error", async () => {
    const fixture = readFixtureJson<HttpFixture>(
      "messages/http/join_table.error.invalid_seat.json",
    );
    mockFetchFor(fixture);
    const result = await joinTable("K7Q2XM", "Bob", 7);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.field).toBe("seat");
  });

  it("maps DISPLAY_NAME_TAKEN to a display_name field error", async () => {
    const fixture = readFixtureJson<HttpFixture>(
      "messages/http/join_table.error.display_name_taken.json",
    );
    mockFetchFor(fixture);
    const result = await joinTable("K7Q2XM", "ALICE", 2);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.field).toBe("display_name");
  });
});

describe("normalizeJoinCode", () => {
  it("uppercases and strips whitespace", () => {
    expect(normalizeJoinCode(" k7 q2xm ")).toBe("K7Q2XM");
  });
});

describe("mapHttpError", () => {
  it("maps TABLE_NOT_FOUND to the code field", () => {
    const error = mapHttpError({
      error: { code: "TABLE_NOT_FOUND", message: "x", field: null },
    });
    expect(error.field).toBe("code");
  });

  it("maps a null-field VALIDATION_FAILED to the form", () => {
    const error = mapHttpError({
      error: { code: "VALIDATION_FAILED", message: "x", field: null },
    });
    expect(error.field).toBe("form");
  });
});

describe("REST responses keep integer-vs-float literals (ADR 0009 §2)", () => {
  function stubText(status: number, text: string) {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(text, { status }));
  }
  const createBody = (seat: string) =>
    `{"table_id":"t1","join_code":"K7Q2XM","seat":${seat},"credential":"c"}`;
  const joinBody = (seat: string) => `{"table_id":"t1","seat":${seat},"credential":"c"}`;

  it("createTable accepts an integer seat", async () => {
    stubText(201, createBody("1"));
    const result = await createTable("Alice");
    expect(result).toEqual({
      ok: true,
      data: { table_id: "t1", join_code: "K7Q2XM", seat: 1, credential: "c" },
    });
  });

  it("joinTable accepts an integer seat", async () => {
    stubText(201, joinBody("2"));
    const result = await joinTable("k7q2xm", "Bob", 2);
    expect(result).toEqual({ ok: true, data: { table_id: "t1", seat: 2, credential: "c" } });
  });

  for (const literal of ["1.0", "1e0", "2.5"]) {
    it(`createTable rejects "seat": ${literal}`, async () => {
      stubText(201, createBody(literal));
      await expect(createTable("Alice")).rejects.toBeInstanceOf(ProtocolDecodeError);
    });

    it(`joinTable rejects "seat": ${literal}`, async () => {
      stubText(201, joinBody(literal));
      await expect(joinTable("k7q2xm", "Bob", 2)).rejects.toBeInstanceOf(ProtocolDecodeError);
    });
  }

  it("still maps an HTTP error body", async () => {
    stubText(409, '{"error":{"code":"SEAT_TAKEN","message":"taken","field":"seat"}}');
    const result = await joinTable("k7q2xm", "Bob", 2);
    expect(result.ok).toBe(false);
  });
});
