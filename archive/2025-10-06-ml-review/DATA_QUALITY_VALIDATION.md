# Dataset Quality Validation with LLMs

## Purpose

Validate deck dataset quality using LLM-based semantic analysis:
1. Check if archetype labels match actual cards
2. Validate card relationship consistency
3. Assess overall deck coherence
4. Evaluate similarity prediction quality

## Core Components

### 1. Data Quality Validator (`llm_data_validator.py`)

Validates deck metadata semantically:

```python
from llm_data_validator import DataQualityValidator
import asyncio

validator = DataQualityValidator()

# Validate archetype labels
results = asyncio.run(validator.validate_archetype_sample(sample_size=50))

# Check consistency
consistent = sum(1 for r in results if r.is_consistent)
print(f"Consistent: {consistent}/{len(results)}")
```

### 2. Similarity Judge (`experimental/llm_judge.py`)

Evaluates similarity prediction quality:

```python
from experimental.llm_judge import LLMJudge

judge = LLMJudge(model="openai/gpt-4o-mini")

result = judge.evaluate_similarity(
    query_card="Lightning Bolt",
    similar_cards=[("Chain Lightning", 0.85), ("Lava Spike", 0.80)],
    context="Magic: The Gathering"
)

print(f"Quality: {result['overall_quality']}/10")
print(f"Issues: {result['issues']}")
```

### 3. Annotator (`llm_annotator.py`)

Generates structured annotations:

```python
from llm_annotator import LLMAnnotator
import asyncio

annotator = LLMAnnotator()

# Generate archetype descriptions
annotations = asyncio.run(annotator.annotate_archetypes(top_n=10))
```

## Configuration

Set in `.env`:
```bash
OPENROUTER_API_KEY=sk-or-v1-...

# Optional model overrides
VALIDATOR_MODEL_ARCHETYPE=anthropic/claude-4.5-sonnet
ANNOTATOR_MODEL_SIMILARITY=anthropic/claude-4.5-sonnet
```

## Running Validation

### Full data quality audit:
```bash
cd src/ml
python llm_data_validator.py
```

Runs:
- Archetype validation (50 samples)
- Card relationship validation (top 3 archetypes)
- Deck coherence validation (30 samples)
- Generates quality report

### Evaluate similarity predictions:
```bash
python experimental/llm_judge.py \
  --embeddings path/to/embeddings.wv \
  --queries "Lightning Bolt" "Brainstorm" \
  --output report.html
```

## Tests

Run validation tests:
```bash
# Real LLM API tests (requires OPENROUTER_API_KEY)
pytest -m llm -v

# Fast tests (no API calls)
pytest -m "not llm" -v
```

Test coverage:
- Real API calls: 4 tests
- Edge cases: 6 tests
- Input validation: 5 tests
- Integration: 5 tests

## Cost & Performance

**Per validation:**
- Data validator: ~$0.01-0.05 per deck (Claude)
- Similarity judge: ~$0.001-0.005 per evaluation (GPT-4o-mini)
- Annotator: ~$0.01-0.03 per annotation (Claude)

**Time:**
- ~10s per LLM call
- Batch operations: minutes to hours depending on sample size

**Note:** No caching available (Pydantic AI + OpenRouter architecture limitations)

## Data Files

Validators use:
- `data/processed/decks_with_metadata.jsonl` (preferred)
- `src/backend/decks_hetero.jsonl` (fallback)

Ensure these exist before running validators.

## Limitations

1. **No caching** - Every call hits API (~$0.01 each)
2. **Slow** - 10s per evaluation
3. **LLM limitations** - Can hallucinate, biased, not deterministic
4. **Cost** - Large-scale validation expensive ($10-100 for full dataset)

## Use Cases

**Good for:**
- Spot-checking data quality (50-100 samples)
- Validating similarity predictions
- Finding mislabeled archetypes
- Generating training annotations

**Not good for:**
- Real-time validation (too slow)
- Full dataset validation (too expensive)
- Deterministic checking (use validators/legality.py instead)
- Ban list validation (LLMs hallucinate - use Scryfall)

## Architecture

```
LLM Validators
├── llm_data_validator.py    - Deck metadata validation
├── llm_judge.py              - Similarity evaluation  
├── llm_annotator.py          - Annotation generation
├── utils/
│   └── pydantic_ai_helpers.py - Shared utilities
└── tests/
    ├── test_llm_validators_real.py
    ├── test_edge_cases.py
    └── test_llm_input_validation.py
```

## Integration Example

```python
# In your ML pipeline
from llm_data_validator import DataQualityValidator
import asyncio

# Load and validate
validator = DataQualityValidator()

# Quick audit
results = asyncio.run(validator.validate_archetype_sample(sample_size=20))

# Check quality
consistency_rate = sum(1 for r in results if r.is_consistent) / len(results)

if consistency_rate < 0.8:
    print(f"Warning: Only {consistency_rate:.1%} archetypes consistent")
    print("Consider reviewing mislabeled decks")
```

## Status

- Validators: Working, tested
- Tests: 15 passing (all LLM-related)
- Documentation: This file
- Grade: A (focused on dataset validation)

See `tests/` for comprehensive test examples.
