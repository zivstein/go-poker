import type { ReactNode } from "react";
import type { ConnectionStatus } from "../connection/ConnectionController";
import type { LastRejection } from "../session/store";
import { Button } from "../ui/Button";
import { isQuietRejection, rejectionText } from "./rejectionText";
import styles from "./StatusLayer.module.css";

export interface StatusLayerProps {
  status: ConnectionStatus;
  lastRejection: LastRejection | null;
  wasLeaving: boolean;
  onDismissRejection: () => void;
  onUseHere: () => void;
  onBackToEntry: () => void;
}

function TerminalScreen({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className={styles.terminal}>
      <p>{title}</p>
      {action}
    </div>
  );
}

export function StatusLayer({
  status,
  lastRejection,
  wasLeaving,
  onDismissRejection,
  onUseHere,
  onBackToEntry,
}: StatusLayerProps) {
  if (status.phase === "closed") {
    switch (status.reason) {
      case "protocol_mismatch":
        return <TerminalScreen title="Please reload." />;
      case "superseded":
        return (
          <TerminalScreen
            title="This table is open in another window."
            action={
              <Button variant="primary" onClick={onUseHere}>
                Use here
              </Button>
            }
          />
        );
      case "auth_failed":
        return (
          <TerminalScreen
            title={wasLeaving ? "You left the table." : "Your session ended."}
            action={
              <Button variant="primary" onClick={onBackToEntry}>
                Back to entry
              </Button>
            }
          />
        );
      case "left_table":
        return (
          <TerminalScreen
            title="You left the table."
            action={
              <Button variant="primary" onClick={onBackToEntry}>
                Back to entry
              </Button>
            }
          />
        );
      case "table_failed":
        return (
          <TerminalScreen
            title="This table has failed."
            action={
              <Button variant="primary" onClick={onBackToEntry}>
                Back to entry
              </Button>
            }
          />
        );
      default:
        return <TerminalScreen title="Disconnected." />;
    }
  }

  return (
    <div className={styles.layer}>
      {(status.phase === "reconnecting" || status.phase === "connecting") && (
        <div className={styles.banner} role="status">
          Reconnecting…
        </div>
      )}
      {status.reconciling && status.phase === "live" && (
        <div className={styles.banner} role="status">
          No response — reconnecting
        </div>
      )}
      {lastRejection && (
        <div
          className={isQuietRejection(lastRejection.code) ? styles.quiet : styles.toast}
          role={isQuietRejection(lastRejection.code) ? "status" : "alert"}
        >
          {rejectionText(lastRejection.code)}
          <button
            type="button"
            className={styles.dismiss}
            onClick={onDismissRejection}
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
