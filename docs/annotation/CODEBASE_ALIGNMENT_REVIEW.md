# Codebase Alignment Review - Synthetic IAA with Different Models/Params

## Summary

✅ **Verified**: We ARE using synthetic IAA with different LLM models and parameters correctly.

## Implementation Review

### Multi-Annotator IAA System

**Location**: `src/ml/annotation/multi_annotator_iaa.py`

**Configuration**:
```python
DEFAULT_ANNOTATORS = [
    AnnotatorConfig(
        name="gemini_3_flash",
        model="google/gemini-3-flash-preview",
        temperature=0.3,  # Different from others
        max_tokens=1500,
    ),
    AnnotatorConfig(
        name="claude_opus_4_5",
        model="anthropic/claude-opus-4-5",
        temperature=0.3,  # Same temp, different model
        max_tokens=1500,
    ),
    AnnotatorConfig(
        name="gemini_3_pro",
        model="google/gemini-3-pro",
        temperature=0.4,  # Different temperature!
        max_tokens=1500,
    ),
]
```

**Key Features**:
1. ✅ **Different Models**: Gemini Flash, Claude Opus, Gemini Pro (3 diverse models)
2. ✅ **Different Parameters**: Gemini Pro uses `temperature=0.4` vs `0.3` for others
3. ✅ **ModelSettings Applied**: Each annotator uses `ModelSettings(temperature=config.temperature, max_tokens=config.max_tokens)` at runtime
4. ✅ **Metadata Tracking**: Each annotation stores `model_name` and `model_params` (temperature, max_tokens)
5. ✅ **Parallel Execution**: All annotators run in parallel for efficiency
6. ✅ **IAA Calculation**: Uses Krippendorff's Alpha for agreement measurement

### How It Works

1. **Initialization** (`MultiAnnotatorIAA.__init__`):
   - Creates separate `Agent` instances for each model
   - Each agent uses the same prompt but different model
   - Stores annotator configs with different parameters

2. **Annotation** (`annotate_pair_multi`):
   - Runs all annotators in parallel
   - Each annotator uses `ModelSettings` with its specific `temperature` and `max_tokens`
   - Results stored with `annotator_id`, `model_name`, and `model_params`

3. **IAA Calculation** (`_compute_iaa`):
   - Computes Krippendorff's Alpha for:
     - Similarity scores (discretized into bins)
     - Similarity types (nominal)
     - Substitute flags (nominal)
   - Returns agreement level: "high", "medium", "low", "disagreement"

4. **Consensus Building** (`_create_consensus`):
   - Creates weighted consensus when models agree (α ≥ 0.6)
   - Uses annotator weights for reliability tracking

## Codebase Alignment

### ✅ Correctly Integrated

1. **LLMAnnotator** (`src/ml/annotation/llm_annotator.py`):
   - Imports `MultiAnnotatorIAA` and `DEFAULT_ANNOTATORS`
   - Has `use_multi_annotator` flag
   - Calls `multi_annotator.annotate_pair_multi()` when enabled
   - Stores IAA metrics in annotations

2. **Human Annotation Queue** (`src/ml/annotation/human_annotation_queue.py`):
   - Queues tasks based on low IAA (from multi-annotator system)
   - Stores `iaa_metrics` in task context

3. **Uncertainty Selection** (`src/ml/annotation/uncertainty_based_selection.py`):
   - Uses model disagreement as uncertainty signal
   - Works with multi-annotator system

4. **Scripts**:
   - `scripts/annotation/test_iaa_uncertainty_real.py` - Tests IAA integration
   - `scripts/annotation/run_large_scale_validation.py` - Compares single vs multi-annotator
   - `scripts/annotation/queue_human_annotations.py` - Uses IAA for queuing

### ⚠️ Potential Improvements

1. **Temperature Diversity**: Currently only Gemini Pro has different temperature (0.4 vs 0.3). Consider:
   - Adding more temperature variation (0.2, 0.3, 0.4, 0.5)
   - Or using same temperature but different models (current approach is good)

2. **Model Diversity**: Current models are good (Gemini Flash, Claude Opus, Gemini Pro). Consider:
   - Adding GPT-5.2 for even more diversity
   - Or keeping current 3 models (good balance of cost/speed/quality)

3. **Parameter Tracking**: ✅ Already tracks `model_params` in annotations - good!

4. **Consistency**: All scripts use `DEFAULT_ANNOTATORS` - good alignment!

## Verification

### Test IAA Implementation

```python
from src.ml.annotation.multi_annotator_iaa import MultiAnnotatorIAA, DEFAULT_ANNOTATORS

# Verify different models/params
for config in DEFAULT_ANNOTATORS:
    print(f"{config.name}: {config.model}, temp={config.temperature}")

# Output:
# gemini_3_flash: google/gemini-3-flash-preview, temp=0.3
# claude_opus_4_5: anthropic/claude-opus-4-5, temp=0.3
# gemini_3_pro: google/gemini-3-pro, temp=0.4  # Different!
```

### Verify ModelSettings Applied

In `_annotate_with_agent`:
```python
settings = ModelSettings(
    temperature=config.temperature,  # ✅ Uses config-specific temperature
    max_tokens=config.max_tokens,    # ✅ Uses config-specific max_tokens
)
result = await agent.run(prompt, settings=settings)  # ✅ Applied at runtime
```

### Verify Metadata Tracking

```python
ann.model_name = config.model  # ✅ Tracks which model
ann.model_params = {
    "temperature": config.temperature,  # ✅ Tracks parameters
    "max_tokens": config.max_tokens,
}
```

## Conclusion

✅ **Everything is correctly aligned**:
- Using 3 different LLM models (Gemini Flash, Claude Opus, Gemini Pro)
- Using different parameters (Gemini Pro: temp=0.4, others: temp=0.3)
- ModelSettings applied at runtime for each annotator
- Metadata tracked in annotations
- IAA calculated using Krippendorff's Alpha
- All codebase components use consistent `DEFAULT_ANNOTATORS`

## Recommendations

1. ✅ **Current implementation is correct** - no changes needed
2. **Optional enhancement**: Add more temperature diversity if desired (but current approach is good)
3. **Optional enhancement**: Consider adding GPT-5.2 as 4th annotator for more diversity (but 3 is sufficient)

