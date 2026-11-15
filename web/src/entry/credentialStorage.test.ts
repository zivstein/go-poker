import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearCredential,
  clearCurrentTable,
  readCredential,
  readStoredSession,
  storeCredential,
  storeSession,
} from "./credentialStorage";

describe("credentialStorage", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("stores and reads a credential keyed by table_id", () => {
    storeCredential("table-1", "cred-1");
    storeCredential("table-2", "cred-2");
    expect(readCredential("table-1")).toBe("cred-1");
    expect(readCredential("table-2")).toBe("cred-2");
  });

  it("returns null for an unknown table", () => {
    expect(readCredential("unknown")).toBeNull();
  });

  it("clears a stored credential", () => {
    storeCredential("table-1", "cred-1");
    clearCredential("table-1");
    expect(readCredential("table-1")).toBeNull();
  });

  it("stores a session: the credential and the tab's current table", () => {
    storeSession("table-1", "cred-1");
    expect(readCredential("table-1")).toBe("cred-1");
    expect(readStoredSession()).toEqual({ tableId: "table-1", credential: "cred-1" });
  });

  it("has no session to resume when nothing was stored", () => {
    expect(readStoredSession()).toBeNull();
  });

  it("has no session to resume for a marker without a credential", () => {
    storeSession("table-1", "cred-1");
    sessionStorage.removeItem("go-poker:credential:table-1");
    expect(readStoredSession()).toBeNull();
  });

  it("forgets the current table when its credential is cleared", () => {
    storeSession("table-1", "cred-1");
    clearCredential("table-1");
    expect(readStoredSession()).toBeNull();
    expect(sessionStorage.getItem("go-poker:current-table")).toBeNull();
  });

  it("keeps the current table when another table's credential is cleared", () => {
    storeCredential("table-old", "cred-old");
    storeSession("table-1", "cred-1");
    clearCredential("table-old");
    expect(readStoredSession()).toEqual({ tableId: "table-1", credential: "cred-1" });
  });

  it("forgets the current table without touching the credential", () => {
    storeSession("table-1", "cred-1");
    clearCurrentTable();
    expect(readStoredSession()).toBeNull();
    expect(readCredential("table-1")).toBe("cred-1");
  });
});

describe("credentialStorage with blocked storage", () => {
  beforeEach(() => {
    const boom = () => {
      throw new DOMException("blocked", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(boom);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(boom);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(boom);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("never throws, and has nothing to read or resume", () => {
    expect(() => storeSession("t", "c")).not.toThrow();
    expect(() => storeCredential("t", "c")).not.toThrow();
    expect(() => clearCredential("t")).not.toThrow();
    expect(() => clearCurrentTable()).not.toThrow();
    expect(readCredential("t")).toBeNull();
    expect(readStoredSession()).toBeNull();
  });
});
