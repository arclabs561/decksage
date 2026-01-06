# Visual Embeddings Integration Plan

**Last Updated**: January 2026

## Executive Summary

This document outlines the integration plan for visual embeddings into the existing DeckSage pipeline. Visual embeddings will be integrated as a new modality in the fusion system, following the same pattern as text embeddings.

## Architecture Overview

### Current Pipeline Architecture

```
Card Data (Go backend)
  ↓
  ├─ Image URLs (already stored in card.Images[].URL)
  ├─ Text (name, type_line, oracle_text)
  └─ Metadata (rarity, set, stats)
  ↓
Python ML Pipeline
  ├─ Text Embeddings (CardTextEmbedder)
  ├─ Co-occurrence Embeddings (Node2Vec/PecanPy)
  ├─ GNN Embeddings (CardGNNEmbedder)
  └─ Fusion System (WeightedLateFusion)
  ↓
Search/Indexing
  ├─ Meilisearch (text search)
  └─ Qdrant (vector search)
  ↓
API/Evaluation
  ├─ Similarity API
  └─ Evaluation scripts
```

### Proposed Architecture with Visual Embeddings

```
Card Data (Go backend)
  ↓
  ├─ Image URLs (already stored)
  ├─ Text (name, type_line, oracle_text)
  └─ Metadata
  ↓
Python ML Pipeline
  ├─ Visual Embeddings (CardVisualEmbedder) ← NEW
  ├─ Text Embeddings (CardTextEmbedder)
  ├─ Co-occurrence Embeddings
  ├─ GNN Embeddings
  └─ Fusion System (WeightedLateFusion) ← UPDATED
  ↓
Search/Indexing
  ├─ Meilisearch (text search)
  └─ Qdrant (vector search) ← UPDATED (multi-vector support)
  ↓
API/Evaluation
  ├─ Similarity API ← UPDATED
  └─ Evaluation scripts ← UPDATED
```

## Integration Points

### 1. Core Embedding Module

**File**: `src/ml/similarity/visual_embeddings.py` (NEW)

**Pattern**: Mirror `CardTextEmbedder` structure

**Key Components**:
- `CardVisualEmbedder` class
- Image download/caching utilities
- Batch processing support
- Similarity computation
- Disk caching (pickle-based, like text embeddings)

**Dependencies**:
- `sentence-transformers` (supports CLIP/SigLIP models)
- `pillow` (already in dependencies)
- `requests` or `httpx` (for image downloads)

### 2. Fusion System Integration

**File**: `src/ml/similarity/fusion.py` (UPDATE)

**Changes**:
1. Add `visual_embed: float = 0.20` to `FusionWeights` dataclass
2. Add `visual_embedder: Any | None = None` to `WeightedLateFusion.__init__`
3. Add `_get_visual_embedding_similarity()` method (mirror `_get_text_embedding_similarity()`)
4. Update `_compute_similarity_scores()` to include visual modality
5. Update all aggregation methods to include visual weights

**Default Weight**: 20% (based on research showing multi-modal benefits)

### 3. Search/Indexing Integration

**File**: `src/ml/search/hybrid_search.py` (UPDATE)

**Changes**:
1. Add `visual_embedding: np.ndarray | None = None` parameter to `index_card()`
2. Store visual embeddings in Qdrant (consider multi-vector support or separate collection)
3. Support visual similarity search queries

**Considerations**:
- Qdrant supports multi-vector collections (one vector per modality)
- Alternative: Store visual embeddings in separate collection
- Meilisearch already stores `image_url` (no changes needed)

### 4. Enrichment Pipeline Integration

**File**: `src/ml/annotation/enriched_annotation.py` (UPDATE)

**Changes**:
1. Add `visual_features: dict[str, Any] | None` field to `EnrichedCardSimilarityAnnotation`
2. Store visual embedding vector and similarity score
3. Track visual coverage in quality metrics

**File**: `src/ml/validation/enrichment_quality_validator.py` (UPDATE)

**Changes**:
- Already tracks `vision_enriched` - ensure it's populated correctly

### 5. API Integration

**File**: `src/ml/api/api.py` (UPDATE)

**Changes**:
1. Load `CardVisualEmbedder` in API state initialization
2. Pass visual embedder to fusion system
3. Include visual similarity in API responses (optional)

