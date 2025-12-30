# Complete Workflow: Training, Annotating, and Comparing Models

## Overview

This guide walks through the complete process from data to rigorous model comparison.

## Phase 1: Train Multiple Models

Train different configurations to compare:

```bash
# Setup
cd src/ml
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Train baseline: dim=64, default p=q=1
python card_similarity_pecan.py \
  --input ../../data/processed/pairs_decks_only.csv \
  --dim 64 \
  --output magic_64d

# Train mid-size: dim=128
python card_similarity_pecan.py \
  --input ../../data/processed/pairs_decks_only.csv \
  --dim 128 \
  --output magic_128d

# Train large: dim=256
python card_similarity_pecan.py \
  --input ../../data/processed/pairs_decks_only.csv \
  --dim 256 \
  --output magic_256d

# Train with different p,q (BFS bias)
python card_similarity_pecan.py \
  --input ../../data/processed/pairs_decks_only.csv \
  --dim 128 \
  --p 2.0 --q 0.5 \
  --output magic_128d_bfs

# Train with DFS bias
python card_similarity_pecan.py \
  --input ../../data/processed/pairs_decks_only.csv \
  --dim 128 \
  --p 0.5 --q 2.0 \
  --output magic_128d_dfs
```

Results: 5 models in `../../data/embeddings/magic_*_pecanpy.wv`

## Phase 2: Create Annotation Tasks

Generate human annotation tasks combining all models:

```bash
python annotate.py create \
  --pairs ../../data/processed/pairs_decks_only.csv \
  --embeddings ../../data/embeddings/magic_*_pecanpy.wv \
  --num-queries 50 \
  --output ../../experiments/annotations/annotations_batch1.yaml \
  --seed 42
```

This creates `annotations_batch1.yaml` with:
- 50 query cards (stratified by popularity)
- Candidate cards from all 5 models
- Empty relevance fields to fill

## Phase 3: Annotate Test Set

Open `annotations_batch1.yaml` in your text editor:

```yaml
instructions:
  relevance_scale:
    0: Completely irrelevant (different colors, function)
    1: Somewhat related (same color or card type)
    2: Related (similar function or archetype)
    3: Very similar (often seen together)
    4: Extremely similar (near substitutes)

tasks:
- query: Lightning Bolt
  context: 'Red instant, 3 damage for R'
  candidates:
  - card: Chain Lightning
    predicted_by: [magic_128d, magic_256d, magic_128d_bfs]
    relevance: 4  # <-- Fill this in
    notes: 'Functional reprint in Legacy'
  
  - card: Lava Dart
    predicted_by: [magic_128d, magic_128d_dfs]
    relevance: 3  # <-- Fill this in
    notes: 'Flashback damage spell'
  
  - card: Mana Drain
    predicted_by: [magic_64d]
    relevance: 0  # <-- Fill this in
    notes: 'Wrong - blue counterspell, totally different'
```

**Tips:**
- Use your domain knowledge (MTG expertise)
- Be consistent across queries
- Use notes for edge cases
- Can have multiple annotators and merge later

## Phase 4: Analyze Annotations

Check annotation quality and see preliminary results:

```bash
python annotate.py analyze \
  --input annotations_batch1.yaml \
  --export test_set_v1.json
```

Output:
```
✓ All 50 tasks fully annotated

📊 Annotation Statistics:
   Tasks: 50
   Candidates: 247
   Mean relevance: 2.3

🏆 Model Precision (% relevant predictions):
   magic_256d                    : 73.2%
   magic_128d                    : 71.8%
   magic_128d_bfs                : 69.4%
   magic_128d_dfs                : 65.1%
   magic_64d                     : 58.9%

📊 Exported test set: test_set_v1.json
```

The test set JSON contains structured ground truth:

```json
{
  "Lightning Bolt": {
    "highly_relevant": ["Chain Lightning", "Lava Spike"],
    "relevant": ["Lava Dart", "Fireblast"],
    "somewhat_relevant": ["Shock"],
    "marginally_relevant": [],
    "irrelevant": ["Mana Drain", "Counterspell"]
  }
}
```

## Phase 5: Rigorous Model Comparison

Compare all models with multiple metrics:

```bash
python compare_models.py \
  --test-set ../../experiments/test_set_v1.json \
  --models ../../data/embeddings/magic_*_pecanpy.wv \
  --methods cosine euclidean \
  --output ../../experiments/comparison_results.csv
```

Output:
```
MODEL COMPARISON RESULTS
================================================================================
              model similarity    P@5    P@10   NDCG@5  NDCG@10     MRR
      magic_256d_cosine  cosine  0.8450  0.7920  0.8821   0.8543  0.9012
      magic_128d_cosine  cosine  0.8280  0.7810  0.8654   0.8432  0.8891
  magic_128d_bfs_cosine  cosine  0.8120  0.7650  0.8512   0.8301  0.8745
      magic_256d_euclidean  euclidean  0.7890  0.7340  0.8201   0.7987  0.8523
  magic_128d_dfs_cosine  cosine  0.7650  0.7210  0.8089   0.7765  0.8401
       magic_64d_cosine  cosine  0.7120  0.6890  0.7543   0.7234  0.7892

🏆 Best model: magic_256d (cosine)
   P@10: 0.7920
   NDCG@10: 0.8543
   MRR: 0.9012
```

