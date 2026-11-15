import { vi } from "vitest";

type Listener = (event: unknown) => void;

const CONNECTING = 0;
const OPEN = 1;
const CLOSING = 2;
const CLOSED = 3;

/**
 * A browser-like `WebSocket` for tests of the real `WebSocketTransport`
 * (unlike `MockTransport`, whose `close()` does nothing):
 *
 * - it opens asynchronously, and a socket closed before it opens never opens;
 * - `close()` really closes it and fires `close` asynchronously (1006 when it
 *   was still connecting, 1005 otherwise, as a browser reports it);
 * - the test plays the server through `serverSend` and `serverClose`.
 *
 * Asynchrony is `setTimeout(0)`, so a test controls it with fake timers.
 */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  /** Replaces the global `WebSocket` and forgets earlier instances. */
  static install(): void {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  }

  /** The sockets that are connecting or open. */
  static live(): FakeWebSocket[] {
    return FakeWebSocket.instances.filter(
      (socket) => socket.readyState === CONNECTING || socket.readyState === OPEN,
    );
  }

  readonly url: string;
  readyState = CONNECTING;
  readonly sent: string[] = [];
  /** Whether the socket ever reached OPEN. */
  everOpened = false;

  private readonly listeners: Record<string, Listener[]> = {};

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
    setTimeout(() => {
      if (this.readyState !== CONNECTING) return; // closed before it opened
      this.readyState = OPEN;
      this.everOpened = true;
      this.dispatch("open", {});
    }, 0);
  }

  addEventListener(type: string, listener: Listener): void {
    const list = this.listeners[type] ?? [];
    list.push(listener);
    this.listeners[type] = list;
  }

  send(text: string): void {
    if (this.readyState !== OPEN)
      throw new Error("FakeWebSocket: send on a socket that is not open");
    this.sent.push(text);
  }

  close(code?: number): void {
    // A browser throws for any code other than 1000 or 3000-4999.
    if (code !== undefined && code !== 1000 && !(code >= 3000 && code <= 4999)) {
      throw new Error(`FakeWebSocket: InvalidAccessError, close code ${code}`);
    }
    if (this.readyState === CLOSING || this.readyState === CLOSED) return;
    const wasConnecting = this.readyState === CONNECTING;
    this.readyState = CLOSING;
    setTimeout(() => {
      this.readyState = CLOSED;
      this.dispatch("close", { code: code ?? (wasConnecting ? 1006 : 1005), reason: "" });
    }, 0);
  }

  /** The server sends a message (only to an open socket). */
  serverSend(message: unknown): void {
    if (this.readyState !== OPEN) return;
    this.dispatch("message", { data: JSON.stringify(message) });
  }

  /** The server (or the network) closes the socket; `close` fires asynchronously. */
  serverClose(code: number): void {
    // Already closing (the client closed first) or closed: a browser fires
    // `close` once, so the server's code is never reported.
    if (this.readyState === CLOSING || this.readyState === CLOSED) return;
    this.readyState = CLOSING;
    setTimeout(() => {
      this.readyState = CLOSED;
      this.dispatch("close", { code, reason: "" });
    }, 0);
  }

  /** The frames the client sent, parsed. */
  sentJson(): Record<string, unknown>[] {
    return this.sent.map((frame) => JSON.parse(frame) as Record<string, unknown>);
  }

  private dispatch(type: string, event: unknown): void {
    for (const listener of this.listeners[type] ?? []) listener(event);
  }
}
