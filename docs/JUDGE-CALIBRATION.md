# Judge calibration

How to know whether the 0-1 judgments are usable, and what public data can and
cannot establish.

## The claim we are allowed to make

Public benchmarks (STS-B, SICK, STS12-16) contain human graded similarity on
everyday English. Agreement with them supports one sentence: "this judge ranks
general-English paraphrases at least this faithfully". It does not license the
0-1 number as a human similarity rate, does not transfer to card vocabulary, and
says nothing about a decision threshold.

Evidence that domain transfer is the risk, not a footnote: eight LLM judges on
biomedical relation extraction scored below 50% accuracy until the tasks were
adapted ([arXiv:2506.00777](https://arxiv.org/html/2506.00777v1)).

## Stage 0: free checks, no human labels

Run `scripts/evaluation/judge_audit.py --game <game>`.

1. **Resolution.** Histogram, tie rate, effective distinct values, and standard
   deviation per score field. Score compression is the documented failure mode
   of scalar judges: scores cluster near the top, ties dominate, and ranking
   resolution collapses ([arXiv:2509.24678](https://arxiv.org/html/2509.24678)).
   If sd < 0.05 or one 0.1 bin holds most of the mass, fix the prompt or use
   per-dimension subscores before buying labels.
2. **Agreement.** Estimate inter-annotator agreement per field on a documented
   shared sample. Judge agreement is a diagnostic and is not an upper bound on
   accuracy against independent human judgments.
3. **Invariance.** Order swap should be near-exact for a symmetric score;
   paraphrase and boilerplate stripping should not move the score much.
   Invariance is necessary, not sufficient: a judge can be perfectly invariant
   and systematically wrong.

## Gate: structural contradictions block scoring

`src/ml/evaluation/label_gate.py` screens a test set with the rules in
`scripts/annotation/screen_contradictions.py` before a metric is computed. Three
rules block: a card judged against itself, a creature judged against a
Trainer/Energy/Spell/Trap as a substitute, and different Pokemon evolution stages
treated as substitutes. A cross-type substitute, a duplicate round, a bucket
mismatch or an evidence-poor record is reported but not blocked: some are
legitimate and the rest need a human.

`calibrate_fusion_weights.py` runs the gate and exits without calibrating when a
blocking hit exists. `--allow-contradictions` calibrates anyway and logs the
override; using it means the resulting weights describe labels the repository's
own metadata contradicts.

Current state (2026-10-29): the canonical test sets pass the gate. The repair
removed 162 Magic, 197 Pokemon (126 evolution, 66 kind, 5 self) and 263 Yu-Gi-Oh
structurally contradictory judgments, archived the originals under
`data-local/test-set-archive-20261029/` and recorded both hashes in
`data/test_sets/REPAIR-LEDGER.json`.

Passing the gate means no *structural* contradiction remains against shipped card
metadata. It does not mean the labels are correct: duplicate rounds, bucket
mismatches and evidence-poor records are still reported, and a judgment can be
wrong in ways metadata cannot express.

## Stage 1: 50-100 human pairs

Prepare a local, blinded review batch with:

```sh
uv run scripts/annotation/prepare_human_review.py --output-dir data-local/review-batch
```

`review.json` contains the card contexts and task but no judge scores; the
separate selection ledger contains the scores and source hashes and must stay
hidden until independent review is complete. A blank score is unreviewed,
not zero. Reviewers should record identity, a 0–1 task-specific score and
reasoning, or leave the score blank when the available context is insufficient.
The sample combines a random pair-task reserve with score-stratified cases;
it is not a representative gold set. It excludes explicitly failed and marked
synthetic records, but missing provenance remains unknown.

Sample by game, task and judge-score band, plus high-disagreement items, and
reserve a separately drawn random sample to assess selection bias. Have
multiple annotators independently review a shared subset, with an explicit
rubric and adjudication protocol. Report uncertainty from the actual sample;
do not assume a universal precision or agreement ceiling.

If sample size and score coverage support it, evaluate a monotone calibration
map with a held-out or cross-fitted assessment. Do not extrapolate beyond the
reviewed distribution. Prediction-powered inference would require its sampling
and inference assumptions to be justified before using it for corpus estimates
([PPI](https://www.science.org/doi/10.1126/science.adi6000),
[PPI++](https://arxiv.org/abs/2311.01453)).

## Known biases to test for

| Bias | Test | Source |
| --- | --- | --- |
| Score compression, ties | resolution audit | [2509.24678](https://arxiv.org/html/2509.24678) |
| Rubric sensitivity | same pairs, two rubric wordings | [2506.22316](https://arxiv.org/abs/2506.22316) |
| Anchoring, familiarity | with and without exemplar anchors; boilerplate stripped | [2405.01724](https://arxiv.org/html/2405.01724) |
| Position/order | swap A and B; asymmetry should be ~0 | [2306.05685](https://arxiv.org/html/2306.05685) |
| Verbosity/length | length-matched pairs | [2310.10076](https://arxiv.org/abs/2310.10076) |
| Self-preference | judge family vs candidate text provenance | [2404.13076](https://arxiv.org/abs/2404.13076) |

## What not to do

- Do not calibrate a scalar similarity judge from pairwise-preference
  benchmarks (Arena-Hard, RewardBench, JudgeBench). Pairwise and pointwise
  judging are distinct skills.
- Do not trust ensemble agreement as correctness. Correlated model families
  agree and are both wrong; treat disagreement as a diagnostic only.
- Do not report a threshold decision without about 30 labels within +/-0.1 of
  that threshold.

## Cheap calibration runs

Calibration work is high-volume and low-stakes per call, so run it on the cheap
route rather than the frontier one. Credentials come from 1Password at process
start; nothing is written to disk.

```sh
# OpenRouter key resolved from the vault, exported only to this process
op run --no-masking --env-file=/dev/null -- \
  env OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash \
  uv run scripts/evaluation/judge_probe.py --pairs data/audit/anchors.jsonl

# or inject a single reference
OPENROUTER_API_KEY="$(op read 'op://Private/OpenRouter/api key')" \
  uv run scripts/evaluation/judge_probe.py --pairs data/audit/anchors.jsonl
```

At roughly 300 input and 100 output tokens per pair, a 500-pair probe costs
about $0.02 to $0.05 on a flash-tier model. That is cheap enough to run the
whole Stage 0 suite on every prompt change instead of once.

### Three techniques, in increasing order of what they prove

1. **Rubric alignment (cheap, weakest).** Score the same 200 pairs under two
   rubric wordings and one exemplar-anchored variant. Keep the variant only if
   score variance drops without rank correlation to the anchor set dropping.
   Proves: the prompt is not adding avoidable noise.
2. **Cross-family agreement (cheap, diagnostic).** Run two or three model
   families on the same pairs; report per-item spread. Treat spread as an
   uncertainty feature, never as truth. Proves: which pairs are unstable.
3. **Anchored calibration (needs labels).** Fit a monotone map from judge score
   to human score, assess it out of sample, and quantify uncertainty. This
   estimates calibration only for the reviewed population and score range.

### Augmentation as a calibration probe, not a label source

Augmented pairs are useful here for one narrow purpose: an invariance test. If
paraphrasing a card's rules text while keeping its function moves the judge's
score more than a small amount, the judge is reading surface form. That is a
cheap, falsifiable check.

What augmentation must not become is ground truth. Per ADR-0002, synthetic
pairs are training-only, carry `_provenance.augmentation`, and are refused by
the evaluation merge. A judge scored against its own paraphrases measures
self-consistency, not correctness.

*Implementation status: `scripts/evaluation/judge_probe.py` implements the
resolution, order-swap and two-variant rubric checks with a `--dry-run` fake
scorer. It still needs an anchor file at `data/audit/anchors.jsonl`, and the
exemplar-anchored third variant is not built, so the rubric gate falls back to
variant-to-variant correlation until human labels exist.*
