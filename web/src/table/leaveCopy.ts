/**
 * The Leave confirmation's copy (A1, D4), from the displayed view. It states
 * only documented server behavior (ARCHITECTURE.md, "Intents, leaving and the
 * host"; ADR 0009 §6): a leave during the member's own hand is pending and
 * applied after the hand, with automatic check/fold and muck meanwhile; a
 * pending leave has no cancel. It promises nothing about rejoining.
 */

import type { TableView } from "../protocol/types";

export function leaveCopy(view: TableView): string[] {
  const lines = [`You'll give up seat ${view.you.seat}. Leaving can't be undone or cancelled.`];
  const hand = view.hand;
  const me =
    view.phase === "hand_in_progress" && hand !== null
      ? hand.participants.find((p) => p.seat === view.you.seat)
      : undefined;
  if (hand !== null && me !== undefined) {
    if (hand.turn?.seat === view.you.seat) {
      lines.push(
        hand.turn.kind === "showdown"
          ? "It's your turn to show or muck: leaving now mucks your cards right away."
          : "It's your turn: leaving now checks if you can, otherwise folds, right away.",
      );
    }
    lines.push(
      me.has_live_cards
        ? "Until this hand ends, the table checks or folds for you on your turns and mucks your cards if you're asked to show. You'll leave when the hand ends."
        : "You'll leave when this hand ends.",
    );
  }
  const othersSeated = view.seats.some((s) => s.occupant !== null && s.seat !== view.you.seat);
  if (view.you.is_host && othersSeated) lines.push("The host role passes to another player.");
  return lines;
}
