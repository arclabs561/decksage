# Feature and attribute audit — 2026-10-31

Question: are we indexing all the data we want, and does anything use it?
Short answer: the catalogs were richer than both indexes, Meilisearch now
carries the attributes, and several loaded signals still do not affect ranking.

## What exists, by layer

| Layer | Magic | Pokémon | Yu-Gi-Oh! |
|---|---|---|---|
| Catalog CSV columns | 15 | 21 | 38 |
| Meilisearch docs (after rebuild) | 36,453 | 4,384 | 14,195 |
| Qdrant points (128D graph) | 25,892 | 4,384 | 14,156 |
| E5 text cache | 37,214 | 4,384 | 14,195 |

## Indexed vs available

Meilisearch, after this audit's rebuild (`scripts/data/rebuild_meilisearch_index.py`):

- Searchable: `name`, `text`, `type_line`, `keywords`, `archetype`.
- Filterable: `game`, `colors`, `type_line`, `cmc`, `rarity`, `set_name`,
  `power`, `toughness`, `hp`, `atk`, `def_stat`, `level_rank_link`, `archetype`,
  `attribute`, `race`, `card_category`, `supertype`, `regulation_mark`.
- Sortable: `name`, `cmc`, `power`, `toughness`, `hp`, `atk`, `def_stat`.
- Verified: `filter="power >= 4"` (Magic), `hp >= 100` (Pokémon),
  `archetype = "Blue-Eyes"` (Yu-Gi-Oh!) all return rows.

Not indexed, still available:

| Field | Where | Why it matters |
|---|---|---|
| `oracle_text_enriched`, `keyword_abilities`, `creature_types`, `color_identity_str` | Magic CSV | text search currently uses raw oracle text only |
| `banlist_tcg/ocg/goat`, `pendulum_scale`, `link_markers`, `fusion/synchro/ritual_material`, `fandom_*` | Yu-Gi-Oh! CSV | legality/format and combo queries |
| `attacks_detail`, `abilities_detail`, `weakness_type`, `resistance_type` | Pokémon CSV | structured combat filtering (text carries a summary) |
| `image_url` | all | served from `card_metadata`; Qdrant has it, Meili does not |
| `legalities`, `prices`, `set`, `set_name` (Magic) | Scryfall raw | served and filterable via flat lookups; not columns in the enriched CSV |
| tags, reprint groups, fusion weights | data-local / experiments | offline arms only; not loaded by the API |

A persisted **unified graph** exists for all three games:

| Game | Edges | text | tag | attribute | cooccurrence |
|---|---|---|---|---|---|
| Magic | 2.10M | 744k | 676k | 433k | 243k |
| Pokémon | 349k | 88k | 88k | 86k | 88k |
| Yu-Gi-Oh! | 1.03M | 284k | 284k | 183k | 283k |

`/v1/graph/neighbors` serves typed edges with a `relations=` filter, ordered by
relation then weight because weights are not comparable across relations
(co-occurrence counts vs cosine vs weighted Jaccard). `/v1/graph/stats` reports
counts, mean and max weight per relation. Basic lands are excluded from Magic
edges; they dominate co-occurrence without being substitution evidence.

Qdrant payloads now carry the fields the retriever filters on
(`colors`, `cmc`, `rarity`, `set_name`, `power`/`toughness`, `hp`,
`atk`/`def_stat`/`level`, `supertype`, `subtypes`, `archetype`) with payload
indexes on every one of them. The semantic arm translates the same filter
expression the lexical arm uses; an untranslatable clause falls back to an
unfiltered vector query rather than dropping the arm.

## Utilized vs merely loaded

| Signal | Loaded | Served | Affects ranking |
|---|---|---|---|
| graph embedding | yes | `mode=embedding`, graph neighbours | yes (co-play) |
| E5 text cache | yes | `mode=text`, semantic fallback | yes |
| tags (Scryfall) | offline only | no | only in experiments |
| reprint groups | offline only | no | only in experiments |
| archetype staples/cooccurrence | yes | contextual | **no** (fusion weight 0, log says unweighted) |
| visual embedder (SigLIP) | yes | no | **no** (`has_visual_index: false`, weight 0) |
| linear reranker | present | no | retired by default |
| banlist / legality / prices | yes | metadata, format filter, budget contextual | display/filter only |
| deck frequency | yes | autocomplete popularity, meta mode | ordering in autocomplete, meta |
| archetypes/templates | yes | contextual | contextual only |

Concrete cost fixed: the visual embedder no longer loads unless
`DECKSAGE_ENABLE_VISUAL=1`; it carries zero fusion weight and has no index.

## Query reach (the "utilize" gap)

`parse_query_filters` historically emitted only color, cmc and type filters, so
even indexed `power`/`hp`/`atk` were unreachable from natural language. It now
parses `power 4+`, `toughness <= 3`, `hp 100+`, `atk >= 2000`, with tests.
Archetype/race/category remain explicit-filter only.

## Research: unified model vs facet models

The multi-task literature supports the middle path this repo's evidence points
to: a shared trunk with task-specific heads (hard parameter sharing), with
negative transfer as the known risk; sparse tasks benefit most from sharing.
Sources: Springer 2025 review of deep MTL (`10.1007/s41060-025-00892-y`), the
CIKM'23 Generalist Recommender (`10.1145/3583780.3615229`), the MTL-for-recsys
survey (`arXiv:2305.13843`), and the partial-supervision MTL review
(`arXiv:2307.14382`).

Mapping to DeckSage: one E5/LLM trunk with `functional`, `synergy` and `meta`
heads is defensible; one undifferentiated score is not, because the labels are
distinct relations (the embedding that ignores that is exactly the graph model
that failed substitution). Negative transfer is the thing to measure: the
shared trunk must match per-facet baselines on held-out queries.

## Status after this pass

- Meili: 36,453 / 4,384 / 14,195, all attributes indexed; power, hp and
  archetype filters verified end to end through `/v1/search`.
- Text caches: 37,214 / 4,384 / 14,195, coverage 1.0 in `/v1/index/status`.
- Visual: disabled by default; opt in only when wired and calibrated.
- Self-fill: `just bootstrap` (one-shot Compose profile) fills Meili gaps and
  missing caches; `just dev-doctor --fill` runs it during repair.
- Qdrant: still graph-limited (Magic 71%); acceptable because text ANN uses the
  in-memory E5 cache, and API enrichment supplies display attributes.

## Actions, in order

1. **Done:** rebuild Meilisearch docs with the attributes; extend filterable,
   sortable and searchable settings; verify power/hp/archetype filters.
2. **Done:** numeric query filters so the new fields are reachable.
3. Load tags/reprints into the API before claiming the tag rerank as a product
   feature; until then they are offline evidence only.
4. Decide the visual embedder: wire it into fusion and index it, or stop
   loading it. Do not keep paying memory for zero weight.
5. **Done:** Scryfall set, `set_name`, legalities and prices are joined into the
   Magic catalog (`scripts/data/build_scryfall_metadata.py`), served on
   `/v1/cards/{card}` and filterable as `set` / `set_name`.
6. **Done:** Qdrant payload fields and indexes for filtered ANN; the semantic
   arm now applies the same filters as the lexical arm.
7. Before adding more text fields, test `oracle_text_enriched` / `keywords` in
   searchable attributes on the judged pools; do not assume enrichment helps.
