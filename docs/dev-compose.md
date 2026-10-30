# Development stack with hot reload and tailnet access

`docker-compose.dev.yml` is an override for the base stack. It is never the
default: name both files explicitly. It does not change the base file's
services, image, or published ports when you don't.

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --wait
docker compose -f docker-compose.yml -f docker-compose.dev.yml watch --prune=false
```

Keep `watch` running while you edit. `just dev-up`, `just dev-watch`, and
`just dev-down` wrap these.

## What the override changes

| Base | Override |
|---|---|
| `./src`, `./frontend` bind-mounted read-only | Compose Watch syncs them into the container layer |
| `uvicorn` without reload | `uvicorn --reload --reload-dir /app/src` |
| `8000:8000` on all interfaces | `127.0.0.1:8000:8000` |
| MeiliSearch, Qdrant published on all interfaces | loopback only |
| MeiliSearch master key from an empty `MEILISEARCH_KEY` | `decksage-dev-meili-key` on both sides |
| proxy variables inherited from `.env` | proxy cleared, `NO_PROXY` set for the backends |
| no model cache, no text embedder | host Hugging Face cache mounted read-only, `sentence-transformers` installed |

`./data` stays a read-only host mount: it is large, generated elsewhere, and
not edited during a session. `./data/cache` is mounted writable on top of it for
the text-embedding cache. Editing `src/` or `frontend/` syncs and reloads;
editing `pyproject.toml`, `uv.lock`, or `Dockerfile` rebuilds and recreates the
API container.

Compose Watch needs a current Compose; this was validated with 2.40.3, which
also supplies the `!override` tag used to replace the base bind mounts and port
publishing.

## Three defects this override had to work around

These are properties of the base stack on a fresh machine, not of Watch. Fixing
them in the override or the base file was unavoidable to get a first run:

- `.dockerignore` listed `!README.md` before `*.md`, so the negation lost and the
  build failed on `COPY README.md`. The negation now follows the exclusion, and
  `src/backend/` (944 MB of Go tooling and corpora) is excluded from the context.
- The Dockerfile copied no source, so the image could only work with the dev
  bind mount and failed on `docker compose up` alone. It now copies `src/ml` and
  `frontend`, and Watch refreshes that copy.
- The Qdrant healthcheck used `curl` and `/health`; the image has neither curl
  nor wget and Qdrant serves `/readyz`. It probes the REST port with bash.

Two application defects surfaced only because the backends became reachable:

- MeiliSearch index creation is asynchronous and was not awaited, so the first
  settings call raced it and startup failed on an empty MeiliSearch.
- Auto-indexing passed numpy scalars straight into the JSON payload, so a fresh
  index failed with `malformed_payload`.

And one configuration mismatch: the bundled MeiliSearch client cannot talk to a
server with no master key (it fails with `invalid_api_key` even when told to use
no key), and `.env` leaves `MEILISEARCH_KEY` empty. The dev stack sets a shared
dev key on both sides.

## Model weights

`sentence-transformers` is installed in the image so the E5 text embedder and the
SigLIP visual embedder load; without them `/v1/search` cannot embed a query and
every signal reports missing. Weights come from `./data-local/hf-hub` mounted
read-only at `HF_HOME`'s `hub/`, with `HF_HUB_OFFLINE=1`.

That copy exists because the host's `~/.cache/huggingface/hub` is a symlink to
`/Volumes/Rebuildable/huggingface/hub`, and Docker Desktop does not follow or
share that path, so a bind mount of it appears empty inside the container. Two
model directories (`intfloat/e5-base-v2`, `google/siglip-base-patch16-224`,
1.2 GB) are copied there. Point `HF_CACHE` at a different directory to override.

## Tailnet access

The API is published on loopback, and `tailscale serve` puts it on the tailnet
with TLS. This is tailnet-only, not Funnel: no public ingress.

```sh
tailscale serve --bg --https=11443 http://127.0.0.1:8000
tailscale serve status
tailscale serve --https=11443 off      # when done
```

Then open <https://<host>.<tailnet>.ts.net:11443/> on the phone. The UI builds
its API URLs from `window.location.origin`, so it works unchanged behind the
proxy. `just dev-tailnet` and `just dev-tailnet-off` wrap these.

### What a phone session exercises

- Works: the landing page at `/`, `/search.html`, similarity over
  `POST /v1/similar` (`embedding`, `jaccard`, `jaccard_faceted`, `fusion`,
  `meta`), `substitute` through the older `GET /v1/cards/{name}/similar`
  endpoint, deck completion, contextual endpoints, autocomplete.
- Note the asymmetry: the request model rejects `mode=substitute` on
  `POST /v1/similar` while the GET endpoint accepts it. The frontend review page
  uses the GET form, so it works; API clients copying the README table hit a 422.
- Degraded: the archetype signal is missing for every game
  (`signals: 2/3 loaded`), so fusion runs on fewer signals than `docs/` claims.
  Treat fusion numbers from this stack as a lower bound.
- First search per game is slow: the query path builds a text-embedding cache
  for all ~26k cards, about 19 minutes on this host at 768D. The cache is
  written to `data/cache/text_emb_cache_cards_<game>.npz`, so it survives a
  restart; without the writable `./data/cache` mount it would rebuild every
  time. Don't mistake that first-query latency for a broken endpoint.
- `GET /health` is not registered on the app root (only `/live` and `/ready`).
  The container healthcheck uses `/live`, so a 404 from `/health` is expected.
- Phrase queries can miss: "destroy all creatures" returns nothing even though
  MeiliSearch holds cards with that exact oracle text, while "counter target
  spell" and "deals 3 damage" resolve. Treat a single empty result as a ranking
  bug to investigate, not as absent data.

Image cost: with `sentence-transformers` and its CPU `torch`, the image is
9.8 GB. The weights are not in it; they come from the read-only local cache with
`HF_HUB_OFFLINE=1`, so the container needs no egress for them.

### Exposure hazard

`env_file: .env` gives the container the real LLM keys, proxy credentials, and
`LLM_PROVIDER`. A tailnet-exposed UI can reach endpoints that spend money
(`use_llm=true`, explain routes). Anyone on the tailnet who can open the URL can
reach them too. The dev override clears the outbound proxy, so provider calls go
direct rather than through the paid proxy. Stop the serve when done, and do not
put this endpoint on a shared tailnet.

## Kanto handoff

Kanto runs K3s with Argo CD; this Compose file is a local integration
environment, not a deployment recipe. Two things it does establish, both of
which the cluster needs: the image now runs with source baked in, and the API
needs no host bind mount except read-only `data/`.

Before cutover, decide and verify on the cluster rather than here:

- Read-only `data/` as a persistent volume, or a data-bearing image layer. The
  current image expects `./data` beside it.
- AMD64: this image is built here for `linux/arm64`. Build and validate an
  AMD64 image on a native builder before advertising that platform.
- MeiliSearch and Qdrant as their own services with real auth, not the dev key
  above.
- Which signals ship. If production is meant to serve `substitute` and full
  fusion, the `enrichment` extra and its model weights belong in the image or a
  mounted cache; today they are missing and the API silently loads fewer
  signals.
- The dev key and cleared proxy must not be carried over.

## Validation boundary

Validated on macOS/arm64 with Compose 2.40.3: the three services reach healthy,
MeiliSearch and Qdrant are reachable only through the compose network and
loopback, and the API answers on `127.0.0.1:8000`. Watch sync and reload are
confirmed on `src/`; nothing here validates kanto, GPU inference, or a full
signal set.
