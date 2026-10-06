import { defineConfig } from "@playwright/test";

// E2E_BASE_URL points the suite at an already-running server (e.g. the
// production build used by the full-stack test); otherwise we use the dev server.
const external = process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: external ?? "http://localhost:3000" },
  webServer: external
    ? undefined
    : {
        command: "npm run dev",
        url: "http://localhost:3000",
        reuseExistingServer: true,
      },
});
