import type { ConnectionStatus } from "../connection/ConnectionController";
import { formatMoney } from "../format/money";
import type { ActArgs, ShowdownDecision, TableView } from "../protocol/types";
import type { LastRejection } from "../session/store";
import { ActionDock } from "./ActionDock";
import { dockConnection } from "./dockState";
import { StatusLayer } from "./StatusLayer";
import { TableHeader } from "./TableHeader";
import styles from "./TableScreen.module.css";
import { TableStage } from "./TableStage";

export interface TableScreenProps {
  view: TableView;
  /** Hand-boundary snapshots received so far (part of the decision identity). */
  handEpoch?: number;
  status: ConnectionStatus;
  lastRejection: LastRejection | null;
  wasLeaving: boolean;
  /** Each returns whether the command was actually sent. */
  onAct: (args: ActArgs) => boolean;
  onShowdownDecision: (decision: ShowdownDecision) => boolean;
  onStartGame: () => boolean;
  onLeave: () => boolean;
  onDismissRejection: () => void;
  onUseHere: () => void;
  onBackToEntry: () => void;
}

function turnAnnouncement(view: TableView, live: boolean): string {
  const legal = view.hand?.legal_actions ?? null;
  if (!live) return "";
  if (legal !== null) {
    return legal.can_call
      ? `Your turn. To call ${formatMoney(legal.call_amount)}.`
      : "Your turn to act.";
  }
  if (view.hand?.showdown_actions) return "Your turn: show or muck.";
  return "";
}

/** The functional table (C6.2 plan §3.2). Presentational: it takes the
 * displayed frame as props and never reads a raw message. */
export function TableScreen({
  view,
  handEpoch,
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
  const connection = dockConnection(status);
  const live = connection === "live";

  return (
    <div className={styles.screen}>
      {/* A polite live region announcing the hero's turn (C6.2 plan §4.6). */}
      <div className="sr-only" aria-live="polite">
        {turnAnnouncement(view, live)}
      </div>
      <TableHeader view={view} status={status} onLeave={onLeave} />
      <div
        className={styles.body}
        data-dimmed={connection === "reconnecting" || connection === "reconciling" || undefined}
      >
        <TableStage view={view} />
      </div>
      <ActionDock
        view={view}
        status={status}
        lastRejection={lastRejection}
        handEpoch={handEpoch}
        onAct={onAct}
        onShowdownDecision={onShowdownDecision}
        onStartGame={onStartGame}
        onDismissRejection={onDismissRejection}
      />
      <StatusLayer
        status={status}
        wasLeaving={wasLeaving}
        onUseHere={onUseHere}
        onBackToEntry={onBackToEntry}
      />
    </div>
  );
}
