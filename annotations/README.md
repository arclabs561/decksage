# Hand Annotation Workflow

This directory contains annotation batches for expanding test sets to 100+ queries with proper statistical rigor.

## Quick Start

### 1. Generate Annotation Batches

```bash
# Generate batches for all games
python -m src.ml.scripts.generate_all_annotation_batches

# Or generate for a specific game
python -m src.ml.annotation.hand_annotate generate \
    --game magic \
    --target 50 \
    --current 38 \
    --output annotations/hand_batch_magic.yaml
```

### 2. Annotate

Open the generated YAML file in your text editor and grade each candidate:

```yaml
tasks:
  - query: "Lightning Bolt"
    candidates:
      - card: "Chain Lightning"
        sources: ["embedding", "cooccurrence"]
        relevance: 4  # ← Fill this in (0-4 scale)
        notes: "Near substitute, same function"
      - card: "Lava Spike"
        sources: ["embedding"]
        relevance: 4
        notes: ""
```

**Relevance Scale:**
- **4**: Extremely similar (near substitutes, same function)
- **3**: Very similar (often seen together, similar role)
- **2**: Somewhat similar (related function or archetype)
- **1**: Marginally similar (loose connection)
- **0**: Irrelevant (different function, color, or archetype)

### 3. Grade Annotations

```bash
# Check completion and validate
python -m src.ml.annotation.hand_annotate grade \
    --input annotations/hand_batch_magic.yaml
```

This will show:
- Completion rate
- Relevance distribution
- Validation errors

### 4. Merge to Test Set

```bash
# Merge completed annotations into canonical test set
python -m src.ml.annotation.hand_annotate merge \
    --input annotations/hand_batch_magic.yaml \
    --test-set experiments/test_set_canonical_magic.json
```

## Target Goals

| Game | Current | Target | Needed |
|------|---------|--------|--------|
| MTG | 38 | 50 | 12 |
| Pokemon | 10 | 25 | 15 |
| Yu-Gi-Oh | 13 | 25 | 12 |
| **Total** | **61** | **100** | **39** |

## Annotation Guidelines

### Focus Areas

1. **Functional Similarity**: Can cards replace each other?
2. **Archetype Context**: Do they appear in the same decks?
3. **Mana Cost**: Similar CMC often indicates substitutability
4. **Card Type**: Same type (creature, instant, etc.) matters

### Edge Cases

- **Staples**: Cards that appear everywhere (e.g., Sol Ring) may have many "relevant" cards
- **Archetype-Specific**: Some cards only work in specific archetypes
- **Power Level**: Consider if cards are at similar power levels
- **Format**: Consider format legality (Modern vs Legacy)

### Notes Field

Use the `notes` field to document:
- Interesting patterns
- Edge cases
- Rationale for borderline decisions
- Archetype-specific context

## Workflow Tips

1. **Batch Processing**: Work through one query at a time
2. **Take Breaks**: Annotation is mentally taxing
3. **Review Later**: Come back to edge cases after initial pass
4. **Consistency**: Try to maintain consistent standards across queries

## Quality Checks

Before merging, ensure:
- ✅ All candidates have relevance scores (0-4)
- ✅ No validation errors
- ✅ Relevance distribution is reasonable (not all 0s or 4s)
- ✅ Notes added for edge cases

## Files

- `hand_batch_*.yaml`: Annotation batches (one per game)
- `README.md`: This file

## Integration with Evaluation

Once merged, test sets are automatically used by:
- `src/ml/utils/evaluation.py` - Standard evaluation
- `src/ml/utils/evaluation_with_ci.py` - Evaluation with confidence intervals
- `src/ml/evaluation/evaluate.py` - Full evaluation pipeline

Confidence intervals are computed using bootstrap resampling (1000 samples by default).
