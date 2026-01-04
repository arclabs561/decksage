# Integration Guide: Text Embeddings and Beam Search

**Date**: November 10, 2025
**Status**: Implementation files created, ready for integration

---

## Files Created

1. ✅ `src/ml/similarity/text_embeddings.py` - Text embeddings module
2. ✅ `src/ml/similarity/fusion_integration.py` - Fusion integration helpers
3. ✅ `src/ml/deck_building/beam_search.py` - Beam search implementation
4. ✅ `src/ml/tests/test_text_embeddings.py` - Tests

---

## Step 1: Install Dependencies

```bash
# When iCloud allows file operations
uv add sentence-transformers
uv add "torch>=2.0.0" "torch-geometric>=2.4.0"  # For future GNN work
```

---

## Step 2: Integrate Text Embeddings into Fusion

### Find Fusion Code

When files are readable, locate fusion implementation:

```bash
grep -n "def.*fusion\|weight\|aggregat" src/ml/similarity/similarity_methods.py
```

### Integration Pattern

In `src/ml/similarity/similarity_methods.py`, add:

```python
from ..similarity.text_embeddings import get_text_embedder
from ..similarity.fusion_integration import (
    compute_fusion_with_text,
    get_default_weights_with_text,
)

# In your fusion function:
def compute_fusion_similarity(card1, card2, method="fusion", weights=None):
    # ... existing code for embed, jaccard, functional ...

    similarities = {
        "embed": embed_sim,
        "jaccard": jaccard_sim,
        "functional": functional_sim,
    }

    # Add text embedding if weights include it
    if weights is None:
        weights = get_default_weights_with_text()

    if "text_embed" in weights:
        fused = compute_fusion_with_text(
            similarities,
            weights,
            card1=card1,
            card2=card2,
        )
    else:
        # Legacy fusion without text
        fused = sum(similarities[s] * weights.get(s, 0) for s in similarities)
        total_weight = sum(weights.get(s, 0) for s in similarities)
        if total_weight > 0:
            fused /= total_weight

    return fused
```

---

## Step 3: Update API

### In `src/ml/api/api.py`

Add text embedding support:

```python
from ml.similarity.text_embeddings import get_text_embedder
from ml.similarity.fusion_integration import get_default_weights_with_text

# In your similarity endpoint:
@app.get("/v1/cards/{card_name}/similar")
async def get_similar_cards(
    card_name: str,
    mode: str = "fusion",
    k: int = 10,
    use_text_embed: bool = True,  # New parameter
):
    # ... existing code ...

    if mode == "fusion" and use_text_embed:
        weights = get_default_weights_with_text()
    else:
        weights = get_legacy_weights()  # Without text

    # Use fusion with text embeddings
    # ...
```

---

## Step 4: Integrate Beam Search

### In `src/ml/deck_building/deck_completion.py`

Add beam search option:

```python
from .beam_search import beam_search_completion

def complete_deck(
    game: str,
    deck: dict,
    candidate_fn: CandidateFn,
    config: CompletionConfig,
    *,
    use_beam_search: bool = False,
    beam_width: int = 3,
) -> dict:
    """Complete deck with optional beam search."""

    if use_beam_search:
        return beam_search_completion(
            deck,
            candidate_fn,
            config,
            beam_width=beam_width,
            tag_set_fn=tag_set_fn,  # If available
            cmc_fn=cmc_fn,  # If available
            curve_target=curve_target,  # If available
        )
    else:
        # Existing greedy implementation
        return greedy_completion(deck, candidate_fn, config)
```

---

## Step 5: Update Fusion Grid Search

### In fusion grid search script

Add text_embed dimension:

```python
# Old grid:
for embed_w in [0.0, 0.1, 0.2, ...]:
    for jaccard_w in [0.0, 0.1, 0.2, ...]:
        for func_w in [0.0, 0.1, 0.2, ...]:
            weights = {"embed": embed_w, "jaccard": jaccard_w, "functional": func_w}
            # Normalize and test

# New grid (with text):
for embed_w in [0.0, 0.1, 0.2, ...]:
    for jaccard_w in [0.0, 0.1, 0.2, ...]:
        for func_w in [0.0, 0.1, 0.2, ...]:
            for text_w in [0.0, 0.1, 0.2, 0.3, 0.4]:  # New dimension
                weights = {
                    "embed": embed_w,
                    "jaccard": jaccard_w,
                    "functional": func_w,
                    "text_embed": text_w,
                }
                # Normalize and test
```

