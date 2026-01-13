# Agentic Meta-Judge - Full Pipeline Integration

## ✅ Integration Complete

The agentic meta-judge system is **fully integrated** into the annotation pipeline with:

1. **LLMAnnotator** - Supports agentic meta-judge with conversation history
2. **MultiAnnotatorIAA** - Passes message_history for multi-round feedback
3. **generate_llm_annotations.py** - CLI arguments for agentic meta-judge
4. **Hard rules optional** - Automatically disabled when using agentic meta-judge

## Usage

### Enable Agentic Meta-Judge

```bash
python3 scripts/annotation/generate_llm_annotations.py \
    --game magic \
    --num-annotations 50 \
    --use-agentic-meta-judge \
    --agentic-max-rounds 3
```

### Programmatic Usage

```python
from ml.annotation.llm_annotator import LLMAnnotator

# With agentic meta-judge (recommended)
annotator = LLMAnnotator(
    game="magic",
    use_agentic_meta_judge=True,
    agentic_meta_judge_max_rounds=3,
    enforce_baseline_rules=False,  # Automatically False when agentic enabled
)

# Hard rules automatically disabled
# Multi-annotator automatically enabled
# Conversation history maintained across rounds
```

## How It Works

1. **Round 1**: 3 annotators generate initial annotations
2. **Meta-Judge**: Reviews each annotation, provides feedback
3. **Consensus Check**: Evaluates agreement and quality
4. **Round 2+**: Annotators revise based on feedback (via conversation history)
5. **Final**: Best annotation selected based on quality + consensus

## Benefits Over Hard Rules

- ✅ **Context-Aware**: Feedback adapts to specific issues
- ✅ **Iterative**: Multiple rounds allow convergence
- ✅ **No Rigid Thresholds**: Meta-judge makes nuanced decisions
- ✅ **Conversation History**: Builds context over time
- ✅ **IAA Moderation**: Explicit consensus building

## Backward Compatibility

- Default: Hard rules enabled (backward compatible)
- Agentic: Opt-in via `--use-agentic-meta-judge` flag
- Both systems can coexist (different use cases)
