import { defineConfig, devices } from "@playwright/test"

/**
 * Playwright configuration for E2E integration tests.
 *
 * Tests authenticate via Cognito and interact with the live deployed frontend
 * to validate the full chat session management flow.
 */
export default defineConfig({
  testDir: "./src/test/e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: false, // Sequential to avoid rate limiting on auth
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 1,

  reporter: "html",

  use: {
    baseURL: process.env.BASE_URL || "https://main.d3de0r2ujefnqj.amplifyapp.com",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: undefined, // Tests run against deployed app, not local dev server

  timeout: 30 * 1000,
  expect: { timeout: 5 * 1000 },
})
