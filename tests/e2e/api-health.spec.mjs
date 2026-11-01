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

test.describe('Unified graph query', () => {
  test('neighbors are typed by relation', async ({ request }) => {
    const text = await request.get('/v1/graph/neighbors', {
      params: { game: 'magic', card: 'Lightning Bolt', relations: 'text', limit: 3 },
    });
    expect(text.ok()).toBeTruthy();
    const textBody = await text.json();
    expect(textBody.source).toBe('unified');
    expect(textBody.neighbors.length).toBeGreaterThan(0);
    expect(textBody.neighbors.every((n) => n.relation === 'text')).toBe(true);

    const coplay = await request.get('/v1/graph/neighbors', {
      params: { game: 'magic', card: 'Lightning Bolt', relations: 'cooccurrence', limit: 3 },
    });
    const coBody = await coplay.json();
    expect(coBody.neighbors.every((n) => n.relation === 'cooccurrence')).toBe(true);
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

test.describe('Scryfall set metadata', () => {
  test('card metadata carries set, prices and legalities', async ({ request }) => {
    const resp = await request.get('/v1/cards/Lightning Bolt', { params: { game: 'magic' } });
    expect(resp.ok()).toBeTruthy();
    const meta = (await resp.json()).metadata;
    expect(meta.set).toBeTruthy();
    expect(meta.set_name).toBeTruthy();
    expect(Object.keys(meta.prices).length).toBeGreaterThan(0);
    expect(Object.keys(meta.legalities).length).toBeGreaterThan(0);
  });

  test('set filter works on both arms', async ({ request }) => {
    const lexical = await request.post('/v1/search', {
      data: { game: 'magic', query: 'bolt', limit: 5, filters: 'set = "clu"' },
    });
    const lexicalSet = (await lexical.json()).results.map(r => r.metadata?.set);
    expect(lexicalSet.length).toBeGreaterThan(0);
    expect(lexicalSet.every(value => value === 'clu')).toBe(true);

    const semantic = await request.post('/v1/search', {
      data: {
        game: 'magic',
        query: 'Lightning Bolt',
        text_weight: 0,
        vector_weight: 1,
        limit: 5,
        filters: 'set = "clu"',
      },
    });
    const semanticSet = (await semantic.json()).results.map(r => r.metadata?.set);
    expect(semanticSet.length).toBeGreaterThan(0);
    expect(semanticSet.every(value => value === 'clu')).toBe(true);
  });
});

test.describe('Semantic filters', () => {
  test('vector-only search honours a colour filter', async ({ request }) => {
    const resp = await request.post('/v1/search', {
      data: {
        game: 'magic',
        query: 'Lightning Bolt',
        text_weight: 0,
        vector_weight: 1,
        filters: 'colors = "R"',
        limit: 5,
      },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.results.length).toBeGreaterThan(0);
    expect(body.results.every(r => (r.metadata?.colors || '').includes('R'))).toBe(true);
  });

  test('vector-only search honours a numeric filter', async ({ request }) => {
    const resp = await request.post('/v1/search', {
      data: {
        game: 'magic',
        query: 'Lightning Bolt',
        text_weight: 0,
        vector_weight: 1,
        filters: 'cmc <= 2',
        limit: 5,
      },
    });
    const body = await resp.json();
    expect(body.results.every(r => Number(r.metadata?.cmc) <= 2)).toBe(true);
  });
});

test.describe('Deck completion input shapes', () => {
  test('accepts structured card lists', async ({ request }) => {
    const resp = await request.post('/v1/deck/complete', {
      data: {
        game: 'magic',
        cards: [
          { name: 'Lightning Bolt', count: 4 },
          { name: 'Mountain', count: 20 },
        ],
        target_main_size: 30,
        max_steps: 3,
        method: 'greedy',
      },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(Array.isArray(body.steps)).toBe(true);
  });
});

test.describe('Artifact self-report', () => {
  test('index status reports tags, reprints and graph per game', async ({ request }) => {
    const resp = await request.get('/v1/index/status');
    expect(resp.ok()).toBeTruthy();
    const games = (await resp.json()).games;
    for (const game of ['magic', 'pokemon', 'yugioh']) {
      expect(games[game]).toBeDefined();
      expect(games[game].tags).toBeGreaterThan(0);
      expect(games[game].reprint_groups).toBeGreaterThan(0);
      expect(games[game].unified_graph).not.toBeNull();
    }
  });

  test('derived tag neighbours exist for pokemon and yugioh', async ({ request }) => {
    for (const [game, card] of [['pokemon', 'Pikachu'], ['yugioh', 'Dark Magician']]) {
      const resp = await request.get('/v1/graph/neighbors', {
        params: { game, card, relations: 'tag', limit: 5 },
      });
      expect(resp.ok()).toBeTruthy();
      const body = await resp.json();
      expect(body.source).toBe('unified');
    }
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

  test('accepts game aliases', async ({ request }) => {
    for (const alias of ['mtg', 'MTG']) {
      const resp = await request.get('/v1/cards', {
        params: { game: alias, prefix: 'bolt', limit: '3' },
      });
      expect(resp.ok()).toBeTruthy();
      const names = (await resp.json()).items?.map(i => i.name) || [];
      expect(names.length).toBeGreaterThan(0);
    }
    const ygo = await request.post('/v1/search', {
      data: { game: 'ygo', query: 'Dark Magician', limit: 1 },
    });
    expect(ygo.ok()).toBeTruthy();
    expect((await ygo.json()).exact_match).toBe(true);
  });

  test('unknown game errors name the valid games', async ({ request }) => {
    const resp = await request.post('/v1/search', {
      data: { game: 'nope', query: 'x', limit: 1 },
    });
    expect(resp.status()).toBe(400);
    const body = await resp.json();
    expect(typeof body.detail).toBe('string');
    expect(body.detail).toContain('Valid games');
  });

  test('validation errors carry a readable message', async ({ request }) => {
    const resp = await request.post('/v1/similar', {
      data: { game: 'magic', query: 'Lightning Bolt', top_k: 'five' },
    });
    expect(resp.status()).toBe(422);
    const body = await resp.json();
    expect(Array.isArray(body.detail)).toBe(true);
    expect(typeof body.message).toBe('string');
  });

  test('search paginates without repeating a page', async ({ request }) => {
    const page = async (offset) => {
      const resp = await request.post('/v1/search', {
        data: { game: 'magic', query: 'dragon', limit: 2, offset },
      });
      expect(resp.ok()).toBeTruthy();
      return resp.json();
    };
    const first = await page(0);
    const second = await page(2);
    expect(first.next_offset).toBe(2);
    const firstNames = first.results.map(r => r.card_name);
    const secondNames = second.results.map(r => r.card_name);
    expect(secondNames.some(name => firstNames.includes(name))).toBe(false);
  });

  test('rejects unknown graph relations', async ({ request }) => {
    const resp = await request.get('/v1/graph/neighbors', {
      params: { game: 'magic', card: 'Lightning Bolt', relations: 'tagg' },
    });
    expect(resp.status()).toBe(400);
    expect((await resp.json()).detail).toContain('Valid');
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
