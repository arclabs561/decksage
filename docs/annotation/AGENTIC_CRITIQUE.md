# Agentic Meta-Judge: Critical Analysis

## Issues Found

### 1. **No Actual Revision Loop** ⚠️ CRITICAL

**Problem**: The `moderate_multi_round` function evaluates annotations but **never calls annotators again** for revisions.

**Current Flow**:
1. Round 1: Annotators generate initial annotations
2. Meta-judge evaluates and provides feedback
3. Round 2+: **Nothing happens** - just evaluates same annotations again

**Expected Flow**:
1. Round 1: Annotators generate initial annotations
2. Meta-judge evaluates and provides feedback
3. Round 2: Annotators **revise** based on feedback (via conversation history)
4. Meta-judge evaluates revisions
5. Repeat until consensus or max rounds

**Code Evidence**:
```python
# src/ml/annotation/agentic_meta_judge.py:427-430
# If continuing, annotators would revise based on feedback
# For now, we return - in practice, you'd call annotators again with feedback
if round_num >= self.max_rounds:
    return round_data, all_rounds
```

**Impact**: The system is **not actually doing multi-round revision** - it's just evaluating the same annotations multiple times.

### 2. **Conversation History Not Used for Revision**

**Problem**: Feedback is stored in `conversation_history` but annotators are never called again with this history.

**Current**:
- Feedback stored in `round_data.conversation_history`
- But `MultiAnnotatorIAA.annotate_pair_multi()` is only called once (initial round)
- Subsequent rounds don't call annotators with feedback

**Expected**:
- Round 2+ should call `multi_annotator.annotate_pair_multi()` again
- Pass `message_history` with feedback from previous rounds
- Annotators revise based on feedback

### 3. **Missing Integration Point**

**Problem**: `LLMAnnotator` calls `moderate_multi_round()` but doesn't handle revision rounds.

**Current Code**:
```python
# llm_annotator.py:597
final_round, all_rounds = await self.agentic_meta_judge.moderate_multi_round(
    multi_result.annotations
)
```

**Issue**: This is a one-shot call. If `moderate_multi_round` decides to continue, there's no mechanism to:
1. Call annotators again with feedback
2. Pass conversation history to annotators
3. Get revised annotations

### 4. **Feedback Messages Not Properly Formatted**

**Problem**: `_create_feedback_messages()` returns empty list.

**Code**:
```python
# agentic_meta_judge.py:391
return []  # Would return proper ModelMessage objects
```

**Impact**: Conversation history is not actually being built for annotators to use.

### 5. **No Feedback Injection into Annotator Prompts**

**Problem**: Even if annotators were called again, feedback isn't injected into their prompts.

**Expected**:
- Round 2+ should include feedback in the prompt
- Or use `message_history` to pass feedback context
- Annotators should see: "Previous round feedback: ..."

**Current**: Annotators never see feedback.

## What Works

### ✅ Architecture
- Clean separation: `AgenticMetaJudge` for moderation, `MultiAnnotatorIAA` for annotation
- Good use of Pydantic models for structured feedback
- Conversation history structure is sound

### ✅ Feedback Generation
- `_get_annotation_feedback()` properly evaluates individual annotations
- `_evaluate_consensus()` makes reasonable consensus decisions
- Feedback structure (`MetaJudgeFeedback`) is comprehensive

### ✅ Integration Points
- `LLMAnnotator` properly initializes agentic meta-judge
- CLI arguments are in place (after fix)
- Hard rules properly disabled when agentic enabled

## Required Fixes

### 1. Implement Revision Loop

```python
# In moderate_multi_round():
for round_num in range(1, self.max_rounds + 1):
    round_data = await self.moderate_annotation_round(round_data, all_rounds)

    if round_data.consensus_decision.recommended_action == "accept":
        return round_data, all_rounds

    # NEW: If continuing, call annotators again with feedback
    if round_data.consensus_decision.recommended_action == "revise":
        # Get revised annotations with feedback
        revised_annotations = await self._revise_annotations(
            round_data.annotations,
            round_data.conversation_history,
            round_data.meta_judge_feedback,
        )
        current_annotations = revised_annotations
```

### 2. Add Revision Method

```python
async def _revise_annotations(
    self,
    current_annotations: dict[str, CardSimilarityAnnotation],
    conversation_history: list[ModelMessage],
    feedback: dict[str, MetaJudgeFeedback],
) -> dict[str, CardSimilarityAnnotation]:
    """Call annotators again with feedback for revision."""
    # This needs access to MultiAnnotatorIAA
    # Pass conversation_history to annotate_pair_multi()
    # Include feedback in prompts
```

### 3. Fix Feedback Messages

```python
def _create_feedback_messages(
    self,
    feedback: dict[str, MetaJudgeFeedback],
    consensus: ConsensusDecision,
) -> list[ModelMessage]:
    """Create conversation messages from feedback."""
    # Actually create ModelMessage objects
    # Format feedback for annotators
    # Return proper message list
```

### 4. Integrate Revision into LLMAnnotator

```python
# In llm_annotator.py:
if self.use_agentic_meta_judge:
    # Pass multi_annotator to agentic_meta_judge so it can call revisions
    final_round, all_rounds = await self.agentic_meta_judge.moderate_multi_round(
        multi_result.annotations,
        multi_annotator=self.multi_annotator,  # NEW: Pass annotator for revisions
        card1=card1,  # NEW: Need card names for revision
        card2=card2,
        graph_context=graph_context,
    )
```

## Design Questions

1. **Should revision happen per-annotator or consensus?**
   - Option A: Each annotator revises independently based on their feedback
   - Option B: All annotators see all feedback and revise together
   - Option C: Only annotators with `should_revise=True` revise

2. **How to inject feedback into prompts?**
   - Option A: Add feedback to prompt string
   - Option B: Use `message_history` (cleaner, maintains context)
   - Option C: Both (feedback in prompt + history)

3. **What if annotators disagree on revision?**
   - Current: Consensus decision applies to all
   - Alternative: Per-annotator revision decisions

## Recommendations

1. **Immediate**: Implement revision loop - this is the core missing piece
2. **High Priority**: Fix feedback message creation
3. **Medium Priority**: Add per-annotator revision support
4. **Low Priority**: Add metrics for revision effectiveness

## Testing Strategy

1. **Unit Test**: `moderate_multi_round` with mock annotators that revise
2. **Integration Test**: Full flow with real annotators (small batch)
3. **Validation**: Compare Round 1 vs Round 2+ annotations for improvement
4. **Metrics**: Track consensus improvement over rounds
