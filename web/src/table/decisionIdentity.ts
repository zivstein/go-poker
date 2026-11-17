/**
 * The identity of the hero's current decision (A1 review, M1).
 *
 * The shared table revision is NOT a decision identity: it increments on every
 * shared transition (ADR 0006 §1), including a join, an applied leave, a
 * sit-out or a host change, none of which change what the hero must decide.
 * The identity is built only from what makes a decision a different decision:
 *
 * - the hand: its `number` is display-only and may restart after an engine
 *   generation reset (ADR 0009 §6), so it is combined with the log's own
 *   `hand_started` event, the hero's dealt cards, and `handEpoch`, which counts
 *   the `hand_boundary` and `resume` snapshots this client has received (ADR
 *   0009: "a new hand is recognized from the cause and the log");
 * - the position in the hand: the log is append-only within a hand, and every
 *   action, including the hero's own, appends to it. A later decision with
 *   identical legal actions therefore has a longer log and a different
 *   identity;
 * - the street and the kind of decision (betting or showdown).
 *
 * `legal_actions` is deliberately NOT part of the identity. A change of the
 * legal range for the same decision is revalidated by the betting controls
 * instead (a still-committable draft is kept; anything else restarts at the
 * new default), never silently reinterpreted.
 *
 * Pure, with no React. Returns `null` when the hero has no decision.
 */

import type { LogEvent, TableView } from "../protocol/types";

export function decisionIdentity(view: TableView, handEpoch = 0): string | null {
  const hand = view.hand;
  if (hand === null) return null;
  const kind = hand.legal_actions !== null ? "betting" : hand.showdown_actions ? "showdown" : null;
  if (kind === null) return null;
  const first = (name: LogEvent["event"]) => hand.log.find((e) => e.event === name);
  return [
    handEpoch,
    kind,
    view.you.seat,
    hand.number,
    hand.street,
    hand.log.length,
    JSON.stringify(first("hand_started") ?? null),
    JSON.stringify(first("hole_cards_dealt") ?? null),
  ].join("|");
}
