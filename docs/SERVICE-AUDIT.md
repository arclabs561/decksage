# Service usage audit (docs vs code)

Checked 2026-11-01 against the docs that match the pinned versions, and against
the running servers.

| Service | Version | Client |
|---|---|---|
| Meilisearch | 1.30.0 (`getmeili/meilisearch:v1.30.0`) | `meilisearch` 0.38.0 |
| Qdrant | 1.16.3 (`qdrant/qdrant:v1.16.3`) | `qdrant-client` 1.16.2 (pinned `<1.17`) |
| FastAPI / uvicorn | 0.139.0 / 0.40.0 | — |
| Pydantic | 2.12.5 | — |
| Docker Compose | v2 | `docker compose` |

## Correct

- **Version pinning.** `qdrant-client>=1.7,<1.17` matches the 1.16.3 server; the
  client dropped `search()` in 1.17, which is why `_qdrant_points` probes
  `query_points` and keeps the legacy call as a fallback.
- **Ranking rules are pinned explicitly** rather than inherited. Meilisearch
  1.56 has already changed the default list (`attributeRank`, `wordPosition`);
  a floating default would silently reorder results on upgrade.
- **Filter syntax.** `colors = "R"` / `color_list = "U"` on an array attribute is
  content matching, which is the documented behaviour; verified on both arms.
- **Pagination bounds.** Meilisearch `pagination.maxTotalHits` defaults to 1000.
  The API caps `offset + limit + 1` at 500, so no request can hit the cap.
- **Payload index types.** `keyword` for string fields, `float` for numeric ones
  (matching the payload values), via `create_payload_index`.
- **Qdrant filter objects.** `FieldCondition`/`Range`/`MatchValue`, `must` +
  `should` for `AND`/`OR`, nested `Filter` for an OR-group. Matches the
  documented shape.
- **Compose.** `profiles` for one-shot jobs, `depends_on: condition:
  service_healthy`, and explicit bind mounts. `docker compose run --rm` is the
  documented way to run the refresh job.
- **FastAPI.** `asynccontextmanager` lifespan, `RequestValidationError` handler,
  `Query(alias=...)` — all current API.

## Defects found

### 1. Numeric equality on the vector arm returns nothing (correctness)

`qdrant_filter_from_string` emits `MatchValue(value=number)` for `cmc = 2`.
Qdrant documents `Match` for **keyword, integer, bool and uuid** payloads; the
numeric fields are indexed as `float`, so the condition matches nothing.

Verified before the fix:

```
vector-only  cmc = 2  ->  []
lexical      cmc = 2  ->  Chart a Course (2.0), See Beyond (2.0), ...
```

Fixed by emitting `Range(gte=n, lte=n)` for numeric equality (`Range` is the
documented condition for float payloads). After:

```
vector-only  cmc = 2  ->  Skullcrack (2.0), Searing Blaze (2.0), ...
```

### 2. Payload indexes were created after ingestion (performance, latent)

Qdrant requires payload indexes to exist before the HNSW graph is built for
filter-aware edges, and says to rebuild HNSW afterwards. Our indexes were added
after 25,892 points were ingested, and the collection reports
`indexed_vectors_count: 0` with `indexing_threshold: 10000`, i.e. queries still
full-scan. No harm today (25k x 128d brute force is fast); if the collection
starts building HNSW, bump `ef_construct` by 1 once to force the rebuild.

### 3. Meilisearch returns whole documents for every hit (waste)

`Index.search` is called without `attributesToRetrieve`, so each of the
`2 x limit` hits carries `text` (up to 2000 chars), `oracle_text`, legality and
price blobs. The result builder reads only `name`, `image_url`, `ref_url`.

Fixed: `attributesToRetrieve: ["name", "image_url", "ref_url"]`.
Measured on the running index: 16,770 -> 1,431 bytes per query (-91%); Meili's
own `processingTimeMs` is unchanged at 1 ms, so the win is transfer and JSON
parsing, not server work.

### 4. `showRankingScoreDetails` is requested but never read (waste)

The per-rule score breakdown is computed for every hit and discarded. The code
only reads `_rankingScore`.

Fixed: dropped. It is pure waste when the breakdown is not read.

### 5. Qdrant returns full payloads for every point (waste)

`query_points` is called without `with_payload`, so the response carries the
2000-char `text` field for `2 x limit` points. Only `name`, `image_url` and
`ref_url` are used.

Fixed: `with_payload=["name", "image_url", "ref_url"]`.
Measured: 10,517 -> 3,667 bytes per query (-65%).

## Not defects

- **Typo tolerance below the 1.30 defaults** (`oneTypo: 4`, `twoTypos: 8` vs
  5/9) is deliberate: card names are short and `dark magicain` must resolve.
- **`attributesToSearchOn: ["name"]`** only for exact-name queries is correct;
  the attribute is in `searchableAttributes`.
- **No Qdrant strict mode.** Unindexed filtering is allowed; every field the
  retriever filters on now has an index, so strict mode is optional.
