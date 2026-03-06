// @ts-check
import { test, expect } from '@playwright/test';

/**
 * API health and endpoint E2E tests.
 *
 * These test the API directly (no browser UI) to verify
 * endpoints return expected shapes before running UI tests.
 */

test.describe('API health', () => {
  test('liveness probe returns live', async ({ request }) => {
    const resp = await request.get('/live');
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.status).toBe('live');
  });

  test('v1 games endpoint returns all three games', async ({ request }) => {
    const resp = await request.get('/v1/games');
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    const games = Object.keys(body.games || {});
    expect(games).toContain('magic');
    expect(games).toContain('pokemon');
    expect(games).toContain('yugioh');
  });
});

test.describe('API search endpoints', () => {
  test('GET /v1/cards/{name}/similar returns results for Magic card', async ({ request }) => {
    const resp = await request.get('/v1/cards/Lightning%20Bolt/similar', {
      params: { game: 'magic', method: 'embedding', k: '5' },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.results?.length).toBeGreaterThanOrEqual(1);
    // Each result should have card name and similarity score
    const first = body.results[0];
    expect(first.card).toBeTruthy();
    expect(typeof first.similarity).toBe('number');
  });

  test('GET /v1/cards/{name}/similar returns results for YGO card', async ({ request }) => {
    const resp = await request.get('/v1/cards/Dark%20Magician/similar', {
      params: { game: 'yugioh', method: 'embedding', k: '5' },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.results?.length).toBeGreaterThanOrEqual(1);
  });

  test('GET /v1/cards/{name}/similar returns results for Pokemon card', async ({ request }) => {
    const resp = await request.get('/v1/cards/Charizard/similar', {
      params: { game: 'pokemon', method: 'embedding', k: '5' },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.results?.length).toBeGreaterThanOrEqual(1);
  });

  test('YGO results include summoning_requirements in metadata', async ({ request }) => {
    // Search for a card that should return Extra Deck monsters
    const resp = await request.get('/v1/cards/Stardust%20Dragon/similar', {
      params: { game: 'yugioh', method: 'embedding', k: '10' },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();

    // At least one result should have summoning_requirements in metadata
    const withSummon = body.results?.filter(
      r => r.metadata?.summoning_requirements
    );
    expect(withSummon?.length).toBeGreaterThan(0);

    // Verify the field looks reasonable
    const req = withSummon[0].metadata.summoning_requirements;
    expect(typeof req).toBe('string');
    expect(req.length).toBeGreaterThan(3);
  });

  test('YGO results include effect_types in metadata', async ({ request }) => {
    const resp = await request.get('/v1/cards/Ash%20Blossom%20%26%20Joyous%20Spring/similar', {
      params: { game: 'yugioh', method: 'embedding', k: '10' },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();

    const withEffects = body.results?.filter(
      r => r.metadata?.effect_types
    );
    expect(withEffects?.length).toBeGreaterThan(0);
  });

  test('unknown card returns 404 or empty results', async ({ request }) => {
    const resp = await request.get('/v1/cards/Xyzzy%20Nonexistent%20Card%2012345/similar', {
      params: { game: 'magic', method: 'embedding', k: '5' },
    });
    // Should be 404 or 200 with empty results
    const status = resp.status();
    if (status === 200) {
      const body = await resp.json();
      expect(body.results?.length || 0).toBe(0);
    } else {
      expect(status).toBe(404);
    }
  });
});

test.describe('API cards endpoint', () => {
  test('lists cards with pagination', async ({ request }) => {
    const resp = await request.get('/v1/cards', {
      params: { game: 'magic', limit: '5' },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.items?.length).toBe(5);
    expect(body.next_offset).toBeDefined();
  });

  test('prefix filter returns matching cards', async ({ request }) => {
    const resp = await request.get('/v1/cards', {
      params: { game: 'magic', prefix: 'Light', limit: '5' },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    const names = body.items?.map(i => i.name) || [];
    expect(names.length).toBeGreaterThan(0);
    // All returned names should start with "Light"
    for (const name of names) {
      expect(name.toLowerCase()).toMatch(/^light/);
    }
  });
});
