# Annotation audit: stratified pairs vs diverse pairs

Read-only audit. Question: are `annotations/*_stratified_pairs.jsonl`
(Feb 25-26) superseded by `data/annotations/diverse_pairs_*.jsonl`
(Mar 21-22), or is each still part of the pipeline?

Snapshot: HEAD `d92ef5f`, observed 2026-10-22. The working tree was clean when
the audit began; by the end of it, another session had modified 68
`data/experiments/*.yaml` files and added
`scripts/validation/generate_experiment_summary.py` (unrelated to this audit,
and none of the annotation files below changed). All counts are read from the
files themselves, not from history. `annotations/` and
`scripts/annotation/archive/` are both gitignored (`.gitignore:192` and
`:193`), so none of the files named here are under version control.

## Verdict

| Family | Files | Verdict | In live path? |
|---|---|---|---|
| Stratified | `annotations/{magic,pokemon,yugioh}_stratified_pairs.jsonl` | **keep** (not superseded; dormant) | No. Generators archived, no consumer has ever existed. |
| Diverse | `data/annotations/diverse_pairs_*.jsonl` | **keep** (live input) | Yes. Feeds the annotator that writes the eval test sets. |

Neither family is "superseded". They are two different sampling frames that
share **zero** pairs, and only one of them is wired into anything.

## 1. Who generates, who consumes

### Stratified family — dormant

| Game | Generator | Output |
|---|---|---|
| magic | `scripts/annotation/archive/generate_stratified_pairs.py` | `annotations/magic_stratified_pairs.jsonl` |
| pokemon | `scripts/annotation/archive/generate_game_stratified_pairs.py` (`GAME_PRESETS`) | `annotations/pokemon_stratified_pairs.jsonl` |
| yugioh | `scripts/annotation/archive/generate_game_stratified_pairs.py` (`GAME_PRESETS`) | `annotations/yugioh_stratified_pairs.jsonl` |

Consumers: **none**. No script, `justfile` target, experiment YAML, or doc in
the current tree reads these files. A `git grep` for `stratified_pairs` across
every revision in the repository matches only the two generators above — no
consumer ever existed, so this is not a case of a consumer being removed later.

Live path: **no**. Both generators live only under
`scripts/annotation/archive/`, moved there by commit `abf4efb`
(2026-03-18, "cleanup: archive 101 old scripts to archive/ dirs"). That
directory is gitignored; the pre-archive copies survive in history at their
old paths (`git show 06a94ef:scripts/annotation/generate_stratified_pairs.py`,
`git show 38a4277:scripts/annotation/generate_game_stratified_pairs.py`).

Note: `generate_game_stratified_pairs.py` still documents its own usage as
`uv run scripts/annotation/generate_game_stratified_pairs.py`, a path that no
longer exists. The docstring is stale, which is itself evidence the script is
not being run.

### Diverse family — live

| Role | Path |
|---|---|
| Generator | `scripts/annotation/generate_diverse_pairs.py` (default output `data/annotations/diverse_pairs_{game}.jsonl`) |
| Consumer | `scripts/annotation/annotate_diverse_pairs.py` (`load_diverse_pairs`, lines 56-66) |
| Downstream | `data/annotations/diverse_checkpoint_{game}.jsonl`, then `data/test_sets/annotated_{game}_v2.json` |
| Documented as | `CLAUDE.md:57` (eval-only source list), experiment `0015_diverse_pair_generation.yaml` |

`annotate_diverse_pairs.py` reads the pair file, writes per-model
checkpoints, and integrates scored pairs into the canonical eval sets
(`annotated_*_v2.json`), which `CLAUDE.md:54` names as the nDCG evaluation
source. This is the live annotation path.

## 2. Content shape and coverage

### Line counts, fields, duplicates

| File | Lines | Unique pairs | Dups | Fields |
|---|---:|---:|---:|---|
| `magic_stratified_pairs.jsonl` | 100 | 100 | 0 | `card1, card2, expected_bucket, embedding_sim, cooccurrence_weight` |
| `pokemon_stratified_pairs.jsonl` | 100 | 100 | 0 | above + `game` |
| `yugioh_stratified_pairs.jsonl` | 100 | 100 | 0 | above + `game` |
| `diverse_pairs_magic.jsonl` | 2299 | 2296 | 3 (0.13%) | `card1, card2, source, text_sim, emb_sim, gap, game, card1_roles, card2_roles, shared_role, colors, price_cheap, price_expensive` |
| `diverse_pairs_pokemon.jsonl` | 1683 | 1649 | 34 (2.02%) | same |
| `diverse_pairs_yugioh.jsonl` | 1913 | 1902 | 11 (0.58%) | same |
| `diverse_pairs_digimon.jsonl` | 648 | 628 | 20 (3.09%) | same, minus the two `price_*` fields |

