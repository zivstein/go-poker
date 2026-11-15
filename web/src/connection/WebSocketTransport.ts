import type { Transport, TransportCloseEvent } from "./Transport";

/** The browser WebSocket implementation of {@link Transport}. */
export class WebSocketTransport implements Transport {
  private socket: WebSocket | null = null;
  private messageHandler: ((text: string) => void) | null = null;
  private openHandler: (() => void) | null = null;
  private closeHandler: ((event: TransportCloseEvent) => void) | null = null;

  open(url: string): void {
    const socket = new WebSocket(url);
    this.socket = socket;
    socket.addEventListener("open", () => {
      this.openHandler?.();
    });
    socket.addEventListener("message", (event) => {
      this.messageHandler?.(String(event.data));
    });
    socket.addEventListener("close", (event) => {
      this.closeHandler?.({ code: event.code, reason: event.reason });
    });
  }

  send(text: string): void {
    this.socket?.send(text);
  }

  close(code?: number): void {
    this.socket?.close(code);
  }

  onOpen(handler: () => void): void {
    this.openHandler = handler;
  }

  onMessage(handler: (text: string) => void): void {
    this.messageHandler = handler;
  }

  onClose(handler: (event: TransportCloseEvent) => void): void {
    this.closeHandler = handler;
  }
}
