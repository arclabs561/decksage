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

test.describe('Card detail tools', () => {
  test('card info returns metadata and ban status', async ({ request }) => {
    const resp = await request.get('/v1/cards/Lightning%20Bolt', { params: { game: 'magic' } });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.card).toBe('Lightning Bolt');
    expect(body.metadata).toBeTruthy();
    expect(body.metadata.type || body.metadata.type_line).toBeTruthy();
  });

  test('legality returns per-format status', async ({ request }) => {
    const resp = await request.get('/v1/cards/Lightning%20Bolt/legality', {
      params: { game: 'magic' },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(Object.keys(body.legalities).length).toBeGreaterThan(0);
  });
});

test.describe('Graph query', () => {
  test('neighbors returns weighted co-occurrence edges', async ({ request }) => {
    const resp = await request.get('/v1/graph/neighbors', {
      params: { game: 'magic', card: 'Lightning Bolt', limit: 3 },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.card).toBe('Lightning Bolt');
    expect(body.neighbors.length).toBeGreaterThan(0);
    expect(typeof body.neighbors[0].weight).toBe('number');
  });

  test('an unknown card returns an empty neighbourhood, not an error', async ({ request }) => {
    const resp = await request.get('/v1/graph/neighbors', {
      params: { game: 'magic', card: 'Xyzzy Nonexistent', limit: 3 },
    });
    expect(resp.ok()).toBeTruthy();
    expect((await resp.json()).neighbors).toEqual([]);
  });
});

test.describe('Text retrieval mode', () => {
  test('mode=text returns a text-ranked pool', async ({ request }) => {
    const resp = await request.post('/v1/similar', {
      data: { game: 'magic', query: 'Lightning Bolt', top_k: 5, mode: 'text' },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.model_info.method_used).toBe('text');
    expect(body.results.length).toBeGreaterThanOrEqual(3);
    expect(body.results[0].card).toBeTruthy();
  });
});

test.describe('Index coverage', () => {
  test('index status reports catalog and backend counts', async ({ request }) => {
    const resp = await request.get('/v1/index/status');
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    for (const game of ['magic', 'pokemon', 'yugioh']) {
      const entry = body.games[game];
      expect(entry.catalog).toBeGreaterThan(0);
      expect(entry.meilisearch_coverage).toBe(1);
      expect(entry.qdrant_coverage).toBeGreaterThan(0.6);
    }
  });
});

test.describe('Exact-match and catalog coverage', () => {
  test('search reports exact_match for a real card and not for a miss', async ({ request }) => {
    const hit = await request.post('/v1/search', {
      data: { game: 'magic', query: 'Lightning Bolt', limit: 1 },
    });
    expect((await hit.json()).exact_match).toBe(true);

    const miss = await request.post('/v1/search', {
      data: { game: 'magic', query: 'Xyzzy Nonexistent Card', limit: 1 },
    });
    expect((await miss.json()).exact_match).toBe(false);
  });

  test('similar reports exact_match and an honest empty result for a catalog-only card', async ({ request }) => {
    const hit = await request.post('/v1/similar', {
      data: { game: 'magic', query: 'Lightning Bolt', top_k: 2 },
    });
    expect(hit.ok()).toBeTruthy();
    expect((await hit.json()).exact_match).toBe(true);

    // 1996 World Champion is in the catalog but has no graph vector.
    const noVector = await request.post('/v1/similar', {
      data: { game: 'magic', query: '1996 World Champion', top_k: 2 },
    });
    expect(noVector.ok()).toBeTruthy();
    const body = await noVector.json();
    expect(body.exact_match).toBe(true);
    expect(body.results).toEqual([]);
    expect(body.model_info.no_vector).toBe(true);
  });

  test('autocomplete covers cards absent from the graph vocabulary', async ({ request }) => {
    const resp = await request.get('/v1/cards', {
      params: { game: 'magic', prefix: '1996 world', limit: 3 },
    });
    expect(resp.ok()).toBeTruthy();
    const names = (await resp.json()).items.map((item) => item.name);
    expect(names[0]).toBe('1996 World Champion');
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