Duplicates are counted order-insensitively (`frozenset(card1, card2)`), because
both schemas describe undirected similarity.

The stratified files are perfectly deduplicated by construction — the generator
tracks a `seen` set across all four buckets. The diverse files were not
deduplicated at generation time (the annotator deduplicates at write time; see
`CLAUDE.md:85`).

Neither file is a label file. Both are candidate-pair queues: the stratified
schema has no relevance field at all, and the diverse schema has scores
(`text_sim`, `emb_sim`, `gap`) but no judgment. Labels live in
`diverse_checkpoint_*`, `consensus_*`, and `annotated_*_v2.json`.

### Sampling frame — complementary, not overlapping

Stratified: 25 pairs per bucket per game, designed for calibration across
similarity bands (`embedding_sim` ranges measured):

| Bucket | magic | pokemon | yugioh | Character |
|---|---|---|---|---|
| HIGH | 0.997-0.999 | 0.998-1.000 | 0.980-0.987 | top cosine **and** co-occurrence |
| MEDIUM_HIGH | 0.917-0.981 | 0.617-0.861 | 0.735-0.851 | co-occurring, mid-high cosine |
| MEDIUM_LOW | 0.326-0.495 | 0.305-0.482 | 0.301-0.491 | co-occurring, mid-low cosine |
| LOW | -0.920-0.954 | -0.391-0.477 | -0.018-0.523 | random, **zero** co-occurrence |

Diverse: four purposeful sources, weighted toward what the embedding misses.

| Source | magic | pokemon | yugioh | Role |
|---|---:|---:|---:|---|
| `role_matched` | 800 | 800 | 800 | same role, cross-archetype |
| `text_similarity` | 798 | 775 | 774 | similar oracle text, low emb_sim |
| `hard_negative` | 301 | 104 | 334 | high emb_sim (0.60-0.97), different function |
| `budget_pair` | 400 | 4 | 5 | cheap vs expensive equivalent |

The frames do not substitute for each other. Diverse deliberately avoids
high-similarity co-occurring positives (that is the "echo chamber" it was
written to break, per its own docstring); its only high-similarity stratum is
`hard_negative`, which is high cosine with *different function*. The stratified
HIGH/MEDIUM_HIGH buckets are high cosine with confirmed co-occurrence, a band
with no diverse counterpart. Conversely, the stratified LOW bucket is random
zero-co-occurrence noise, which diverse does not sample.

## 3. Overlap between the families

Order-insensitive (query, candidate) overlap, per game:

| Game | Stratified unique | Diverse unique | Overlap | % of stratified |
|---|---:|---:|---:|---:|
| magic | 100 | 2296 | **0** | 0.0% |
| pokemon | 100 | 1649 | **0** | 0.0% |
| yugioh | 100 | 1902 | **0** | 0.0% |
| All 3 + digimon | 300 | 6475 | **0** | 0.0% |

Cross-game collisions inside the stratified set: 0. So the 300 stratified
pairs are 300 pairs that the diverse files do not contain, in any game.

**The stratified files do contain pairs the diverse files do not.** That part
of the premise holds. The consequence drawn from it does not.

## 4. Do those pairs carry labels?

The premise "deleting them would lose labels" is the one point the evidence
contradicts. Every labeled store in the repository was searched for the 300
pairs:

| Store | Stratified pairs found |
|---|---:|
| `data/test_sets/annotated_{game}_v2.json` (live eval sets) | 38 (magic 7, pokemon 3, yugioh 28) |
| `data/annotations/dialogue_yugioh.json` | 2 (not in the test set above) |
| `data/annotations/diverse_checkpoint_*.jsonl` | 0 |
| `data/annotations/consensus_*.json` | 0 |
| `annotations/*_llm_annotations.jsonl` | 0 |
| `data/graphs/*annotation_edges*.edg` | 0 |
| `annotations/hand_batch_*.yaml` | 0 |

Result: **40 of 300 pairs are labeled anywhere; 260 are labeled nowhere.** The
three stratified JSONL files themselves contain no labels, so deleting them
would not destroy a single relevance judgment. It would destroy:

- 300 curated, non-overlapping candidate selections (2 of which exist only as
  selections — their labels live in `dialogue_yugioh.json`),
- the bucket rationale (`expected_bucket`) and the embedding/co-occurrence
  measurements taken against the Feb-2026 embeddings,
- 260 pairs that no other file records at all.

