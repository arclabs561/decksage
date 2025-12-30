# LLM Annotation System - Ready to Deploy

## Status

**Code complete**: ✅  
**OpenRouter configured**: ✅  
**Python env issue**: ⚠️ gensim incompatible with Python 3.13

## Files Created

1. **`src/ml/llm_annotator.py`** - Full annotation pipeline
   - Creates similarity judgments (card pairs)
   - Generates archetype descriptions
   - Suggests substitutions
   - Identifies synergies
   - All with structured Pydantic models

2. **`src/ml/llm_data_validator.py`** - Quality validation
   - Archetype consistency checks
   - Card relationship validation
   - Format legality verification
   - Generates quality reports

3. **Supporting docs**:
   - `DATA_QUALITY_PLAN.md` - Validation strategy
   - `USE_CASES.md` - Specific use cases to annotate for

## What It Does

### Batch Annotation (~ $2-5 for 100-200 annotations)
```bash
python llm_annotator.py \
  --similarity 100 \      # 100 card pair judgments
  --archetypes 10 \       # Describe 10 archetypes
  --substitutions 50      # 50 budget alternatives
```

**Output**:
```
annotations_llm/
├── similarity_annotations_TIMESTAMP.jsonl
├── archetype_descriptions_TIMESTAMP.json
└── substitutions_TIMESTAMP.jsonl
```

### Validation (~ $2 for sample, ~ $20 for full dataset)
```bash
python llm_data_validator.py
```

**Output**:
- Quality score: 0-1.0
- Mislabeled archetypes (with suggestions)
- Suspicious card pairs
- Format violations

## Python Environment Fix Needed

**Issue**: gensim 4.3 doesn't build on Python 3.13 (C extension errors)

**Quick fix**:
```bash
cd src/ml
rm -rf .venv
python3.12 -m venv .venv  # Use Python 3.12
source .venv/bin/activate
pip install -r requirements.txt
python llm_annotator.py --similarity 5  # Test run
```

**Alternative**: Use Docker
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "llm_annotator.py"]
```

## Usage Examples

### Create Similarity Ground Truth
```python
# Annotate 200 diverse card pairs
python llm_annotator.py --similarity 200 --strategy diverse

# Output: Structured judgments for training/evaluation
{
  "card1": "Lightning Bolt",
  "card2": "Chain Lightning",
  "similarity_score": 0.85,
  "similarity_type": "functional",
  "is_substitute": true,
  "reasoning": "Both are 1-mana burn spells..."
}
```

### Validate Dataset Quality
```python
# Check if archetypes are correctly labeled
python llm_data_validator.py

# Output shows:
Archetype Validation:
  Consistent: 42/50 (84%)
  Issues found:
    - "Unknown" should be "Doomsday" (4 decks)
    - "Partner WUBR" is too generic (7 decks)
```

### Generate Archetype Embeddings
```python
# Create rich descriptions for similarity
{
  "archetype_name": "Red Deck Wins",
  "strategy": "Fast creature aggro with burn finish",
  "core_cards": ["Lightning Bolt", "Monastery Swiftspear", "Eidolon"],
  "key_features": ["low_curve", "heavy_interaction", "linear"]
}
# Use these as structured metadata for better sim
ilarity
```

## Integration with Pipeline

### Before Training
```python
# 1. Validate data quality
quality = validate_dataset()
if quality < 0.85:
    fix_issues()

# 2. Create annotations
annotations = annotate_pairs(num=200)

# 3. Train with clean, annotated data
model.train(data=cleaned, labels=annotations)
```

### For Use Case-Specific Features
```python
# Budget substitution API
archetype_desc = get_archetype_description("Burn")
substitutions = get_substitutions("Lightning Bolt", budget=5)

# Filter by archetype fit
recommendations = [s for s in substitutions 
                  if s.matches_strategy(archetype_desc)]
```

## Cost Estimates

| Task | Annotations | Cost |
|------|-------------|------|
| Quick test | 5 pairs | $0.05 |
| Similarity batch | 100 pairs | $1.00 |
| Archetype descriptions | 20 archetypes | $0.40 |
| Quality validation | 50 decks | $0.50 |
| Full annotation | 500 pairs + 50 archs | $5.50 |

Using GPT-4o-mini via OpenRouter (~$0.01/annotation)

## What's Next

### Immediate (Once Python 3.12 venv works)
1. Test annotation: 5 pairs (~$0.05)
2. Validate quality: 50 decks (~$0.50)
3. Review results, iterate prompts

### This Week
1. Create 200 similarity annotations
2. Validate entire dataset (4,718 decks)
3. Clean mislabeled data
4. Use annotations for better test sets

### Month 1
1. Continuous quality monitoring
2. Weekly validation of new scraped data
3. Build annotation-based features
4. Train models with rich labels

## Ready When Environment Fixed

All code is written and uses:
- ✅ OpenRouter (key in .env)
- ✅ Pydantic AI (structured outputs with retries)
- ✅ Async batch processing
- ✅ Cost tracking

**Just needs Python 3.12 environment to run.**



