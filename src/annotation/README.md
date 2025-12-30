# DeckSage Annotation Tool (Rust)

Hand annotation system for expanding test sets with proper statistical rigor.
Integrates with `rank-fusion` and `rank-refine` for candidate generation and ranking.

## Features

- **Candidate Fusion**: Uses `rank-fusion` to combine candidates from multiple sources (embeddings, co-occurrence, etc.)
- **Reranking**: Uses `rank-refine` for SIMD-accelerated embedding-based reranking
- **Query Generation**: Stratified sampling for diverse query selection
- **Validation**: Comprehensive grading and validation of annotations
- **Test Set Management**: Merge annotations into canonical test sets

## Usage

### Generate Annotation Batch

```bash
cargo run --bin decksage-annotate -- generate \
    --game magic \
    --target 50 \
    --current 38 \
    --pairs ../../data/processed/pairs_large.csv \
    --test-set ../../experiments/test_set_canonical_magic.json \
    --output annotations/hand_batch_magic.yaml
```

### Grade Annotations

```bash
cargo run --bin decksage-annotate -- grade \
    --input annotations/hand_batch_magic.yaml
```

### Merge to Test Set

```bash
cargo run --bin decksage-annotate -- merge \
    --input annotations/hand_batch_magic.yaml \
    --test-set ../../experiments/test_set_canonical_magic.json
```

## Integration with Rank Libraries

### rank-fusion

Used for combining candidate lists from multiple sources:
- **RRF (Reciprocal Rank Fusion)**: Default method for incompatible score scales
- **Weighted Fusion**: When you have confidence in source quality
- **Multi-list Fusion**: Handles 3+ sources efficiently

### rank-refine

Used for reranking candidates with embeddings:
- **SIMD-accelerated cosine similarity**: Fast embedding comparisons
- **ColBERT MaxSim**: Late interaction for token-level matching
- **MMR Diversity**: Maximal Marginal Relevance for result diversification

## Architecture

```
┌─────────────────┐
│  Query Generator│  → Stratified sampling
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Candidate Gen   │  → rank-fusion (RRF)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Refinement     │  → rank-refine (cosine/MaxSim)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Annotation     │  → YAML output
└─────────────────┘
```

## Dependencies

- `rank-fusion`: Multi-list ranking fusion
- `rank-refine`: SIMD-accelerated reranking
- `serde`: Serialization (JSON/YAML)
- `clap`: CLI argument parsing
- `anyhow`: Error handling

## Next Steps

1. Integrate with actual embedding models (load from Python/Gensim)
2. Add support for loading graph data (co-occurrence pairs)
3. Implement batch processing for large candidate sets
4. Add progress tracking and resume capability

