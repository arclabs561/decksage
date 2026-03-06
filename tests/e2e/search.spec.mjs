// @ts-check
import { test, expect } from '@playwright/test';

/**
 * Search flow E2E tests.
 *
 * Covers: search submission, result rendering, autocomplete,
 * game switching, URL state persistence.
 */

const FRONTEND = '/search.html';

/** Click a game pill button to switch games. */
async function selectGame(page, game) {
  await page.click(`.game-btn[data-game="${game}"]`);
}

/** Wait for results to appear (similarity cards). */
async function waitForResults(page, { timeout = 15_000 } = {}) {
  await page.waitForSelector('.result-item', { timeout });
}

/** Get the current game from body class. */
async function currentGame(page) {
  const cls = await page.getAttribute('body', 'class');
  const m = cls?.match(/game-(\w+)/);
  return m ? m[1] : null;
}

// ---------------------------------------------------------------------------
// Basic search
// ---------------------------------------------------------------------------

test.describe('Search', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(FRONTEND);
    await page.waitForLoadState('networkidle');
  });

  test('page loads with search form visible', async ({ page }) => {
    await expect(page.locator('#unifiedInput')).toBeVisible();
    await expect(page.locator('.game-btn[data-game="magic"]')).toBeVisible();
    await expect(page.locator('.game-btn[data-game="pokemon"]')).toBeVisible();
    await expect(page.locator('.game-btn[data-game="yugioh"]')).toBeVisible();
  });

  test('search returns results for a known Magic card', async ({ page }) => {
    await selectGame(page, 'magic');
    await page.fill('#unifiedInput', 'Lightning Bolt');
    await page.click('#unifiedSearchForm button[type="submit"]');
    await waitForResults(page);

    const items = page.locator('.result-item');
    await expect(items.first()).toBeVisible();
    const count = await items.count();
    expect(count).toBeGreaterThanOrEqual(3);

    // Each result has a card name and similarity score
    const firstName = await items.first().locator('.result-name').textContent();
    expect(firstName?.trim().length).toBeGreaterThan(0);
    await expect(items.first().locator('.similarity-percent')).toBeVisible();
  });

  test('search returns results for a known YGO card', async ({ page }) => {
    await selectGame(page, 'yugioh');
    await page.fill('#unifiedInput', 'Dark Magician');
    await page.click('#unifiedSearchForm button[type="submit"]');
    await waitForResults(page);

    const items = page.locator('.result-item');
    const count = await items.count();
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test('search returns results for a known Pokemon card', async ({ page }) => {
    await selectGame(page, 'pokemon');
    await page.fill('#unifiedInput', 'Charizard');
    await page.click('#unifiedSearchForm button[type="submit"]');
    await waitForResults(page);

    const items = page.locator('.result-item');
    const count = await items.count();
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test('empty search shows validation or no results', async ({ page }) => {
    await page.fill('#unifiedInput', '');
    await page.click('#unifiedSearchForm button[type="submit"]');

    await page.waitForTimeout(1000);
    const items = page.locator('.result-item');
    const count = await items.count();
    expect(count).toBe(0);
  });

  test('unknown card shows error status', async ({ page }) => {
    await selectGame(page, 'magic');
    await page.fill('#unifiedInput', 'Xyzzy Nonexistent Card 12345');
    await page.click('#unifiedSearchForm button[type="submit"]');

    await page.waitForTimeout(3000);
    const items = page.locator('.result-item');
    const count = await items.count();
    expect(count).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Autocomplete
// ---------------------------------------------------------------------------

test.describe('Autocomplete', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(FRONTEND);
    await page.waitForLoadState('networkidle');
  });

  test('typing shows autocomplete suggestions', async ({ page }) => {
    await selectGame(page, 'magic');
    // Type slowly to trigger autocomplete debounce
    await page.locator('#unifiedInput').pressSequentially('Light', { delay: 80 });

    await page.waitForSelector('.autocomplete-dropdown.visible', { timeout: 5000 });
    const dropdown = page.locator('.autocomplete-dropdown');
    await expect(dropdown).toBeVisible();

    const suggestions = dropdown.locator('.autocomplete-item');
    const count = await suggestions.count();
    expect(count).toBeGreaterThan(0);
  });

  test('clicking autocomplete suggestion fills input', async ({ page }) => {
    await selectGame(page, 'magic');
    await page.locator('#unifiedInput').pressSequentially('Light', { delay: 80 });

    await page.waitForSelector('.autocomplete-dropdown.visible', { timeout: 5000 });
    const firstOption = page.locator('.autocomplete-item').first();
    if (await firstOption.isVisible()) {
      await firstOption.click();
      const val = await page.inputValue('#unifiedInput');
      expect(val.length).toBeGreaterThan(4);
    }
  });
});

// ---------------------------------------------------------------------------
// Game switching
// ---------------------------------------------------------------------------

test.describe('Game switching', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(FRONTEND);
    await page.waitForLoadState('networkidle');
  });

  test('switching game changes body class', async ({ page }) => {
    await selectGame(page, 'magic');
    expect(await currentGame(page)).toBe('magic');

    await selectGame(page, 'pokemon');
    expect(await currentGame(page)).toBe('pokemon');

    await selectGame(page, 'yugioh');
    expect(await currentGame(page)).toBe('yugioh');
  });

  test('game switch updates active button state', async ({ page }) => {
    await selectGame(page, 'magic');
    await expect(page.locator('.game-btn[data-game="magic"]')).toHaveClass(/active/);

    await selectGame(page, 'pokemon');
    await expect(page.locator('.game-btn[data-game="pokemon"]')).toHaveClass(/active/);
    await expect(page.locator('.game-btn[data-game="magic"]')).not.toHaveClass(/active/);
  });
});

// ---------------------------------------------------------------------------
// URL state persistence (History API)
// ---------------------------------------------------------------------------

test.describe('URL routing', () => {
  test('search state persists in URL', async ({ page }) => {
    await page.goto(FRONTEND);
    await page.waitForLoadState('networkidle');

    await selectGame(page, 'magic');
    await page.fill('#unifiedInput', 'Lightning Bolt');
    await page.click('#unifiedSearchForm button[type="submit"]');
    await waitForResults(page);

    const url = page.url();
    expect(url).toContain('q=');
    expect(url).toContain('game=magic');
  });

  test('loading URL with params restores search', async ({ page }) => {
    await page.goto(`${FRONTEND}?q=Lightning+Bolt&game=magic&method=embedding&tab=search`);
    await page.waitForLoadState('networkidle');

    await waitForResults(page, { timeout: 20_000 });

    const items = page.locator('.result-item');
    const count = await items.count();
    expect(count).toBeGreaterThanOrEqual(3);

    const val = await page.inputValue('#unifiedInput');
    expect(val).toBe('Lightning Bolt');
  });
});
