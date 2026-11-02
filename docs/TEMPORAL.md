# TEMPORAL.md — what the corpus knows about time, and what `as_of` should mean

**Status**: proposed · **Date**: 2026-11-01 · **Scope**: design only, no `src/` change.
Numbers below were read from the named file. Items I could not confirm are marked
UNVERIFIED with what would settle them.

The service is time-blind in one specific, fixable way: it has **printing dates** and **deck
collection dates**, but no artifact carrying a **period** from decks through edges into labels
or retrieval. `as_of` cannot be honoured at any layer except card release.

## 1. Audit — what is time-stamped, and what it costs to stamp

| Layer | Signal today (path, count) | Verdict | Cheapest stamp |
|---|---|---|---|
| Card printing (magic) | `data/processed/scryfall_sets.json` 36,453 cards, 534 sets, **100%** `released_at`, `1993-11-01`→`2026-06-26`; joins 36,453/36,453 of `card_attributes_magic_enriched.csv` | complete | already done |
| Card printing (pokemon) | `card_attributes_pokemon_enriched.csv` 4,384 rows, **100%** `set_release_date`, `1999/01/09`→`2026/01/30`, 151 sets; `regulation_mark` filled 2,337/4,384 (`D`191 `E`266 `F`300 `G`333 `H`500 `I`692 `J`55) | complete | normalise `YYYY/MM/DD`; mark is the era key |
| Card printing (yugioh) | `card_attributes_yugioh_enriched.csv` 14,195 rows, **no date or era column**; `banlist_tcg`/`_ocg`/`_goat` are one status each (`Forbidden`118/`Limited`87/blank 13,980) | absent | `data/raw/ygoprodeck/cardinfo.json` set dates |
| Deck date | 36 `data/decks/*.jsonl` (4 empty); `created_at` on goldfish 73,389, masterduelmeta 75,428, archidekt_commander 51,083, moxfield×4 44,915, mtgtop8 5,000, pokemon_limitless×4 24,483, yugioh_resolved 794. Magic total **179,738** dated decks | strong, undocumented | already done |
| Deck date (broken) | `decks_pokemon_limitless-web-expanded.jsonl` 12,000 rows `"created_at": "13th February 2026"`; `decks_riftbound.jsonl` 1 row `"2025-22-02"` — both fail `datetime.fromisoformat` and the `strptime` table in `src/ml/utils/temporal_filtering.py` | unparseable | one format table |
| Deck date (none) | `decks_pokemon.jsonl` 1,208; `decks_digimon*.jsonl` 288+4×365; `decks_onepiece*` 76 | absent | some parse from URL |
| Edge | `pairs_large.csv` 7,111,569 rows, cols `NAME_1,NAME_2,COUNT_SET,COUNT_MULTISET`; `data/graphs/pairs_large.edg` 3 cols | **no provenance** | gap 1 |
| Edge (recoverable) | `pairs_magic_goldfish.csv` 2,053,907 rows carries `DECK_ID=deck:3496146` → `decks_magic_goldfish.jsonl` (join verified for goldfish, mtgtop8, archidekt) | recoverable | add `deck_date` at pair time |
| Edge (fake date) | `data/graphs/{magic,pokemon,yugioh}_unified.db` edges 11,534,993 / 1,092,648 / 4,577,454; `first_seen`+`last_seen` 100% filled but equal build time — magic `co_occurrence` values only `2026-03-01` (9,355,506), `2026-03-22` (644,917), `2026-03-23` (13,354) | **misleading** | `src/ml/data/incremental_graph.py:952` uses `datetime.now()` |
| Edge (designed, empty) | same DB: `monthly_counts` **0/11.5M**, `format_periods` **0/11.5M**, `deck_sources` all `[]` | unwired | filled when a timestamp is passed |
| Edge decay | `scripts/training/build_unified_graph.py:615` `halflife_days=0`; CLI `--halflife-days` default `0` (`:871`); `FORMAT_HALFLIFE` Standard 90 / Pioneer 180 / Modern 365 / Commander 365; magic `base_edgelist` is the undated `data/graphs/pairs_large.edg` (`:70`) | implemented, never enabled | `--halflife-days` after §6 |
| Label | `data/test_sets/annotated_magic_v2.json` 3,047 queries / 43,791 pairs, file `created` `2026-03-17` / `updated` `2026-03-30`, per pair **no date, no as_of**; `mode_counts` synergy 2733, substitution 2138, **meta 869**. `data/annotations/refined/*_pairs.json` magic 4,299 / pokemon 3,683 / yugioh 3,912, no date; `magic_2000_v4.json` `generated_at` `2026-02-28` | judge time only | add `judged_at` + `meta_as_of` |
| Legality | `data/processed/scryfall_legality.json` 36,453 × 21 formats, `{legal,not_legal,banned,restricted}` | **one snapshot, no history** | gap 2 |
| Legality history | `src/ml/data/format_events.py` hand-curated `FORMAT_EVENTS`, **7 dated events** (MTG 3, PKM 2, YGO 2); MTG Modern/Pioneer/Legacy/Commander `[]`; no retrieval path consumes it | thin | gap 2 |
| Era text | `data/game_knowledge/*.json` `last_updated` magic `2025-01-01`, pokemon `2025-01-01`, yugioh `2026-02-26`; `temporal_context.current_meta` prose injected into judge prompts at `src/ml/annotation/multi_annotator_iaa.py:239-243` | stale prose | delete from prompts until dated |
| Corpus velocity | 89 `data/experiments/*.yaml`, `2026-03-17`→`2026-11-01`; 13 landed 03-19/20, 13 on 10-31 | fast | — |

