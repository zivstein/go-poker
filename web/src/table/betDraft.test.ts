import { describe, expect, it } from "vitest";
import { draftHint, normalizeDraftText, parseDraft } from "./betDraft";

const RANGE = { min: 20, max: 1000 };

describe("parseDraft", () => {
  it.each([
    ["20", 20],
    ["21", 21],
    ["150", 150],
    ["999", 999],
    ["1000", 1000],
    ["0150", 150],
    [" 120 ", 120],
  ])("accepts %j as exactly %d", (text, target) => {
    expect(parseDraft(text, RANGE)).toEqual({ kind: "ok", target });
  });

  it.each(["", "   "])("reads %j as empty", (text) => {
    expect(parseDraft(text, RANGE)).toEqual({ kind: "empty" });
  });

  it.each(["-", "-5", "1.5", "0.5", "1e3", "$20", "20 0", "abc"])(
    "reads %j as invalid, never as a guessed amount",
    (text) => {
      expect(parseDraft(text, RANGE)).toEqual({ kind: "invalid" });
    },
  );

  it.each(["0", "007", "3", "19"])("reads %j as below the minimum", (text) => {
    expect(parseDraft(text, RANGE)).toEqual({ kind: "below" });
  });

  it.each(["1001", "5000", "9".repeat(25), "9".repeat(400)])(
    "reads %j as above the maximum, never clamped",
    (text) => {
      expect(parseDraft(text, RANGE)).toEqual({ kind: "above" });
    },
  );

  it("treats a single-value range exactly", () => {
    expect(parseDraft("45", { min: 45, max: 45 })).toEqual({ kind: "ok", target: 45 });
    expect(parseDraft("44", { min: 45, max: 45 })).toEqual({ kind: "below" });
    expect(parseDraft("46", { min: 45, max: 45 })).toEqual({ kind: "above" });
  });
});

describe("normalizeDraftText", () => {
  it("rewrites only the spelling of a committable amount", () => {
    expect(normalizeDraftText("0150", RANGE)).toBe("150");
    expect(normalizeDraftText(" 120 ", RANGE)).toBe("120");
  });

  it.each(["5000", "3", "1.5", "", "-"])("never changes %j, which is not committable", (text) => {
    expect(normalizeDraftText(text, RANGE)).toBe(text);
  });
});

describe("draftHint", () => {
  it("shows the server's range for a committable draft", () => {
    expect(draftHint({ kind: "ok", target: 150 }, RANGE)).toEqual({
      text: "Min $20 · Max $1,000",
      tone: "info",
    });
  });

  it("explains why a draft cannot be committed", () => {
    expect(draftHint({ kind: "empty" }, RANGE)).toEqual({
      text: "Enter an amount from $20 to $1,000",
      tone: "info",
    });
    expect(draftHint({ kind: "invalid" }, RANGE).tone).toBe("error");
    expect(draftHint({ kind: "below" }, RANGE)).toEqual({
      text: "The minimum is $20",
      tone: "error",
    });
    expect(draftHint({ kind: "above" }, RANGE)).toEqual({
      text: "The maximum is $1,000",
      tone: "error",
    });
  });
});
