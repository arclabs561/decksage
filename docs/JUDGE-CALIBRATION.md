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
2. **Agreement ceiling.** Krippendorff alpha per field. Synergy and
   substitutability sit near 0.2 and 0.4, which caps every downstream number.
3. **Invariance.** Order swap should be near-exact for a symmetric score;
   paraphrase and boilerplate stripping should not move the score much.
   Invariance is necessary, not sufficient: a judge can be perfectly invariant
   and systematically wrong.

## Stage 1: 50-100 human pairs

Sample actively by judge-score decile plus the highest-disagreement items, and
keep about 30 random pairs to check selection bias. Have three annotators cover
30 items to estimate rater variance, which is the ceiling every later number is
measured against. At n=50-100 and r about 0.8, the honest precision is about
+/-0.10 on Spearman; a kappa can only be called roughly 0.6-0.8.

Then fit a monotone (isotonic) map from judge score to human score with
cross-fitting, and report out-of-fold error. Propagate aggregates to the full
judged set with prediction-powered inference rather than assuming the judge is
calibrated ([PPI](https://www.science.org/doi/10.1126/science.adi6000),
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
