import { useRef, useState } from "react";
import type { ConnectionStatus } from "../connection/ConnectionController";
import type { TableView } from "../protocol/types";
import { Button } from "../ui/Button";
import { ProductLogo } from "../ui/ProductLogo";
import { dockConnection } from "./dockState";
import { LeaveDialog } from "./LeaveDialog";
import { leaveCopy } from "./leaveCopy";
import styles from "./TableHeader.module.css";
import { TableMenu } from "./TableMenu";

export interface TableHeaderProps {
  view: TableView;
  status: ConnectionStatus;
  /** Whether the `leave` command was actually sent. */
  onLeave: () => boolean;
}

function connectionLabel(status: ConnectionStatus): string {
  if (status.phase === "live") return status.reconciling ? "Reconnecting…" : "Connected";
  if (status.phase === "reconnecting") return "Reconnecting…";
  if (status.phase === "connecting") return "Connecting…";
  return "Disconnected";
}

export function TableHeader({ view, status, onLeave }: TableHeaderProps) {
  const { settings, join_code: joinCode } = view;
  const [copied, setCopied] = useState(false);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const restoreFocus = useRef<(() => void) | null>(null);
  const leaveAvailable = dockConnection(status) === "live" && !status.pending;

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(joinCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can fail silently (permissions, insecure context); no poker state is affected.
    }
  }

  return (
    <header className={styles.header}>
      <ProductLogo variant="compact" />
      <div className={styles.info}>
        <span>
          {settings.variant === "texas_holdem" ? "Texas Hold'em" : settings.variant} ·{" "}
          {settings.betting_structure === "no_limit" ? "No-Limit" : settings.betting_structure}
        </span>
        <span>
          ${settings.small_blind}/${settings.big_blind}
        </span>
        <span>Seats: {settings.max_seats}</span>
      </div>
      <div className={styles.code}>
        <span>Code: {joinCode}</span>
        <Button variant="neutral" onClick={copyCode}>
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <div className={styles.status} data-phase={status.phase}>
        {connectionLabel(status)}
      </div>
      {view.you.pending_leave && <span className={styles.leaving}>Leaving after this hand</span>}
      <TableMenu
        leaveAvailable={leaveAvailable}
        leavePending={view.you.pending_leave}
        onLeaveRequested={(restore) => {
          restoreFocus.current = restore;
          setLeaveOpen(true);
        }}
      />
      {leaveOpen && (
        <LeaveDialog
          lines={leaveCopy(view)}
          available={leaveAvailable}
          onConfirm={onLeave}
          onClose={() => {
            setLeaveOpen(false);
            restoreFocus.current?.();
          }}
        />
      )}
    </header>
  );
}
