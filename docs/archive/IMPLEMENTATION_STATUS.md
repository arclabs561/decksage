# Strategic Data Priorities - Implementation Status

**Date**: 2025-01-27  
**Status**: Core infrastructure complete, ready for data generation

---

## ✅ Completed

### 1. LLM-as-Judge for Batch Evaluation
**File**: `src/ml/annotation/llm_judge_batch.py`

- ✅ Batch judgment of similarity predictions
- ✅ Converts judgments to test set format
- ✅ Supports top-k evaluation
- ✅ Cost: ~$0.002 per judgment

**Usage**:
```bash
python -m src.ml.annotation.llm_judge_batch \
    --test-set experiments/test_set_canonical_magic.json \
    --predictions predictions.json \
    --output judgments.json \
    --top-k 20
```

### 2. Sideboard Signal Integration
**Files**: 
- `src/ml/similarity/sideboard_signal.py` (signal computation)
- `src/ml/similarity/fusion.py` (integration)

- ✅ Sideboard co-occurrence computation
- ✅ Mainboard-sideboard transition signals
- ✅ Integrated into `FusionWeights` (0.1 weight)
- ✅ Added to all aggregation methods

**Usage**:
```python
from src.ml.similarity.sideboard_signal import compute_sideboard_cooccurrence
from src.ml.similarity.fusion import WeightedLateFusion, FusionWeights

sb_cooccur = compute_sideboard_cooccurrence(decks_path)
fusion = WeightedLateFusion(
    ...,
    sideboard_cooccurrence=sb_cooccur,
    weights=FusionWeights(sideboard=0.1)
)
```

### 3. Temporal Trend Analysis
**File**: `src/ml/analysis/temporal_trends.py`

- ✅ Monthly co-occurrence computation
- ✅ Trending pair detection
- ✅ Card popularity trends
- ✅ Temporal similarity signal (recent months weighted higher)
- ✅ Integrated into `FusionWeights` (0.05 weight)

**Usage**:
```python
from src.ml.analysis.temporal_trends import compute_monthly_cooccurrence, find_trending_pairs

monthly_cooccur = compute_monthly_cooccurrence(decks_path)
trending = find_trending_pairs(monthly_cooccur)
```

### 4. Fusion Weights Updated
**File**: `src/ml/similarity/fusion.py`

- ✅ Added `sideboard` and `temporal` to `FusionWeights`
- ✅ Updated normalization
- ✅ Added similarity methods: `_get_sideboard_similarity()`, `_get_temporal_similarity()`
- ✅ Integrated into all aggregation methods (weighted, RRF, CombSum, CombMax, CombMin)
- ✅ Added to ranking computation for RRF

**New Default Weights**:
- embed: 0.25
- jaccard: 0.25
- functional: 0.25
- text_embed: 0.1
- sideboard: 0.1
- temporal: 0.05

### 5. Bootstrap Script
**File**: `src/ml/scripts/bootstrap_all_annotations.py`

- ✅ Automated bootstrap for all games
- ✅ Targets: 12 MTG, 15 Pokemon, 12 YGO
- ✅ Generates YAML files for human verification

**Usage**:
```bash
python -m src.ml.scripts.bootstrap_all_annotations
```

---

## 🔄 Next Steps (Data Generation)

### Phase 1: Generate Sideboard & Temporal Signals

1. **Compute Sideboard Co-occurrence**:
```bash
cd src/ml
uv run python -c "
from similarity.sideboard_signal import compute_sideboard_cooccurrence
from utils.paths import PATHS
import json

sb_cooccur = compute_sideboard_cooccurrence(PATHS.decks_with_metadata, min_decks=5)
with open('experiments/sideboard_cooccurrence.json', 'w') as f:
    json.dump(sb_cooccur, f)
print(f'Computed sideboard co-occurrence for {len(sb_cooccur)} cards')
"
```

