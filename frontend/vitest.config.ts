import { defineConfig } from "vitest/config";

// Unit tests for the API client (adapters + the human-review submit sequence).
// Node env + a tiny localStorage shim (src/test/setup.ts) — no DOM needed.
export default defineConfig({
  test: {
    environment: "node",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.ts"],
  },
});
