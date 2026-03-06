import { defineConfig, devices } from '@playwright/test';

/**
 * DeckSage E2E test configuration.
 *
 * Expects the API server running at BASE_URL (default localhost:8001)
 * and the frontend served from frontend/test_search.html.
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,  // sequential — tests share server state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 30_000,

  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8001',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
