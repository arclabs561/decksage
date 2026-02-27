# UX-Driven Annotation Strategy

Last updated: 2026-02-26

This document maps each user-facing task to the annotation data it
requires, identifies gaps, and proposes concrete annotation types to fill
them.  The ordering is by user impact (highest first).

---

## 1. Inventory of UX tasks

The frontend (`frontend/test_search.html`) has four tabs.  The API
(`src/ml/api/api.py`) exposes corresponding endpoints.

| Tab / Endpoint | UX action | What the model must rank |
|---|---|---|
| **Search** (`POST /v1/similar`, `GET /v1/cards/{name}/similar`) | User enters a card, gets top-K similar cards. Use-cases: `substitute`, `synergy`, `meta`. | Pairwise card relevance, conditioned on use-case. |
| **Contextual** (`GET /v1/cards/{card}/contextual`) | User picks a card, sees synergies / alternatives / upgrades / downgrades. | Four separate ranked lists per card, with price/co-occurrence context. |
| **Deck Completion** (`POST /v1/deck/complete`) | User pastes an incomplete deck, gets a completed deck (greedy or beam search). | Next-card-to-add quality given a partial deck context. |
| **Deck Refinement** (`POST /v1/deck/suggest_actions`) | User pastes a deck, gets add/remove/replace/move suggestions. | Per-suggestion quality: relevance, role fit, archetype match, explanation quality. |
| **Feedback** (`POST /v1/feedback`) | User rates a suggestion (0-4) and optionally marks `is_substitute`. | (Itself annotation data -- but currently unstructured.) |
| **Review** (`frontend/review_similarities.html`) | Bulk annotation of similarity pairs. | (Internal tool, not end-user.) |

### Hidden UX surface: deck patching

`POST /v1/deck/apply_patch` applies a structured `DeckPatch` (add/remove/replace/move).
This is the execution layer for suggestions from refinement/completion.
It validates via `src/ml/validation/validators/models.py`.
No annotation type tests whether the *patched deck* is better than the original.

---

## 2. Existing annotation types

| Annotation type | Source files | Schema (key fields) | Covers which UX task? |
|---|---|---|---|
| **Card-pair similarity** (LLM multi-judge) | `annotations/*_llm_annotations.jsonl` | `card1, card2, similarity_score (0-1), similarity_type, is_substitute, card_comparison, graph_features` | Search (substitute use-case) |
| **Card-pair similarity** (hand YAML) | `annotations/hand_batch_*.yaml` | `query, candidates[{card, relevance (0-4), similarity_type, is_substitute, role_match, archetype_context, format_context}]` | Search (all use-cases partially) |
| **Hardcoded ground truth** | `src/ml/annotation/create_ground_truth.py` | `{query: {substitutes, similar_function, synergies, related, irrelevant}}` | Search (substitute + synergy) |
| **User feedback** | `data/annotations/user_feedback.jsonl` | `query_card, suggested_card, task_type, rating (0-4), is_substitute, context` | All tasks (but sparse, unstructured context) |
| **Deck modification judgment** (LLM judge) | `src/ml/evaluation/deck_modification_judge.py` | `DeckModificationJudgment: relevance, explanation_quality, archetype_match, role_fit, + 11 optional dimensions` | Deck refinement |
| **Contextual judgment** (LLM judge) | `src/ml/evaluation/deck_modification_judge.py` | `ContextualJudgment: relevance, reasoning, price_accuracy, synergy_strength, combo_piece_identification, upgrade_path_coherence` | Contextual |
| **Test sets** (unified) | `data/test_set_unified_{game}.json` | `{query: {highly_relevant, relevant, somewhat_relevant, marginally_relevant, irrelevant}}` | Search (evaluation only, no task differentiation) |

---

## 3. Gap analysis

### Gap G1: No annotation distinguishes the three use-cases (substitute / synergy / meta)

The Search tab lets users pick a `use_case`.  But the primary annotation
type (card-pair LLM annotations) produces a single `similarity_score`.
There are `is_substitute` and `similarity_type` fields, but:

- `similarity_type` is a post-hoc label, not a structured multi-axis score.
- There is no `synergy_score` separate from `functional_score` in the test
  set format.
- The unified test sets (`highly_relevant`, ..., `irrelevant`) are a single
  ranking -- the same for all use-cases.

**Consequence**: the evaluation cannot tell whether the model is good at
substitutes but bad at synergies (or vice versa).  Fusion weights optimized
on one axis may degrade another.

### Gap G2: No deck-context annotation for completion

Deck completion (`greedy_complete`, `beam_search`) selects next cards
given a partial deck.  The evaluation (`deck_quality_validation.py`) uses
proxy metrics (mana curve KL, tag diversity, synergy coherence) computed
against reference decks.

No annotation directly answers: "Given this partial deck, is card X a
good addition?"  The `DeckModificationJudgment` schema is close but
requires a full deck + an already-generated suggestion.  There is nothing
for evaluating the *set of completions* as a whole.

