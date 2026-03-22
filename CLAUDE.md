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
- Never trust sweep-internal eval for absolute numbers. Inline eval inflated LightGCN from 0.095 to 0.545 (experiment 0004).
- Always report per-game metrics. A single "overall" number hides domain-specific results.
- **Every eval result must include dataset fingerprint**: card count, edge count, annotation count, test set version. The dataset grows concurrently with experiments -- results are only comparable at the same data snapshot.
- **Test set deduplication is mandatory**: multi-model/multi-variant IAA produces multiple annotations per (query, candidate) pair. These MUST be consensus-averaged (not stored as separate entries) before nDCG evaluation. Duplicate annotations inflate nDCG by 50-90%. The `annotate_diverse_pairs.py` now deduplicates at write time; run `dataset_diagnostics.py` to verify.
- **Run diagnostics before trusting any eval number**: `uv run scripts/evaluation/dataset_diagnostics.py --all-games` checks for duplicate edges, annotation duplication, edge imbalance, and metadata gaps.
- Contextual recall: measure at both embedding level (eval_per_mode.py offline) and API level (eval_contextual.py). They differ significantly.

### True Baselines (post-dedup, 2026-03-22)

These are the honest numbers after fixing the 43-76% annotation duplication:
- Magic v5_fused: sub nDCG **0.045**, contextual recall 0.274
- Pokemon v5_fused: sub nDCG **0.024**, coverage 96.4%
- YuGiOh MetaPath2Vec: sub nDCG **0.157**, contextual recall 0.711
- All prior session nDCG numbers were inflated by test set duplication.

---

## Bespoke Audit Commands

- `/qa` -- Real-world quality audit
- `/arch-review` -- Architecture audit
- `/training` -- Training pipeline health check
- `/eval` -- Evaluation and feedback loop audit
- `/dataset` -- Data extraction and dataset improvement
