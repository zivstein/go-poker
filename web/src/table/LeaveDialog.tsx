import { useEffect, useId, useRef, useState } from "react";
import { Button } from "../ui/Button";
import styles from "./LeaveDialog.module.css";

export interface LeaveDialogProps {
  lines: string[];
  /** Whether a `leave` can be sent right now (live, nothing in flight). It is
   * read again when the player confirms, because it can change while the
   * dialog is open. */
  available: boolean;
  /** Sends the `leave`; returns whether it was actually sent. */
  onConfirm: () => boolean;
  /** The dialog closed, by Stay, Esc or after the leave was sent. */
  onClose: () => void;
}

const UNAVAILABLE_TEXT =
  "Can't leave right now: the connection is paused or another action is in flight. Nothing was sent.";

/**
 * The Leave confirmation (D4): a native modal `<dialog>`. `showModal()` makes
 * the rest of the page inert and puts the dialog in the top layer, so there
 * is no hand-written focus trap. Stay is focused first; Esc (the `cancel`
 * event) counts as Stay.
 *
 * "Leave table" sends at most one `leave`, and only closes the dialog once the
 * connection reports it was sent. A refused send keeps the dialog open with an
 * explicit message, so the player is never left believing they left. The
 * outcome itself still comes only from the server.
 */
export function LeaveDialog({ lines, available, onConfirm, onClose }: LeaveDialogProps) {
  const titleId = useId();
  const bodyId = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const sent = useRef(false);
  const finished = useRef(false);
  const [refused, setRefused] = useState(false);

  useEffect(() => {
    const element = dialog.current;
    if (element === null) return;
    if (!element.open) element.showModal();
    element.querySelector<HTMLButtonElement>("[data-initial-focus]")?.focus();
  }, []);

  // Once the connection is usable again, the earlier refusal no longer applies.
  useEffect(() => {
    if (available) setRefused(false);
  }, [available]);

  // Closes the dialog and tells the owner exactly once. The native `close`
  // event is not relied on for our own closes (Stay, a sent leave): it is
  // queued as a task and was not delivered in a browser smoke test, which left
  // a closed dialog mounted and the next "Leave table…" inert. Esc still
  // arrives through it.
  function finish() {
    if (finished.current) return;
    finished.current = true;
    dialog.current?.close();
    onClose();
  }

  function confirm() {
    if (sent.current) return;
    // Re-checked now, not when the dialog opened. `aria-disabled` rather than
    // `disabled`, so focus never leaves the dialog's buttons.
    if (!available || !onConfirm()) {
      setRefused(true);
      return;
    }
    sent.current = true;
    finish();
  }

  const unavailable = !available || refused;

  return (
    <dialog
      ref={dialog}
      className={styles.dialog}
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      onClose={finish}
    >
      <h2 id={titleId} className={styles.title}>
        Leave this table?
      </h2>
      <div id={bodyId} className={styles.body}>
        {lines.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </div>
      {unavailable && (
        <p role="alert" className={styles.unavailable}>
          {UNAVAILABLE_TEXT}
        </p>
      )}
      <div className={styles.actions}>
        <Button variant="secondary" data-initial-focus onClick={finish}>
          Stay
        </Button>
        <Button variant="destructive" aria-disabled={!available || undefined} onClick={confirm}>
          <span aria-hidden="true">⚠</span>
          Leave table
        </Button>
      </div>
    </dialog>
  );
}
