/**
 * The displayed frame and queue (C6.2 plan §2.3 rule 6): presentation may
 * lag the authoritative store, never leads it, never reorders or alters
 * content. Whenever the latest snapshot gives the hero a decision, or on a
 * reconnect / revision gap, presentation fast-forwards (jumps) to that
 * snapshot at once, skipping any remaining animation.
 *
 * This module has no React and no DOM dependency; it holds data only.
 */

import type { SnapshotCause, TableView } from "../protocol/types";

export interface IncomingFrame {
  revision: number;
  cause: SnapshotCause;
  view: TableView;
}

export interface DisplayedFrame extends IncomingFrame {
  /** How many `hand_boundary` and `resume` snapshots this queue has received
   * up to this frame (ADR 0009 §6: a new hand is recognized from the cause and
   * the log). Part of the hero's decision identity. It counts received
   * snapshots, not displayed ones, so a fast-forward never hides a boundary. */
  handEpoch: number;
}

/** `legal_actions`/`showdown_actions` are set only in the decider's own view. */
export function heroHasDecision(view: TableView): boolean {
  const hand = view.hand;
  if (hand === null) return false;
  return hand.legal_actions !== null || hand.showdown_actions !== null;
}

export class PresentationQueue {
  private readonly holdMs: number;
  private queue: DisplayedFrame[] = [];
  private displayed: DisplayedFrame | null = null;
  private animating = false;
  private handEpoch = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private readonly listeners = new Set<() => void>();

  constructor(holdMs = 0) {
    this.holdMs = holdMs;
  }

  // A bound property, like `subscribe`: both are passed directly to
  // `useSyncExternalStore`, which calls them with no `this`.
  getDisplayed = (): DisplayedFrame | null => {
    return this.displayed;
  };

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  push(incoming: IncomingFrame): void {
    if (incoming.cause === "hand_boundary" || incoming.cause === "resume") this.handEpoch += 1;
    const frame: DisplayedFrame = { ...incoming, handEpoch: this.handEpoch };
    const isJump =
      this.displayed === null ||
      frame.cause === "connected" ||
      frame.revision > this.displayed.revision + 1 ||
      frame.revision < this.displayed.revision;
    if (isJump || heroHasDecision(frame.view)) {
      this.clearTimer();
      this.queue = [];
      this.animating = false;
      this.setDisplayed(frame);
      return;
    }
    this.queue.push(frame);
    this.drain();
  }

  private drain(): void {
    if (this.animating) return;
    const next = this.queue.shift();
    if (next === undefined) return;
    this.animating = true;
    this.setDisplayed(next);
    if (this.holdMs <= 0) {
      this.animating = false;
      this.drain();
      return;
    }
    this.timer = setTimeout(() => {
      this.animating = false;
      this.drain();
    }, this.holdMs);
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private setDisplayed(frame: DisplayedFrame): void {
    this.displayed = frame;
    this.listeners.forEach((listener) => {
      listener();
    });
  }
}
