import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readCredential, readStoredSession } from "./credentialStorage";
import { EntryScreen } from "./EntryScreen";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

function mockFetchOnce(status: number, body: unknown) {
  vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
    new Response(JSON.stringify(body), { status }),
  );
}

describe("EntryScreen", () => {
  it("creates a table and stores the credential, keyed by table_id", async () => {
    mockFetchOnce(201, {
      table_id: "table-1",
      join_code: "ABCDEF",
      seat: 1,
      credential: "cred-1",
    });
    const onEnter = vi.fn();
    render(<EntryScreen onEnter={onEnter} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Your name", { selector: "#create-name" }), "Alice");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(onEnter).toHaveBeenCalledWith("table-1", "cred-1");
    expect(readCredential("table-1")).toBe("cred-1");
    expect(readStoredSession()).toEqual({ tableId: "table-1", credential: "cred-1" });
  });

  it("joins a table and records it as the tab's current table", async () => {
    mockFetchOnce(201, {
      table_id: "table-2",
      seat: 3,
      credential: "cred-2",
    });
    const onEnter = vi.fn();
    render(<EntryScreen onEnter={onEnter} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Table code"), "K7Q2XM");
    await user.type(screen.getByLabelText("Your name", { selector: "#join-name" }), "Bob");
    await user.click(screen.getByRole("button", { name: "Join" }));
    expect(onEnter).toHaveBeenCalledWith("table-2", "cred-2");
    expect(readCredential("table-2")).toBe("cred-2");
    expect(readStoredSession()).toEqual({ tableId: "table-2", credential: "cred-2" });
  });

  it("shows a seat field error on SEAT_TAKEN, without storing a credential", async () => {
    mockFetchOnce(409, {
      error: { code: "SEAT_TAKEN", message: "This seat is already occupied", field: "seat" },
    });
    const onEnter = vi.fn();
    render(<EntryScreen onEnter={onEnter} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Table code"), "K7Q2XM");
    await user.type(screen.getByLabelText("Your name", { selector: "#join-name" }), "Bob");
    await user.click(screen.getByRole("button", { name: "Join" }));
    expect(await screen.findByText("This seat is already occupied")).toBeDefined();
    expect(onEnter).not.toHaveBeenCalled();
  });
});
