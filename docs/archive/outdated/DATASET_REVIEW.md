# Dataset Review

## Overview

This review covers all datasets in the DeckSage project, including raw data, processed data, test sets, embeddings, and annotations.

## Fixes Applied (Latest Update)

### Completed
1. ✅ **Expanded ground_truth_v1.json**: 5 → 38 queries (merged with canonical test set)
2. ✅ **Created embedding documentation**: `data/embeddings/README.md` documents all 19 embeddings
3. ✅ **Created validation script**: `scripts/validate_datasets.py` checks data consistency
4. ✅ **Documented multi-game issue**: Added note about pairs_multi_game.csv naming

### Remaining Issues
1. ⚠️ **pairs_multi_game.csv**: Still contains only MTG data (documented in NOTE file)
2. ⚠️ **decks_pokemon.jsonl**: Still empty (requires data collection)
3. ⚠️ **Test sets**: Pokemon (10) and Yu-Gi-Oh (13) still below targets

---

## Dataset Inventory

### Raw Data

#### Deck Data
- **`data/decks/yugioh_decks.jsonl`**: 20 Yu-Gi-Oh decks
  - Format: JSONL with deck metadata, archetype, format, source URL, and card lists
  - Issue: Very small sample (only 20 decks)
  
- **`data/processed/decks_pokemon.jsonl`**: 0 Pokemon decks
  - Issue: File is empty

#### Card Attributes
- **`data/processed/card_attributes_enriched.csv`**: 47,131 cards
  - Columns: name, type, colors, mana_cost, cmc, rarity, power, toughness, set, set_name, oracle_text, keywords
  - Status: Well-structured, comprehensive attributes
  
- **`data/processed/card_attributes_minimal.csv`**: 26,960 cards
  - Status: Subset of enriched attributes

### Processed Co-occurrence Data

#### Pairs Data
- **`data/processed/pairs_large.csv`**: 7,541,436 pairs
  - Format: NAME_1, NAME_2, COUNT, DECK_ID, SOURCE
  - Status: Large dataset, appears to be MTG-only despite name
  
- **`data/processed/pairs_multi_game.csv`**: 24,605,118 pairs
  - Format: NAME_1, NAME_2, GAME_1, GAME_2, COUNT, DECK_ID, SOURCE
  - Issue: Despite name, appears to contain only MTG data (GAME_1/GAME_2 columns exist but all values are "MTG" in sample)
  - Status: Very large dataset, but multi-game claim is questionable

### Test Sets

#### Canonical Test Sets
- **`experiments/test_set_canonical_magic.json`**: 38 queries, 156 total labels
  - Format: Query card → relevance categories (highly_relevant, relevant, somewhat_relevant, marginally_relevant, irrelevant)
  - Status: Well-structured, good coverage for MTG
  
- **`experiments/test_set_canonical_pokemon.json`**: 10 queries, 38 total labels
  - Issue: Small size (target is 25+ queries)
  
- **`experiments/test_set_canonical_yugioh.json`**: 13 queries, 43 total labels
  - Issue: Small size (target is 25+ queries)

#### Ground Truth
- **`data/processed/ground_truth_v1.json`**: 5 queries, 52 total labels
  - Format: Same as canonical test sets
  - Issue: Very small (only 5 queries: Lightning Bolt, Brainstorm, Dark Ritual, Force of Will, Delver of Secrets)
  - Status: High quality but insufficient for evaluation

### Embeddings

**Location**: `data/embeddings/`

**Count**: 19 embedding files (.wv format)

**Notable Embeddings**:
- `production.wv` - Production deployment
- `trained_contrastive_substitution_v2.wv` - Latest contrastive model
- `trained_functional_improved.wv` - Improved functional similarity
- `multitask_sub2.wv`, `multitask_sub5.wv`, `multitask_sub10.wv` - Multi-task variants
- `node2vec_*.wv` - Graph-based embeddings (bfs, dfs, default)
- `deepwalk.wv` - DeepWalk embeddings
- `oracle_text_embeddings.pkl` - Text-based embeddings

**Status**: Good variety of embedding methods, but unclear which are actively used vs experimental.

### Annotations

**Location**: `annotations/`

- **`batch_001_initial.yaml`**: Initial annotation batch
- **`batch_auto_generated.yaml`**: Auto-generated batch
- **`test_batch_oct_3.json`**: 5 test items with deck annotations
- **`llm_judgments/judgment_20251001_105332.json`**: LLM-generated judgments