One observation worth carrying forward, though not part of the deletion
decision: the test-set labels for the 38 overlapping pairs often contradict the
generator's bucket hypothesis. Several `HIGH` pairs are labeled `irrelevant`
(e.g. `Boseiju, Who Endures` / `Scrap Welder`, `Team Magma Admin` / `Team Magma
Grunt`). This looks like an artifact of integrating undirected pairs in one
direction, or of the buckets encoding co-occurrence rather than substitutability.
If the stratified set is ever used, that discrepancy should be understood first.

## 5. Does any live plan depend on the stratified generator?

`scripts/annotation/UX_ANNOTATION_STRATEGY.md` (last updated 2026-02-26) is the
only doc that mentions it. Two places:

- **Section 4, item A5** (line 241): "modify `generate_game_stratified_pairs.py`
  to produce pairs grouped by (format, archetype)". This is a proposal to
  *modify* the generator, not to consume its existing output.
- **Section 5 priority table** (line 278): A5 is **P2**, blocking rationale
  "Format-specific tuning has no data."

Section 7 "Immediate next steps" does **not** include A5. No `justfile` target,
experiment YAML, or script invokes the generator. The doc's path reference
(`generate_game_stratified_pairs.py`, no `archive/` prefix) is stale, and no
other document links to this strategy doc. So no live plan depends on the
stratified **files**; at most a P2 proposal points at the archived **script**,
which would need de-archiving and re-pointing regardless of whether these JSONL
files survive.

### Regeneration is not currently possible

The generators' default inputs are gone:

| Input | Status |
|---|---|
| `data/embeddings/production.wv` (magic) | **missing** |
| `data/graphs/pairs_large.edg` (magic) | present (2025-12-06) |
| `data/embeddings/yugioh_blended.wv`, `data/graphs/yugioh_named.edg` | **missing** |
| `data/embeddings/pokemon_blended.wv`, `data/graphs/pokemon_packs.edg` | **missing** |

Even with the archived scripts recovered from git history, re-running them
today would not reproduce these files, because the embeddings and edge lists
they read no longer exist. Today's `data/embeddings/` holds a different
generation of models (`magic_metapath2vec*`, `magic_cleora*`, etc.).

## Recommendation

1. **Keep `data/annotations/diverse_pairs_*.jsonl`.** They are the live input
   to `annotate_diverse_pairs.py` and therefore to the eval test sets.

2. **Keep `annotations/*_stratified_pairs.jsonl` for now — do not delete.**
   They are dormant, unlabeled, and outside the live path, so nothing breaks by
   keeping them, and nothing is gained by removing them beyond 46 KB. The claim
   that they are superseded by the diverse family is false: overlap is 0/300 and
   the sampling frames are complementary.

3. **Their real status is "undecided", not "dead".** They are the only record
   of 260 pairs, they record the only calibration-band sampling frame this repo
   has produced, and they are the substrate the P2/A5 format-stratification
   proposal would build on. The decision that is missing is whether that
   calibration band belongs in the eval program — not whether the files are
   redundant.

4. **If they are eventually retired, the irreversible step is the deletion
   itself, and it must be explicitly authorized.** Three facts make it one-way:

   - `annotations/` is gitignored (`.gitignore:192`), and `git log --all` shows
     these three files were never committed. There is no history to restore from.
   - Regeneration is impossible while `production.wv`, `*_blended.wv`,
     `yugioh_named.edg` and `pokemon_packs.edg` are missing.
   - `expected_bucket` and the Feb-2026 `embedding_sim` values cannot be
     re-measured against the embeddings that produced them.

   Safe sequencing if retirement is chosen: **snapshot first** (commit the three
   files, or archive them outside the ignored path, or record them in a tracked
   manifest), confirm the snapshot is readable from a fresh clone, *then*
   delete. Deleting first and discovering the gap afterwards is unrecoverable.

### Evidence sufficiency

- **Sufficient** to conclude the stratified family is not superseded by the
  diverse family (0/300 overlap, disjoint sampling frames).
- **Sufficient** to conclude no live code path consumes the stratified files
  (no consumer in the tree, none in any revision, not in `justfile` or any
  experiment).
- **Not sufficient** to call deletion of the stratified files cheap or
  reversible. The deletion decision depends on information this audit cannot
  supply: whether the 25-per-band calibration frame is still wanted for
  evaluation, and whether the P2/A5 format-stratification plan will be pursued.
  That is an owner decision, not a data question.

- **Not verified**: whether the 38 test-set labels for the overlapping pairs
  were produced by an annotator that had the stratified files in view, or fell
  out of the separate top-K hole-filling path. If the former holds, those pairs
  carry a provenance link here that should be recorded before any move.