**No `as_of` exists in `src/`** (grep: 0 hits). The only shipped date filter is `format=`
(`src/ml/api/api.py:2086,2259,3071`), reading the current snapshot.

**Mtimes are not vintages.** `data/raw/scryfall/oracle-cards.json` mtime `2026-03-01` but holds
382 cards with later `released_at`, 309 with non-null `usd` — so it was fetched later and the
mtime was copied back. UNVERIFIED which date `scryfall_legality.json` (mtime `2026-10-31`)
actually reflects; settle by re-running `build_scryfall_metadata.py --force` and diffing.

## 2. Proposed model — `as_of` per layer

`as_of` is one ISO date per request. It is **not** one behaviour; conflating the layers is how a
temporal system becomes quietly wrong.

| Layer | `as_of` means | Filter or weight | Why |
|---|---|---|---|
| Card identity | nothing: name, reprint family (`magic_reprints.json`, 32,173), colour, type | **never filtered** | a card is one object across eras |
| Card printing | existed: `released_at <= as_of`, clamped to `min(as_of, today)` | **hard filter** | 21 entries in `scryfall_sets.json` carry a 2026-06 date later than the bulk's mtime |
| Legal term | the format's rules that date, from a dated snapshot | **hard filter, never decayed** | a banned card is not "less legal"; it is illegal |
| Co-occurrence edge | support from decks with `deck_date <= as_of` | **weight** (windowed sum, optional decay) | a pair has a support history, not a date; filtering deletes signal |
| Label | which judgments are in-domain for an eval at `as_of` | **eval-set metadata only** | never rescale a score by date |
| Index / embedding | which build; each declares `max_deck_date`, `built_at` | **metadata + refusal** | a 2019 request on a 2026-only index should be refused |

**Never time-filtered**: card identity and reprint membership; a label's historical value for
the task it was collected for (ADR-0001); any `as_of` applied retroactively. **Unmodelled
risk**: `oracle_text` is one snapshot of current wording, so pre-errata text is invisible — a
card's function can change while its identity does not.

## 3. Options

| | Option | Gate | Rank | Confidence |
|---|---|---|---|---|
| 0 | **Do nothing.** Keep pooling eras, keep `first_seen` as a pseudo-date | fails: build-time dates already reach `leakage_analysis.py:82` | **F** | confident |
| a | **Era-filtered retrieval only.** `as_of` on release + a deck-date window | passes: honest answer for "what was playable then" | **A** | confident |
| b | **Decayed co-occurrence weights.** Enable `--halflife-days` | passes: code exists and is tested; effect unmeasured | **B** | likely |
| c | **Full temporal graph with snapshots** | passes: highest correctness | **C** | likely |

- **(a)** cheapest and reversible — a `released_at` join plus a date predicate. Cost: hides era mixing rather than fixing it; an edge still blends 2020 and 2026 support. Breaks when the query card is itself from the filtered-out era.
- **(b)** reuses machinery already present. Cost: a tuning change with no evidence, and it can lose real signal — the pooled corpus is 3× larger than any recent window. Breaks if pointed at the undated `pairs_large.edg`, where every edge gets weight 1.0 and nothing changes.
- **(c)** correct at every layer and supports "what changed" answers. Cost: blocked by gaps 1 and 2. Breaks on thin months — goldfish has a 29-month hole (2023-02→2025-06).

**Recommendation**: (a) now, the only option shippable without new data. (b) after §6 passes. (c) after gap 1. **This flips if** §6 gives `Δρ ≤ 0.01`: then era pooling is harmless for co-occurrence and the effort belongs in legality and labels, not edge weights.