## Phase 6: Iterative Improvement

Based on results:

### If 256d is best but marginal:
```bash
# Train even larger
python card_similarity_pecan.py \
  --input ../../data/processed/pairs_decks_only.csv \
  --dim 512 \
  --output magic_512d

# Re-evaluate
python compare_models.py \
  --test-set ../../experiments/test_set_v1.json \
  --models ../../data/embeddings/magic_256d_pecanpy.wv \
           ../../data/embeddings/magic_512d_pecanpy.wv \
  --output ../../experiments/comparison_v2.csv
```

### If BFS is bad, try intermediate:
```bash
python card_similarity_pecan.py \
  --input ../../data/processed/pairs_decks_only.csv \
  --p 1.5 --q 0.75 \
  --output magic_128d_balanced
```

### If all models struggle on certain queries:
- Check if those cards are rare/edge cases
- Extract more diverse data
- Create specialized models per format

## Phase 7: Statistical Significance

For publication/production, test significance:

```python
# In Python
import pandas as pd
from scipy import stats

df = pd.read_csv('comparison_results.csv')
baseline = df[df['model'] == 'magic_64d']['P@10'].values[0]
best = df[df['model'] == 'magic_256d']['P@10'].values[0]

# Bootstrap confidence interval (requires raw per-query scores)
# Or paired t-test if you have multiple annotators
```

## Best Practices

### Annotation Quality
- **Multiple annotators**: Have 2-3 people annotate same set
- **Inter-annotator agreement**: Compute Cohen's kappa or Fleiss' kappa
- **Consensus**: Resolve disagreements through discussion
- **Calibration**: Start with 5 examples together to align standards

### Model Selection
- **Don't overfit**: Best on test ≠ best in production
- **Consider latency**: 64d might be 4x faster than 256d
- **Inspect failures**: Look at worst queries to understand limitations
- **Diversity**: Test on different formats (Modern, Legacy, Pauper)

### Experiment Tracking
```bash
# Log every experiment
python card_similarity_pecan.py --input data.csv --dim 128 | tee log_128d.txt

# Track in spreadsheet or MLflow
model,dim,p,q,P@10,NDCG@10,training_time
magic_64d,64,1.0,1.0,0.689,0.723,23s
magic_128d,128,1.0,1.0,0.781,0.843,45s
...
```

## Example: Complete Run

```bash
# 1. Train 3 models
for dim in 64 128 256; do
  python card_similarity_pecan.py \
    --input ../../data/processed/pairs.csv \
    --dim $dim \
    --output magic_${dim}d
done

# 2. Create annotations
python annotate.py create \
  --pairs ../../data/processed/pairs.csv \
  --embeddings ../../data/embeddings/magic_*_pecanpy.wv \
  --num-queries 30 \
  --output ../../experiments/annotations/annotations.yaml

# 3. Annotate manually
# (Open annotations.yaml, fill in relevance scores)

# 4. Validate & export
python annotate.py analyze \
  --input ../../experiments/annotations/annotations.yaml \
  --export ../../experiments/test_set.json

# 5. Compare
python compare_models.py \
  --test-set ../../experiments/test_set.json \
  --models ../../data/embeddings/magic_*_pecanpy.wv \
  --output ../../experiments/results.csv

# 6. View results
cat ../../experiments/results.csv
```

## Going Further

### Cross-validation
Split into multiple test sets, average results:

```bash
for seed in 42 43 44 45 46; do
  python annotate.py create \
    --seed $seed \
    --output ../../experiments/annotations/annotations_fold${seed}.yaml
  
  # Annotate, then:
  python compare_models.py \
    --test-set ../../experiments/test_set_fold${seed}.json \
    --models ../../data/embeddings/magic_*.wv \
    --output ../../experiments/results_fold${seed}.csv
done

# Average results across folds
```

### Per-archetype analysis
Create test sets for specific archetypes:

```yaml
# annotations_burn.yaml - Only burn spells
# annotations_control.yaml - Only control cards
# annotations_creatures.yaml - Only creatures
```

### Production deployment
Once you have a winner:

```bash
# Use best model
cp ../../data/embeddings/magic_256d_pecanpy.wv ../../data/embeddings/production.wv

# Build API (see api.py)
python api.py --embeddings ../../data/embeddings/production.wv
```

## Troubleshooting

**Problem**: All models have low P@10 (<0.5)

**Solutions**:
- Data quality: Extract more diverse decks
- Graph quality: Remove noise edges
- Task difficulty: Queries might be too hard/ambiguous

**Problem**: 256d not better than 128d

**Solutions**:
- Not enough data (overfitting larger model)
- Train longer (more walks/epochs)
- Try different p,q parameters

**Problem**: Models disagree wildly with annotations

**Solutions**:
- Check if embeddings trained on same data as test queries
- Verify annotation quality (inter-annotator agreement)
- Look at specific failure cases for insights

