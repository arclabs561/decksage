# Data Quality Validation Plan

## Overview

Use LLMs to validate data quality at scale across 4,718+ decks.

## Validation Phases

### Phase 1: Archetype Consistency (50 samples)
**Question**: Does archetype label match actual cards?

**Example:**
```
Claimed: "Aggro"
Cards: Island, Counterspell, Control Magic, ...
→ LLM: "Not consistent - these are control cards" ❌
```

**Output**: 
- % of archetypes correctly labeled
- Suggested relabeling for inconsistent decks
- Common mislabeling patterns

**Action**: Relabel or remove inconsistent decks

---

### Phase 2: Card Relationship Validity (60 pairs)
**Question**: Do common card pairs make sense?

**Example:**
```
Pair: Lightning Bolt + Monastery Swiftspear
Archetype: Burn
→ LLM: "Makes sense - both aggressive red cards" ✅

Pair: Lightning Bolt + Ancient Tomb
Archetype: Unknown
→ LLM: "Suspicious - different strategies" ⚠️
```

**Output**:
- % of pairs that make sense
- Suspicious pairs (might be data errors)
- Relationship types (synergy/staples/suspicious)

**Action**: Investigate outliers, might reveal data corruption

---

### Phase 3: Format Legality (90 decks)
**Question**: Are decks legal in claimed format?

**Example:**
```
Format: Modern
Cards: ..., Black Lotus, ...
→ LLM: "Illegal - Black Lotus banned in Modern" ❌
```

**Output**:
- % of decks with format violations
- Banned cards found
- Wrong rarity (Pauper)

**Action**: Remove illegal decks or fix format labels

---

### Phase 4: Overall Quality Score
**Combines all validations:**
```
Quality Score = 0.4 * archetype_consistency 
              + 0.3 * relationship_validity
              + 0.3 * format_legality
```

**Target**: Score > 0.85 = "High quality dataset"

---

## Implementation

### Batch Processing
```python
# Sample validation (cheap)
validator = DataQualityValidator()
await validator.validate_archetype_sample(50)      # ~$0.50
await validator.validate_card_relationships(60)     # ~$0.60
await validator.validate_format_legality(90)        # ~$0.90
# Total: ~$2 for initial quality check
```

### Full Validation (if needed)
```python
# All 4,718 decks (expensive)
await validator.validate_all_archetypes()           # ~$50
await validator.validate_all_relationships()        # ~$100
await validator.validate_all_formats()              # ~$50
# Total: ~$200 for comprehensive validation
```

**Recommendation**: Start with sample, only go full if issues found

---

## Expected Findings

Based on initial experiments:

### Likely Issues
1. **Generic archetype labels** - "Unknown", "Partner WUBR" (not descriptive)
2. **Format mislabeling** - cEDH vs Duel Commander confusion
3. **Outlier cards** - Random cards in decks (scraping errors?)

### Quality Estimates
- Archetype consistency: ~70-80% (some generic labels)
- Card relationships: ~85-90% (mostly valid)
- Format legality: ~95%+ (rare violations)

**Overall expected quality: 0.80-0.85** (Good but improvable)

---

## Automation

### Weekly Quality Checks
```bash
# Run on new data batches
python llm_data_validator.py --new-decks-only --sample 50

# Generate trend report
python quality_trends.py --weeks 4
```

### Continuous Validation
```python
# On data ingestion
for new_deck in scrape_tournament():
    if not quick_validate(new_deck):
        flag_for_review(new_deck)
```

---

## Output Format

### JSON Report
```json
{
  "timestamp": "2025-10-02T15:30:00",
  "dataset": {"total_decks": 4718, "validated": 50},
  "archetype_validation": {
    "consistent": 38,
    "inconsistent": 12,
    "avg_confidence": 0.82,
    "issues_by_archetype": {
      "Unknown": ["Needs better label", ...],
      "Partner WUBR": ["Too generic", ...]
    }
  },
  "summary": {
    "quality_score": 0.83,
    "critical_issues": ["12 mislabeled archetypes"],
    "recommendations": ["Review 'Unknown' labels", ...]
  }
}
```

### Human-Readable Report
```
DATA QUALITY REPORT
====================

Archetype Validation:
  Consistent: 38/50 (76.0%)
  Avg Confidence: 0.82

Card Relationships:
  Red Deck Wins: 18/20 valid (90.0%)
  Affinity: 19/20 valid (95.0%)
  Reanimator: 17/20 valid (85.0%)

Format Legality:
  Modern: 29/30 legal (96.7%)
  Pauper: 30/30 legal (100%)
  Legacy: 28/30 legal (93.3%)

Quality Score: 0.83/1.0

✅ Dataset quality is GOOD
⚠️  12 archetypes need relabeling
⚠️  2 Legacy decks have banned cards
```

---

## Integration with Pipeline

```python
# After scraping
decks = scrape_tournament_source()

# Validate batch
validator = DataQualityValidator()
results = await validator.validate_batch(decks)

# Filter by quality
high_quality = [d for d, score in results if score > 0.8]

# Save with quality scores
save_with_metadata(high_quality, quality_scores=results)
```

---

## Cost Management

**Per validation costs (GPT-4o-mini):**
- Archetype check: ~$0.01 per deck
- Card relationship: ~$0.01 per pair
- Format legality: ~$0.01 per deck

**Budget strategies:**
1. **Sample validation**: $2-5 for quick check
2. **Incremental**: Validate new data as it arrives
3. **Problem-focused**: Only validate suspicious decks
4. **Confidence-based**: Skip high-confidence items

---

## Success Metrics

**Goals:**
- Quality score > 0.85
- < 5% archetype mislabeling
- < 1% format violations
- Identify and fix data corruption

**Outcome:**
- Cleaner training data
- More reliable similarity results
- Confidence in published baselines
- Automated quality monitoring



