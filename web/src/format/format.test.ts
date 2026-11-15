import { describe, expect, it } from "vitest";
import { cardAccessibleName, cardColor, cardRankLabel, cardSuitSymbol } from "./cards";
import { formatMoney } from "./money";

describe("formatMoney", () => {
  it("formats whole dollars with grouping and no cents", () => {
    expect(formatMoney(0)).toBe("$0");
    expect(formatMoney(5)).toBe("$5");
    expect(formatMoney(1250)).toBe("$1,250");
    expect(formatMoney(1463)).toBe("$1,463");
    expect(formatMoney(1_000_000)).toBe("$1,000,000");
  });
});

describe("card formatting", () => {
  it("names cards accessibly", () => {
    expect(cardAccessibleName("As")).toBe("Ace of spades");
    expect(cardAccessibleName("Th")).toBe("Ten of hearts");
    expect(cardAccessibleName("2c")).toBe("Two of clubs");
    expect(cardAccessibleName("Kd")).toBe("King of diamonds");
  });

  it("labels the rank as printed, 10 for T", () => {
    expect(cardRankLabel("Th")).toBe("10");
    expect(cardRankLabel("As")).toBe("A");
    expect(cardRankLabel("7c")).toBe("7");
  });

  it("colors diamonds and hearts red, the rest black", () => {
    expect(cardColor("Ah")).toBe("red");
    expect(cardColor("Ad")).toBe("red");
    expect(cardColor("As")).toBe("black");
    expect(cardColor("Ac")).toBe("black");
  });

  it("gives each suit its symbol", () => {
    expect(cardSuitSymbol("Ah")).toBe("♥");
    expect(cardSuitSymbol("Ad")).toBe("♦");
    expect(cardSuitSymbol("As")).toBe("♠");
    expect(cardSuitSymbol("Ac")).toBe("♣");
  });
});
