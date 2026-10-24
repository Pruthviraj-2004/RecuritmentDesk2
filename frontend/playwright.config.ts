import { defineConfig } from "@playwright/test";

// E2E runs against `python -m tests.e2e_server` (port 8001, isolated SQLite, fake Gmail/OAuth) and `vite` on 5173 proxying to it.
// Uses the locally installed Microsoft Edge so no browser download is required; set PW_CHANNEL=chrome to use Chrome instead.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45_000,
  reporter: [["list"]],
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173", channel: process.env.PW_CHANNEL ?? "msedge", trace: "retain-on-failure", screenshot: "only-on-failure", acceptDownloads: true },
});