### Gap G3: No before/after deck quality annotation

`apply_deck_patch` transforms a deck.  The `DeckPatchResult` reports
validity and errors, but there is no annotation that captures "the
patched deck is better/worse than the original."  `deck_quality.py`
computes `DeckQualityMetrics` (overall_score 0-10), but this is
unsupervised (no human ground truth for what score 7 vs 8 means).

### Gap G4: No contextual-relationship ground truth per category

`ContextualResponse` returns four lists: synergies, alternatives, upgrades,
downgrades.  The `ContextualJudgment` schema exists in the judge code but
there are no persistent annotation files for it.  The hand YAML batches
do not distinguish these four categories.

### Gap G5: No format/archetype-conditioned annotations

Both `SimilarityRequest` and `SuggestActionsRequest` accept `archetype`
and format context.  The hand YAML schema has `archetype_context` and
`format_context` fields, but they are `null` in existing batches.
Evaluation treats all formats/archetypes as one pool.

### Gap G6: No explanation quality ground truth

The API returns `reasoning` strings in contextual and deck suggestion
responses.  The `DeckModificationJudgment` has an `explanation_quality`
field, but no persistent annotation dataset scores explanations.  Without
this, explanation generation cannot be tuned or regressed.

### Gap G7: User feedback is not converted to structured training signal

`convert_feedback_to_annotations.py` and `expand_test_set_from_feedback.py`
exist as scripts, but the feedback schema lacks task-specific structure
(e.g., a deck completion feedback has no `partial_deck` field to reproduce
the context).

---

## 4. Proposed annotation types

### A1: Multi-axis card-pair annotation (fills G1)

Replace the single `similarity_score` with per-axis scores.

```
{
  "card1": str,
  "card2": str,
  "game": str,
  "substitute_score": float,   # 0-1, functional replacement quality
  "synergy_score": float,      # 0-1, how well they work together
  "meta_relevance": float,     # 0-1, co-occurrence in competitive play
  "is_substitute": bool,
  "similarity_type": "functional" | "synergy" | "archetype" | "manabase" | "unrelated",
  "format_context": str | null,     # e.g. "Modern"
  "archetype_context": str | null,  # e.g. "Burn"
  "annotator_id": str,
  "timestamp": str
}
```

**Migration**: existing `similarity_score` maps to `substitute_score`
when `similarity_type == "functional"` or `is_substitute == true`.
For existing annotations where these are mixed, backfill by re-running
the multi-judge pipeline with axis-specific prompts.

**Evaluation change**: the unified test set gains per-axis ground truth.
Metrics become: nDCG@10(substitute), nDCG@10(synergy), nDCG@10(meta).

### A2: Deck-context card judgment (fills G2)

Annotates whether a candidate card is a good addition given a specific
partial deck.

```
{
  "game": str,
  "partial_deck": {              # deck dict (partitions + cards)
    "partitions": [...],
    "metadata": {"archetype": str, "format": str}
  },
  "candidate_card": str,
  "relevance": int,              # 0-4
  "role_filled": str | null,     # e.g. "removal", "threat", "ramp"
  "coverage_delta": int,         # how many new functional tags it adds
  "curve_fit": float | null,     # how well it fits the mana curve
  "reasoning": str,
  "annotator_id": str,
  "timestamp": str
}
```

**Generation**: for each game, take N tournament decks, remove 10-20
cards, and have judges rate the top-K candidates from the completion
engine.  Can reuse the `create_test_cases()` logic from
`deck_quality_validation.py`.

### A3: Deck delta annotation (fills G3)

Annotates whether a set of changes (a `DeckPatch`) improves a deck.

```
{
  "game": str,
  "original_deck": dict,
  "patch": DeckPatch,            # the ops applied
  "patched_deck": dict,
  "delta_quality": int,          # -2 to +2 (much worse .. much better)
  "dimension_deltas": {
    "power_level": int,          # -2 to +2
    "consistency": int,
    "budget": int,
    "meta_positioning": int
  },
  "reasoning": str,
  "annotator_id": str,
  "timestamp": str
}
```

**Use**: regression test for `suggest_actions` and `complete` endpoints.
If a model change causes `delta_quality` to drop across the test set,
block the deploy.

### A4: Contextual category ground truth (fills G4)

Per-card annotation with ground truth for each of the four contextual
categories.

```
{
  "game": str,
  "query_card": str,
  "format": str | null,
  "archetype": str | null,
  "synergies": [
    {"card": str, "score": int, "reasoning": str}  # 0-4
  ],
  "alternatives": [
    {"card": str, "score": int, "reasoning": str}
  ],
  "upgrades": [
    {"card": str, "score": int, "price_delta": float, "reasoning": str}
  ],
  "downgrades": [
    {"card": str, "score": int, "price_delta": float, "reasoning": str}
  ],
  "annotator_id": str,
  "timestamp": str
}
```

