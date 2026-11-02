# Data-plane topology and self-healing policy

Self-healing needs a declared graph, not tribal knowledge. `config/topology.toml`
is that graph: every artifact, what builds it, what it is built from, and who
consumes it. `scripts/ops/topology.py` evaluates it; the API serves the same
assessment at `/v1/topology` and folds it into `/health`.

## The graph

```
sources                derived                        serving
────────────────────────────────────────────────────────────────────────────
catalog.{game} ──┬──> tags.{game} ────────────┐
                 ├──> reprints.{game}         │
                 └──> e5_cache.{game} ──┬─────┴──> graph.{game} ──> api.graph
                                        │
                                        ├──> qdrant.e5.{game} ──> similar.e5
                                        └──> meili.{game} ───────> search
cooccurrence.{game} ────────────────────┘
scryfall.oracle ──> scryfall.sets / .legalities / .prices ──> api, meili, qdrant
tag_bulk.magic  ──> tags.magic
```

`{game}` expands over `magic`, `pokemon`, `yugioh`. Two nodes are game-specific
overrides because their inputs differ: Magic tags come from the curated bulk,
Magic reprints from the Scryfall bulk; the other games derive both from their
catalog text. The spec says so explicitly rather than pretending one shape fits.

Check it:

```bash
just topology                  # exit 1 on missing/stale/unknown/cycle
curl -s /v1/topology | jq .findings
```

`/health` reports `degraded` when any node is missing, stale, or a backend is
unreachable. It stays HTTP 200: an orchestrator should not kill a server for a
stale artifact, but an agent should be able to see it.

## Reaction policy: who fixes what, and when

| Event | Owner | Reaction | Fallback while it is wrong |
|---|---|---|---|
| A source file is updated | refresh (`scheduler` profile) | rebuild every derived node in topological order | API keeps serving the previous artifacts |
| A derived artifact is rebuilt | refresh | `POST /v1/admin/reload` re-reads metadata, tags, reprints, set data and graph in place | no restart, no downtime |
| The reload call never lands | API watcher (30 s mtime poll) | reload the affected game automatically | — |
| A backend (Meili/Qdrant) dies | request path | that arm is skipped; the other arm answers | `/health` shows `degraded`; the container stays up |
| The E5 collection is missing | request path | catalog-only cards fall back to no vector result | graph arm still works |
| The unified graph is missing | request path | `/v1/graph/neighbors` falls back to co-occurrence adjacency | relations filter returns co-occurrence only |
| A card is in the catalog but not in the graph vocab | request path | vector arm uses the card's E5 vector (`vector_source: text_e5`) | empty result before 2026-11-01 |
| The API worker hangs | Compose | `restart: unless-stopped` on crash; healthcheck marks it unhealthy | **not automatic** — see below |
| A label is wrong | nobody | labels are versioned artifacts; repaired in a patch file, never edited in place | — |

### What is deliberately not automatic

- **Restarting an unhealthy-but-running container.** Docker does not restart on
  unhealthy without an external supervisor, and adding one (autoheal or a
  Docker-socket sidecar) buys a privilege we do not want for this stack. The
  reload hang that motivated this was removed instead: hot reload is opt-in.
- **Scraping.** The catalog is an external input. Refresh rebuilds from what is
  on disk; it never fetches.
- **Promoting labels.** A model label stays a model label until a human reviews
  it. Auto-promoting would make the system confidently wrong faster.

## Verifying the topology itself

The check catches the failure that matters most in practice: an artifact newer
than what it feeds, or an input nobody rebuilt. A cycle or an edge to an
undeclared node fails the check rather than being silently ignored, so the spec
cannot rot into fiction.

`data-local/label-anchor-20261030/` is mounted into the API only because the
tag-bulk mtime is part of the DAG; nothing reads its contents at serve time.