### 6. Evaluation Integration

**File**: `src/ml/evaluation/similarity_helper.py` (UPDATE)

**Changes**:
1. Add visual embedder to `create_similarity_function()`
2. Include visual weights in default fusion weights
3. Support visual embeddings in evaluation scripts

## Implementation Steps

### Phase 1: Core Visual Embedder (Week 1)

**Goal**: Create `CardVisualEmbedder` following `CardTextEmbedder` pattern

**Tasks**:
1. ✅ Create `src/ml/similarity/visual_embeddings.py`
2. ✅ Implement image download/caching utilities
3. ✅ Implement `CardVisualEmbedder` class with:
   - `__init__()` with model selection (default: SigLIP 2 ViT-B)
   - `embed_card()` method (accepts card dict or image URL)
   - `similarity()` method (cosine similarity)
   - `embed_batch()` method (batch processing)
   - Caching (memory + disk, pickle-based)
4. ✅ Add image preprocessing (resize, normalize)
5. ✅ Add error handling (missing images, download failures)
6. ✅ Write unit tests

**Dependencies**:
- `sentence-transformers>=2.2.0` (supports CLIP/SigLIP)
- `pillow>=10.0.0` (already in dependencies)
- `requests` or `httpx` (for downloads)

**File Structure**:
```python
# src/ml/similarity/visual_embeddings.py
class CardVisualEmbedder:
    def __init__(self, model_name: str = "google/siglip-base-patch16-224", ...)
    def _download_image(self, url: str) -> Image
    def _preprocess_image(self, image: Image) -> Image
    def embed_card(self, card: dict[str, Any] | str | Image) -> np.ndarray
    def similarity(self, card1, card2) -> float
    def embed_batch(self, cards: list) -> np.ndarray
```

### Phase 2: Fusion System Integration (Week 1-2)

**Goal**: Add visual embeddings to fusion system

**Tasks**:
1. ✅ Update `FusionWeights` to include `visual_embed: float = 0.20`
2. ✅ Update `WeightedLateFusion.__init__()` to accept `visual_embedder`
3. ✅ Implement `_get_visual_embedding_similarity()` method
4. ✅ Update `_compute_similarity_scores()` to compute visual similarity
5. ✅ Update all aggregation methods (`_aggregate_weighted`, `_aggregate_rrf`, etc.)
6. ✅ Update `_get_candidates()` to optionally use visual embeddings for candidate generation
7. ✅ Write integration tests

**Default Weights** (after normalization):
- GNN: 30%
- Instruction-tuned text: 25%
- Co-occurrence: 20%
- **Visual: 20%** ← NEW
- Jaccard: 15%
- Functional: 10%

### Phase 3: Search/Indexing Integration (Week 2)

**Goal**: Store visual embeddings in search systems

**Tasks**:
1. ✅ Update `HybridSearch.index_card()` to accept `visual_embedding` parameter
2. ✅ Store visual embeddings in Qdrant (multi-vector or separate collection)
3. ✅ Update `index_cards.py` to generate and index visual embeddings
4. ✅ Add visual similarity search capability
5. ✅ Write indexing tests

**Qdrant Options**:
- **Option A**: Multi-vector collection (one vector per modality)
- **Option B**: Separate collection for visual embeddings
- **Option C**: Store visual embeddings in payload (for retrieval, not search)

**Recommendation**: Start with Option C (payload storage), upgrade to Option A if needed

### Phase 4: Enrichment Pipeline Integration (Week 2-3)

**Goal**: Include visual embeddings in enrichment pipeline

**Tasks**:
1. ✅ Update `EnrichedCardSimilarityAnnotation` to include `visual_features`
2. ✅ Generate visual embeddings during enrichment
3. ✅ Store visual similarity scores in annotations
4. ✅ Update quality validators to track visual coverage
5. ✅ Update enrichment scripts to use visual embeddings

**Data Structure**:
```python
visual_features: {
    "embedding": np.ndarray,  # 512-dim vector
    "similarity_score": float,  # Visual similarity to query
    "model_name": str,  # e.g., "google/siglip-base-patch16-224"
    "image_url": str,  # Source image URL
}
```

