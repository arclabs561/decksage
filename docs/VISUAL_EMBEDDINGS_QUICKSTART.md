# Visual Embeddings Quick Start

Get visual embeddings working in 5 minutes.

## Installation

```bash
# Install dependencies
uv add sentence-transformers pillow requests transformers sentencepiece

# Or install enrichment group
uv sync --extra enrichment
```

## Basic Usage

### 1. Initialize Embedder

```python
from ml.similarity.visual_embeddings import get_visual_embedder

embedder = get_visual_embedder()
```

### 2. Embed a Card

```python
card = {
    "name": "Lightning Bolt",
    "image_url": "https://cards.scryfall.io/normal/front/0/6/06a3b5e7-8b78-4c4e-9c5a-8e3f2d1c0b9a.jpg"
}

embedding = embedder.embed_card(card)
print(f"Embedding shape: {embedding.shape}")
```

### 3. Compute Similarity

```python
card1 = {"name": "Lightning Bolt", "image_url": "https://..."}
card2 = {"name": "Shock", "image_url": "https://..."}

similarity = embedder.similarity(card1, card2)
print(f"Visual similarity: {similarity:.3f}")
```

### 4. Use in Fusion

```python
from ml.similarity.fusion import FusionWeights, WeightedLateFusion

fusion = WeightedLateFusion(
    embeddings=embeddings,
    adj=adj,
    weights=FusionWeights(visual_embed=0.2),
    visual_embedder=get_visual_embedder(),
    card_data=card_attrs,
)

results = fusion.similar("Lightning Bolt", k=10)
```

## API Usage

### Start API with Visual Embeddings

```bash
# Set model (optional, defaults to google/siglip-base-patch16-224)
export VISUAL_EMBEDDER_MODEL=google/siglip-base-patch16-224

# Start API
./scripts/start_api.sh
```

### Test Endpoint

```bash
# Visual embeddings automatically included in fusion
curl "http://localhost:8000/v1/cards/Lightning%20Bolt/similar?mode=fusion&k=10"
```

### Check Status

```bash
# Verify visual embedder loaded
curl http://localhost:8000/ready
# Should show visual_embed in fusion_default_weights
```

## Validation

Run validation script:

```bash
python3 scripts/validation/validate_visual_embeddings.py
```

Run demo:

```bash
python3 scripts/demo/visual_embeddings_demo.py
```

## Troubleshooting

### Model Download Slow
- First run downloads ~300MB model
- Subsequent runs use cached model

### Missing Images
- Cards without image URLs return 0.0 similarity (graceful degradation)
- System continues working without visual embeddings

### Import Errors
```bash
# Install missing dependencies
uv add sentence-transformers pillow requests transformers sentencepiece
```

## Next Steps

1. **Evaluate**: Measure P@10 improvement
2. **Fine-tune**: Collect card images and fine-tune model
3. **Optimize**: Tune fusion weights based on results

See `docs/VISUAL_EMBEDDINGS_USAGE.md` for detailed documentation.