2. **Compute Temporal Trends**:
```bash
cd src/ml
uv run python -c "
from analysis.temporal_trends import compute_monthly_cooccurrence, find_trending_pairs
from utils.paths import PATHS
import json

monthly_cooccur = compute_monthly_cooccurrence(PATHS.decks_with_metadata, min_decks_per_month=20)
trending = find_trending_pairs(monthly_cooccur, min_months=3)

with open('experiments/monthly_cooccurrence.json', 'w') as f:
    json.dump(monthly_cooccur, f)
with open('experiments/trending_pairs.json', 'w') as f:
    json.dump([{'card1': c1, 'card2': c2, 'trend': t} for c1, c2, t in trending[:100]], f)

print(f'Computed {len(monthly_cooccur)} months of data')
print(f'Found {len(trending)} trending pairs')
"
```

### Phase 2: LLM Bootstrap Annotations

3. **Bootstrap Test Set Expansion**:
```bash
# Requires OPENROUTER_API_KEY
python -m src.ml.scripts.bootstrap_all_annotations
```

**Expected Output**:
- `annotations/batch_magic_expansion.yaml` (12 queries)
- `annotations/batch_pokemon_expansion.yaml` (15 queries)
- `annotations/batch_yugioh_expansion.yaml` (12 queries)

**Cost**: ~$2-5 for all games

### Phase 3: LLM-as-Judge Evaluation

4. **Run Batch Evaluation**:
```bash
# First, generate predictions
python -m src.ml.evaluation.fusion_grid_search  # or your evaluation script

# Then judge predictions
python -m src.ml.annotation.llm_judge_batch \
    --test-set experiments/test_set_canonical_magic.json \
    --predictions experiments/predictions_magic.json \
    --output experiments/judgments_magic.json \
    --top-k 20
```

**Cost**: ~$40 for 20k judgments (100 queries × 20 candidates)

---

## 📊 Integration Points

### API Integration

To use new signals in the API, update `src/ml/api/api.py`:

```python
from src.ml.similarity.sideboard_signal import compute_sideboard_cooccurrence
from src.ml.analysis.temporal_trends import compute_monthly_cooccurrence

# Load signals (cache these)
sb_cooccur = compute_sideboard_cooccurrence(PATHS.decks_with_metadata)
monthly_cooccur = compute_monthly_cooccurrence(PATHS.decks_with_metadata)

# Pass to fusion
fusion = WeightedLateFusion(
    ...,
    sideboard_cooccurrence=sb_cooccur,
    temporal_cooccurrence=monthly_cooccur,
    weights=FusionWeights(sideboard=0.1, temporal=0.05)
)
```

### Evaluation Integration

Update evaluation scripts to:
1. Load sideboard/temporal signals
2. Pass to fusion model
3. Compare performance with/without new signals

---

## 🎯 Expected Impact

### Sideboard Signal
- **Use Case**: "What do people sideboard in Burn?"
- **Expected**: High precision for sideboard-specific queries
- **Reality Check**: Co-occurrence excels at this (from `REALITY_FINDINGS.md`)

### Temporal Signal
- **Use Case**: "What's trending with Lightning Bolt?"
- **Expected**: Better recency (recent meta shifts)
- **Reality Check**: Discovers emerging synergies

### LLM-as-Judge
- **Use Case**: Large-scale evaluation without human annotation
- **Expected**: 100x faster than human annotation
- **Reality Check**: Needs calibration against human annotations (n=100)

---

## ⚠️ Known Limitations

1. **Sideboard Signal**: Requires decks with sideboard data (partition="Sideboard")
2. **Temporal Signal**: Requires deck dates in metadata
3. **LLM-as-Judge**: Cost scales with number of queries × candidates
4. **Signal Quality**: New signals need validation against test sets

---

## 📈 Success Metrics

- **Sideboard Signal**: P@10 improvement for sideboard-specific queries
- **Temporal Signal**: Better recency in recommendations
- **LLM-as-Judge**: Correlation >0.8 with human annotations
- **Test Set Expansion**: 100+ queries total (currently 61)

---

## 🔗 Related Files

- `STRATEGIC_DATA_PRIORITIES.md` - Original analysis
- `src/ml/experimental/REALITY_FINDINGS.md` - What actually works
- `DEEP_REVIEW_TRIAGED_ACTIONS.md` - Original action plan
- `src/ml/analysis/sideboard_analysis.py` - Existing sideboard analysis
- `src/ml/analysis/archetype_staples.py` - Archetype staple detection
