/** Card names and glyphs from the ADR 0009 §3 two-character encoding. */

const RANK_NAMES: Record<string, string> = {
  "2": "Two",
  "3": "Three",
  "4": "Four",
  "5": "Five",
  "6": "Six",
  "7": "Seven",
  "8": "Eight",
  "9": "Nine",
  T: "Ten",
  J: "Jack",
  Q: "Queen",
  K: "King",
  A: "Ace",
};

const SUIT_NAMES: Record<string, string> = {
  c: "clubs",
  d: "diamonds",
  h: "hearts",
  s: "spades",
};

const SUIT_SYMBOLS: Record<string, string> = {
  c: "♣",
  d: "♦",
  h: "♥",
  s: "♠",
};

export function cardRank(card: string): string {
  return card.charAt(0);
}

export function cardSuit(card: string): string {
  return card.charAt(1);
}

/** The two-color deck: red for diamonds and hearts, black otherwise (W23). */
export function cardColor(card: string): "red" | "black" {
  const suit = cardSuit(card);
  return suit === "d" || suit === "h" ? "red" : "black";
}

/** The rank as printed on the card face: "10" for "T", else itself. */
export function cardRankLabel(card: string): string {
  const rank = cardRank(card);
  return rank === "T" ? "10" : rank;
}

export function cardSuitSymbol(card: string): string {
  return SUIT_SYMBOLS[cardSuit(card)] ?? "";
}

/** An accessible name, for example "Ace of spades" (W23). */
export function cardAccessibleName(card: string): string {
  const rankName = RANK_NAMES[cardRank(card)] ?? cardRank(card);
  const suitName = SUIT_NAMES[cardSuit(card)] ?? cardSuit(card);
  return `${rankName} of ${suitName}`;
}