**Generation**: extend `generate_contextual_annotations()` in
`deck_modification_judge.py`.  Currently that function exists but
produces no persistent files.  Wire it to write JSONL to
`annotations/contextual/`.

### A5: Format/archetype-conditioned similarity (fills G5)

Not a new schema -- extend A1 with required (non-null) `format_context`
and `archetype_context` fields.  Generate batches stratified by format
and archetype.

**Concrete action**: modify `generate_game_stratified_pairs.py` to
produce pairs grouped by (format, archetype).  When annotating, inject
the constraint "evaluate this pair specifically in the context of
{format} / {archetype}."

### A6: Structured user feedback (fills G7)

Extend `FeedbackRequest` to capture task context for replay.

```python
class FeedbackRequest(BaseModel):
    # ... existing fields ...
    # New: task-specific context for reproducibility
    partial_deck: dict | None = None       # for deck_completion
    full_deck: dict | None = None          # for deck_refinement
    use_case: str | None = None            # substitute|synergy|meta
    format: str | None = None
    archetype: str | None = None
    # New: comparative judgment
    better_than: str | None = None         # "I preferred card X over card Y"
    worse_than: str | None = None
```

**Pipeline**: a nightly job converts structured feedback into A1/A2/A4
annotations (with appropriate confidence downweighting since these are
single-user, non-expert judgments).

---

## 5. Priority order

| Priority | Type | Effort | Blocks |
|---|---|---|---|
| **P0** | A1 (multi-axis pairs) | Medium: new judge prompt + test set schema change | Evaluation per use-case. Currently all three use-cases share one metric. |
| **P1** | A4 (contextual GT) | Low: wire existing `generate_contextual_annotations` to persist JSONL | Contextual tab has no regression test data. |
| **P1** | A6 (structured feedback) | Low: extend `FeedbackRequest`, add `partial_deck`/`full_deck` fields | Feedback cannot be replayed into training without context. |
| **P2** | A2 (deck-context card) | Medium: need partial-deck sampling + judge prompt | Completion quality is evaluated only by unsupervised proxies. |
| **P2** | A5 (format/archetype) | Low: stratified pair generation + prompt injection | Format-specific tuning has no data. |
| **P3** | A3 (deck delta) | High: requires running the full suggest+patch pipeline per test case | Deck refinement has no end-to-end regression test. |

---

## 6. What this implies for training and testing

### Training

1. **Multi-objective loss**: with A1 annotations, training can optimize
   separate objectives for substitute vs synergy retrieval.  The fusion
   weights (`WeightedLateFusion`) should be per-use-case, not global.
   Current codebase already supports per-request `weights` in
   `SimilarityRequest` -- the missing piece is per-use-case default
   weights tuned on per-use-case ground truth.

2. **Deck-conditioned scoring**: A2 annotations enable training a
   context-aware reranker that takes (partial_deck, candidate_card) as
   input rather than (card, card).  The existing `train_reranker.py`
   operates on pairwise data -- it would need a new feature set that
   includes deck composition features.

3. **Feedback loop**: A6 structured feedback lets the system
   automatically generate hard negatives from user rejections.  A card
   the user rated 0 in a specific deck context is a confirmed negative
   for A2-style training.

### Testing / Evaluation

1. **Per-use-case metrics**: the eval harness should report
   nDCG@10(substitute), nDCG@10(synergy), nDCG@10(meta) separately.
   A regression in one should not be masked by improvement in another.

2. **Deck completion regression suite**: A2 + A3 annotations create a
   deterministic test: given partial deck P, the completion engine
   should produce cards that score >= threshold on the A2 judgments,
   and the resulting full deck should score positive on A3 delta.

3. **Contextual discovery precision**: A4 annotations enable P@K per
   category (synergies, alternatives, upgrades, downgrades).  Currently
   contextual discovery has no quantitative eval.

4. **Format-stratified reporting**: A5 annotations allow per-format
   metric breakdowns.  A model that is good at Modern but bad at
   Commander should be visible in the report.

---

## 7. Immediate next steps

1. Implement A1 prompt changes in the multi-judge pipeline
   (`scripts/annotation/run_multi_judge_batch.py`): add axis-specific
   scoring instructions.  Backfill one game (start with yugioh, the
   current default) with ~500 pairs.

2. Extend `FeedbackRequest` in `src/ml/api/feedback.py` with the A6
   fields (`partial_deck`, `full_deck`, `use_case`, `format`,
   `archetype`).  Ship to production so feedback starts accumulating
   context.

3. Wire `generate_contextual_annotations()` in
   `src/ml/evaluation/deck_modification_judge.py` to persist JSONL
   output in `annotations/contextual/`.  Run for 50 cards per game.

4. Update the eval harness to report per-use-case nDCG when multi-axis
   ground truth (A1) is available.
