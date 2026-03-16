// @ts-check
import { test, expect } from '@playwright/test';
import { existsSync } from 'fs';
import { PASS_THRESHOLD, CARD_GAME_RUBRIC, GAME_CONTEXTS, gamePrompt } from './vlm-rubric.mjs';

/**
 * Visual regression tests using VLM (ai-visual-test).
 *
 * Takes Playwright screenshots and evaluates them with the custom
 * 7-dimension card-game rubric via validateWithRubric(). Requires an
 * API key in environment (auto-loaded from ../.env by playwright.config.mjs).
 *
 * Run with: npx playwright test tests/e2e/visual.spec.mjs
 * Skip VLM: SKIP_VLM=1 npx playwright test tests/e2e/visual.spec.mjs
 */

const FRONTEND = '/search.html';
const SCREENSHOT_DIR = '/tmp';

// Check if VLM provider key is available
const hasVLMKey = !!(
  process.env.GEMINI_API_KEY ||
  process.env.OPENAI_API_KEY ||
  process.env.ANTHROPIC_API_KEY ||
  process.env.OPENROUTER_API_KEY ||
  process.env.GROQ_API_KEY
);
const skipVLM = process.env.SKIP_VLM === '1' || !hasVLMKey;

// Game configs for screenshot + evaluation
const GAMES = Object.entries(GAME_CONTEXTS).map(([key, ctx]) => ({
  key,
  name: ctx.name,
  searchCard: { magic: 'Lightning Bolt', pokemon: 'Charizard', yugioh: 'Dark Magician' }[key],
  screenshotFile: `vlm_${key}.png`,
}));

// ---------------------------------------------------------------------------
// Screenshot capture (always runs -- useful even without VLM)
// ---------------------------------------------------------------------------

test.describe('Visual screenshots', () => {
  for (const game of GAMES) {
    test(`capture ${game.key} theme screenshot`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(FRONTEND);
      await page.waitForLoadState('networkidle');

      await page.click(`.game-btn[data-game="${game.key}"]`);
      await page.fill('#unifiedInput', game.searchCard);
      await page.click('#unifiedSearchForm button[type="submit"]');

      await page.waitForSelector('.result-item', { timeout: 20_000 });
      await page.waitForTimeout(3000); // allow card images to load

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
  test.skip(() => skipVLM, 'No VLM API key available (set OPENROUTER_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY)');

  let validateWithRubric;

  test.beforeAll(async () => {
    try {
      const mod = await import('@arclabs561/ai-visual-test');
      validateWithRubric = mod.validateWithRubric;
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

      const result = await validateWithRubric(
        path,
        gamePrompt(game.key),
        CARD_GAME_RUBRIC,
        { testType: 'visual-quality' },
        { enforceZeroTolerance: false },
      );

      const score = result.score ?? 0;
      console.log(`${game.key}: ${score}/10`);

      if (result.dimensionScores) {
        for (const [dim, val] of Object.entries(result.dimensionScores)) {
          const bar = val >= PASS_THRESHOLD ? '+' : '-';
          console.log(`  ${bar} ${dim}: ${val}/10`);
        }
      }

      if (result.issues?.length) {
        console.log(`  Issues: ${result.issues.slice(0, 3).join('; ')}`);
      }

      expect(score).toBeGreaterThanOrEqual(PASS_THRESHOLD);
    });
  }
});
