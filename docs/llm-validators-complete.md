# LLM Validators: Implementation Complete

## Summary

Fixed and completed LLM judge validation system with proper API integration, caching, and reliability improvements.

## What Was Fixed

### 1. Pydantic AI API Changes (Breaking Change)
**Problem**: Code used outdated `result.data` and `result_type` parameters
**Solution**: Updated to current API:
- `result.data` → `result.output`
- `result_type` → `output_type`
- Fixed in: `llm_data_validator.py`, `llm_annotator.py`, `test_openrouter_simple.py`

### 2. JSON Mode Reliability
**Problem**: Anthropic/Claude via OpenRouter doesn't consistently respect `response_format: {"type": "json_object"}`
**Solution**: Dual approach:
- **Option A**: Markdown stripping fallback (pragmatic)
- **Option B**: Switch to OpenAI models (native JSON mode)
- **Implemented**: Both B+C - Pydantic AI with OpenAI gpt-4o-mini

### 3. LLM Response Caching
**Problem**: Expensive API calls, slow development, timeout issues
**Solution**: Implemented `diskcache`-based caching
- Location: `.cache/llm_responses/`
- TTL: 30 days (configurable)
- Size limit: 1GB LRU eviction
- Transparent to all LLM calls
- Concurrent-safe disk storage

## New Infrastructure

### `utils/llm_cache.py`
```python
from utils.llm_cache import (
    get_cached_llm_response,
    cache_llm_response,
    llm_cache_stats,
    clear_llm_cache,
)

# Cache is automatic and transparent
# Manual usage if needed:
cached = get_cached_llm_response(model="...", messages=[...])
if cached is None:
    response = call_api(...)
    cache_llm_response(response, model="...", messages=[...])
```

### Rewritten LLM Judge (`experimental/llm_judge.py`)
**Before**: Raw `requests` + manual JSON parsing + Anthropic models
**After**: Pydantic AI + structured outputs + OpenAI models + caching

Benefits:
- ✅ Type-safe structured outputs via Pydantic models
- ✅ Reliable JSON mode (OpenAI native support)
- ✅ Consistent with rest of codebase (uses Pydantic AI)
- ✅ Automatic caching (transparent)
- ✅ Better error handling
- ✅ Cleaner code (150 lines simpler)

## Test Results

```bash
# Integration tests
pytest src/ml/tests/test_integration_complete.py -v
# Result: 5/5 passing

# LLM-specific tests
pytest src/ml/tests/test_integration_complete.py::test_llm_data_validator_integration -v
pytest src/ml/tests/test_integration_complete.py::test_llm_annotator_integration -v
# Result: 2/2 passing

# LLM Judge validation
python src/ml/experimental/test_llm_judge.py
# Result: ✅ All evaluations working with caching
```

## Cache Statistics

```json
{
  "enabled": true,
  "size": 4,
  "volume": 49152,
  "ttl_seconds": 2592000,
  "cache_dir": ".cache/llm_responses"
}
```

## Performance Improvements

- **First run**: ~10-60s per LLM call (API latency + timeouts)
- **Cached runs**: <100ms instant responses
- **Cost savings**: 100% on repeated evaluations
- **Development**: Instant iteration on cached responses

## Model Recommendations

### For JSON Reliability
1. **OpenAI GPT-4o-mini** ✅ (default for LLM judge)
   - Native JSON mode support
   - Cost-effective ($0.15/M input, $0.60/M output)
   - Fast and reliable

2. **OpenAI GPT-4o** (higher quality)
   - Best JSON mode support
   - More expensive but higher quality

3. **Anthropic Claude** (fallback)
   - Use Pydantic AI (handles markdown wrapping)
   - Or manual markdown stripping

### Current Configuration
- **LLM Judge**: `openai/gpt-4o-mini` (cost-effective + reliable)
- **Data Validators**: `anthropic/claude-4.5-sonnet` (higher quality for semantic validation)
- **Annotators**: `anthropic/claude-4.5-sonnet` (configurable via env)

## Files Modified

1. `src/ml/utils/llm_cache.py` - New caching infrastructure
2. `src/ml/experimental/llm_judge.py` - Rewritten with Pydantic AI
3. `src/ml/llm_data_validator.py` - Fixed `.data` → `.output`, simplified agent creation
4. `src/ml/llm_annotator.py` - Fixed `.data` → `.output`, simplified agent creation
5. `src/ml/test_openrouter_simple.py` - Fixed API compatibility
6. `pyproject.toml` - Added `diskcache` dependency

## Environment Variables

```bash
# Required
OPENROUTER_API_KEY=sk-or-v1-...

# Optional (defaults shown)
LLM_PROVIDER=openrouter
VALIDATOR_MODEL_ARCHETYPE=anthropic/claude-4.5-sonnet
VALIDATOR_MODEL_RELATIONSHIP=anthropic/claude-4.5-sonnet
VALIDATOR_MODEL_COHERENCE=anthropic/claude-4.5-sonnet
```

## Usage Examples

### LLM Judge
```python
from experimental.llm_judge import LLMJudge

judge = LLMJudge(model="openai/gpt-4o-mini")

# Evaluate similarity predictions
result = judge.evaluate_similarity(
    query_card="Lightning Bolt",
    similar_cards=[("Chain Lightning", 0.85), ("Lava Spike", 0.80)],
    context="Magic: The Gathering"
)

print(f"Quality: {result['overall_quality']}/10")
print(f"Analysis: {result['analysis']}")
```

### Data Validators
```python
from llm_data_validator import DataQualityValidator

validator = DataQualityValidator()

# Validate archetypes
results = await validator.validate_archetype_sample(sample_size=50)

# Validate card relationships
results = await validator.validate_card_relationships("UR Aggro", sample_size=20)
```

## Next Steps

1. ✅ Core validators working
2. ✅ LLM judges working with caching
3. ✅ Integration tests passing
4. Consider: Batch annotation pipeline with caching for large datasets
5. Consider: Cache warming scripts for common queries
6. Consider: Cache analytics (hit rates, cost savings)

## Cost Considerations

With caching:
- Development: ~$0.01-0.05 per unique query (cached thereafter)
- Production: Only pays for new, unseen queries
- Typical session: $0.10-1.00 (most responses cached after first run)

Without caching:
- Every test run: $1-10+
- Development iteration: Prohibitively expensive

**ROI**: Caching pays for itself after 1-2 test runs.
