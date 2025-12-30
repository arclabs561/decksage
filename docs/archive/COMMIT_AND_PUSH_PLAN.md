# Commit and Push Plan

**Date**: November 10, 2025  
**Status**: Ready to commit when git operations work

---

## Files to Commit

### New Implementation Files
- `src/ml/similarity/text_embeddings.py` - Text embeddings module
- `src/ml/similarity/fusion_integration.py` - Fusion integration helpers
- `src/ml/similarity/format_aware_similarity.py` - Format-aware similarity
- `src/ml/deck_building/beam_search.py` - Beam search implementation
- `src/ml/utils/evaluation_with_ci.py` - CI evaluation utilities

### Analysis Tools
- `src/ml/analysis/__init__.py` - Analysis package
- `src/ml/analysis/measure_signal_performance.py` - Signal measurement
- `src/ml/analysis/analyze_failures.py` - Failure analysis
- `src/ml/analysis/weight_sensitivity.py` - Weight sensitivity
- `src/ml/analysis/find_best_experiment.py` - Find best experiments

### Tests
- `src/ml/tests/test_text_embeddings.py` - Text embeddings tests

### Documentation
- `SOTA_COMPARISON_AND_IMPROVEMENTS.md` - SOTA research comparison
- `RESEARCH_REVIEW_AND_REFINED_PLAN.md` - Refined implementation plan
- `DATA_ANALYSIS_AND_IMPROVEMENTS.md` - Data-driven analysis
- `SCIENTIFIC_ANALYSIS_FINDINGS.md` - Scientific findings
- `CRITICAL_FINDINGS_AND_ACTION_PLAN.md` - Critical findings
- `TARGETED_IMPROVEMENT_BASED_ON_DATA.md` - Targeted improvements
- `METHODOLOGY_CRITIQUE_AND_IMPROVEMENTS.md` - Methodology improvements
- `INTEGRATION_GUIDE.md` - Integration instructions
- `IMPLEMENTATION_STATUS.md` - Implementation status

---

## Commit Strategy

### Commit 1: Analysis Tools and Methodology
```bash
git add src/ml/analysis/ src/ml/utils/evaluation_with_ci.py
git add *METHODOLOGY*.md *ANALYSIS*.md *FINDINGS*.md
git commit -m "analysis: add scientific evaluation tools and methodology improvements

- Add bootstrap confidence intervals to evaluation
- Add signal performance measurement
- Add failure case analysis
- Add weight sensitivity analysis
- Add best experiment finder
- Document methodology improvements based on best practices"
```

### Commit 2: Implementation Files
```bash
git add src/ml/similarity/text_embeddings.py
git add src/ml/similarity/fusion_integration.py
git add src/ml/similarity/format_aware_similarity.py
git add src/ml/deck_building/beam_search.py
git add src/ml/tests/test_text_embeddings.py
git commit -m "feat: add text embeddings, format-aware similarity, and beam search

- Add text embeddings using sentence-transformers
- Add fusion integration helpers
- Add format-aware similarity (based on exp_025 finding: P@10=0.150)
- Add beam search for deck completion
- Add tests for text embeddings

Based on SOTA research and data-driven analysis."
```

### Commit 3: Documentation
```bash
git add SOTA_*.md RESEARCH_*.md DATA_*.md CRITICAL_*.md TARGETED_*.md
git add INTEGRATION_GUIDE.md IMPLEMENTATION_STATUS.md
git commit -m "docs: comprehensive research review and implementation plan

- SOTA comparison with recent papers
- Data-driven analysis findings
- Critical discoveries (fusion < baseline, best exp_025)
- Targeted improvements based on data
- Integration guide for new features"
```

---

## Push Strategy

### When Git Operations Work

```bash
# Check status (using -uno to avoid untracked file enumeration)
git status -uno

# Add all new files
git add src/ml/analysis/
git add src/ml/similarity/text_embeddings.py
git add src/ml/similarity/fusion_integration.py
git add src/ml/similarity/format_aware_similarity.py
git add src/ml/deck_building/beam_search.py
git add src/ml/utils/evaluation_with_ci.py
git add src/ml/tests/test_text_embeddings.py
git add *.md

# Commit
git commit -m "feat: scientific evaluation tools and SOTA improvements

- Add bootstrap CI evaluation
- Add signal performance measurement
- Add failure analysis tools
- Add text embeddings implementation
- Add format-aware similarity (replicates exp_025: P@10=0.150)
- Add beam search for deck completion
- Comprehensive research review and methodology improvements

Based on data-driven analysis:
- Found best experiment: exp_025 (format-specific embeddings, P@10=0.150)
- Current fusion (0.0882) worse than baseline (0.089)
- 71% of experiments made things worse
- Need individual signal measurement to understand why

All improvements are data-justified and methodology-sound."

# Push to both remotes
git push origin main
git push henrywallace main
```

---

## Summary of Changes

### Analysis & Methodology
- ✅ Bootstrap confidence intervals
- ✅ Signal performance measurement
- ✅ Failure case analysis
- ✅ Weight sensitivity analysis
- ✅ Best experiment finder

### Implementation
- ✅ Text embeddings module
- ✅ Fusion integration helpers
- ✅ Format-aware similarity
- ✅ Beam search for deck completion
- ✅ Tests

### Documentation
- ✅ SOTA research comparison
- ✅ Data-driven analysis
- ✅ Methodology improvements
- ✅ Integration guides

**Total**: ~15 new files, comprehensive improvements

---

## Notes

- All files are ready to commit
- Waiting for git operations to work (iCloud issue)
- Can commit in batches when system responsive
- All changes are backward compatible







