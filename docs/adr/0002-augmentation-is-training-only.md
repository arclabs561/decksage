# ADR-0002: augmentation is training-only

**Status**: proposed
**Date**: 2026-10-22

## Context

Labels are expensive and sparse: about 89K judgments over 5,895 unique pairs,
with a median of one graded pair for a Magic query. Augmentation is attractive
for training, and it is tempting to also strengthen the evaluation set.

Those are different operations. A training augmentation teaches invariance the
model should have. A test augmentation changes the distribution being measured,
so the resulting number no longer describes production behavior. Adding
paraphrased or synthetic pairs to an eval set raises scores for reasons that do
not transfer to real queries.

There is also a leakage trap specific to this repository: evaluation candidates
were selected by the model's own top-k, so any synthetic negative generated from
the same candidates inherits that selection.

## Decision

- Training may use: symmetric pairs, attribute-matched hard negatives (same mana
  value, type, color, rarity, low judged relevance), role-swapped pairs within a
  game, and LLM-generated paraphrases of oracle text marked `synthetic: true`
  with the generating model and prompt version.
- Every synthetic or augmented pair records `_provenance.augmentation` naming
  the transform, the source pair, and the generator.
- Augmented pairs never enter `data/test_sets/`. The hole-fill writer refuses
  them, and the merge path rejects `synthetic: true`.
- Test-time robustness is measured on slices, not on an augmented headline:
  long card names, non-Latin names, missing oracle text, extreme mana values.
  A slice may lower the score; that is information, not a regression.
- A synthetic pair never outranks a human label for the same pair; if both
  exist, the human label wins and the synthetic one is dropped.

## Rejected

- Mixing paraphrases into eval to increase coverage. Coverage is what hole
  filling was for, and that already has a selection bias to manage.
- Random negatives. In a dense graph most random cards are connected, so the
  negative teaches nothing (the BPR result in experiment 0012).
- Paraphrasing only the query side. It teaches name matching and amplifies the
  dominant failure mode in the failure taxonomy.

## Consequences

- Training data grows without changing the meaning of the evaluation number.
- Synthetic provenance adds storage but makes a later contamination audit
  possible.
- Robustness claims need slice-level reporting, which costs a small extra
  evaluation pass.

## See also

`docs/AUGMENTATION.md` holds the transformation catalog: text, art, and graph
analogues of crop, flip, jitter and occlusion, with what each preserves and the
failure mode when applied to the wrong task. It also names the one permitted
non-training use, the invariance probe that tests a judge rather than scoring
it against its own paraphrases.
