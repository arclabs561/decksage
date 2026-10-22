# Augmentation catalog

Card-domain analogues of the image transforms that made CNNs robust: crop,
flip, jitter, occlusion. Each entry states what it preserves, which task it is
valid for, and how to detect that it changed the label by accident.

The governing decision is ADR-0002: augmentation is training-only, carries
`_provenance.augmentation`, and is refused by the evaluation merge. The one
exception is the invariance probe described in `JUDGE-CALIBRATION.md`, which
uses augmentation to test the judge rather than to score it.

## Text and attributes

| Transform | Image analogue | Preserves | Valid for | Failure if misused |
|---|---|---|---|---|
| Oracle-text paraphrase | rotation | function | training, invariance probe | model learns the paraphraser's phrasing |
| Truncate rules text to first N words | center crop | rough role, not details | training with a `truncated` flag | turns a combo piece into a generic card |
| Drop one attribute (type, cost, colour) | channel dropout | role at coarse grain | training | removes the signal that separates near-duplicates |
| Normalise formatting, unify reminder text | resize | semantics | training, preprocessing | none, but normalise train and eval together |
| Mask the card name in text | occlusion | function without name | training | cannot be evaluated with names present |
| Translate oracle text | colour jitter | rules meaning | training, robustness slice | translation errors become label noise |
| Swap flavour text only | background change | everything | training | wasted compute if flavour is unused |
| Shuffle ability order | pixel permutation | abilities present, not priority | **invalid** | order carries meaning and cost structure |

Name masking is the highest-value text transform for this project, because the
failure taxonomy names text token overlap as the top failure mode: the reranker
matches shared words in names. Training with names masked forces function.

## Art

| Transform | Preserves | Valid for | Failure if misused |
|---|---|---|---|
| Random resized crop of the art box | style, palette, subject | visual embedding training | cropping into the text box changes what is being compared |
| Horizontal flip | style | visual training | asymmetric compositions and watermarks |
| Colour jitter, saturation | subject | visual training | colour identity matters in some games' art |
| Occlusion patch | coarse style | visual training | hides the subject entirely |
| Compression artefacts | style | robustness slice | none, if measured separately |
| Frame and set-symbol removal | art only | visual training | removes the printing identity you may want |

For art similarity, crop and flip are safe because the target is style, not
legibility. For function similarity they are irrelevant, which is why the
visual tower should never be the only signal for a substitute query.

## Graph and labels

| Transform | Preserves | Valid for | Failure if misused |
|---|---|---|---|
| Edge dropout | structure at coarse grain | embedding training | removes the only link for cold cards |
| Degree-preserving rewiring | degree distribution | negative sampling | creates edges that never co-occurred |
| Subgraph sampling | local neighbourhood | scalable training | biases toward hubs |
| Attribute-matched hard negatives | label | contrastive training | none, this is the strongest negative sampler |
| Symmetric pair duplication | label | contrastive training | double-counts in any mean |

Attribute-matched negatives (same cost, type, colour, rarity, low judged
relevance) are the equivalent of hard-negative mining in vision: they force the
model to use function instead of surface statistics.

## What augmentation cannot do

It cannot create truth. A model trained on paraphrases learns invariance to the
paraphraser, and a judge scored on its own augmented pairs measures
self-consistency. Neither substitutes for the audited anchor set.

## Measurement

Every transform is evaluated the same way: train or probe with it, then compare
on (a) the frozen eval slice, (b) the invariance probe, and (c) the robustness
slices (long names, non-Latin names, missing rules text, extreme costs). A
transform that improves the headline but worsens a robustness slice is a
regression with better marketing.
