# Visual Embeddings Usage Guide

## Quick Start

Visual embeddings are automatically integrated into the fusion system. They work out of the box when:

1. Cards have image URLs in their data
2. `VISUAL_EMBEDDER_MODEL` environment variable is set (default: `google/siglip-base-patch16-224`)
3. Fusion weights include `visual_embed > 0.0` (default: 20%)

## Basic Usage

### Using CardVisualEmbedder Directly

```python
from ml.similarity.visual_embeddings import CardVisualEmbedder, get_visual_embedder

# Get global instance (recommended)
embedder = get_visual_embedder()

# Or create custom instance
embedder = CardVisualEmbedder(
    model_name="google/siglip-base-patch16-224",
    cache_dir=".cache/visual_embeddings",
    image_cache_dir=".cache/card_images",
)

# Embed a card (requires image URL in card dict)
card = {
    "name": "Lightning Bolt",
    "image_url": "https://example.com/lightning_bolt.png",
}
embedding = embedder.embed_card(card)

# Compute similarity between two cards
card1 = {"name": "Lightning Bolt", "image_url": "https://..."}
card2 = {"name": "Shock", "image_url": "https://..."}
similarity = embedder.similarity(card1, card2)  # Returns float in [0, 1]

# Batch processing
cards = [card1, card2, card3]
embeddings = embedder.embed_batch(cards)  # Returns (n_cards, embedding_dim) array
```

### Using in Fusion System

Visual embeddings are automatically included in fusion when:

```python
from ml.similarity.fusion import FusionWeights, WeightedLateFusion
from ml.similarity.visual_embeddings import get_visual_embedder

# Create fusion with visual embeddings
fusion = WeightedLateFusion(
    embeddings=embeddings,
    adj=adjacency_dict,
    tagger=functional_tagger,
    weights=FusionWeights(
        embed=0.20,
        jaccard=0.15,
        functional=0.10,
        text_embed=0.25,
        visual_embed=0.20,  # Visual embeddings
        gnn=0.30,
    ),
    visual_embedder=get_visual_embedder(),
    card_data=card_attrs,  # Needed for image URL lookup
)

# Find similar cards (visual embeddings included automatically)
results = fusion.similar("Lightning Bolt", k=10)
```

## Configuration

### Environment Variables

- `VISUAL_EMBEDDER_MODEL`: Model name (default: `google/siglip-base-patch16-224`)
  - Options: `google/siglip-base-patch16-224`, `google/siglip-large-patch16-384`, etc.
- `TEXT_EMBEDDER_MODEL`: Text embedder model (separate from visual)

### Model Selection

**Recommended models:**
- `google/siglip-base-patch16-224`: Good balance of speed and accuracy (86M params)
- `google/siglip-large-patch16-384`: Better accuracy, slower (303M params)
- `google/siglip-so400m-patch14-384`: Larger model (400M params)

**For production:**
- Start with `siglip-base-patch16-224` for speed
- Upgrade to `siglip-large-patch16-384` if accuracy is more important than latency

## Image Requirements

Cards must have image URLs in one of these formats:

```python
# Format 1: Direct image_url field
{"name": "Card", "image_url": "https://..."}

# Format 2: image field
{"name": "Card", "image": "https://..."}

# Format 3: images list
{"name": "Card", "images": [{"url": "https://..."}]}

# Format 4: images dict
{"name": "Card", "images": {"large": "https://...", "png": "https://..."}}
```

## Caching

Visual embeddings are cached automatically:

- **Memory cache**: In-process cache for fast repeated access
- **Disk cache**: Pickle file at `.cache/visual_embeddings/{model_name}.pkl`
- **Image cache**: Downloaded images cached at `.cache/card_images/{url_hash}.png`

Cache is loaded on initialization and saved on shutdown.

## Error Handling

The system gracefully handles missing images:

