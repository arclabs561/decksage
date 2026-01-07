# Visual Embeddings Evaluation Results

**Date:** January 6, 2026  
**Evaluation Script:** `scripts/evaluation/run_visual_evaluation_simple.py`  
**Test Set:** `experiments/test_set_unified_magic.json` (940 queries, sampled 100)  
**Embeddings:** `data/embeddings/multitask_enhanced_vv2024-W01.wv` (26,958 cards)  
**Graph:** `data/processed/pairs_all_games_combined.csv` (28,726 cards)

## Results

### With Visual Embeddings
- **P@10:** 0.12325
- **Queries Evaluated:** 100
- **Queries Skipped:** 0

### Without Visual Embeddings
- **P@10:** 0.12325
- **Queries Evaluated:** 100
- **Queries Skipped:** 0

### Improvement
- **Absolute:** +0.0000
- **Relative:** +0.00%

## Analysis

The evaluation shows **no improvement** from visual embeddings. This is expected because:

1. **Missing Image URLs:** Cards in the test set don't have image URLs, so visual embeddings default to zero vectors
2. **Zero Vectors Don't Help:** When visual embeddings are all zeros, they don't contribute to similarity scores
3. **Same Weights:** Both runs use the same fusion weights (just redistributed), so results are identical

## Next Steps

To properly evaluate visual embeddings:

1. **Collect Image URLs:** Run `scripts/data/collect_card_images.py` to gather image URLs for cards
2. **Update Card Data:** Ensure card data includes `image_url` field
3. **Re-run Evaluation:** Run evaluation again with actual image data

## Files Generated

- `experiments/visual_embeddings_evaluation_simple.json` - Full evaluation results
- `experiments/visual_embeddings_evaluation_results.json` - Original evaluation results (from first script)

## Technical Notes

- Visual embedder model: `google/siglip2-base-patch16-224` (SigLIP 2)
- Evaluation uses fusion with weights:
  - With visual: embed=0.20, jaccard=0.15, functional=0.10, text_embed=0.25, visual_embed=0.20, gnn=0.10
  - Without visual: embed=0.25, jaccard=0.20, functional=0.15, text_embed=0.30, visual_embed=0.0, gnn=0.10
- Sample size: 100 queries (from 940 total) for faster evaluation

