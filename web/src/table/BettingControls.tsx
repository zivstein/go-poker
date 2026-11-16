import { type KeyboardEvent, type ReactNode, useEffect, useId, useState } from "react";
import { formatMoney } from "../format/money";
import type { ActArgs, BettingStructure, LegalActions } from "../protocol/types";
import { Button } from "../ui/Button";
import { betSizerRange, isAllInTarget } from "../variant/toActionOptions";
import styles from "./ActionDock.module.css";
import { BetSizer } from "./BetSizer";
import { type DraftStatus, draftHint, normalizeDraftText, parseDraft } from "./betDraft";
import {
  type DockActionId,
  DockRows,
  type PressedAction,
  pickStatus,
  type StatusParts,
} from "./DockRows";
import { useFoldConfirm } from "./useDecisionGuard";

export interface BettingControlsProps {
  legal: LegalActions;
  structure: BettingStructure;
  statusId: string;
  /** The dock's status candidates; the armed-Fold explanation is slotted in
   * between them (see {@link pickStatus}). */
  status: StatusParts;
  /** Extra aside content from the dock (the pending-leave chip). */
  asideExtra: ReactNode;
  /** The controls cannot act: not live, or a command in flight. These are
   * truly `disabled`. */
  unavailable: boolean;
  /** The turn-arrival guard is running (AM3). Activations are dropped, but the
   * controls stay enabled and focusable (`aria-disabled`), so focus never
   * moves and the decision stays reachable. */
  guarded: boolean;
  /** Commands can be sent on this connection (live, not reconciling). */
  connectionLive: boolean;
  /** The control whose command is in flight, by stable identity. */
  busy: PressedAction | null;
  onSend: (action: PressedAction, args: ActArgs) => boolean;
}

const CONFIRM_FOLD = "Confirm fold";

function callLabel(legal: LegalActions): string {
  const amount = formatMoney(legal.call_amount);
  return legal.call_is_all_in ? `Call ${amount} (All-in)` : `Call ${amount}`;
}

function commitLabel(
  legal: LegalActions,
  structure: BettingStructure,
  target: number | null,
): string {
  if (target === null) return legal.can_bet ? "Bet" : "Raise to";
  if (isAllInTarget(legal, target, structure)) return `All-in ${formatMoney(target)}`;
  return legal.can_bet ? `Bet ${formatMoney(target)}` : `Raise to ${formatMoney(target)}`;
}

/**
 * One betting decision: Fold apart, Check/Call, the sizer (amount selection
 * only) and the commit button. The draft and the Fold confirmation are
 * local UI state of this decision; legality and every bound come from
 * `legal` (server-authoritative). The dock remounts this component for each
 * new decision.
 */
