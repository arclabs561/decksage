# Missing Nuances - Complete Analysis

## Critical Data Quality Issues

### 1. Missing Source Attribution (4.7%)
- **4,105 decks** missing `source` field
- **Impact**: Can't filter by source, broken data lineage
- **Fix**: Backfill from URL patterns or directory structure

### 2. Duplicate Decks (10.5%)
- **2,002 decks** with duplicate URLs
- **9,100 decks** with duplicate card lists
- **Impact**: Inflated counts, training bias
- **Fix**: Deduplicate by URL, keep best metadata

### 3. Missing Metadata
- **Archetype**: 26,572 empty (30.5%)
- **Format**: 2,031 empty (2.3%)
- **Player**: 29,390 missing (33.7%)
- **Event**: 29,387 missing (33.7%)
- **Placement**: 77,602 missing (89.1%)
- **Event Date**: 87,096 missing (100%)
- **Impact**: Limited analysis capabilities

### 4. No Validation Applied
- **Issue**: Exported decks not validated
- **Existing validators**: `src/ml/validation/validators/`
- **Impact**: Invalid decks (wrong sizes, banned cards)
- **Fix**: Run validators during export

### 5. No Card Name Normalization
- **Issue**: Names not normalized (Unicode, HTML entities)
- **Existing**: `src/backend/games/normalize.go`
- **Impact**: Same card with different names won't match
- **Fix**: Apply normalization during export

### 6. Invalid Deck Sizes
- **Min**: 1 card (invalid)
- **Max**: 3,765 cards (likely cube/set)
- **Issue**: No game-specific size validation
- **Fix**: Filter by game rules (60-card, 100-card, etc.)

### 7. Game-Specific Rules Not Enforced
- **Partitions**: Not validated per game
- **Card counts**: No copy limit checks (4-of rule, etc.)
- **Format legality**: No ban list checking
- **Fix**: Add game-specific validators

### 8. Schema Inconsistencies
- **Optional fields**: Inconsistent presence
- **Type mismatches**: `placement` sometimes string/int
- **Missing fields**: `event_date` completely missing
- **Fix**: Standardize schema, backfill fields

## Summary Statistics

**Total Decks**: 87,096

**By Game:**
- Magic: 83,092 (95.4%)
- Pokemon: 2,416 (2.8%)
- Yu-Gi-Oh: 1,588 (1.8%)

**Data Quality:**
- ✅ All have: deck_id, url, cards, game
- ⚠️ 95.3% have: source
- ⚠️ 69.5% have: archetype
- ⚠️ 97.7% have: format
- ⚠️ 66.3% have: player/event
- ⚠️ 10.9% have: placement
- ❌ 0% have: event_date

**Issues:**
- 4.7% missing source
- 30.5% missing archetype
- 2.3% missing format
- 10.5% duplicate card lists
- 2.3% duplicate URLs

## Recommended Actions

### Immediate (Priority 1)
1. Backfill missing `source` fields
2. Deduplicate by URL
3. Apply card name normalization
4. Filter invalid deck sizes

### Short-term (Priority 2)
5. Run validators on exported decks
6. Backfill missing archetypes/formats
7. Standardize schema types
8. Add game-specific validation

### Long-term (Priority 3)
9. Extract metadata from URLs
10. Query source APIs for missing data
11. Create data quality dashboard
12. Set up automated validation pipeline

## Files to Create/Update

1. `scripts/enhance_exported_decks.py` - Apply fixes
2. `scripts/validate_exported_decks.py` - Run validators
3. `scripts/backfill_metadata.py` - Fill missing fields
4. `scripts/deduplicate_decks.py` - Remove duplicates
5. Update `export_and_unify_all_decks.py` with fixes
