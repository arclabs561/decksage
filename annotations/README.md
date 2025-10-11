# Annotation Dataset

Systematic collection of card similarity ground truth.

## Structure

```
annotations/
├── schema.yaml              # Guidelines and metadata
├── batch_001_initial.yaml   # Initial 5 queries (complete)
├── batch_002_expansion.yaml # Next 10 queries (pending)
└── batch_003_validation.yaml # Multi-annotator validation (pending)
```

## Workflow

### 1. Create Batch
```bash
cd src/ml
python annotate.py create \
  --pairs ../backend/pairs_500decks.csv \
  --num-queries 10 \
  --output ../../annotations/batch_002_expansion.yaml
```

### 2. Annotate
Edit `batch_002_expansion.yaml`:
- Fill in relevance scores (0-4)
- Add notes for edge cases
- Follow guidelines in `schema.yaml`

### 3. Validate
```bash
python annotation_manager.py
```
Checks:
- All fields filled
- Consistency with guidelines
- Inter-annotator agreement (if multiple)

### 4. Export & Evaluate
```bash
python annotation_manager.py  # Exports test_set_v1.json

python compare_models.py \
  --test-set ../../assets/experiments/test_set_v1.json \
  --models ../../data/embeddings/*.wv
```

## Best Practices

### Multiple Annotators
- **Goal:** 2-3 annotators per query for validation
- **Measure:** Cohen's kappa (agreement)
- **Resolve:** Discussion for disagreements

### Progressive Growth
- **Week 1:** 5 queries (validate process)
- **Week 2:** +10 queries (15 total)
- **Week 3:** +15 queries (30 total)
- **Week 4:** +20 queries (50 total)

### Quality Checks
- Inter-annotator agreement > 0.7 (good)
- Balanced relevance distribution
- Cover diverse archetypes
- Include edge cases

### Tracking Over Time

```
annotations/
└── metrics/
    ├── quality_2025_10_01.json  # Snapshot
    ├── quality_2025_10_08.json
    └── quality_2025_10_15.json
```

Track:
- Dataset size growth
- Inter-annotator agreement trend
- Model performance trend
- Coverage of archetypes

## Current Status

**Batch 001:** 5 queries, 1 annotator, complete  
**Coverage:** Burn (Bolt), Draw (Brainstorm), Fast Mana (Ritual), Counter (FoW), Tempo (Delver)  
**Next:** Add 10 queries covering Removal, Ramp, Card Advantage, Creatures, Combo

## Annotation Guidelines

See `schema.yaml` for:
- Relevance scale (0-4)
- Similarity types
- Annotation process
- Edge case handling



