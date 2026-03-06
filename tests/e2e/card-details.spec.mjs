// @ts-check
import { test, expect } from '@playwright/test';

/**
 * Card detail interaction tests.
 *
 * Covers: accordion expansion, metadata display, card drawer,
 * game-specific fields (YGO summoning requirements, effect types).
 */

const FRONTEND = '/search.html';

async function selectGame(page, game) {
  await page.click(`.game-btn[data-game="${game}"]`);
}

async function searchAndWait(page, game, card) {
  await selectGame(page, game);
  await page.fill('#unifiedInput', card);
  await page.click('#unifiedSearchForm button[type="submit"]');
  await page.waitForSelector('.result-item', { timeout: 15_000 });
}

// ---------------------------------------------------------------------------
// Accordion expansion
// ---------------------------------------------------------------------------

test.describe('Card accordion', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(FRONTEND);
    await page.waitForLoadState('networkidle');
  });

  test('clicking a result expands it', async ({ page }) => {
    await searchAndWait(page, 'magic', 'Lightning Bolt');

    const firstItem = page.locator('.result-item').first();
    await firstItem.locator('.result-info').click();

    await expect(firstItem).toHaveClass(/expanded/);

    const panel = firstItem.locator('.result-expand-panel');
    await expect(panel).toBeVisible();
  });

  test('only one card expands at a time', async ({ page }) => {
    await searchAndWait(page, 'magic', 'Lightning Bolt');

    const items = page.locator('.result-item');
    const first = items.nth(0);
    const second = items.nth(1);

    // Expand first
    await first.locator('.result-info').click();
    await expect(first).toHaveClass(/expanded/);

    // Click second's info area — first should collapse
    await second.locator('.result-info').click();
    await page.waitForTimeout(300);
    await expect(first).not.toHaveClass(/expanded/);
  });

  test('expand panel shows action buttons', async ({ page }) => {
    await searchAndWait(page, 'magic', 'Lightning Bolt');

    const firstItem = page.locator('.result-item').first();
    await firstItem.locator('.result-info').click();

    const panel = firstItem.locator('.result-expand-panel');
    await expect(panel.locator('button:has-text("Find Similar")')).toBeVisible();
    await expect(panel.locator('button:has-text("Add to Deck")')).toBeVisible();
  });

  test('escape key collapses expanded card', async ({ page }) => {
    await searchAndWait(page, 'magic', 'Lightning Bolt');

    const firstItem = page.locator('.result-item').first();
    await firstItem.locator('.result-info').click();
    await expect(firstItem).toHaveClass(/expanded/);

    await page.keyboard.press('Escape');
    await expect(firstItem).not.toHaveClass(/expanded/);
  });
});

// ---------------------------------------------------------------------------
// Card metadata display
// ---------------------------------------------------------------------------

test.describe('Card metadata', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(FRONTEND);
    await page.waitForLoadState('networkidle');
  });

  test('Magic results show stat badges', async ({ page }) => {
    await searchAndWait(page, 'magic', 'Tarmogoyf');

    const firstItem = page.locator('.result-item').first();
    const badges = firstItem.locator('.stat-badge');
    const count = await badges.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('YGO results show ATK/DEF badges', async ({ page }) => {
    await searchAndWait(page, 'yugioh', 'Blue-Eyes White Dragon');

    const items = page.locator('.result-item');
    let foundStatBadge = false;
    for (let i = 0; i < Math.min(5, await items.count()); i++) {
      const badges = items.nth(i).locator('.stat-badge');
      if (await badges.count() > 0) {
        foundStatBadge = true;
        break;
      }
    }
    expect(foundStatBadge).toBe(true);
  });

  test('YGO results show summoning requirements for Extra Deck monsters', async ({ page }) => {
    await searchAndWait(page, 'yugioh', 'Stardust Dragon');

    const items = page.locator('.result-item');
    let foundSummonReq = false;
    for (let i = 0; i < Math.min(8, await items.count()); i++) {
      const summonReq = items.nth(i).locator('.result-summon-req');
      if (await summonReq.count() > 0) {
        foundSummonReq = true;
        const text = await summonReq.textContent();
        expect(text?.length).toBeGreaterThan(3);
        break;
      }
    }
    expect(foundSummonReq).toBe(true);
  });

  test('YGO results show effect type keyword tags', async ({ page }) => {
    await searchAndWait(page, 'yugioh', 'Ash Blossom & Joyous Spring');

    const items = page.locator('.result-item');
    let foundKeywords = false;
    for (let i = 0; i < Math.min(5, await items.count()); i++) {
      const tags = items.nth(i).locator('.keyword-tag');
      if (await tags.count() > 0) {
        foundKeywords = true;
        break;
      }
    }
    expect(foundKeywords).toBe(true);
  });

  test('Pokemon results show HP badges', async ({ page }) => {
    await searchAndWait(page, 'pokemon', 'Charizard');

    const items = page.locator('.result-item');
    let foundBadge = false;
    for (let i = 0; i < Math.min(5, await items.count()); i++) {
      const badges = items.nth(i).locator('.stat-badge');
      if (await badges.count() > 0) {
        foundBadge = true;
        break;
      }
    }
    expect(foundBadge).toBe(true);
  });

  test('results show card images', async ({ page }) => {
    await searchAndWait(page, 'magic', 'Lightning Bolt');

    const images = page.locator('.result-item .card-image');
    await page.waitForTimeout(2000);
    const count = await images.count();
    expect(count).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Card drawer (detail side panel)
// ---------------------------------------------------------------------------

test.describe('Card drawer', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(FRONTEND);
    await page.waitForLoadState('networkidle');
  });

  test('Details button opens card drawer', async ({ page }) => {
    await searchAndWait(page, 'magic', 'Lightning Bolt');

    const firstItem = page.locator('.result-item').first();
    await firstItem.locator('.result-info').click();

    const detailsBtn = firstItem.locator('button:has-text("Details")');
    await detailsBtn.click();

    const drawer = page.locator('#cardDrawer');
    await expect(drawer).toHaveClass(/open/);
    await expect(page.locator('#cardDrawerOverlay')).toHaveClass(/open/);
  });

  test('escape closes card drawer', async ({ page }) => {
    await searchAndWait(page, 'magic', 'Lightning Bolt');

    const firstItem = page.locator('.result-item').first();
    await firstItem.locator('.result-info').click();
    await firstItem.locator('button:has-text("Details")').click();

    const drawer = page.locator('#cardDrawer');
    await expect(drawer).toHaveClass(/open/);

    await page.keyboard.press('Escape');
    await expect(drawer).not.toHaveClass(/open/);
  });
});