**Status**: Annotation workflow exists but appears underutilized.

## Data Quality Issues

### Critical Issues

1. **Multi-game data is actually single-game**
   - `pairs_multi_game.csv` has GAME_1/GAME_2 columns but all sampled values are "MTG"
   - Either the file is misnamed or multi-game data wasn't properly integrated

2. **Missing Pokemon deck data**
   - `decks_pokemon.jsonl` is empty
   - Pokemon test set exists (10 queries) but no deck data to train on

3. **Very small ground truth**
   - Only 5 queries in `ground_truth_v1.json`
   - Insufficient for rigorous evaluation

### Moderate Issues

4. **Small Yu-Gi-Oh deck sample**
   - Only 20 decks in `yugioh_decks.jsonl`
   - Likely insufficient for training quality embeddings

5. **Test set coverage gaps**
   - Pokemon: 10 queries (target: 25+)
   - Yu-Gi-Oh: 13 queries (target: 25+)
   - Magic: 38 queries (target: 50+)

6. **Embedding inventory unclear**
   - 19 embedding files but unclear which are:
     - Production-ready
     - Experimental
     - Deprecated
   - No clear documentation on embedding lineage

## Recommendations

### Immediate Actions

1. **Verify multi-game data**
   ```bash
   # Check if pairs_multi_game.csv actually contains multiple games
   cut -d',' -f3,4 data/processed/pairs_multi_game.csv | sort | uniq -c | head -20
   ```
   - If only MTG: Rename file or fix data pipeline
   - If multiple games: Document which games are included

2. **Populate Pokemon deck data**
   - Either scrape Pokemon decks or remove Pokemon from multi-game claims
   - Current state: Pokemon test set exists but no training data

3. **Expand ground truth**
   - Current 5 queries is insufficient
   - Target: 20-30 queries minimum for statistical rigor
   - Use annotation workflow in `annotations/README.md`

### Short-term Improvements

4. **Expand test sets to targets**
   - Pokemon: 10 → 25 queries
   - Yu-Gi-Oh: 13 → 25 queries
   - Magic: 38 → 50 queries
   - Use `src/ml/scripts/generate_all_annotation_batches` workflow

5. **Document embedding lineage**
   - Create `data/embeddings/README.md` documenting:
     - Which embeddings are production-ready
     - Training configuration for each
     - Performance metrics
     - Deprecation status

6. **Validate data consistency**
   - Check that card names in pairs match card names in attributes
   - Verify deck IDs in pairs match actual deck files
   - Ensure test set queries exist in card attributes

### Long-term Enhancements

7. **Data versioning**
   - Add version metadata to all datasets
   - Track data lineage (source → processed → test set)
   - Document data collection dates

8. **Automated quality checks**
   - Script to validate:
     - No duplicate pairs
     - All test set queries exist in card attributes
     - Deck files are non-empty
     - Embeddings match expected vocabulary

9. **Multi-game support**
   - If multi-game is a goal:
     - Verify data collection covers all target games
     - Ensure test sets are balanced across games
     - Document game-specific considerations

## Dataset Statistics Summary

| Dataset | Size | Status | Issues |
|---------|------|--------|--------|
| `pairs_large.csv` | 7.5M pairs | ✅ Good | Single game only |
| `pairs_multi_game.csv` | 24.6M pairs | ⚠️ Questionable | Claims multi-game but appears MTG-only |
| `card_attributes_enriched.csv` | 47K cards | ✅ Good | - |
| `yugioh_decks.jsonl` | 20 decks | ⚠️ Small | Needs more data |
| `decks_pokemon.jsonl` | 0 decks | ❌ Empty | Critical issue |
| `test_set_canonical_magic.json` | 38 queries | ✅ Good | Could expand |
| `test_set_canonical_pokemon.json` | 10 queries | ⚠️ Small | Below target |
| `test_set_canonical_yugioh.json` | 13 queries | ⚠️ Small | Below target |
| `ground_truth_v1.json` | 5 queries | ❌ Too small | Critical issue |
| Embeddings | 19 files | ✅ Good | Needs documentation |

## Next Steps

1. Run data validation script to check consistency
2. Investigate multi-game data claim
3. Prioritize expanding Pokemon/Yu-Gi-Oh test sets
4. Document embedding inventory
5. Create automated quality checks
