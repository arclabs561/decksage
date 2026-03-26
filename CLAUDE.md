# CLAUDE.md -- DeckSage

Project-specific rules for DeckSage. Inherits from `~/Documents/dev/CLAUDE.md`.

---

## Experiment Discipline

Every ML/DS experiment must be logged in `data/experiments/` before results are reported.

### Before running

Create `data/experiments/NNNN_short_name.yaml` with at minimum:
- `id`, `date`, `title`, `game`
- `hypothesis`: one sentence -- what you expect and why
- `method.script`, `method.args`: exact command to reproduce
- `data.training.source`, `data.training.count`: what data, how much

### After running

Fill in:
- `results`: all measured metrics (use "not recorded" if missing, never guess)
- `conclusion`: one sentence -- did the hypothesis hold? what next?
- `artifacts`: paths to produced files

### Rules

- Next ID: check `ls data/experiments/*.yaml | tail -1` and increment.
- Update `data/experiments/SUMMARY.md` table with the new row.
- Never backfill metrics you didn't measure. "not recorded" is honest.
- The legacy `experiment_log.tsv` is kept for backward compat but YAML is canonical.
- Commit experiment files with the code/training changes, not separately.

### Schema reference

See `data/experiments/README.md` for the full YAML schema.

---

## Train/Eval Separation (hard rule)

**Annotations are for evaluation only. Training uses self-supervised data only.**

Training sources (OK for embedding training):
- Co-occurrence pairs from deck JSONL files (self-supervised)
- Enriched edges (PPMI, oracle text similarity, propagated)
- Commander/Archidekt deck co-occurrence
- Set, precon, keyword co-occurrence
- Card attribute features (type, mana cost, colors)

Evaluation sources (NEVER in training):
- `data/test_sets/annotated_*_v2.json` -- nDCG evaluation
- `data/annotations/*_v4.json` -- IAA quality measurement
- `data/annotations/diverse_checkpoint_*.jsonl` -- multi-model IAA
- `data/annotations/diverse_pairs_*.jsonl` -- diverse pair judgments
- `data/graphs/*_annotation_edges.edg` -- DO NOT feed to MetaPath2Vec
- `data/graphs/*_diverse_annotation_edges.edg` -- DO NOT feed to MetaPath2Vec

Why: any annotation-to-training feedback loop makes the evaluation less independent. The model should improve from better self-supervised signal (more decks, richer edge types, better negative sampling), not from memorizing annotated pairs.

The `export_annotation_edges.py` script exists for potential future use but its output must NOT be connected to `train_metapath2vec.py` or any other training script.

## Training Data Provenance

- **Mode-aware routing**: substitution pairs get substitution instructions, synergy pairs get synergy instructions. Never mix modes under a single instruction prefix.
- **Graded labels**: use continuous similarity scores (0.0-1.0) from annotations, not binary 1.0/0.0.
- **Graph edges are synergy signal**: co-occurrence edges must never be used as substitution training data. Route to synergy/completion instructions only.
- **Record data breakdown**: log exact counts per mode (substitution/synergy/meta) and per source (annotations/graph/pairs) in the experiment YAML.

---

## Evaluation

