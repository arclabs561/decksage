# Code Tidying Summary

**Date**: 2025-01-27  
**Scope**: Rust annotation crate + Python codebase cleanup

## ✅ Rust Annotation Crate Cleanup

### Removed Unused Dependencies
- ❌ `itertools` - Not used anywhere
- ❌ `thiserror` - Using `anyhow` instead
- ❌ `pathdiff` - Not used

### Fixed Unused Imports
- Removed `HashSet` from `lib.rs` (not used)
- Removed `PathBuf` from `lib.rs` (not used)
- Removed `StdRng` from `query.rs` (not needed)
- Removed `generate_candidates_fused` from `main.rs` (not used in CLI)

### Code Formatting
- ✅ Added `.rustfmt.toml` configuration
- ✅ Ran `cargo fmt` (auto-formatted)
- ✅ All code compiles cleanly

### Final Dependencies (8 total)
```
decksage-annotation
├── rank-fusion (zero deps)
├── rank-refine (optional deps)
├── anyhow
├── serde + serde_json + serde_yaml
├── clap
├── rand
├── csv
└── chrono
```

## 📊 Crate Review Summary

### rank-fusion v0.1.19
- **Dependencies**: Zero (optional serde)
- **Status**: ✅ Excellent - Zero overhead
- **Usage**: RRF for candidate fusion

### rank-refine v0.7.36
- **Dependencies**: Optional (kodama, serde)
- **Status**: ✅ Excellent - SIMD-accelerated
- **Usage**: Cosine similarity for reranking
- **Potential**: Could use MMR, MaxSim, explainability features

### rank-anno
- **Status**: ❌ Does not exist as separate crate
- **Note**: We created `decksage-annotation` instead
- **Future**: Could extract if needed for reuse

## 🔍 Python Codebase TODOs Found

Found 9 TODO comments:
- `src/ml/api/api.py`: 2 TODOs (archetype loading, reference decks)
- `src/ml/similarity/format_aware_similarity.py`: 3 TODOs (embedding loader, format checks)
- `src/ml/analysis/analyze_failures.py`: 1 TODO (similarity function)
- `src/ml/analysis/measure_signal_performance.py`: 1 TODO (similarity functions)
- `src/ml/similarity/text_embeddings.py`: 1 TODO (card resolver)
- `src/ml/analysis/analyze_embeddings.py`: 1 TODO (frequency loading)

## ✅ Status

**Rust Code**: ✅ Clean, formatted, no warnings  
**Dependencies**: ✅ Minimal, all used  
**Python Code**: ⚠️ 9 TODOs (non-critical, future enhancements)

## 📋 Files Modified

1. `src/annotation/Cargo.toml` - Removed unused deps
2. `src/annotation/src/lib.rs` - Removed unused imports
3. `src/annotation/src/query.rs` - Removed unused imports
4. `src/annotation/src/main.rs` - Removed unused imports
5. `src/annotation/.rustfmt.toml` - Added formatting config
6. `CRATE_REVIEW.md` - Comprehensive crate analysis

## 🎯 Next Steps

1. ✅ Rust code is clean and ready
2. 🔮 Consider using more rank-refine features (MMR, MaxSim)
3. 🔮 Address Python TODOs as needed
4. 🔮 Consider extracting annotation logic to `rank-anno` if reusable

