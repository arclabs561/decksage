# Agentic Meta-Judge Integration

## Overview

The agentic meta-judge system is **fully integrated** into the annotation pipeline, replacing hard-coded Jaccard rules with dynamic, conversation-based feedback loops.

## Integration Points

### 1. **LLMAnnotator** (`src/ml/annotation/llm_annotator.py`)

**New Parameters:**
- `use_agentic_meta_judge: bool = False` - Enable agentic meta-judge
- `agentic_meta_judge_max_rounds: int = 3` - Maximum revision rounds
- `enforce_baseline_rules: bool = True` - Hard rules (disabled when using agentic)

**Behavior:**
- When `use_agentic_meta_judge=True`, automatically enables `use_multi_annotator=True`
- Hard Jaccard rules are automatically disabled when agentic meta-judge is enabled
- Agentic meta-judge moderates multi-annotator rounds with conversation history

### 2. **MultiAnnotatorIAA** (`src/ml/annotation/multi_annotator_iaa.py`)

**Enhanced:**
- `annotate_pair_multi()` now accepts `message_history` parameter
- `_annotate_with_agent()` passes conversation history to agents
- Supports multi-round feedback injection via Pydantic AI's `message_history`

### 3. **generate_llm_annotations.py**

**New CLI Arguments:**
```bash
--use-agentic-meta-judge    # Enable agentic meta-judge
--agentic-max-rounds 3      # Maximum rounds (default: 3)
```

**Usage:**
```bash
# With agentic meta-judge (recommended)
python3 scripts/annotation/generate_llm_annotations.py \
    --game magic \
    --num-annotations 50 \
    --use-agentic-meta-judge \
    --agentic-max-rounds 3

# Without agentic meta-judge (uses hard rules)
python3 scripts/annotation/generate_llm_annotations.py \
    --game magic \
    --num-annotations 50
```

## How It Works

### Multi-Round Flow

1. **Round 1**: Multiple annotators (3 models) generate initial annotations
2. **Meta-Judge Review**: Agentic meta-judge reviews each annotation and provides feedback
3. **Consensus Check**: Meta-judge evaluates consensus and decides: accept, revise, or continue
4. **Round 2+**: If not accepted, annotators revise based on feedback (via conversation history)
5. **Final Decision**: Best annotation selected based on quality scores and consensus

### Conversation History

Feedback is injected via Pydantic AI's `message_history`:

```python
# Round 1
result1 = await agent.run(prompt)

# Round 2 (with feedback from meta-judge)
result2 = await agent.run(
    revised_prompt,
    message_history=result1.new_messages() + feedback_messages
)
```

This maintains context across rounds, allowing annotators to learn from feedback.

## Benefits

1. **No Hard Rules**: Replaces rigid Jaccard thresholds with context-aware feedback
2. **Multi-Round Convergence**: Annotators can revise and improve
3. **IAA Moderation**: Explicit consensus building with quality checks
4. **Conversation History**: Builds context over time
5. **Backward Compatible**: Hard rules still available if needed

## Migration Path

**Current (Hard Rules):**
```python
annotator = LLMAnnotator(game="magic")
# Uses hard Jaccard rules: Jaccard > 0.3 → score >= 0.6
```

**New (Agentic):**
```python
annotator = LLMAnnotator(
    game="magic",
    use_agentic_meta_judge=True,
    agentic_meta_judge_max_rounds=3,
)
# Uses agentic feedback, no hard rules
```

## Configuration

**Default Behavior:**
- `use_agentic_meta_judge=False` (backward compatible)
- `enforce_baseline_rules=True` (hard rules enabled by default)

**When Agentic Enabled:**
- `enforce_baseline_rules=False` (automatically disabled)
- `use_multi_annotator=True` (automatically enabled)

## Testing

Test the integration:

```bash
# Test with agentic meta-judge
python3 scripts/annotation/generate_llm_annotations.py \
    --game magic \
    --num-annotations 5 \
    --use-agentic-meta-judge \
    --agentic-max-rounds 2
```

Expected output:
```
  Agentic meta-judge enabled (max 2 rounds, IAA moderation)
  Multi-annotator IAA enabled (3 models, consensus building)
  Meta-judge: accept (consensus=0.85, rounds=2)
```
