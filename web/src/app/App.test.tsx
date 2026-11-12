import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { App } from "./App";

test("the placeholder app renders its heading", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "Go! Poker" })).toBeDefined();
});