## 4. Stop doing now

1. **Stop treating `first_seen`/`last_seen` as event dates.** They are `datetime.now()` at `src/ml/data/incremental_graph.py:952`. `src/ml/scripts/export_filtered_edgelist_from_graph.py` documents the false comfort in its own docstring — "Since pairs_large.csv lacks timestamps, we export edges from the graph (which has first_seen timestamps) and filter by temporal split. This prevents leakage" — so the leak guard splits by *build* time and calls it a temporal split. `src/ml/evaluation/leakage_analysis.py:82` reads the same field.
2. **Stop building the Magic graph from `data/graphs/pairs_large.edg`** (3 undated columns, mtime 2025-12-06) while 179,738 dated decks sit in `deck_jsonl` used only for node metadata (`build_unified_graph.py:70,650`).
3. **Stop serving `format=` as current.** It reads a snapshot with no history and an uncertain vintage, so it answers today's question with last season's rules.
4. **Stop emitting `meta` labels without a reference date.** 869 magic + 819 pokemon + 491 yugioh meta queries, judged 2026-02/03, with `current_meta` prose dated `2025-01-01` in the prompt. Those labels are not wrong, they are undated — fatal for `meta` specifically.
5. **Stop patching reprints via `data/patches/magic_reprint_labels_20261031.json`** (31 pairs). That file is evidence the generator is edition-blind; patching pairs leaves it blind.


## 5. Data gaps, ranked, with the cheapest acquisition

1. **Edge-level deck provenance in the file that feeds the graph.** `pairs_large.csv`, 7.1 M rows, no `DECK_ID`. *Cheapest*: regenerate from the per-source pair files that already carry it and join `created_at` — verified `deck:3496146`→`2020-11-05`, `mtgtop8:816694`→`2026-02-28`, `archidekt:5000000`→`2023-07-25`. No new scraping; the key exists for ~18 M rows.
2. **Dated legality history.** 7 curated events; MTG non-rotating formats empty. *Cheapest*: write today's snapshot as `scryfall_legality_2026-11-01.json` and never overwrite — one dated row per `card.format.date` from here on. Backfill from MTGJSON versions; do not synthesise history from memory.
3. **Date-parse hygiene.** 12,000 rows with `"13th February 2026"`, 1 with `"2025-22-02"`, and `scraped_at` on 88 k+ rows but missing from the key list at `src/ml/utils/temporal_filtering.py:54`. *Cheapest*: extend that list and the format table — one function, recovers 88 k dated decks currently discarded.

## 6. Smallest first experiment that could fail

Pre-registered. **Do not run yet.** No embedding training, no LLM calls.

- **Question**: does co-occurrence from an *old* era predict today's judgments worse than co-occurrence from a *recent* era, on the same pairs? **H1**: for judged Magic pairs supported in both eras, `Δρ = ρ_recent − ρ_old ≥ 0.05`.
- **Population**: `data/test_sets/annotated_magic_v2.json` (3,047 queries, 43,791 pairs) ∩ `decks_magic_goldfish.jsonl` (73,389 decks), split at its natural gap — old `≤ 2023-01`, recent `≥ 2025-07`. **Eligible 2,810 pairs** (1,636 irrelevant, 519 marginal, 383 highly, 193 somewhat, 79 relevant); strict-band subset 2,098 = 462 positive / 1,636 negative is the primary analysis. Coverage is uneven and must be reported: 2,571 judged cards pre-2023, 4,639 in 2025+, 1,077 in both.
- **Signal**: co-occurrence over that window's decks only → PPMI; absent pair scores 0 and is kept, not dropped.
- **Metric**: Spearman ρ between window score and judged band ordinal (0–4), paired on the same pairs; primary statistic `Δρ` with a 1,000-sample bootstrap CI paired **by pair**, not by card (cards recur).
- **Pass**: `Δρ ≥ 0.05` and CI excludes 0 → (b) is justified. **Falsify**: `Δρ ≤ 0.01` or CI spans 0 → era pooling is harmless for this metric and the effort belongs in legality and labels. A null result is a kept result.
- **Negative control**: permute `created_at` across goldfish decks, preserving the month marginal and destroying the card↔date association; rebuild both windows; re-run. Require `|Δρ_control| < 0.02` with CI spanning 0. If the control also reaches 0.05, the effect is window sample size and H1 is unsupported.
- **Named confound**: the recent window has more decks *and* more judged-card coverage (4,639 vs 2,571). Re-run with deck counts equalised by subsampling. If the effect survives equalisation it is era; if not, it was coverage.
