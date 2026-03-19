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

## Training Data Provenance

When consuming annotation data for training:
- **Mode-aware routing**: substitution pairs get substitution instructions, synergy pairs get synergy instructions. Never mix modes under a single instruction prefix.
- **Graded labels**: use continuous similarity scores (0.0-1.0) from annotations, not binary 1.0/0.0.
- **Graph edges are synergy signal**: co-occurrence edges must never be used as substitution training data. Route to synergy/completion instructions only.
- **Record data breakdown**: log exact counts per mode (substitution/synergy/meta) and per source (annotations/graph/pairs) in the experiment YAML.

---

## Evaluation

- `eval_per_mode.py` is the canonical nDCG evaluator. When a sweep script has its own eval, verify results against `eval_per_mode.py` before reporting.
- Always report per-game metrics. A single "overall" number hides that YuGiOh nDCG is 0.554 while Magic is 0.156.
- Contextual recall: measure at both embedding level (`sweep_contextual_weights.py`) and API level (`eval_contextual.py`). They differ significantly (38% vs 8% historically).

---

## Bespoke Audit Commands

- `/qa` -- Real-world quality audit
- `/arch-review` -- Architecture audit
- `/training` -- Training pipeline health check
- `/eval` -- Evaluation and feedback loop audit
- `/dataset` -- Data extraction and dataset improvement
