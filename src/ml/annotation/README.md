# Annotation System

Unified annotation system for creating training and evaluation data.

## Architecture

### Data Flow

```
LLM Annotations (JSONL)
    ↓
[Conversion Utilities]
    ↓
Substitution Pairs (JSON)
    ↓
Training (5x weight)
```

### Annotation Types

1. **LLM Similarity Annotations** (`CardSimilarityAnnotation`)
   - Format: JSONL (one annotation per line)
   - Fields: `card1`, `card2`, `similarity_score` (0-1), `similarity_type`, `is_substitute`, `reasoning`
   - Purpose: Rich similarity judgments with substitutability flag
   - Created by: `llm_annotator.py`

2. **Hand Annotations** (YAML)
   - Format: YAML with `query_card` and `candidates` list
   - Fields: `relevance` (0-4), `similarity_type`, `notes`
   - Purpose: Manual expert annotations for test set expansion
   - Created by: Manual annotation in YAML files
   - Auto-converted: `is_substitute=True` if `relevance=4` and `similarity_type="substitute"`

3. **Substitution Pairs** (JSON)
   - Format: `[[card1, card2], ...]`
   - Purpose: Direct training signal (weighted 5x in training)
   - Created by: `generate_substitution_pairs_llm.py` or converted from annotations (both formats)

4. **Test Sets** (JSON)
   - Format: `{"queries": {"card": {"highly_relevant": [...], "relevant": [...]}}}`
   - Purpose: Evaluation ground truth
   - Created by: Hand annotation or `expand_test_set_with_llm.py`

## Usage

### Creating Annotations

```bash
# Generate LLM similarity annotations (JSONL)
python -m src.ml.annotation.llm_annotator \
    --similarity 100 \
    --strategy diverse

# Output: annotations/similarity_annotations_YYYYMMDD_HHMMSS.jsonl

# Or use hand annotations (YAML)
# Hand annotations are created manually in YAML format
# See: annotations/batch_001_initial.yaml for format
```

### Converting to Training Data

```bash
# Convert LLM annotations (JSONL) to substitution pairs
python -m src.ml.scripts.convert_annotations_to_substitution_pairs \
    --input annotations/similarity_annotations_20250103.jsonl \
    --output experiments/substitution_pairs_from_annotations.json \
    --min-similarity 0.8 \
    --stats

# Convert hand annotations (YAML) to substitution pairs
python -m src.ml.scripts.convert_annotations_to_substitution_pairs \
    --input annotations/batch_001_initial.yaml \
    --output experiments/substitution_pairs_from_hand.json \
    --min-relevance 4 \
    --stats

# Or use directly in training (automatic conversion, supports both formats)
python -m src.ml.scripts.train_multitask_refined_enhanced \
    --pairs data/processed/pairs_large.csv \
    --similarity-annotations annotations/similarity_annotations_20250103.jsonl \
    --annotation-min-similarity 0.8 \
    --output embeddings/multitask_with_annotations.wv

# Hand annotations work too
python -m src.ml.scripts.train_multitask_refined_enhanced \
    --pairs data/processed/pairs_large.csv \
    --similarity-annotations annotations/batch_001_initial.yaml \
    --output embeddings/multitask_with_hand_annotations.wv
```

### Programmatic Usage

```python
from ml.utils.annotation_utils import (
    load_similarity_annotations,
    extract_substitution_pairs_from_annotations,
    convert_annotations_to_substitution_pairs,
)

# Load annotations
annotations = load_similarity_annotations(Path("annotations/similarity_annotations.jsonl"))

# Extract substitution pairs
pairs = extract_substitution_pairs_from_annotations(
    annotations,
    min_similarity=0.8,
    require_substitute_flag=True,
)

# Or convert directly
pairs = convert_annotations_to_substitution_pairs(
    annotation_path=Path("annotations/similarity_annotations.jsonl"),
    output_path=Path("experiments/substitution_pairs.json"),
    min_similarity=0.8,
)
```

## Best Practices

### Annotation Quality

1. **Use format/archetype context**: Include format and archetype metadata in prompts
2. **Filter by quality**: Use placement metadata to prioritize high-quality decks
3. **Temporal bounds**: Respect temporal splits (same as training data)
4. **Game-specific prompts**: Customize prompts per game for better quality

### Conversion Settings

- **min_similarity**: 0.8 recommended (filters low-quality pairs)
- **require_substitute_flag**: True recommended (only truly substitutable pairs)
- **similarity_type**: Prefer "functional" for substitution pairs

### Training Integration

- **Priority**: Explicit substitution pairs file > similarity annotations
- **Weight**: Substitution pairs weighted 2x higher than co-occurrence (optimal: 2.0, tested: 1.0-5.0)
  - Empirical results (2025-01-01): Weight 2.0 exceeds baseline (P@10 +2.9%, MRR +0.1%)
  - Default changed from 5.0 to 2.0 based on optimization results
- **Automatic conversion**: Training scripts automatically convert annotations if provided
- **Optimal annotation count**: ~50-60 pairs (quality > quantity)

## File Formats

### Similarity Annotation (JSONL)

```json
{
  "card1": "Lightning Bolt",
  "card2": "Chain Lightning",
  "similarity_score": 0.9,
  "similarity_type": "functional",
  "is_substitute": true,
  "reasoning": "Both are 1-mana red burn spells, functionally identical",
  "context_dependent": false,
  "example_decks": []
}
```

### Substitution Pairs (JSON)

```json
[
  ["Lightning Bolt", "Chain Lightning"],
  ["Brainstorm", "Ponder"],
  ["Path to Exile", "Swords to Plowshares"]
]
```

### Test Set (JSON)

```json
{
  "version": "1.0",
  "game": "magic",
  "queries": {
    "Lightning Bolt": {
      "highly_relevant": ["Chain Lightning", "Lava Spike"],
      "relevant": ["Fireblast", "Lava Dart"],
      "somewhat_relevant": ["Monastery Swiftspear"],
      "marginally_relevant": ["Goblin Guide"],
      "irrelevant": ["Counterspell"]
    }
  }
}
```

## Integration Points

### Training Scripts

- `train_multitask_refined_enhanced.py`: Accepts `--similarity-annotations` and `--substitution-pairs`
- `train_multitask_refined.py`: Accepts `--substitution-pairs`
- `train_embeddings_triplet_substitution.py`: Uses substitution pairs for triplet loss

### Evaluation Scripts

- `evaluate_multitask.py`: Uses substitution pairs for evaluation
- `evaluate_downstream_complete.py`: Comprehensive downstream task evaluation
- `generate_downstream_test_data.py`: Extracts substitution pairs from test sets

## Future Improvements

1. **Unified schema**: Convert all annotation formats to canonical 0-4 int scale
2. **Format-aware annotations**: Generate format-specific annotations
3. **Quality metrics**: Track annotation quality over time
4. **IAA tracking**: Inter-annotator agreement for LLM judges
5. **Temporal validation**: Automatic temporal bound checking

