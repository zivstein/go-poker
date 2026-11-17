import type { KeyboardEvent } from "react";
import styles from "./BetSizer.module.css";
import type { DraftRange } from "./betDraft";

export interface BetSizerProps {
  range: DraftRange;
  /** The raw text of the exact-amount field (UI-only draft state). */
  draftText: string;
  /** Where the slider's thumb sits: the last committable draft, so invalid
   * text never moves it. */
  sliderValue: number;
  /** Whether the field's text cannot be committed. */
  invalid: boolean;
  disabled: boolean;
  /** The id of the hint describing the range or the draft's problem. */
  hintId: string;
  onDraftText: (text: string) => void;
  onBlur: () => void;
  onMin: () => void;
  onMax: () => void;
  /** Enter in the field: commit the draft, through the dock's guards. */
  onCommit: () => void;
}

/**
 * Amount selection only (D2): Min, the slider, Max and the exact field change
 * the draft and never commit. The commit button stays outside this component.
 * A future preset row (W21, server-provided targets) would sit beside these
 * controls and call `onDraftText`; none is rendered until such targets exist.
 */
export function BetSizer({
  range,
  draftText,
  sliderValue,
  invalid,
  disabled,
  hintId,
  onDraftText,
  onBlur,
  onMin,
  onMax,
  onCommit,
}: BetSizerProps) {
  function handleFieldKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    if (!event.repeat) onCommit();
  }

  return (
    <div className={styles.sizer}>
      <button type="button" className={styles.end} disabled={disabled} onClick={onMin}>
        Min
      </button>
      <input
        type="range"
        className={styles.slider}
        min={range.min}
        max={range.max}
        value={sliderValue}
        disabled={disabled}
        aria-label="Bet amount"
        aria-describedby={hintId}
        onChange={(e) => onDraftText(e.target.value)}
      />
      <button type="button" className={styles.end} disabled={disabled} onClick={onMax}>
        Max
      </button>
      <input
        type="text"
        inputMode="numeric"
        autoComplete="off"
        className={styles.field}
        value={draftText}
        disabled={disabled}
        aria-label="Bet amount (exact)"
        aria-invalid={invalid || undefined}
        aria-describedby={hintId}
        onChange={(e) => onDraftText(e.target.value)}
        onBlur={onBlur}
        onKeyDown={handleFieldKeyDown}
      />
    </div>
  );
}
