/** Shared view builders for the Action Dock tests (fixtures from ADR 0009). */

import type { ConnectionStatus } from "../connection/ConnectionController";
import type { LegalActions, TableView } from "../protocol/types";
import { readFixtureJson } from "../testing/fixtures";

export const LIVE: ConnectionStatus = {
  phase: "live",
  pending: false,
  reconciling: false,
  attempt: 0,
  reason: null,
};

export function fixtureView(fixture: string): TableView {
  return readFixtureJson<{ view: TableView }>(`messages/server/${fixture}`).view;
}

/** snapshot.heads_up.preflop.actor: call $5, raise range 20 .. 1,000. */
export function actorView(): TableView {
  return fixtureView("snapshot.heads_up.preflop.actor.json");
}

function decision(v: TableView) {
  const hand = v.hand;
  if (hand === null || hand.legal_actions === null) throw new Error("fixture has no decision");
  return { hand, legal: hand.legal_actions };
}

/** The same decision with different legal actions (and the same log). */
export function withLegal(v: TableView, patch: Partial<LegalActions>): TableView {
  const { hand, legal } = decision(v);
  return { ...v, hand: { ...hand, legal_actions: { ...legal, ...patch } } };
}

/** The actor's decision with Check free (the big blind's option). */
export function checkFreeView(): TableView {
  return withLegal(actorView(), {
    can_check: true,
    can_call: false,
    amount_owed: 0,
    call_amount: 0,
  });
}

/**
 * The hero's NEXT decision in the same hand, with legal actions identical to
 * this one: an action was logged in between, as it always is.
 */
export function laterDecision(v: TableView): TableView {
  const { hand } = decision(v);
  return {
    ...v,
    hand: {
      ...hand,
      log: [
        ...hand.log,
        {
          event: "action_taken",
          seat: v.you.seat,
          action: "call",
          target: null,
          chips: 5,
          all_in: false,
        },
      ],
    },
  };
}

/** A shared transition that does not change the hero's decision (a host
 * change): a new revision, the same decision. */
export function unrelatedTransition(v: TableView): TableView {
  return { ...v, you: { ...v.you, is_host: !v.you.is_host } };
}
