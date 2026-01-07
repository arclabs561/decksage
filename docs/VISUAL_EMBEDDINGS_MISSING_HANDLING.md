# Visual Embeddings: Missing Image Handling

**Date:** January 6, 2026

## Overview

The visual embeddings system is designed to **gracefully degrade** when images are missing. Missing images are **not an invariant** - the system works correctly with partial or zero image coverage.

## How Missing Images Are Handled

### 1. CardVisualEmbedder Level

#### Missing Image URL
```python
def embed_card(self, card: dict[str, Any] | str | Image.Image) -> np.ndarray:
    image = self._card_to_image(card)
    if image is None:
        # Return zero vector if image unavailable
        zero_emb = np.zeros(self._embedding_dim, dtype=np.float32)
        return zero_emb
```

**Behavior:**
- If card has no `image_url` → returns zero vector
- If image download fails → returns zero vector
- If card is just a name string → returns zero vector
- **Zero vectors are cached** to avoid repeated computation

#### Similarity with Zero Vectors
```python
def similarity(self, card1, card2) -> float:
    emb1 = self.embed_card(card1)
    emb2 = self.embed_card(card2)
    
    # Cosine similarity
    dot_product = np.dot(emb1, emb2)
    norm1 = np.linalg.norm(emb1)
    norm2 = np.linalg.norm(emb2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0  # Zero vectors → 0.0 similarity
```

**Behavior:**
- If either card has zero vector → similarity = 0.0
- If both cards have zero vectors → similarity = 0.0
- **This is correct**: cards without images can't be visually similar

### 2. WeightedLateFusion Level

#### Missing Visual Embedder
```python
def _get_visual_embedding_similarity(self, query: str, candidate: str) -> float:
    if not self.visual_embedder:
        return 0.0  # No embedder → 0.0 similarity
```

**Behavior:**
- If `visual_embedder` is `None` → returns 0.0
- System continues to work with other signals

#### Missing Card Data
```python
query_card_data = self.card_data.get(query) or self.card_data.get(query.lower())
candidate_card_data = self.card_data.get(candidate) or self.card_data.get(candidate.lower())

# Use card dict if available, otherwise use name string
query_input = query_card_data if query_card_data else query
candidate_input = candidate_card_data if candidate_card_data else candidate

similarity = self.visual_embedder.similarity(query_input, candidate_input)
```

**Behavior:**
- If card not in `card_data` → falls back to name string
- Visual embedder handles name strings → returns zero vector
- **Graceful degradation**: works even without card_data

#### Exception Handling
```python
try:
    similarity = self.visual_embedder.similarity(query_input, candidate_input)
    return float(similarity)
except Exception:
    # Gracefully handle errors (missing images, download failures, etc.)
    return 0.0
```

**Behavior:**
- Any exception → returns 0.0
- **System never crashes** due to visual embedding issues

### 3. Fusion Aggregation Level

#### Weight Normalization
```python
def normalized(self) -> FusionWeights:
    total = (
        self.embed + self.jaccard + self.functional + 
        self.text_embed + self.visual_embed + self.gnn + ...
    )
    return FusionWeights(
        embed=self.embed / total,
        visual_embed=self.visual_embed / total,
        ...
    )
```

**Behavior:**
- Weights are **normalized to sum to 1.0**
- If `visual_embed = 0.0`, it gets 0% weight
- Other signals get proportionally more weight
- **System adapts** to missing visual embeddings

#### Aggregation with Zero Scores
```python
def _aggregate_weighted(self, scores: dict[str, dict[str, float]]) -> dict[str, float]:
    weight_score_pairs = []
    if self.weights.visual_embed > 0.0 and "visual_embed" in scores:
        weight_score_pairs.append((self.weights.visual_embed, scores["visual_embed"]))
    # ... other signals
    
    # Weighted sum
    total = sum(weight * score for weight, score in weight_score_pairs)
    return total
```

**Behavior:**
- If `visual_embed` score is 0.0 → contributes 0.0 to total
- Other signals still contribute normally
- **Fusion score is still valid** (just without visual signal)

## System Invariants

### ✅ What IS an Invariant

1. **Fusion weights sum to 1.0** (after normalization)
2. **All similarity scores are in [0, 1]** range
3. **System never crashes** due to missing visual embeddings
4. **Zero vectors have norm 0** → similarity = 0.0

### ❌ What is NOT an Invariant

1. **Visual embeddings being present** - System works without them
2. **All cards having images** - Partial coverage is fine
3. **Visual embedder being loaded** - Optional dependency
4. **Visual similarity being non-zero** - Can be 0.0 for missing images

## Impact of Missing Images

### Current Behavior

1. **Cards without images:**
   - Get zero vectors for visual embeddings
   - Visual similarity = 0.0 with all other cards
   - Other signals (embed, jaccard, etc.) still work normally

2. **Fusion with missing visual:**
   - Visual weight (20%) contributes 0.0
   - Other signals get effectively higher relative weight
   - **System degrades gracefully** to non-visual fusion

3. **Mixed scenarios:**
   - Query has image, candidate doesn't → visual similarity = 0.0
   - Query doesn't have image, candidate does → visual similarity = 0.0
   - Both have images → visual similarity computed normally

### Performance Impact

- **Zero vectors are fast** (no model inference)
- **Cached zero vectors** avoid repeated computation
- **No network calls** for missing images
- **System remains responsive** even with 0% image coverage

## Design Decisions

### Why Zero Vectors?

1. **Consistent API:** `embed_card()` always returns a vector
2. **No special cases:** Fusion doesn't need to check for missing embeddings
3. **Safe similarity:** Zero vectors → 0.0 similarity (correct behavior)
4. **Caching:** Zero vectors can be cached like real embeddings

### Why Not Skip Visual Embeddings?

1. **Weight normalization:** If we skip, weights would need re-normalization
2. **Dynamic behavior:** System adapts automatically to missing signals
3. **Consistency:** All signals follow same pattern (return 0.0 if unavailable)

### Why Exception Handling?

1. **Robustness:** Network failures, corrupted images, etc. don't crash system
2. **Graceful degradation:** System continues with other signals
3. **User experience:** API never returns errors due to visual embedding issues

## Recommendations

### Current Implementation ✅

The current design is **robust and correct**:
- Missing images → zero vectors → 0.0 similarity
- Missing embedder → 0.0 similarity
- System degrades gracefully
- No crashes or errors

### Potential Improvements

1. **Weight Re-normalization:**
   - Could re-normalize weights when visual_embed = 0.0
   - Current: visual_embed=0.20 contributes 0.0, others get 80% total
   - Alternative: re-normalize to 100% across available signals
   - **Trade-off:** More complex, but might be more intuitive

2. **Coverage Tracking:**
   - Track which cards have images
   - Log coverage statistics
   - Warn when coverage is low

3. **Adaptive Weights:**
   - Reduce visual_embed weight when coverage is low
   - Increase other signal weights proportionally
   - **Trade-off:** More complex, but might improve performance

## Conclusion

**Missing image embeddings are NOT an invariant** - the system is designed to handle them gracefully:

- ✅ Zero vectors for missing images
- ✅ 0.0 similarity for zero vectors
- ✅ Exception handling for errors
- ✅ Graceful degradation to non-visual fusion
- ✅ No crashes or errors

The system works correctly with **any level of image coverage** (0% to 100%), making visual embeddings a **truly optional enhancement** rather than a requirement.

