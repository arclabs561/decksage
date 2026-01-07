# Visual Embeddings for Trading Cards: Research Summary and Recommendation

**Last Updated**: January 2026

## Executive Summary

After comprehensive research into state-of-the-art vision models (2024-2025), the recommended approach for trading card visual embeddings is:

**Primary Recommendation: Fine-tuned SigLIP 2 (ViT-B or ViT-L)**
- Start with pre-trained SigLIP 2 for initial implementation
- Fine-tune on trading card datasets for domain adaptation
- Combine with existing text embeddings via weighted fusion

**Rationale:**
1. SigLIP 2 outperforms CLIP and original SigLIP at all scales
2. Pre-trained models struggle with card art styles (anime, non-realistic) - fine-tuning is essential
3. Multi-modal fusion (visual + text + metadata) outperforms single-modality approaches
4. SigLIP 2 offers good efficiency-performance tradeoff (152 img/sec for ViT-B-16)

## Research Findings

### State-of-the-Art Models (2024-2025, current as of 2026)

#### 1. SigLIP 2 (Recommended)
- **Performance**: Outperforms CLIP and original SigLIP on zero-shot classification, image-text retrieval, and transfer learning
- **Efficiency**: ViT-B-16 achieves ~152 images/sec on RTX 3090
- **Features**: 
  - Multilingual support
  - Dynamic resolution variants (`-naflex` suffix)
  - Improved training objectives (captioning, self-distillation, masked prediction)
- **Model sizes**: ViT-B (86M), L (303M), So400m (400M), g (1B)
- **Embedding dimension**: 512 (standard)

#### 2. DINOv3 (Alternative for dense features)
- **Strengths**: Best for dense prediction tasks (segmentation, detection)
- **Limitations**: No text alignment (requires post-hoc CLIP-style alignment for retrieval)
- **Use case**: If you need pixel-level visual features, not just global embeddings
- **Performance**: State-of-the-art on COCO detection (66.1 mAP) and ADE20k segmentation (63.0 mIoU)

#### 3. RADIO/RADIOv2.5 (Efficiency-focused)
- **Strengths**: 6-10x faster than CLIP, agglomerative learning from multiple teachers
- **Performance**: Competitive accuracy with fewer parameters
- **Use case**: Resource-constrained deployments

#### 4. EVA-02 (Efficiency-focused)
- **Strengths**: 304M parameters, 90% ImageNet accuracy, 80.4% zero-shot CLIP accuracy
- **Use case**: When parameter count is a hard constraint

### Trading Card Specific Findings

1. **Pre-trained models struggle with card art styles**
   - Pokémon cards: Non-realistic "anime-style" eyes, varied illustration styles
   - Pre-trained models trained on realistic images fail to generalize
   - **Fine-tuning on card datasets is essential**

2. **Multi-modal approaches outperform single-modality**
   - Research on Magic: The Gathering shows combining text + visual + metadata + usage-based features works best
   - Visual features alone miss semantic information (card text, stats, rarity)

3. **Production examples**
   - MobileCLIP used successfully for card attribute matching
   - 500-dimensional embeddings for card attributes/titles
   - Pre-computed text embeddings for efficient matching

4. **Generalization to unseen cards**
   - RGB-based visual representation critical for generalization
   - Simple representations (random vectors) work for known cards but fail on unseen ones

## Implementation Strategy

### Phase 1: Baseline (Pre-trained SigLIP 2)
1. Use `sentence-transformers` with SigLIP 2 model
2. Follow `CardTextEmbedder` pattern in `src/ml/similarity/text_embeddings.py`
3. Create `CardVisualEmbedder` class
4. Integrate into `HybridSearch` (already has `image_url` field)
5. Add to fusion weights optimization

**Model**: `google/siglip-base-patch16-224` or `google/siglip-large-patch16-384`

### Phase 2: Fine-tuning (Domain Adaptation)
1. Collect card image dataset (Scryfall, Riftcodex, YGOPRODeck already have image URLs)
2. Fine-tune SigLIP 2 on card images with card text as captions
3. Use card metadata (name, type, oracle text) as positive pairs
4. Evaluate on card similarity benchmarks

### Phase 3: Multi-modal Fusion
1. Combine visual embeddings with existing text embeddings
2. Add metadata features (rarity, set, stats)
3. Optimize fusion weights (existing infrastructure in place)
4. Evaluate on downstream tasks (deck completion, substitution)

## Technical Details

### Embedding Dimensions
- **SigLIP 2**: 512 dimensions (standard)
- **Trade-off**: Higher dimensions = better discrimination but more storage/compute
- **Recommendation**: Start with 512, consider 256 for efficiency if needed

### Image Preprocessing
- Cards already have `image_url` in data structure
- Need to download/cache images (Pillow already in dependencies)
- Standard preprocessing: resize to model input size (224x224 or 384x384), normalize

### Integration Points
1. **`src/ml/similarity/visual_embeddings.py`** (new file)
   - `CardVisualEmbedder` class (mirror `CardTextEmbedder`)
   - Caching, batch processing, similarity calculation

2. **`src/ml/search/hybrid_search.py`**
   - Already has `image_url` field
   - Add visual embedding to Qdrant payload
   - Support visual similarity search

3. **Enrichment pipeline**
   - Add visual embeddings to `EnrichedCardSimilarityAnnotation`
   - Track `vision_coverage` metrics (already in place)

4. **Fusion weights**
   - Add visual component to existing fusion optimization
   - Expected weight: 20-30% (based on research showing multi-modal benefits)

## Performance Expectations

Based on research:
- **Current**: ~0.08 P@10 with co-occurrence alone
- **Papers**: 0.42 P@10 with multi-modal features (text + images + metadata)
- **Target**: 0.15-0.20 P@10 (project priority)

Visual embeddings should contribute 5-10 percentage points to P@10, bringing us from ~0.08 to ~0.13-0.18, getting closer to the 0.15-0.20 target.

## Trade-offs Summary

| Approach | Accuracy | Computational Cost | Implementation Complexity | Recommendation |
|----------|----------|-------------------|--------------------------|----------------|
| Pre-trained SigLIP 2 | Good | Low | Low | ✅ Start here |
| Fine-tuned SigLIP 2 | Better | Medium | Medium | ✅ Phase 2 |
| DINOv3 | Best (dense) | High | High | ❌ Overkill for similarity |
| Multi-modal fusion | Best (overall) | High | High | ✅ Phase 3 |
| MobileCLIP | Good | Very Low | Low | ⚠️ Consider for mobile |

## Next Steps

1. **Immediate**: Implement `CardVisualEmbedder` with pre-trained SigLIP 2
2. **Short-term**: Collect card image dataset for fine-tuning
3. **Medium-term**: Fine-tune SigLIP 2 on card images
4. **Long-term**: Multi-modal fusion optimization

## References

- SigLIP 2: https://huggingface.co/blog/siglip2
- Trading card research: https://arxiv.org/html/2407.05879v1
- Multi-modal MTG: https://arxiv.org/html/2512.09802
- Vision encoder survey: https://jina.ai/vision-encoder-survey.pdf
- DINOv3: https://arxiv.org/html/2508.10104v1
- RADIO: https://github.com/NVlabs/RADIO

