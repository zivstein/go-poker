/**
 * The one Transport abstraction (C6.2 plan §2.2, §2.6): a browser WebSocket
 * and a scripted mock, and no other abstraction over them.
 */

export interface TransportCloseEvent {
  code: number;
  reason: string;
}

export interface Transport {
  open(url: string): void;
  send(text: string): void;
  /**
   * A client-initiated close. A real transport still reports the resulting
   * close event to the close handler, asynchronously (the uncertain-outcome
   * reconnect relies on it); a close before the connection opened aborts it.
   */
  close(code?: number): void;
  onOpen(handler: () => void): void;
  onMessage(handler: (text: string) => void): void;
  onClose(handler: (event: TransportCloseEvent) => void): void;
}