---

## Step 6: Testing

### Test Text Embeddings

```bash
uv run pytest src/ml/tests/test_text_embeddings.py -v
```

### Test Integration

```bash
# Test fusion with text
uv run python -c "
from ml.similarity.fusion_integration import compute_fusion_with_text, get_default_weights_with_text
similarities = {'embed': 0.5, 'jaccard': 0.6, 'functional': 0.7}
weights = get_default_weights_with_text()
card1 = {'name': 'Lightning Bolt', 'oracle_text': 'Deal 3 damage.'}
card2 = {'name': 'Shock', 'oracle_text': 'Deal 2 damage.'}
result = compute_fusion_with_text(similarities, weights, card1=card1, card2=card2)
print(f'Fused similarity: {result}')
"
```

### Test Beam Search

```bash
# Test on sample deck
uv run python -c "
from ml.deck_building.beam_search import beam_search_completion
from ml.deck_building.deck_completion import CompletionConfig
# ... test code ...
"
```

---

## Step 7: Re-run Evaluation

After integration:

1. **Update test set** (if needed)
2. **Re-run fusion grid search** with text_embed dimension
3. **Compare P@10**:
   - Baseline: 0.088
   - Expected with text: 0.15-0.18
   - Expected with text + beam: 0.20-0.28

---

## Backward Compatibility

All changes maintain backward compatibility:

- **Text embeddings**: Optional, can be disabled
- **Beam search**: Optional, greedy still default
- **Fusion weights**: Legacy weights available
- **API**: New parameters optional

---

## Performance Considerations

### Text Embeddings
- **Caching**: Embeddings cached to disk (`.cache/text_embeddings/`)
- **Batch processing**: Use `embed_batch()` for multiple cards
- **Model**: `all-MiniLM-L6-v2` is fast (~50ms per card)

### Beam Search
- **Beam width**: Start with 3, increase if needed
- **Caching**: Candidate generation should be cached
- **Early stopping**: Stops when target size reached

---

## Troubleshooting

### Import Errors
```bash
# Ensure dependencies installed
uv sync
uv run python -c "from sentence_transformers import SentenceTransformer; print('OK')"
```

### Cache Issues
```bash
# Clear cache if needed
rm -rf .cache/text_embeddings/
```

### Performance Issues
- Reduce beam width
- Use smaller text embedding model
- Cache more aggressively

---

## Next Steps After Integration

1. **Measure improvements**: Compare P@10 before/after
2. **Tune weights**: Re-run grid search
3. **Add GNN**: PyTorch Geometric integration (Phase 2)
4. **Add Siamese network**: Card-deck fit learning (Phase 2)
5. **Add RL**: If beam search insufficient (Phase 2)

---

## Expected Results

| Phase | Implementation | Expected P@10 | Status |
|-------|----------------|---------------|--------|
| Baseline | Current system | 0.088 | ✅ |
| Phase 0 | Text embeddings | 0.15-0.18 | 🚧 In progress |
| Phase 1 | + Beam search | 0.20-0.28 | 📝 Ready |
| Phase 2 | + GNN + Siamese | 0.30-0.40 | 📋 Planned |

---

## Files to Review (When Readable)

1. `src/ml/similarity/similarity_methods.py` - Find fusion implementation
2. `src/ml/api/api.py` - Find endpoint definitions
3. `src/ml/deck_building/deck_completion.py` - Find greedy implementation
4. `experiments/fusion_grid_search_latest.json` - Current weights

---

## Questions to Answer

1. Where is fusion currently implemented?
2. How are weights currently applied?
3. Where is candidate generation in deck completion?
4. How is API structured for similarity queries?

These will be answered when files are readable.