- Cards without image URLs return zero embeddings
- Download failures return zero embeddings
- Invalid image formats are skipped
- All errors are logged but don't crash the pipeline

## Performance

### Throughput (on RTX 3090)
- `siglip-base-patch16-224`: ~152 images/sec
- `siglip-large-patch16-384`: ~30 images/sec

### Latency
- First embedding: ~100-200ms (model loading)
- Cached embeddings: <1ms (memory cache)
- Image download: ~50-200ms (depends on network)

### Memory
- Model: ~300MB (ViT-B), ~1GB (ViT-L)
- Embeddings: 512 dimensions × 4 bytes = 2KB per card
- Image cache: ~50-200KB per image (PNG)

## Fine-tuning

To fine-tune SigLIP 2 on card images:

1. **Collect images**:
   ```bash
   python scripts/data/collect_card_images.py --game magic --output data/card_images/magic
   ```

2. **Prepare dataset**: Images + card text captions

3. **Fine-tune**: Use HuggingFace Transformers or sentence-transformers training API

4. **Evaluate**: Compare fine-tuned vs. pre-trained on card similarity benchmarks

## Troubleshooting

### Images not downloading
- Check network connectivity
- Verify image URLs are accessible
- Check image cache directory permissions

### Low similarity scores
- Verify images are valid (not corrupted)
- Check image preprocessing (should be 224x224 RGB)
- Consider fine-tuning on card datasets

### Memory issues
- Use smaller model (`siglip-base` instead of `siglip-large`)
- Reduce batch size in `embed_batch()`
- Clear image cache periodically

### Slow performance
- Enable GPU if available (sentence-transformers uses GPU automatically)
- Use smaller model
- Increase batch size for batch processing
- Check cache hit rate (should be high after warmup)

## Examples

### Example 1: Simple Similarity

```python
from ml.similarity.visual_embeddings import get_visual_embedder

embedder = get_visual_embedder()

card1 = {"name": "Lightning Bolt", "image_url": "https://..."}
card2 = {"name": "Shock", "image_url": "https://..."}

similarity = embedder.similarity(card1, card2)
print(f"Visual similarity: {similarity:.3f}")
```

### Example 2: Batch Processing

```python
from ml.similarity.visual_embeddings import get_visual_embedder

embedder = get_visual_embedder()

cards = [
    {"name": "Card1", "image_url": "https://..."},
    {"name": "Card2", "image_url": "https://..."},
    {"name": "Card3", "image_url": "https://..."},
]

embeddings = embedder.embed_batch(cards)
print(f"Embeddings shape: {embeddings.shape}")  # (3, 512)
```

### Example 3: Integration with Fusion

```python
from ml.similarity.fusion import FusionWeights, WeightedLateFusion
from ml.similarity.visual_embeddings import get_visual_embedder

# Setup fusion with visual embeddings
fusion = WeightedLateFusion(
    embeddings=embeddings,
    adj=adj,
    tagger=tagger,
    weights=FusionWeights(visual_embed=0.20),
    visual_embedder=get_visual_embedder(),
    card_data=card_attrs,
)

# Find similar cards (includes visual similarity)
results = fusion.similar("Lightning Bolt", k=10)
for card, score in results:
    print(f"{card}: {score:.3f}")
```

## API Usage

Visual embeddings are automatically used in the API when:

1. `VISUAL_EMBEDDER_MODEL` is set
2. Cards have image URLs
3. Fusion method is used

```bash
# API automatically includes visual embeddings in fusion
curl -X POST "http://localhost:8000/v1/similar" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Lightning Bolt",
    "top_k": 10,
    "mode": "fusion"
  }'
```

## Next Steps

1. **Evaluate**: Run evaluation scripts to measure P@10 improvement
2. **Fine-tune**: Collect card images and fine-tune on domain data
3. **Optimize**: Tune fusion weights for your specific use case
4. **Monitor**: Track visual embedding coverage and performance metrics

