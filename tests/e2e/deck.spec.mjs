// @ts-check
import { test, expect } from '@playwright/test';

/**
 * Deck management E2E tests.
 *
 * Covers: tab switching, deck text import, cross-tab navigation.
 */

const FRONTEND = '/search.html';

async function selectGame(page, game) {
  await page.click(`.game-btn[data-game="${game}"]`);
}

test.describe('Deck tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(FRONTEND);
    await page.waitForLoadState('networkidle');
    // Clear localStorage to start fresh
    await page.evaluate(() => {
      const keys = Object.keys(localStorage).filter(k => k.startsWith('decksage_'));
      keys.forEach(k => localStorage.removeItem(k));
    });
  });

  test('deck completion tab is accessible', async ({ page }) => {
    const deckTab = page.locator('#deck-tab-btn, [data-tab="deck"]');
    if (await deckTab.count() > 0) {
      await deckTab.click();
      await page.waitForTimeout(500);
      const active = page.locator('.tab-content.active, [data-tab-content="deck"]');
      if (await active.count() > 0) {
        await expect(active).toBeVisible();
      }
    }
  });

  test('can input deck text', async ({ page }) => {
    const deckTab = page.locator('#deck-tab-btn, [data-tab="deck"]');
    if (await deckTab.count() === 0) {
      test.skip();
      return;
    }
    await deckTab.click();
    await page.waitForTimeout(500);

    const deckInput = page.locator('#deckInput');
    if (await deckInput.count() > 0) {
      await deckInput.fill('4 Lightning Bolt\n4 Counterspell\n2 Dark Ritual');
      const val = await deckInput.inputValue();
      expect(val).toContain('Lightning Bolt');
    }
  });
});

// ---------------------------------------------------------------------------
// Cross-tab navigation
// ---------------------------------------------------------------------------

test.describe('Tab navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(FRONTEND);
    await page.waitForLoadState('networkidle');
  });

  test('all main tabs are visible', async ({ page }) => {
    const searchTab = page.locator('#unified-search-tab-btn');
    const contextualTab = page.locator('#contextual-tab-btn');

    await expect(searchTab).toBeVisible();
    await expect(contextualTab).toBeVisible();
  });

  test('switching tabs shows correct content', async ({ page }) => {
    const contextualTab = page.locator('#contextual-tab-btn');
    await contextualTab.click();
    await page.waitForTimeout(300);

    const contextualInput = page.locator('#contextualCardInput');
    if (await contextualInput.count() > 0) {
      await expect(contextualInput).toBeVisible();
    }

    await page.locator('#unified-search-tab-btn').click();
    await page.waitForTimeout(300);
    await expect(page.locator('#unifiedInput')).toBeVisible();
  });

  test('"Find Similar" button on expanded card triggers new search', async ({ page }) => {
    await selectGame(page, 'magic');
    await page.fill('#unifiedInput', 'Lightning Bolt');
    await page.click('#unifiedSearchForm button[type="submit"]');
    await page.waitForSelector('.result-item', { timeout: 15_000 });

    const firstItem = page.locator('.result-item').first();
    const cardName = await firstItem.locator('.result-name').textContent();

    // Expand and click Find Similar
    await firstItem.locator('.result-info').click();
    await firstItem.locator('button:has-text("Find Similar")').click();

    await page.waitForTimeout(2000);

    const newVal = await page.inputValue('#unifiedInput');
    expect(newVal.trim()).toBe(cardName?.trim());
  });
});
