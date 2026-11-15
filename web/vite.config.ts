import react from "@vitejs/plugin-react";
import { searchForWorkspaceRoot } from "vite";
import { defineConfig } from "vitest/config";
import { fixtureExclusionCheck } from "./tooling/fixtureExclusionCheck";

// The Backend's dev command, same origin through this proxy (C6.3 plan D5).
const BACKEND_DEV_ORIGIN = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), fixtureExclusionCheck()],
  server: {
    fs: {
      // Exactly this path, for the dev server only (Brief §2 item 9): the
      // dev-only mock mode dynamic-imports scenario fixtures from here.
      allow: [searchForWorkspaceRoot(process.cwd()), "../docs/adr/0009-wire-protocol-v1/"],
    },
    proxy: {
      "/tables": BACKEND_DEV_ORIGIN,
      "/health": BACKEND_DEV_ORIGIN,
      "/ws": { target: BACKEND_DEV_ORIGIN, ws: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/testing/setupTests.ts"],
  },
});
