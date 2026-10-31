// @ts-check
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Regressions found while fixing search on the composed stack.
 *
 * Run through `just test-e2e-compose`, which builds the stack from the working
 * tree first. The asset checks fail when Compose Watch is not running and the
 * container serves an older frontend than the one on disk — the failure mode
 * that made several earlier UI checks look wrong.
 *
 * The two search regressions:
 *   - the embedding vocabulary is case-sensitive, so "dark magician" 404'd;
 *   - a typo used to fall into the cold text-embedding build and take ~20s.
 */

const ROOT = resolve(import.meta.dirname, '../..');
const COMPOSE = !!process.env.COMPOSE_E2E;

test.describe('compose serves the working tree', () => {
  test.skip(!COMPOSE, 'set COMPOSE_E2E=1 (just test-e2e-compose)');

  for (const [url, file] of [
    ['/search.html', 'frontend/test_search.html'],
    ['/static/retro.css', 'frontend/static/retro.css'],
  ]) {
    test(`${file} is not stale in the container`, async ({ request }) => {
      const resp = await request.get(url);
      expect(resp.ok()).toBeTruthy();
      const served = await resp.text();
      const local = readFileSync(resolve(ROOT, file), 'utf8');
      expect(served).toBe(local);
    });
  }
});

test.describe('search API regressions', () => {
  test('lowercase card names resolve to the canonical card', async ({ request }) => {
    for (const [game, query, expected] of [
      ['magic', 'lightning bolt', 'Lightning Bolt'],
      ['yugioh', 'dark magician', 'Dark Magician'],
    ]) {
      const resp = await request.post('/v1/search', {
        data: { game, query, limit: 3 },
      });
      expect(resp.ok()).toBeTruthy();
      const body = await resp.json();
      expect(body.results?.[0]?.card_name).toBe(expected);
      expect(body.results?.[0]?.score).toBeGreaterThan(0.9);
    }
  });

  test('a typo is answered by text search, not a cold embedding build', async ({ request }) => {
    const started = Date.now();
    const resp = await request.post('/v1/search', {
      data: { game: 'pokemon', query: 'charizrd', limit: 3 },
    });
    const elapsed = Date.now() - started;

    expect(resp.ok()).toBeTruthy();
    const names = (await resp.json()).results?.map((r) => r.card_name) || [];
    expect(names[0]).toMatch(/charizard/i);
    expect(elapsed).toBeLessThan(5_000);
  });

  test('autocomplete tolerates a typo and ranks popular names first', async ({ request }) => {
    const typo = await request.get('/v1/cards', {
      params: { game: 'pokemon', prefix: 'charizrd', limit: 5 },
    });
    expect(typo.ok()).toBeTruthy();
    const typoNames = (await typo.json()).items.map((i) => i.name);
    expect(typoNames[0]).toMatch(/charizard/i);

    const prefix = await request.get('/v1/cards', {
      params: { game: 'magic', prefix: 'light', limit: 5 },
    });
    expect(prefix.ok()).toBeTruthy();
    const prefixNames = (await prefix.json()).items.map((i) => i.name);
    // Exact prefix matches stay first; popularity decides their order.
    expect(prefixNames[0]).toBe('Lightning Bolt');
  });

  test('the API is still live after a free-text query', async ({ request }) => {
    const resp = await request.post('/v1/search', {
      data: { game: 'magic', query: 'deal 3 damage to any target', limit: 5 },
    });
    expect(resp.ok()).toBeTruthy();

    const live = await request.get('/live');
    expect(live.ok()).toBeTruthy();
    expect((await live.json()).status).toBe('live');
  });
});

test.describe('search UI regressions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/search.html');
    await page.waitForLoadState('networkidle');
  });

  test('a lowercase name searches instead of erroring', async ({ page }) => {
    await page.fill('#unifiedInput', 'lightning bolt');
    await page.click('#unifiedSearchForm button[type="submit"]');

    await page.waitForSelector('.result-item', { timeout: 15_000 });
    const status = (await page.locator('#statusMessage').innerText()).toLowerCase();
    expect(status).not.toContain('error');
  });

  test('a miss in one game offers the game that has the card', async ({ page }) => {
    await page.click('.game-btn[data-game="magic"]');
    await page.fill('#unifiedInput', 'dark magician');
    await page.click('#unifiedSearchForm button[type="submit"]');

    const hint = page.locator('[id*="Hint"]').first();
    await expect(hint).toBeVisible({ timeout: 15_000 });
    await expect(hint).toContainText('Yu-Gi-Oh!');

    await hint.locator('button').click();
    await expect(page.locator('body')).toHaveClass(/game-yugioh/);
    await page.waitForSelector('.result-item', { timeout: 15_000 });
  });

  test('the retro skin is default and the toggle persists', async ({ page }) => {
    await expect(page.locator('body')).toHaveClass(/retro/);

    await page.click('#themeToggle');
    await expect(page.locator('body')).not.toHaveClass(/retro/);

    await page.reload();
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).not.toHaveClass(/retro/);
  });

  test('the search field is above the fold at 1440x900', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.reload();
    await page.waitForLoadState('networkidle');

    const box = await page.locator('#unifiedInput').boundingBox();
    expect(box).not.toBeNull();
    expect(box.y + box.height).toBeLessThan(900);
  });
});
