import { defineConfig, devices } from '@playwright/test';
import { readFileSync, existsSync } from 'fs';
import { resolve } from 'path';

// Load .env from parent directory (../dev/.env) for API keys (OpenRouter, etc.)
const envPath = resolve(import.meta.dirname, '..', '.env');
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, 'utf8').split('\n')) {
    const match = line.match(/^([A-Z_]+)=(.+)$/);
    if (match && !process.env[match[1]]) {
      process.env[match[1]] = match[2].trim();
    }
  }
}

/**
 * DeckSage E2E test configuration.
 *
 * Expects the API server running at BASE_URL (default 127.0.0.1:8001).
 * VLM tests require an API key (OPENROUTER_API_KEY, GEMINI_API_KEY, etc.)
 * — auto-loaded from ../dev/.env if present.
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
