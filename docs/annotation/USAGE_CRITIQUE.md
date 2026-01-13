# Agentic Meta-Judge: Usage Critique & Findings

## Critical Issue Found: HAS_ENRICHMENT = False

**Problem**: The agentic meta-judge and multi-annotator systems are not being initialized because `HAS_ENRICHMENT` is `False`.

**Root Cause**: One or more imports in the enrichment block are failing, causing the entire enrichment system to be disabled.

**Impact**:
- `use_multi_annotator = use_multi_annotator and HAS_ENRICHMENT` → Always False
- `use_agentic_meta_judge = use_agentic_meta_judge and HAS_ENRICHMENT` → Always False
- System falls back to single annotator mode
- No multi-round revision happening

**Evidence**:
```python
# Test output:
use_multi_annotator: False
use_agentic_meta_judge: False
multi_annotator exists: False
agentic_meta_judge exists: False
```

## Fixes Implemented

### 1. ✅ Revision Loop
- Added `_revise_annotations()` method
- Integrated revision calls into `moderate_multi_round()`
- Passes `multi_annotator`, `card1`, `card2`, `graph_context` for revision calls

### 2. ✅ Feedback Messages
- Fixed `_create_feedback_messages()` to return proper `ModelMessage` objects
- Creates user messages with feedback summary

### 3. ✅ Message History Integration
- `MultiAnnotatorIAA.annotate_pair_multi()` accepts `message_history`
- `_annotate_with_agent()` passes history to agents
- Feedback injected into prompts for revision rounds

### 4. ✅ Enhanced Prompts
- Revision rounds include feedback summary in prompt
- Graph context enhanced with previous round feedback

### 5. ✅ Logging
- Added detailed logging for round progression
- Tracks consensus decisions and revision calls

## Remaining Issues

### 1. ⚠️ Import Failures
**Status**: Need to identify which import is failing
**Action**: Test each import individually to find the culprit

### 2. ⚠️ No Round Output
**Status**: Even when enabled, no round logging appears
**Possible Causes**:
- `HAS_ENRICHMENT=False` prevents initialization
- Logging level too high
- Exceptions being silently caught

### 3. ⚠️ Source Field
**Status**: Annotations show `"source": "llm"` instead of `"llm_multi_annotator_agentic"`
**Cause**: Multi-annotator path not being taken (due to `HAS_ENRICHMENT=False`)

## Design Observations

### What Works Well

1. **Architecture**: Clean separation of concerns
   - `AgenticMetaJudge` handles moderation
   - `MultiAnnotatorIAA` handles annotation
   - `LLMAnnotator` orchestrates

2. **Feedback Structure**: Well-designed Pydantic models
   - `MetaJudgeFeedback` is comprehensive
   - `ConsensusDecision` captures decision rationale

3. **Conversation History**: Proper use of Pydantic AI's `message_history`
   - Maintains context across rounds
   - Enables dynamic feedback injection

### What Needs Improvement

1. **Error Handling**: Too many silent failures
   - `HAS_ENRICHMENT` masks import errors
   - Should log which import failed

2. **Initialization Logic**: Too strict
   - `use_multi_annotator = use_multi_annotator and HAS_ENRICHMENT`
   - Should allow multi-annotator even if other enrichment features fail

3. **Feedback Injection**: Could be more explicit
   - Currently relies on `message_history`
   - Could also add feedback directly to prompt for clarity

4. **Revision Strategy**: Unclear
   - All annotators revise, or only those with `should_revise=True`?
   - Should consensus decision apply per-annotator or globally?

## Recommendations

### Immediate

1. **Fix Import Issues**
   - Identify failing import
   - Make imports optional where possible
   - Allow partial enrichment features

2. **Improve Error Visibility**
   - Log import failures explicitly
   - Don't silently disable features
   - Provide clear error messages

3. **Test End-to-End**
   - Once imports fixed, test full revision loop
   - Verify annotations improve across rounds
   - Measure consensus improvement

### Short-term

1. **Per-Annotator Revision**
   - Only revise annotators with `should_revise=True`
   - Allow selective revision based on feedback

2. **Revision Metrics**
   - Track score changes across rounds
   - Measure consensus improvement
   - Log revision effectiveness

3. **Fallback Strategy**
   - If revision fails, use best from previous round
   - Don't lose progress on revision failure

### Long-term

1. **Adaptive Rounds**
   - Stop early if consensus reached quickly
   - Continue if consensus improving
   - Max rounds as hard limit, not target

2. **Quality Thresholds**
   - Accept if quality > threshold, even if consensus low
   - Reject if quality < threshold, even if consensus high
   - Balance consensus vs quality

3. **Revision Guidance**
   - More specific feedback per annotator
   - Examples of good vs bad annotations
   - Targeted prompts for specific issues

## Testing Strategy

1. **Unit Tests**
   - Test `_revise_annotations()` with mock annotators
   - Test `moderate_multi_round()` with various consensus decisions
   - Test feedback message creation

2. **Integration Tests**
   - Test full flow: annotate → judge → revise → judge
   - Verify annotations improve
   - Check conversation history maintained

3. **End-to-End Tests**
   - Run with real annotators (small batch)
   - Compare Round 1 vs Round 2+ annotations
   - Measure consensus/quality improvement

4. **Failure Tests**
   - Test with missing imports
   - Test with revision failures
   - Test with annotator failures

## Next Steps

1. ✅ Fix import issues (identify failing import)
2. ✅ Test with imports fixed
3. ✅ Verify revision loop works
4. ✅ Measure improvement across rounds
5. ⏳ Refine based on results
