import type { KeyboardEvent, ReactNode } from "react";
import styles from "./ActionDock.module.css";

/** The stable identity of a dock control (A1 review, M3): what the pending
 * state and the busy marker follow, never a visible label that can change. */
export type DockActionId = "fold" | "check" | "call" | "commit" | "show" | "muck" | "start_game";

/** The control whose command is in flight. */
export interface PressedAction {
  id: DockActionId;
  /** Names the command in the status line: "Sending {text}…". */
  text: string;
  /** The control's label while the command is in flight, so it never reverts
   * (a confirmed Fold keeps reading "Confirm fold"). */
  label: string;
}

/** The status line's candidates, strongest first (see {@link pickStatus}). */
export interface StatusParts {
  /** Reconnecting or an uncertain outcome. */
  connection: ReactNode | null;
  /** A command is in flight. */
  sending: ReactNode | null;
  /** The last rejection, until dismissed or superseded. */
  rejection: ReactNode | null;
  /** The mode's own text. */
  mode: ReactNode;
}

/** One status line: the connection outranks everything; an armed-Fold
 * explanation outranks the rest (the player just asked for it); a command in
 * flight outranks an older rejection. */
export function pickStatus(parts: StatusParts, warning: ReactNode | null = null): ReactNode {
  return parts.connection ?? warning ?? parts.sending ?? parts.rejection ?? parts.mode;
}

export interface DockRowsProps {
  statusId: string;
  status: ReactNode;
  aside?: ReactNode;
  /** Bottom-row controls; the row keeps its height when there are none. */
  controls?: ReactNode;
  /** The bottom row's accessible group name, when it holds decision controls. */
  controlsLabel?: string;
  onControlsKeyDown?: (event: KeyboardEvent<HTMLDivElement>) => void;
}

/** A held Enter or Space never repeats an activation, on any dock control. */
function guardHeldKeys(
  event: KeyboardEvent<HTMLDivElement>,
  onKeyDown: DockRowsProps["onControlsKeyDown"],
) {
  if (event.repeat && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    return;
  }
  onKeyDown?.(event);
}

/** The dock's fixed two rows (A1, Option B): status and hints on top,
 * controls below. Every dock state renders through it, so its geometry never
 * changes between states. */
export function DockRows({
  statusId,
  status,
  aside,
  controls,
  controlsLabel,
  onControlsKeyDown,
}: DockRowsProps) {
  return (
    <>
      <div className={styles.topRow}>
        <div className={styles.status} id={statusId}>
          {status}
        </div>
        {aside !== undefined && aside !== null && <div className={styles.aside}>{aside}</div>}
      </div>
      {controlsLabel !== undefined ? (
        // biome-ignore lint/a11y/useSemanticElements: an action group is not a form fieldset
        <div
          className={styles.controls}
          role="group"
          aria-label={controlsLabel}
          onKeyDown={(event) => guardHeldKeys(event, onControlsKeyDown)}
        >
          {controls}
        </div>
      ) : (
        // biome-ignore lint/a11y/noStaticElementInteractions: only cancels a held key's repeat
        <div
          className={styles.controls}
          onKeyDown={(event) => guardHeldKeys(event, onControlsKeyDown)}
        >
          {controls}
        </div>
      )}
    </>
  );
}