- `eval_per_mode.py` is the canonical evaluator. Use `--json` for machine-readable output, `--compare` for multi-embedding comparison tables, `--all-games` for all games.
- **After deploying new embeddings**, grep all scripts for the old embedding name and update defaults: `grep -r 'old_name' scripts/`. Six scripts had stale v4/v5 defaults when v7 was deployed.
- Never trust sweep-internal eval for absolute numbers. Inline eval inflated LightGCN from 0.095 to 0.545 (experiment 0004). Sweep scripts must call `eval_per_mode.py` as a subprocess -- never reimplement ranking logic.
- **Multi-seed validation mandatory**: any claimed nDCG improvement must be validated across 3+ seeds. PecanPy training has std ~0.001 but outliers of +0.008 observed (deployed v7 was >4 sigma above mean). Single-run comparisons are unreliable.
- **Link prediction != similarity quality**: GNN approaches using link prediction or reconstruction loss produce embeddings near-random for card similarity (confirmed: LightGCN exp 0004, HGT exp 0054). Use contrastive or similarity-preserving objectives.
- Always report per-game metrics. A single "overall" number hides domain-specific results.
- **Every eval result must include dataset fingerprint**: card count, edge count, annotation count, test set version. The dataset grows concurrently with experiments -- results are only comparable at the same data snapshot.
- **Test set deduplication is mandatory**: multi-model/multi-variant IAA produces multiple annotations per (query, candidate) pair. These MUST be consensus-averaged (not stored as separate entries) before nDCG evaluation. Duplicate annotations inflate nDCG by 50-90%. The `annotate_diverse_pairs.py` now deduplicates at write time; run `dataset_diagnostics.py` to verify.
- **Run diagnostics before trusting any eval number**: `uv run scripts/evaluation/dataset_diagnostics.py --all-games` checks for duplicate edges, annotation duplication, edge imbalance, and metadata gaps.
- **Graph schema changes break downstream scripts**: `IncrementalCardGraph` edge keys are 3-tuples `(card1, card2, source_type)`. Scripts that unpack as 2-tuples will crash silently. After schema changes, test the export pipeline end-to-end.
- **Run annotation QC after adding annotations from a new model**: `uv run scripts/annotation/multi_model_annotate.py qc --game <game>` catches zero-score deflation and score inflation.
- **Condensed nDCG is the primary ranking quality metric** (Sakai 2007). Standard nDCG is systematically biased downward when annotation coverage is sparse -- it measures coverage, not ranking quality. When standard nDCG converges to condensed nDCG (gap < 0.05), annotation coverage is saturated *for the current embedding* and the metric reflects true ranking quality.
- **Saturation is embedding-specific AND retrieval-method-specific**: new embeddings reshuffle top-K, surfacing unjudged cards that may be better matches. Changing retrieval method (cosine -> fusion) also surfaces entirely different candidates. "Saturated" means the current method's top-K is fully judged. Exp 0060: switching substitute from cosine to fusion created 24K new holes; filling 5K moved nDCG from 0.031 to 0.035 (gap 0.238). The outer loop is: fill holes -> get true quality -> train better embedding OR switch method -> fill new holes -> repeat.
- **Unified graph DB uses short game codes**: `IncrementalCardGraph` stores game as MTG/PKM/YGO, not magic/pokemon/yugioh. Use `graph_loading.GAME_DB_CODES` for mapping. Passing full game names to `query_edges(game=...)` silently returns 0 edges.
- **Prioritize eval-time hole filling** (`fill_eval_holes.py`) over random pair annotation. Filling top-K holes has 5-10x the nDCG impact per annotation dollar. Monitor the standard-vs-condensed gap: when it closes for the current embedding, train a new one and re-fill.
- **Use `--model multi`** (multi_model_annotate.py cascade) as default annotation backend. Groq 70B + Cerebras 235B at $0.40/1000 pairs. Ollama only as offline fallback (54% zero scores with llama3.2). OpenRouter budget-limited.
- **Annotation provenance is mandatory**: every annotation must include `_provenance` dict (backend, model, prompt_version, temperature). The merge step must preserve `_provenance` -- verify with `repair_annotations.py audit`. Annotations without provenance are untrustworthy.
- **Never use 8B models for calibrated scoring** (corr=-0.076 vs IAA ground truth). Minimum viable: 70B. Enriched prompt with calibration anchors is mandatory for models < frontier.
- **Background batch race condition**: do not start annotation batches while test set cleanup is pending. Batches started before cleanup overwrite cleaned files. Always commit cleanup before launching new batches.
- Contextual recall: measure at both embedding level (eval_per_mode.py offline) and API level (eval_contextual.py). They differ significantly.

### True Baselines (SATURATED, 2026-03-25)

Best embeddings per game (canonical eval_per_mode.py, all top-10 holes filled, exp 0058-0059):
- Magic: **v7_spectral_mu35 sub nDCG 0.525** (condensed 0.527, gap 0.002) [SATURATED]
- Pokemon: **v7_fused sub nDCG 0.437** (condensed 0.438, gap 0.001) [SATURATED]
- YuGiOh: **v7_spectral_mu3 sub nDCG 0.478** (condensed 0.482, gap 0.004) [SATURATED]
- Total annotations: Magic 36K / Pokemon 25K / YuGiOh 27K (~89K total, ~$23)
- Saturation is embedding-specific: new embeddings will create new holes to fill
- All nDCG numbers before 2026-03-22 were inflated by test set duplication.

---

## Bespoke Audit Commands

- `/qa` -- Real-world quality audit
- `/arch-review` -- Architecture audit
- `/training` -- Training pipeline health check
- `/eval` -- Evaluation and feedback loop audit
- `/dataset` -- Data extraction and dataset improvement
