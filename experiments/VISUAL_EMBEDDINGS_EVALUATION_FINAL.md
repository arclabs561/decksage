# Visual Embeddings Evaluation - Final Results

**Date:** January 6, 2026  
**Evaluation Script:** `scripts/evaluation/run_visual_evaluation_simple.py`  
**Test Set:** `experiments/test_set_unified_magic.json` (940 queries, sampled 100)  
**Embeddings:** `data/embeddings/multitask_enhanced_vv2024-W01.wv` (26,958 cards)  
**Graph:** `data/processed/pairs_all_games_combined.csv` (28,726 cards)  
**Image URLs:** 937 cards with image URLs (from Scryfall API)

## Data Collection

### Image URL Collection
- **Script:** `scripts/data/update_card_data_with_images.py`
- **Source:** Scryfall API
- **Cards Processed:** 1,000 (test set cards)
- **Successfully Fetched:** 937 image URLs (93.7% success rate)
- **Failed:** 63 cards (6.3% - likely alternate names or special cards)
- **Output:** `data/processed/card_attributes_enriched_image_urls.json`

### Card Data Coverage
- **Total Cards in Test Set:** 5,683 unique cards
- **Cards with Image URLs:** 937 (16.5% coverage)
- **Cards Evaluated:** 100 queries sampled from 940 total

## Results

### With Visual Embeddings
- **P@10:** 0.1355
- **Queries Evaluated:** 100
- **Queries Skipped:** 0

### Without Visual Embeddings
- **P@10:** 0.1355
- **Queries Evaluated:** 100
- **Queries Skipped:** 0

### Improvement
- **Absolute:** +0.0000
- **Relative:** +0.00%

## Analysis

### Why No Improvement?

Despite having 937 image URLs, visual embeddings show **no improvement**. Possible reasons:

1. **Limited Coverage:** Only 16.5% of test set cards have image URLs
   - Most query cards and their relevant matches don't have images
   - Visual embeddings default to zero vectors for cards without images
   - Zero vectors don't contribute to similarity scores

2. **Query Coverage:** The sampled 100 queries may not include many cards with images
   - Random sampling may miss cards that have image URLs
   - Need to ensure queries and their relevant cards both have images

3. **Weight Distribution:** Visual embeddings may need higher weight
   - Current weight: 0.20 (20%)
   - May need to increase to 0.30-0.40 to see impact

4. **Model Performance:** SigLIP 2 may need fine-tuning
   - Pre-trained on general images, not trading cards
   - May not capture card-specific visual features well

## Next Steps

### Immediate Actions
1. **Increase Image Coverage:** Fetch image URLs for all 5,683 test set cards
2. **Filter Evaluation:** Only evaluate queries where both query and relevant cards have images
3. **Weight Optimization:** Run ablation study to find optimal visual embedding weight

### Future Improvements
1. **Fine-tune SigLIP 2:** Train on trading card images for better domain-specific features
2. **Card-Specific Features:** Extract card-specific visual features (art style, color palette, layout)
3. **Multi-Modal Fusion:** Better integration of visual and text features

## Files Generated

- `data/processed/card_attributes_enriched_image_urls.json` - Image URL mapping (937 cards)
- `data/processed/card_attributes_test_set_images.csv` - Card data with image URLs
- `experiments/visual_embeddings_evaluation_simple.json` - Evaluation results
- `experiments/VISUAL_EMBEDDINGS_EVALUATION_FINAL.md` - This document

## Technical Notes

- **Visual Embedder Model:** `google/siglip2-base-patch16-224` (SigLIP 2)
- **Image Source:** Scryfall API (Magic: The Gathering)
- **Evaluation Method:** Weighted precision@10 with relevance levels
- **Fusion Weights:**
  - With visual: embed=0.20, jaccard=0.15, functional=0.10, text_embed=0.25, visual_embed=0.20, gnn=0.10
  - Without visual: embed=0.25, jaccard=0.20, functional=0.15, text_embed=0.30, visual_embed=0.0, gnn=0.10

