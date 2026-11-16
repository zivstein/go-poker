import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  FOLD_CONFIRM_WINDOW_MS,
  GUARD_MS,
  useArrivalGuard,
  useFoldConfirm,
} from "./useDecisionGuard";

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("useArrivalGuard", () => {
  it("uses the provisional 350 ms value", () => {
    expect(GUARD_MS).toBe(350);
  });

  it("is armed from the first render of a decision and releases after the guard", () => {
    const { result } = renderHook(() => useArrivalGuard("rev-4"));
    expect(result.current).toBe(true);
    act(() => vi.advanceTimersByTime(349));
    expect(result.current).toBe(true);
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe(false);
  });

  it("is not armed when there is no actionable decision", () => {
    const { result } = renderHook(() => useArrivalGuard(null));
    expect(result.current).toBe(false);
  });

  it("re-arms for a new decision, in the same render that shows it", () => {
    const { result, rerender } = renderHook(({ key }) => useArrivalGuard(key), {
      initialProps: { key: "rev-4" as string | null },
    });
    act(() => vi.advanceTimersByTime(GUARD_MS));
    expect(result.current).toBe(false);
    rerender({ key: "rev-6" });
    expect(result.current).toBe(true);
    act(() => vi.advanceTimersByTime(GUARD_MS));
    expect(result.current).toBe(false);
  });

  it("re-arms when the same decision becomes actionable again after a reconnect", () => {
    const { result, rerender } = renderHook(({ key }) => useArrivalGuard(key), {
      initialProps: { key: "rev-4" as string | null },
    });
    act(() => vi.advanceTimersByTime(GUARD_MS));
    rerender({ key: null }); // reconnecting
    expect(result.current).toBe(false);
    rerender({ key: "rev-4" }); // live again, same decision
    expect(result.current).toBe(true);
  });

  it("does not re-arm while the decision stays the same (a pending command, a rejection)", () => {
    const { result, rerender } = renderHook(({ key }) => useArrivalGuard(key), {
      initialProps: { key: "rev-4" as string | null },
    });
    act(() => vi.advanceTimersByTime(GUARD_MS));
    rerender({ key: "rev-4" });
    expect(result.current).toBe(false);
  });

  it("can be turned off with a zero guard", () => {
    const { result } = renderHook(() => useArrivalGuard("rev-4", 0));
    expect(result.current).toBe(false);
  });
});

describe("useFoldConfirm", () => {
  it("arms, becomes ready only after the guard, and lapses with no command", () => {
    const { result } = renderHook(() => useFoldConfirm());
    expect(result.current.phase).toBe("idle");
    act(() => result.current.arm());
    expect(result.current.phase).toBe("arming");
    act(() => vi.advanceTimersByTime(GUARD_MS - 1));
    expect(result.current.phase).toBe("arming");
    act(() => vi.advanceTimersByTime(1));
    expect(result.current.phase).toBe("ready");
    act(() => vi.advanceTimersByTime(FOLD_CONFIRM_WINDOW_MS - GUARD_MS));
    expect(result.current.phase).toBe("idle");
  });

  it("disarms at once and leaves no timer behind", () => {
    const { result } = renderHook(() => useFoldConfirm());
    act(() => result.current.arm());
    act(() => result.current.disarm());
    expect(result.current.phase).toBe("idle");
    act(() => vi.advanceTimersByTime(FOLD_CONFIRM_WINDOW_MS));
    expect(result.current.phase).toBe("idle");
  });
});
