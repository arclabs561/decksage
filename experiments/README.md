# Experiments Directory

## Unified Test Sets

This directory contains unified test sets for all games. These are the canonical test sets used by all evaluation and training scripts.

### Active Test Sets

- `test_set_unified_magic.json` - Magic: The Gathering (940 queries, 10,569 labels)
- `test_set_unified_pokemon.json` - Pokemon TCG (58 queries, 1,175 labels)
- `test_set_unified_yugioh.json` - Yu-Gi-Oh! (58 queries, 1,065 labels)

### Canonical References

- `test_set_canonical_*.json` - Original canonical sets (kept for reference)

### Archived Test Sets

- `test_sets_archive/` - Old test sets superseded by unified sets

## Evaluation Results

- `evaluation_results_unified.json` - Evaluation results using unified test sets
- `evaluation_results.json` - Old results (5 queries only - INVALID, kept for reference)

## Usage

All scripts default to unified test sets:

```python
from ml.utils.paths import PATHS

# Load unified test set
test_set = load_test_set("magic")  # Uses test_set_unified_magic.json
```

## Maintenance

To update unified test sets:
1. Run `scripts/unify_test_sets.py` to merge new test sets
2. Test sets are automatically synced to S3
3. All scripts will use updated unified sets automatically
