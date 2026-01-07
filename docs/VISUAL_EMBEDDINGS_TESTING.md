# Visual Embeddings Testing Guide

## Test Suite Overview

The visual embeddings implementation includes comprehensive testing at multiple levels:

1. **Unit Tests**: Core functionality (`test_visual_embeddings.py`)
2. **Fusion Integration Tests**: Fusion system integration (`test_fusion_with_visual.py`)
3. **Integration Tests**: Full pipeline integration (`test_visual_embeddings_integration.py`)
4. **Usage Tests**: Real-world usage scenarios (`test_visual_embeddings_usage.py`)

## Running Tests

### Quick Test (Integration)
```bash
python3 scripts/testing/test_visual_embeddings_integration.py
```

### Full Test Suite
```bash
./scripts/testing/run_visual_embeddings_tests.sh
```

### Individual Test Files
```bash
# Unit tests
pytest src/ml/tests/test_visual_embeddings.py -v

# Fusion integration
pytest src/ml/tests/test_fusion_with_visual.py -v

# Full integration
pytest src/ml/tests/test_visual_embeddings_integration.py -v

# Usage tests
python3 scripts/testing/test_visual_embeddings_usage.py
```

## Test Coverage

### Unit Tests (`test_visual_embeddings.py`)
- ✅ Embedder initialization
- ✅ Image URL extraction (multiple formats)
- ✅ Image download and caching
- ✅ Embedding generation
- ✅ Similarity computation
- ✅ Batch processing
- ✅ Error handling
- ✅ Caching behavior

### Fusion Integration (`test_fusion_with_visual.py`)
- ✅ Fusion weights with visual embeddings
- ✅ Fusion system accepts visual embedder
- ✅ Visual embedding similarity computation
- ✅ Fusion without visual embedder (backward compatibility)
- ✅ Aggregation methods include visual embeddings

### Integration Tests (`test_visual_embeddings_integration.py`)
- ✅ Fusion system integration
- ✅ API state integration
- ✅ Load signals integration
- ✅ Error handling
- ✅ Caching
- ✅ Batch processing

### Usage Tests (`test_visual_embeddings_usage.py`)
- ✅ Similarity search with visual embeddings
- ✅ Batch processing in real scenarios
- ✅ Fusion aggregation with visual embeddings
- ✅ API-like usage patterns
- ✅ Mixed modalities

## Test Scenarios

### 1. Basic Functionality
```python
from ml.similarity.visual_embeddings import CardVisualEmbedder

embedder = CardVisualEmbedder()
card = {"name": "Card", "image_url": "https://example.com/image.png"}
embedding = embedder.embed_card(card)
similarity = embedder.similarity(card1, card2)
```

### 2. Fusion Integration
```python
from ml.similarity.fusion import FusionWeights, WeightedLateFusion
from ml.similarity.visual_embeddings import get_visual_embedder

fusion = WeightedLateFusion(
    embeddings=embeddings,
    adj=adj,
    weights=FusionWeights(visual_embed=0.2),
    visual_embedder=get_visual_embedder(),
    card_data=card_attrs,
)
results = fusion.similar("Lightning Bolt", k=10)
```

### 3. API Usage
```python
# Visual embeddings automatically included when:
# 1. VISUAL_EMBEDDER_MODEL is set
# 2. Cards have image URLs
# 3. Fusion method is used

curl -X POST "http://localhost:8000/v1/similar" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Lightning Bolt",
    "top_k": 10,
    "mode": "fusion"
  }'
```

## Expected Test Results

### All Tests Passing
- ✅ Initialization: Visual embedder can be created
- ✅ Fusion Integration: Visual embeddings work in fusion
- ✅ API Integration: API state includes visual embedder
- ✅ Load Signals: Visual embedder loads correctly
- ✅ Error Handling: Missing images handled gracefully
- ✅ Caching: Embeddings cached correctly

### Common Issues

1. **Missing Dependencies**
   - Error: `sentence-transformers not installed`
   - Fix: `uv add sentence-transformers pillow requests`

2. **Model Download**
   - First run downloads model (~300MB)
   - Subsequent runs use cached model

3. **Image Download Failures**
   - Tests use mock/placeholder images
   - Real image downloads may fail (expected in tests)

4. **Missing Card Data**
   - Tests may fail if card_attrs not loaded
   - This is expected - tests verify graceful degradation

## Continuous Integration

Tests should be run:
- Before committing changes
- In CI/CD pipeline
- After dependency updates
- Before releases

## Performance Benchmarks

Future tests should include:
- Embedding generation latency
- Batch processing throughput
- Memory usage
- Cache hit rates

## Manual Testing

### Test Visual Embeddings in API
1. Start API: `./scripts/start_api.sh`
2. Set environment: `export VISUAL_EMBEDDER_MODEL=google/siglip-base-patch16-224`
3. Test endpoint:
   ```bash
   curl "http://localhost:8000/v1/cards/Lightning%20Bolt/similar?mode=fusion&k=5"
   ```
4. Verify visual embeddings are included in fusion weights

### Test Image Download
```python
from ml.similarity.visual_embeddings import CardVisualEmbedder

embedder = CardVisualEmbedder()
card = {
    "name": "Lightning Bolt",
    "image_url": "https://cards.scryfall.io/normal/front/0/6/06a3b5e7-8b78-4c4e-9c5a-8e3f2d1c0b9a.jpg"
}
embedding = embedder.embed_card(card)
print(f"Embedding shape: {embedding.shape}")
```

## Troubleshooting

### Tests Fail with Import Errors
- Ensure dependencies installed: `uv sync`
- Check Python version: `python3 --version` (should be 3.11+)

### Tests Fail with Model Download
- First run downloads model (expected)
- Check internet connection
- Model cached after first download

### Tests Fail with Image Download
- Tests use placeholder images (expected)
- Real image URLs may fail (this is OK for tests)
- Verify error handling works correctly

### API Tests Fail
- Ensure API dependencies installed
- Check API is running: `curl http://localhost:8000/live`
- Verify embeddings loaded: `curl http://localhost:8000/ready`

