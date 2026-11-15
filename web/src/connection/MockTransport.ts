import type { Transport, TransportCloseEvent } from "./Transport";

/**
 * A scripted mock {@link Transport} (C6.2 plan §2.2, §2.6). It never plays a
 * poker engine: a test (or the dev-only mock mode) drives it explicitly by
 * calling `emitOpen`, `emitMessage` and `emitClose`, and reads what was sent
 * through `sentFrames`.
 */
export class MockTransport implements Transport {
  readonly openedUrls: string[] = [];
  readonly sentFrames: string[] = [];
  readonly closedCodes: (number | undefined)[] = [];

  private messageHandler: ((text: string) => void) | null = null;
  private openHandler: (() => void) | null = null;
  private closeHandler: ((event: TransportCloseEvent) => void) | null = null;

  open(url: string): void {
    this.openedUrls.push(url);
  }

  send(text: string): void {
    this.sentFrames.push(text);
  }

  close(code?: number): void {
    this.closedCodes.push(code);
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

  emitOpen(): void {
    this.openHandler?.();
  }

  emitMessage(message: unknown): void {
    this.messageHandler?.(JSON.stringify(message));
  }

  emitRawMessage(text: string): void {
    this.messageHandler?.(text);
  }

  emitClose(code: number, reason = ""): void {
    this.closeHandler?.({ code, reason });
  }

  /** The most recent frame sent, parsed. */
  lastSent<T = unknown>(): T {
    const frame = this.sentFrames[this.sentFrames.length - 1];
    if (frame === undefined) throw new Error("no frame was sent");
    return JSON.parse(frame) as T;
  }
}
