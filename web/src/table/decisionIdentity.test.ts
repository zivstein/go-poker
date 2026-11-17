import { describe, expect, it } from "vitest";
import { decisionIdentity } from "./decisionIdentity";
import { actorView, fixtureView, laterDecision, unrelatedTransition, withLegal } from "./testViews";

describe("decisionIdentity", () => {
  it("is null when the hero has no decision", () => {
    expect(decisionIdentity(fixtureView("snapshot.heads_up.preflop.waiting.json"))).toBeNull();
    expect(decisionIdentity(fixtureView("snapshot.waiting_for_players.json"))).toBeNull();
    expect(
      decisionIdentity(fixtureView("snapshot.heads_up.settled.opponent_mucked.json")),
    ).toBeNull();
  });

  it("identifies a betting decision and a showdown decision", () => {
    expect(decisionIdentity(actorView())).not.toBeNull();
    expect(
      decisionIdentity(fixtureView("snapshot.heads_up.showdown_decision.json")),
    ).not.toBeNull();
  });

  it("is unchanged by a shared transition that does not change the decision", () => {
    const v = actorView();
    expect(decisionIdentity(unrelatedTransition(v))).toBe(decisionIdentity(v));
    expect(decisionIdentity({ ...v })).toBe(decisionIdentity(v));
  });

  it("is unchanged when only the legal range changes: that is revalidated, not a new decision", () => {
    const v = actorView();
    expect(decisionIdentity(withLegal(v, { max_target: 500, min_full_target: 40 }))).toBe(
      decisionIdentity(v),
    );
  });

  it("is different for a later decision with identical legal actions", () => {
    const v = actorView();
    expect(decisionIdentity(laterDecision(v))).not.toBe(decisionIdentity(v));
    expect(laterDecision(v).hand?.legal_actions).toEqual(v.hand?.legal_actions);
  });

  it("is different for the next hand, even with the same number, log length and cards", () => {
    const v = actorView();
    // A hand-boundary or resume snapshot was received in between.
    expect(decisionIdentity(v, 1)).not.toBe(decisionIdentity(v, 0));
  });

  it("is different when the hand's own start or the hero's cards differ", () => {
    const v = actorView();
    const hand = v.hand;
    if (hand === null) throw new Error("fixture has no hand");
    const otherCards = {
      ...v,
      hand: {
        ...hand,
        log: hand.log.map((e) =>
          e.event === "hole_cards_dealt" ? { ...e, own_cards: ["2c", "7d"] as never } : e,
        ),
      },
    };
    expect(decisionIdentity(otherCards)).not.toBe(decisionIdentity(v));
    const otherNumber = { ...v, hand: { ...hand, number: hand.number + 1 } };
    expect(decisionIdentity(otherNumber)).not.toBe(decisionIdentity(v));
  });
});
