import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.PLAYWRIGHT_UI_PORT || 3001);
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "list",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // Always build so new App Router pages (e.g. evidence detail) are included.
    // Use 3001 by default to avoid reusing a stale server on :3000.
    command: `pnpm build && pnpm exec next start -p ${port}`,
    url: `${baseURL}/login`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
