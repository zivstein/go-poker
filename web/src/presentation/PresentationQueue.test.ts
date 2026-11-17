import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TableView } from "../protocol/types";
import { readFixtureJson } from "../testing/fixtures";
import { heroHasDecision, PresentationQueue } from "./PresentationQueue";

function view(fixture: string): TableView {
  return readFixtureJson<{ view: TableView }>(`messages/server/${fixture}`).view;
}

const waiting = view("snapshot.connected.not_started.json");
const actorTurn = view("snapshot.heads_up.preflop.actor.json"); // the hero must act
const waitingViewer = view("snapshot.heads_up.preflop.waiting.json"); // not the hero's turn

describe("heroHasDecision", () => {
  it("is true only when legal_actions or showdown_actions is set", () => {
    expect(heroHasDecision(actorTurn)).toBe(true);
    expect(heroHasDecision(waitingViewer)).toBe(false);
    expect(heroHasDecision(waiting)).toBe(false);
  });
});

describe("PresentationQueue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("displays the first frame immediately", () => {
    const queue = new PresentationQueue(1000);
    queue.push({ revision: 1, cause: "connected", view: waiting });
    expect(queue.getDisplayed()?.revision).toBe(1);
  });

  it("holds a queued frame for holdMs before advancing to the next", () => {
    const queue = new PresentationQueue(1000);
    queue.push({ revision: 1, cause: "connected", view: waiting });
    queue.push({ revision: 2, cause: "command", view: waitingViewer });
    queue.push({ revision: 3, cause: "command", view: waitingViewer });
    expect(queue.getDisplayed()?.revision).toBe(2); // the first queued frame shows at once
    vi.advanceTimersByTime(999);
    expect(queue.getDisplayed()?.revision).toBe(2);
    vi.advanceTimersByTime(1);
    expect(queue.getDisplayed()?.revision).toBe(3);
  });

  it("fast-forwards to a frame that gives the hero a decision, skipping the queue", () => {
    const queue = new PresentationQueue(1000);
    queue.push({ revision: 1, cause: "connected", view: waiting });
    queue.push({ revision: 2, cause: "command", view: waitingViewer });
    queue.push({ revision: 3, cause: "command", view: actorTurn });
    expect(queue.getDisplayed()?.revision).toBe(3);
    // The queued (revision 2) frame was discarded, not merely sped through.
    vi.advanceTimersByTime(10_000);
    expect(queue.getDisplayed()?.revision).toBe(3);
  });

  it("jumps with no animation on reconnect (a `connected` cause)", () => {
    const queue = new PresentationQueue(1000);
    queue.push({ revision: 1, cause: "connected", view: waiting });
    queue.push({ revision: 2, cause: "command", view: waitingViewer });
    queue.push({ revision: 9, cause: "connected", view: waitingViewer });
    expect(queue.getDisplayed()?.revision).toBe(9);
  });

  it("jumps with no animation on a revision gap", () => {
    const queue = new PresentationQueue(1000);
    queue.push({ revision: 1, cause: "connected", view: waiting });
    queue.push({ revision: 5, cause: "hand_boundary", view: waitingViewer });
    expect(queue.getDisplayed()?.revision).toBe(5);
  });

  it("never reorders queued content", () => {
    const queue = new PresentationQueue(1000);
    queue.push({ revision: 1, cause: "connected", view: waiting });
    queue.push({ revision: 2, cause: "command", view: waitingViewer });
    queue.push({ revision: 3, cause: "command", view: waitingViewer });
    const seen = [queue.getDisplayed()?.revision];
    vi.advanceTimersByTime(1000);
    seen.push(queue.getDisplayed()?.revision);
    vi.advanceTimersByTime(1000);
    seen.push(queue.getDisplayed()?.revision);
    expect(seen).toEqual([2, 3, 3]);
  });
});

describe("PresentationQueue hand epoch (decision identity)", () => {
  it("counts hand_boundary and resume snapshots, and nothing else", () => {
    const queue = new PresentationQueue();
    const push = (revision: number, cause: Parameters<PresentationQueue["push"]>[0]["cause"]) =>
      queue.push({ revision, cause, view: actorTurn });
    push(1, "connected");
    expect(queue.getDisplayed()?.handEpoch).toBe(0);
    push(2, "command");
    push(2, "private");
    push(3, "pre_action");
    push(4, "leave_auto_action");
    expect(queue.getDisplayed()?.handEpoch).toBe(0);
    push(5, "hand_boundary");
    expect(queue.getDisplayed()?.handEpoch).toBe(1);
    push(6, "resume");
    expect(queue.getDisplayed()?.handEpoch).toBe(2);
    push(6, "connected"); // a reconnect repeats a revision; it is not a boundary
    expect(queue.getDisplayed()?.handEpoch).toBe(2);
  });

  it("counts a boundary even when presentation fast-forwards past it", () => {
    const queue = new PresentationQueue(1000);
    queue.push({ revision: 1, cause: "connected", view: waitingViewer });
    queue.push({ revision: 2, cause: "command", view: waitingViewer }); // displayed; the hold starts
    queue.push({ revision: 3, cause: "hand_boundary", view: waitingViewer }); // queued, not shown
    expect(queue.getDisplayed()?.revision).toBe(2);
    queue.push({ revision: 4, cause: "command", view: actorTurn }); // the hero's decision: jump
    expect(queue.getDisplayed()?.revision).toBe(4);
    expect(queue.getDisplayed()?.handEpoch).toBe(1);
  });
});