### Phase 5: API and Evaluation Integration (Week 3)

**Goal**: Expose visual embeddings in API and evaluation

**Tasks**:
1. ✅ Load `CardVisualEmbedder` in API state initialization
2. ✅ Pass visual embedder to fusion system in API
3. ✅ Update `similarity_helper.py` to support visual embeddings
4. ✅ Update evaluation scripts to include visual modality
5. ✅ Add visual embeddings to API responses (optional metadata)
6. ✅ Write API integration tests

### Phase 6: Fine-tuning Preparation (Week 4+)

**Goal**: Prepare for domain-specific fine-tuning

**Tasks**:
1. ✅ Create card image dataset collection script
2. ✅ Download card images from Scryfall/Riftcodex/YGOPRODeck
3. ✅ Create fine-tuning dataset (card images + text captions)
4. ✅ Document fine-tuning process
5. ✅ Evaluate fine-tuned model vs. pre-trained

## Data Flow

### Embedding Generation Flow

```
1. Card Data (from Go backend)
   └─ card.Images[0].URL → image_url

2. CardVisualEmbedder.embed_card()
   ├─ Check cache (memory → disk)
   ├─ Download image (if not cached)
   ├─ Preprocess (resize to 224x224, normalize)
   ├─ Generate embedding (SigLIP 2 model)
   └─ Cache embedding (memory + disk)

3. Storage
   ├─ Memory cache (dict[str, np.ndarray])
   ├─ Disk cache (.cache/visual_embeddings/{model_name}.pkl)
   └─ Qdrant (for search)
```

### Similarity Computation Flow

```
1. Query Card
   └─ CardVisualEmbedder.embed_card(query_card)

2. Candidate Cards
   └─ CardVisualEmbedder.embed_batch(candidate_cards)

3. Similarity Scores
   └─ Cosine similarity (query_embedding, candidate_embeddings)

4. Fusion
   └─ WeightedLateFusion._get_visual_embedding_similarity()
      └─ Returns similarity score [0, 1]
```

### Fusion Integration Flow

```
1. WeightedLateFusion.similar(query, k)
   ├─ Get candidates (from graph, embeddings, etc.)
   ├─ Compute similarity scores per modality:
   │  ├─ embed (co-occurrence)
   │  ├─ jaccard
   │  ├─ functional
   │  ├─ text_embed
   │  ├─ visual_embed ← NEW
   │  └─ gnn
   └─ Aggregate scores (weighted sum, RRF, etc.)
```

## File Changes Summary

### New Files
- `src/ml/similarity/visual_embeddings.py` - Core visual embedder
- `src/ml/utils/image_utils.py` - Image download/caching utilities (optional)

### Modified Files
- `src/ml/similarity/fusion.py` - Add visual modality
- `src/ml/search/hybrid_search.py` - Store visual embeddings
- `src/ml/search/index_cards.py` - Generate visual embeddings during indexing
- `src/ml/annotation/enriched_annotation.py` - Add visual_features field
- `src/ml/api/api.py` - Load visual embedder
- `src/ml/evaluation/similarity_helper.py` - Support visual embeddings
- `pyproject.toml` - Add dependencies (if needed)

### Configuration
- Default model: `google/siglip-base-patch16-224`
- Default weight: 20% (in fusion)
- Cache directory: `.cache/visual_embeddings/`
- Image cache: `.cache/card_images/` (optional)

## Testing Strategy

### Unit Tests
- `test_visual_embeddings.py`
  - Test image download/caching
  - Test embedding generation
  - Test similarity computation
  - Test batch processing
  - Test error handling (missing images, invalid URLs)

### Integration Tests
- `test_fusion_with_visual.py`
  - Test visual embeddings in fusion system
  - Test weight normalization
  - Test aggregation methods
  - Test candidate generation

### End-to-End Tests
- `test_visual_search.py`
  - Test indexing with visual embeddings
  - Test search with visual similarity
  - Test API endpoints with visual embeddings

### Performance Tests
- Benchmark embedding generation speed
- Benchmark similarity computation
- Benchmark fusion with visual modality
- Compare with/without visual embeddings

## Performance Considerations