export function BettingControls({
  legal,
  structure,
  statusId,
  status,
  asideExtra,
  unavailable,
  guarded,
  connectionLive,
  busy,
  onSend,
}: BettingControlsProps) {
  const hintId = useId();
  const sizer = betSizerRange(legal);
  const range = sizer ? { min: sizer.min, max: sizer.max } : null;
  const defaultText = String(sizer?.shortAllInTarget ?? sizer?.min ?? 0);
  const rangeKey = sizer ? `${sizer.kind}:${sizer.min}:${sizer.max}:${sizer.shortAllInTarget}` : "";

  // The draft is read against this decision's server range. An equal range
  // keeps it as is. A different range revalidates it (A1 review, M1): a draft
  // that is still committable keeps exactly the amount the player chose (the
  // commit label still shows it); anything else restarts at the new default.
  // Nothing is clamped to a different amount.
  const [draft, setDraft] = useState({ key: rangeKey, text: defaultText, slider: sizer?.min ?? 0 });
  let current = draft;
  if (draft.key !== rangeKey) {
    const kept =
      range !== null && sizer?.shortAllInTarget === null ? parseDraft(draft.text, range) : null;
    current =
      kept?.kind === "ok"
        ? { key: rangeKey, text: draft.text, slider: kept.target }
        : { key: rangeKey, text: defaultText, slider: sizer?.min ?? 0 };
    setDraft(current);
  }

  // The confirmation keeps its own 350 ms minimum, independent of the
  // (injectable) arrival guard, so a double-click can never fold.
  const fold = useFoldConfirm();
  const foldArmed = fold.phase !== "idle";
  const { disarm } = fold;
  useEffect(() => {
    if (!connectionLive) disarm();
  }, [connectionLive, disarm]);

  const draftStatus: DraftStatus | null = range ? parseDraft(current.text, range) : null;
  const shortTarget = sizer?.shortAllInTarget ?? null;
  const commitTarget =
    shortTarget !== null ? shortTarget : draftStatus?.kind === "ok" ? draftStatus.target : null;

  function updateDraft(text: string) {
    disarm();
    const parsed = range ? parseDraft(text, range) : null;
    setDraft((d) => ({
      key: d.key,
      text,
      slider: parsed?.kind === "ok" ? parsed.target : d.slider,
    }));
  }

  // Every activation that could send or arm goes through here: the guard
  // drops it, never defers it.
  const blocked = unavailable || guarded;

  function send(id: DockActionId, text: string, label: string, args: ActArgs): boolean {
    if (blocked) return false;
    return onSend({ id, text, label }, args);
  }

  function handleFold() {
    if (blocked) return;
    if (!legal.can_check) {
      send("fold", "Fold", "Fold", { action: "fold", target: null });
      return;
    }
    // Check is free: the first press arms, a second press after the guard
    // folds (D3). A press while still arming is dropped, never deferred.
    if (fold.phase === "idle") {
      fold.arm();
      return;
    }
    if (fold.phase === "arming") return;
    fold.disarm();
    send("fold", "Fold", CONFIRM_FOLD, { action: "fold", target: null });
  }

  function handleCheckOrCall() {
    if (blocked) return;
    disarm();
    send(
      legal.can_check ? "check" : "call",
      callOrCheck,
      callOrCheck,
      legal.can_check ? { action: "check", target: null } : { action: "call", target: null },
    );
  }

  function handleCommit() {
    if (blocked || sizer === null || commitTarget === null) return;
    disarm();
    const label = commitLabel(legal, structure, commitTarget);
    send("commit", label, label, { action: sizer.kind, target: commitTarget });
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    // (A held Enter or Space is cancelled for every dock control by DockRows.)
    if (event.key !== "Escape") return;
    if (foldArmed) {
      event.preventDefault();
      disarm();
      return;
    }
    if (
      range !== null &&
      event.target instanceof HTMLInputElement &&
      event.target.type === "text"
    ) {
      event.preventDefault();
      setDraft((d) => ({ key: d.key, text: defaultText, slider: sizer?.min ?? d.slider }));
    }
  }

  // The Fold control keeps the label it was pressed with while its command is
  // in flight, so a confirmed fold never reverts to "Fold" under the pointer.
  const foldBusy = busy?.id === "fold";
  const foldLabel = foldBusy ? busy.label : foldArmed ? CONFIRM_FOLD : "Fold";
  const foldConfirming = foldLabel === CONFIRM_FOLD;
  const callOrCheck = legal.can_check ? "Check" : callLabel(legal);
  const commit = commitLabel(legal, structure, commitTarget);
  const hint =
    sizer === null ? null : shortTarget !== null ? (
      <span className={styles.hint} id={hintId}>
        Your only raise: {commit}
      </span>
    ) : range !== null && draftStatus !== null ? (
      <HintText id={hintId} {...draftHint(draftStatus, range)} />
    ) : null;

  const statusLine = pickStatus(
    status,
    foldArmed ? (
      <span className={styles.warning}>
        <span aria-hidden="true">⚠ </span>Check is free. Press Fold again to fold, or Esc to cancel.
      </span>
    ) : null,
  );

  return (
    <DockRows
      statusId={statusId}
      status={statusLine}
      aside={
        hint || asideExtra ? (
          <>
            {hint}
            {asideExtra}
          </>
        ) : null
      }
      controlsLabel="Actions"
      onControlsKeyDown={handleKeyDown}
      controls={
        <>
          {legal.can_fold && (
            <div className={styles.foldSlot}>
              <Button
                variant={foldConfirming ? "destructive" : "neutral"}
                disabled={unavailable}
                aria-disabled={guarded || undefined}
                busy={foldBusy}
                aria-describedby={foldArmed ? statusId : undefined}
                onClick={handleFold}
              >
                {foldConfirming && <span aria-hidden="true">⚠</span>}
                {foldLabel}
              </Button>
            </div>
          )}
          {(legal.can_check || legal.can_call) && (
            <div className={styles.callSlot}>
              <Button
                variant="secondary"
                disabled={unavailable}
                aria-disabled={guarded || undefined}
                busy={busy?.id === "check" || busy?.id === "call"}
                onClick={handleCheckOrCall}
              >
                {callOrCheck}
              </Button>
            </div>
          )}
          {sizer !== null && range !== null && shortTarget === null && (
            <BetSizer
              range={range}
              draftText={current.text}
              sliderValue={current.slider}
              invalid={draftStatus !== null && draftStatus.kind !== "ok"}
              disabled={unavailable}
              hintId={hintId}
              onDraftText={updateDraft}
              onBlur={() => {
                const normalized = normalizeDraftText(current.text, range);
                if (normalized !== current.text) updateDraft(normalized);
              }}
              onMin={() => updateDraft(String(range.min))}
              onMax={() => updateDraft(String(range.max))}
              onCommit={handleCommit}
            />
          )}
          <span className="sr-only" aria-live="polite">
            {foldArmed ? "Check is free. Press Fold again to fold." : ""}
          </span>
          {sizer !== null && (
            <div className={styles.commitSlot}>
              <Button
                variant="primary"
                disabled={unavailable || commitTarget === null}
                aria-disabled={guarded || undefined}
                busy={busy?.id === "commit"}
                onClick={handleCommit}
              >
                {commit}
              </Button>
            </div>
          )}
        </>
      }
    />
  );
}

function HintText({ id, text, tone }: { id: string; text: string; tone: "info" | "error" }) {
  return (
    <span className={tone === "error" ? styles.hintError : styles.hint} id={id}>
      {tone === "error" && <span aria-hidden="true">⚠ </span>}
      {text}
    </span>
  );
}
