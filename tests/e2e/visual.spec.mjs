// @ts-check
import { test, expect } from '@playwright/test';
import { existsSync } from 'fs';

/**
 * Visual regression tests using VLM (ai-visual-test).
 *
 * Takes Playwright screenshots and evaluates them with the custom
 * card-game rubric. Requires GEMINI_API_KEY (or OPENAI_API_KEY
 * or ANTHROPIC_API_KEY) in environment.
 *
 * Run with: npx playwright test tests/e2e/visual.spec.mjs
 * Skip VLM: SKIP_VLM=1 npx playwright test tests/e2e/visual.spec.mjs
 */

const FRONTEND = '/search.html';
const SCREENSHOT_DIR = '/tmp';
const PASS_THRESHOLD = 7;

// Check if VLM provider key is available
const hasVLMKey = !!(
  process.env.GEMINI_API_KEY ||
  process.env.OPENAI_API_KEY ||
  process.env.ANTHROPIC_API_KEY
);
const skipVLM = process.env.SKIP_VLM === '1' || !hasVLMKey;

// Game configs for screenshot + evaluation
const GAMES = [
  {
    key: 'magic',
    searchCard: 'Lightning Bolt',
    screenshotFile: 'vlm_magic.png',
  },
  {
    key: 'pokemon',
    searchCard: 'Charizard',
    screenshotFile: 'vlm_pokemon.png',
  },
  {
    key: 'yugioh',
    searchCard: 'Dark Magician',
    screenshotFile: 'vlm_yugioh.png',
  },
];

// ---------------------------------------------------------------------------
// Screenshot capture (always runs — useful even without VLM)
// ---------------------------------------------------------------------------

test.describe('Visual screenshots', () => {
  for (const game of GAMES) {
    test(`capture ${game.key} theme screenshot`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(FRONTEND);
      await page.waitForLoadState('networkidle');

      // Set game via pill button and search
      await page.click(`.game-btn[data-game="${game.key}"]`);
      await page.fill('#unifiedInput', game.searchCard);
      await page.click('#unifiedSearchForm button[type="submit"]');

      // Wait for results and images to load
      await page.waitForSelector('.result-item', { timeout: 20_000 });
      await page.waitForTimeout(3000); // allow card images to load

      // Take screenshot
      const path = `${SCREENSHOT_DIR}/${game.screenshotFile}`;
      await page.screenshot({ path, fullPage: false });

      expect(existsSync(path)).toBe(true);
    });
  }
});

// ---------------------------------------------------------------------------
// VLM evaluation (conditional on API key availability)
// ---------------------------------------------------------------------------

test.describe('VLM visual quality', () => {
  // Skip entire suite if no VLM key
  test.skip(() => skipVLM, 'No VLM API key available (set GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY)');

  let validateScreenshot, createConfig;

  test.beforeAll(async () => {
    // Dynamic import to avoid failure when package not installed
    try {
      const mod = await import('@arclabs561/ai-visual-test');
      validateScreenshot = mod.validateScreenshot;
      createConfig = mod.createConfig;
    } catch {
      test.skip();
    }
  });

  for (const game of GAMES) {
    test(`${game.key} theme scores >= ${PASS_THRESHOLD}/10`, async () => {
      const path = `${SCREENSHOT_DIR}/${game.screenshotFile}`;
      if (!existsSync(path)) {
        test.skip();
        return;
      }

      const result = await validateScreenshot(path, `Evaluate this card game search UI for ${game.key}. Score 0-10 on visual quality, information hierarchy, typography, whitespace, and game identity.`, {
        useCache: true,
        modelTier: 'balanced',
        useRubric: true,
        includeDimensions: true,
        testType: 'visual-quality',
      });

      const score = result.score ?? 0;
      console.log(`${game.key}: ${score}/10`);

      if (result.dimensionScores) {
        for (const [dim, val] of Object.entries(result.dimensionScores)) {
          console.log(`  ${dim}: ${val}/10`);
        }
      }

      expect(score).toBeGreaterThanOrEqual(PASS_THRESHOLD);
    });
  }
});
