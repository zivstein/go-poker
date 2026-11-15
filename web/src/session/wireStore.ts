import type { ConnectionController } from "../connection/ConnectionController";
import type { TableStore } from "./store";

/** Wires a {@link ConnectionController}'s events into a {@link TableStore}. */
export function wireStore(store: TableStore, controller: ConnectionController): () => void {
  const unsubStatus = controller.onStatusChange((status) => store.applyStatus(status));
  const unsubSnapshot = controller.onSnapshot((event) => store.applySnapshot(event));
  const unsubOutcome = controller.onOutcome((event) => store.applyOutcome(event));
  return () => {
    unsubStatus();
    unsubSnapshot();
    unsubOutcome();
  };
}
