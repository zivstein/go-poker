import type { ConnectionStatus } from "../connection/ConnectionController";
import type { ActArgs, ShowdownDecision, TableView } from "../protocol/types";
import type { LastRejection } from "../session/store";
import { ActionDock } from "./ActionDock";
import { StatusLayer } from "./StatusLayer";
import { TableHeader } from "./TableHeader";
import styles from "./TableScreen.module.css";
import { TableStage } from "./TableStage";

export interface TableScreenProps {
  view: TableView;
  status: ConnectionStatus;
  lastRejection: LastRejection | null;
  wasLeaving: boolean;
  onAct: (args: ActArgs) => void;
  onShowdownDecision: (decision: ShowdownDecision) => void;
  onStartGame: () => void;
  onLeave: () => void;
  onDismissRejection: () => void;
  onUseHere: () => void;
  onBackToEntry: () => void;
}

/** The functional table (C6.2 plan §3.2). Presentational: it takes the
 * displayed frame as props and never reads a raw message. */
export function TableScreen({
  view,
  status,
  lastRejection,
  wasLeaving,
  onAct,
  onShowdownDecision,
  onStartGame,
  onLeave,
  onDismissRejection,
  onUseHere,
  onBackToEntry,
}: TableScreenProps) {
  const actionsEnabled = status.phase === "live" && !status.reconciling;
  const hand = view.hand;
  const turnAnnouncement =
    actionsEnabled && hand?.legal_actions
      ? "Your turn to act."
      : actionsEnabled && hand?.showdown_actions
        ? "Your turn: show or muck."
        : "";

  return (
    <div className={styles.screen}>
      {/* A polite live region announcing the hero's turn (C6.2 plan §4.6). */}
      <div className="sr-only" aria-live="polite">
        {turnAnnouncement}
      </div>
      <TableHeader
        settings={view.settings}
        joinCode={view.join_code}
        status={status}
        onLeave={onLeave}
      />
      <div className={styles.body}>
        <TableStage view={view} />
      </div>
      <ActionDock
        view={view}
        disabled={!actionsEnabled || status.pending}
        onAct={onAct}
        onShowdownDecision={onShowdownDecision}
        onStartGame={onStartGame}
      />
      <StatusLayer
        status={status}
        lastRejection={lastRejection}
        wasLeaving={wasLeaving}
        onDismissRejection={onDismissRejection}
        onUseHere={onUseHere}
        onBackToEntry={onBackToEntry}
      />
    </div>
  );
}
