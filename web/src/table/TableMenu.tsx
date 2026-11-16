import { useEffect, useId, useRef, useState } from "react";
import styles from "./TableMenu.module.css";

export interface TableMenuProps {
  /** Whether Leave can be requested now (live, nothing in flight). */
  leaveAvailable: boolean;
  /** A leave is already pending: it has no cancel. */
  leavePending: boolean;
  /** Opens the Leave confirmation; `restoreFocus` returns focus here once it
   * closes. */
  onLeaveRequested: (restoreFocus: () => void) => void;
}

/**
 * The secondary table menu (D4): a disclosure button with a small panel, not
 * an ARIA `menu`. Esc and a click outside close it.
 */
export function TableMenu({ leaveAvailable, leavePending, onLeaveRequested }: TableMenuProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: Esc closes the disclosure from either of its controls
    <div
      ref={root}
      className={styles.menu}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          setOpen(false);
          trigger.current?.focus();
        }
      }}
    >
      <button
        ref={trigger}
        type="button"
        className={styles.trigger}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        Table <span aria-hidden="true">▾</span>
      </button>
      <div id={panelId} className={styles.panel} hidden={!open}>
        <button
          type="button"
          className={styles.item}
          disabled={leavePending || !leaveAvailable}
          onClick={() => {
            setOpen(false);
            onLeaveRequested(() => trigger.current?.focus());
          }}
        >
          {leavePending ? "Leave pending" : "Leave table…"}
        </button>
      </div>
    </div>
  );
}