### Caching Strategy
- **Memory cache**: LRU cache for frequently accessed embeddings
- **Disk cache**: Pickle-based cache (like text embeddings)
- **Image cache**: Optional local image storage to avoid re-downloads

### Batch Processing
- Process images in batches (default: 32)
- Use GPU if available (sentence-transformers supports GPU)
- Parallelize image downloads (if needed)

### Lazy Loading
- Load model only when first embedding is requested
- Cache model in memory (don't reload per request)
- Use global instance pattern (like `get_text_embedder()`)

### Error Handling
- Gracefully handle missing images (return zero vector or skip)
- Handle download failures (retry with exponential backoff)
- Handle invalid image formats (skip or convert)
- Log errors but don't crash pipeline

## Dependencies

### New Dependencies
```toml
# pyproject.toml
[project.optional-dependencies]
enrichment = [
    "pillow>=10.0.0",  # Already present
    "sentence-transformers>=2.2.0",  # Already present (supports CLIP/SigLIP)
    "requests>=2.31.0",  # For image downloads (or use httpx)
]
```

### Model Downloads
- SigLIP 2 models are downloaded automatically by `sentence-transformers`
- First run will download model (~300MB for ViT-B)
- Models are cached in HuggingFace cache directory

## Migration Path

### Backward Compatibility
- Visual embeddings are **optional** - fusion works without them
- If visual embedder is `None`, visual similarity returns 0.0
- Existing code continues to work (no breaking changes)

### Gradual Rollout
1. **Phase 1**: Deploy visual embedder (disabled by default)
2. **Phase 2**: Enable in evaluation/experiments
3. **Phase 3**: Enable in production API (with feature flag)
4. **Phase 4**: Fine-tune on card datasets
5. **Phase 5**: Optimize weights based on evaluation

## Monitoring and Metrics

### Quality Metrics
- Visual embedding coverage (% of cards with embeddings)
- Visual similarity distribution
- Fusion performance with/without visual

### Performance Metrics
- Embedding generation latency
- Cache hit rate
- Image download success rate
- Memory usage

### Evaluation Metrics
- P@10 improvement with visual embeddings
- Downstream task performance (deck completion, substitution)
- Ablation studies (visual vs. text vs. graph)

## Future Enhancements

### Fine-tuning
- Collect card image dataset
- Fine-tune SigLIP 2 on card images + text captions
- Evaluate fine-tuned model performance

### Multi-vector Search
- Upgrade Qdrant to multi-vector collections
- Support separate similarity search per modality
- Combine results with fusion

### Image Preprocessing
- Card-specific preprocessing (crop borders, normalize aspect ratio)
- Handle multiple card faces (transform cards)
- Handle different card formats (standard, oversized, tokens)

### Advanced Features
- Visual similarity for card art style
- OCR for card text extraction
- Visual quality assessment (blurry, low-res images)

## Risk Mitigation

### Risks
1. **Image download failures**: Implement retry logic, graceful degradation
2. **Model size**: SigLIP 2 ViT-B is ~300MB, consider smaller models for production
3. **Latency**: Visual embeddings are slower than text, optimize with caching
4. **Storage**: Visual embeddings add storage overhead, consider compression

### Mitigations
- Make visual embeddings optional (can disable if issues)
- Use smaller models for production (MobileCLIP if needed)
- Aggressive caching to reduce latency
- Compress embeddings if storage is concern (quantization)

## Success Criteria

### Phase 1 (Core Implementation)
- ✅ Visual embedder works with pre-trained SigLIP 2
- ✅ Integration with fusion system
- ✅ Basic tests passing

### Phase 2 (Production Ready)
- ✅ Visual embeddings in search/indexing
- ✅ API integration complete
- ✅ Evaluation shows improvement in P@10

### Phase 3 (Optimization)
- ✅ Fine-tuned model on card datasets
- ✅ Optimized fusion weights
- ✅ Performance benchmarks met

## Timeline

- **Week 1**: Core visual embedder + fusion integration
- **Week 2**: Search/indexing + enrichment pipeline
- **Week 3**: API + evaluation integration
- **Week 4+**: Fine-tuning + optimization

## Next Steps

1. Review and approve this plan
2. Create implementation tickets
3. Set up development environment
4. Begin Phase 1 implementation

