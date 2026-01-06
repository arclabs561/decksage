# Annotation System - Current Status

## System Status: ✅ Operational

### Core Components

1. **LLM Annotator**: ✅ Working
   - Single annotator: ✅ Generating annotations
   - Graph enrichment: ✅ Enabled and working
   - EVōC clustering: ✅ Enabled for pair selection
   - Meta-judge: ✅ Providing feedback
   - Output validator: ✅ Catching contradictions

2. **Multi-Annotator IAA**: ⚠️ Partially Working
   - Gemini 3 Flash: ✅ Working
   - Claude Sonnet 3.5: ⚠️ Model ID needs verification
   - Gemini 2.0 Flash: ✅ Working
   - **Issue**: Some model IDs not valid on OpenRouter
   - **Status**: Using fallback to single annotator when models fail

3. **Uncertainty Selection**: ✅ Working
   - Identifying uncertain pairs correctly
   - Selecting diverse pairs for annotation

4. **Human Annotation Queue**: ✅ Working
   - Queue management: ✅ Functional
   - Task tracking: ✅ Working
   - MTurk integration: ✅ Ready (AWS billing enabled)
   - Scale AI: ⏳ Waiting for API access

### Recent Annotations Generated

**Magic**: 30 annotations
- Score range: 0.02 - 0.55
- Mean: ~0.18
- **Issue**: Score clustering in very_low range (0.0-0.2)

**Pokemon**: 10 annotations  
- Score range: 0.35 - 0.45
- Mean: ~0.40
- **Issue**: Limited range utilization

**Yu-Gi-Oh**: 10 annotations
- Score range: 0.72 - 0.85
- Mean: ~0.75
- **Issue**: Score clustering in high range, wrong game context

### Meta-Judge Feedback

**Common Issues Identified**:
1. **Score Clustering**: Not using full 0.0-1.0 range
2. **Missing Card Data**: Card attributes not populated in `card_comparison`
3. **Game Context**: Yu-Gi-Oh annotations using Magic terminology
4. **Inconsistent Scoring**: Similar relationships getting varying scores

**Feedback Applied**:
- Score anchors added to prompts
- Examples of mid-range similarities
- Game context enforcement

### Next Steps

1. **Fix Model IDs**: Verify and update OpenRouter model IDs for multi-annotator
2. **Address Score Clustering**: 
   - Add more diverse examples to prompts
   - Improve score calibration
   - Use uncertainty selection to find diverse pairs
3. **Fix Card Attributes**: Ensure card data is populated correctly
4. **Fix Game Context**: Enforce game-specific terminology
5. **Generate More Annotations**: Continue across all games

### Commands

```bash
# Generate annotations for a game
uv run python3 scripts/annotation/generate_llm_annotations.py \
    --game magic \
    --num-annotations 50 \
    --strategy diverse

# Run continuous improvement
uv run python3 scripts/annotation/run_continuous_improvement.py \
    --game magic \
    --num-pairs 20 \
    --iterations 3

# Test E2E
uv run python3 scripts/annotation/test_e2e_annotation_system.py
```

