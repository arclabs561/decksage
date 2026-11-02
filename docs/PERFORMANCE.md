# Performance ledger

Measurements on the dev stack (`127.0.0.1:8000`, 3 games), macOS host with
Docker Desktop. The host is shared with other sessions and containers, so
endpoint medians move by 3-5x between windows; only the claims marked
*attributable* are used to justify a change.

Commands

```bash
# endpoint medians (7-9 runs per case)
uv run python /tmp/bench_api.py 7
# startup: read the lifespan line
docker logs decksage-api 2>&1 | grep "Serving 3 game"
```

## 2026-11-01, startup

| | value | note |
|---|---|---|
| before | 61.8 s | 28.7 s embedder load + 32 s artifacts, serial |
| after, cold page cache | 46.7 s | model thread overlaps the artifact loop |
| after, warm page cache | 15.5 s | same code; files already in the page cache |

**Attributable:** the embedder load (torch import + weights) and the per-game
artifact load are independent and now run concurrently; the model is attached
after the loop. `lifespan` logs the split, so a regression is visible in one
line.

## 2026-11-01, `/v1/index/status`

| | value |
|---|---|
| before | 130 ms |
| after, cold | 27 ms |
| after, warm (10 s TTL) | 2.4-3.2 ms |

**Attributable:** the endpoint made six backend calls (Meili stats, Qdrant
collection info, per game) on every request. Cached for 10 s; a stale-by-10 s
artifact count is acceptable for a diagnostic endpoint.

## 2026-11-01, response payloads (measured on the indexes, not end-to-end)

| path | before | after | change |
|---|---|---|---|
| Meili search, 20 hits | 16,770 B | 1,431 B | -91% |
| Qdrant query, 20 points | 10,517 B | 3,667 B | -65% |

Meili's own `processingTimeMs` stayed at 1 ms, so this is transfer and JSON
parsing, not server work. The Qdrant cut came with `with_payload` selection; the
Meili cut with `attributesToRetrieve` and dropping the unused
`showRankingScoreDetails`.

## Endpoint medians (shared host, 7-9 runs)

Two windows on the same code, to show the spread rather than a single number:

| case | window A | window B |
|---|---|---|
| search lexical | 18.9 ms | 46.9 ms |
| search card name | 14.0 ms | 27.0 ms |
| search filtered | 30.2 ms | 69.8 ms |
| similar embedding | 11.7 ms | 46.2 ms |
| similar text | 32.5 ms | 34.3 ms |
| similar union | 62.5 ms | 65.8 ms |
| card info | 2.0 ms | 14.4 ms |
| graph neighbors | 7.2 ms | 5.0 ms |
| deck complete | 369 ms | 516 ms |

Control paths that were not touched (`card info`, `graph neighbors`) move just
as much as the changed ones, which is why the table is not used to attribute
anything.

## Rejected

- **Lazy-loading the embedder to cut startup further.** It would move 29 s onto
  the first semantic request. Not worth it while a cold start fits in ~47 s.
- **A TTL cache on `/v1/similar`.** Completion asks for a different card each
  step, so a per-request cache would miss; a cross-request cache needs an
  invalidation story the data plane does not have yet.
