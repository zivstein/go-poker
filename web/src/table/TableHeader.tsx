import { useState } from "react";
import type { ConnectionStatus } from "../connection/ConnectionController";
import type { Settings } from "../protocol/types";
import { Button } from "../ui/Button";
import { ProductLogo } from "../ui/ProductLogo";
import styles from "./TableHeader.module.css";

export interface TableHeaderProps {
  settings: Settings;
  joinCode: string;
  status: ConnectionStatus;
  onLeave: () => void;
}

function connectionLabel(status: ConnectionStatus): string {
  if (status.phase === "live") return status.reconciling ? "Reconnecting…" : "Connected";
  if (status.phase === "reconnecting") return "Reconnecting…";
  if (status.phase === "connecting") return "Connecting…";
  return "Disconnected";
}

export function TableHeader({ settings, joinCode, status, onLeave }: TableHeaderProps) {
  const [copied, setCopied] = useState(false);

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
      <Button variant="neutral" onClick={onLeave}>
        Leave
      </Button>
    </header>
  );
}
