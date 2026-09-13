import { defineConfig } from "@playwright/test";

/**
 * Visual verification config for the Kisan Mitra dashboard (Part A + Part B).
 *
 * Assumes the backend (port 8001) and frontend dev server (port 3000) are
 * ALREADY running - this does not start them, so it can be wired into the
 * same `npm run verify` step as smoke_test.py without double-booting
 * servers. See package.json's `verify` script.
 */
export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
    // Points at the full Chrome build (not the separate "headless shell"
    // binary Playwright normally downloads) - avoids a second large
    // download on this connection; --headless=new keeps it headless.
    launchOptions: {
      executablePath:
        process.env.LOCALAPPDATA +
        "\\ms-playwright\\chromium-1243\\chrome-win64\\chrome.exe",
      args: ["--headless=new"],
    },
  },
});
