# Strategic Data Priorities: What Matters Most

**Date**: 2025-01-27  
**Context**: Identifying critical data gaps, annotation needs, LLM opportunities, and scraping potential

---

## Executive Summary

**Current Reality**: P@10 = 0.08 plateau for co-occurrence alone. Need multi-modal signals + better evaluation.

**Critical Gaps**:
1. **Gold Annotations**: 38 MTG, <20 Pokemon/YGO → Need 100+ total
2. **Implicit Signals**: Sideboard patterns, temporal trends, matchup data (underutilized)
3. **LLM Synthetic Data**: Can bootstrap 1000s of judgments cheaply (~$0.002/card)
4. **Scraping Opportunities**: Tournament results, meta trends, deck evolution over time

---

## 1. Missing Datasets & Gold Annotations

### Current Test Sets

| Game | Current | Target | Gap | Status |
|------|---------|--------|-----|--------|
| **MTG** | 38 queries | 50 | 12 | ⚠️ Close |
| **Pokemon** | ~10 queries | 25 | 15 | ⚠️ Needs work |
| **Yu-Gi-Oh** | ~13 queries | 25 | 12 | ⚠️ Needs work |
| **Total** | **~61** | **100** | **39** | ⚠️ **Critical** |

### What We Need

**Gold Annotations (Human-Verified)**:
- ✅ **Functional substitutes**: "Can X replace Y?" (highest value)
- ✅ **Synergy pairs**: "Do X and Y work together?" (high value)
- ✅ **Archetype staples**: "What's essential in Burn?" (medium value)
- ⚠️ **Format-specific**: "Modern vs Legacy substitutes" (low value - reality shows this fails)

**Annotation Strategy**:
1. **LLM Bootstrap** → Generate 1000s of draft annotations (~$2-5)
2. **Human Verify** → Review top 200-300 for quality
3. **Active Learning** → Prioritize uncertain/high-impact queries

**Priority**: **T0.1** - Blocks all reliable evaluation

---

## 2. What Can We Synthetically Judge with LLMs?

### Already Implemented ✅

**`llm_annotator.py`** provides:
- ✅ Card similarity judgments (0-1 score + reasoning)
- ✅ Archetype descriptions (strategy, core cards, flex slots)
- ✅ Substitution recommendations (quality score, trade-offs)
- ✅ Synergy analysis (combo cards, anti-synergy)
- ✅ Functional categorization

**`annotation_bootstrap_llm.py`** provides:
- ✅ Batch candidate generation (12-24 candidates per query)
- ✅ Draft relevance scores (0-4 scale)
- ✅ Schema-aligned YAML output

### What We Can Add (High Value)

#### 2.1. LLM-as-Judge for Evaluation ✅ **IMMEDIATE OPPORTUNITY**

**Use Case**: Judge similarity of model predictions without human annotation

```python
# For each query in test set:
query = "Lightning Bolt"
predictions = model.similar(query, top_k=20)  # Model predictions

# LLM judges each prediction
for card, score in predictions:
    judgment = llm_judge_similarity(query, card)
    # Returns: relevance (0-4), reasoning, confidence
```

**Benefits**:
- **Scale**: Judge 1000s of predictions cheaply (~$0.002 per judgment)
- **Consistency**: Same judge for all comparisons
- **Speed**: 100x faster than human annotation
- **Calibration**: Can validate against human annotations (n=100)

**Cost**: ~$0.002 per judgment × 1000 queries × 20 candidates = **$40** for 20k judgments

**Implementation**: Extend `llm_annotator.py` with batch judgment mode

#### 2.2. LLM-Generated Synthetic Test Queries

**Use Case**: Generate diverse test queries covering edge cases

```python
# Generate queries for underrepresented categories
queries = llm_generate_test_queries(
    categories=["removal", "ramp", "combo_pieces", "win_conditions"],
    game="magic",
    n_per_category=10
)
```

**Benefits**:
- **Coverage**: Ensure all card types/archetypes represented
- **Edge Cases**: Include difficult queries (rare cards, format-specific)
- **Balance**: Stratified sampling across dimensions

**Cost**: ~$0.01 per query × 100 queries = **$1**

#### 2.3. LLM Archetype Analysis (Already Partially Done)

**Use Case**: Extract archetype knowledge from deck data

```python
# For each archetype with 20+ decks:
archetype_data = llm_analyze_archetype(
    archetype="Burn",
    sample_decks=decks_by_archetype["Burn"][:10],
    format="Modern"
)
# Returns: core_cards, flex_slots, strategy, mana_curve, etc.
```

**Benefits**:
- **Staples Detection**: Identify cards appearing in 70%+ of archetype decks
- **Flex Slot Analysis**: Understand what's replaceable
- **Meta Positioning**: Understand archetype role (aggro/control/combo)

**Cost**: ~$0.01 per archetype × 50 archetypes = **$0.50**

#### 2.4. LLM Deck Quality Assessment

**Use Case**: Judge whether completed decks are tournament-viable

```python
quality = llm_assess_deck_quality(
    deck=completed_deck,
    format="Modern",
    archetype="Burn"
)
# Returns: viability_score, issues, recommendations
```

**Benefits**:
- **Validation**: Check if deck completion actually works
- **Feedback**: Explain why deck is good/bad
- **Calibration**: Compare to tournament deck quality

**Cost**: ~$0.01 per deck × 100 decks = **$1**

### LLM Synthetic Data Summary

| Task | Cost | Scale | Value | Priority |
|------|------|-------|-------|----------|
| **LLM-as-Judge** | $40 | 20k judgments | ⭐⭐⭐⭐⭐ | **T0** |
| **Test Query Generation** | $1 | 100 queries | ⭐⭐⭐⭐ | T1 |
| **Archetype Analysis** | $0.50 | 50 archetypes | ⭐⭐⭐ | T1 |
| **Deck Quality** | $1 | 100 decks | ⭐⭐⭐ | T2 |

**Total LLM Budget**: ~$50 for comprehensive synthetic evaluation

---

## 3. What Can We Extract Explicitly from Scraping?

### Already Scraping ✅

**Tournament Decks**:
- ✅ MTGTop8 (55k decks)
- ✅ MTGDecks.net (10k+ target)
- ✅ Limitless TCG (1.2k Pokemon)
- ✅ YGOPRODeck (520 YGO)

**Card Data**:
- ✅ Scryfall (35k MTG cards)
- ✅ Pokemon TCG Data (19k cards)
- ✅ YGOPRODeck (13.9k YGO cards)

**Enrichment**:
- ✅ EDHREC (Commander data)
- ✅ Pricing (Scryfall, TCGPlayer models)

### Missing Explicit Data (High Value)

#### 3.1. Tournament Results & Matchups ⭐⭐⭐⭐⭐

**What**: Win/loss records, matchup data, meta share

**Sources**:
- **MTGGoldfish**: Meta share, win rates by archetype
- **MTGTop8**: Tournament brackets (if available)
- **Limitless TCG**: Pokemon tournament results
- **YGOPRODeck**: Tournament standings

**Extract**:
- Win rate by archetype
- Matchup win rates (Burn vs Control, etc.)
- Meta share over time
- Deck performance by format

**Value**: **CRITICAL** - Enables deck quality validation
- "Does this deck win?" (not just "does it look similar?")
- Matchup-specific recommendations
- Meta positioning

**Effort**: Medium (new scrapers needed)

#### 3.2. Temporal Trends ⭐⭐⭐⭐

**What**: How deck composition changes over time

**Extract from existing data**:
- Deck composition by month/quarter
- Card popularity trends
- Archetype rise/fall
- Ban list impact

**Value**: 
- Understand meta evolution
- Predict future trends
- Temporal similarity (cards that rise/fall together)

**Effort**: Low (analyze existing deck dates)

#### 3.3. Sideboard Patterns ⭐⭐⭐⭐

**What**: What cards appear in sideboards vs mainboards

**Extract from existing data**:
- Sideboard frequency by archetype
- Mainboard → Sideboard transitions
- Matchup-specific sideboard tech

**Value**: **HIGH** - This is where co-occurrence excels
- "What do people sideboard in Burn?" (works great)
- "What's the sideboard tech against X?" (high value)

**Effort**: Low (already have partition data)

**Status**: ✅ Partially implemented (`sideboard_analysis.py`)

#### 3.4. Player/Event Metadata ⭐⭐⭐

**What**: Player skill, event size, placement

**Extract**:
- Top player decklists (higher quality signal)
- Large event vs small event (meta relevance)
- Placement correlation (do winning decks differ?)

**Value**: 
- Quality filtering (top players = better decks)
- Meta relevance (large events = current meta)

**Effort**: Low (metadata already scraped, need analysis)

---

## 4. What Can We Extract Implicitly from Scraping?

### Implicit Signals (Underutilized) ⭐⭐⭐⭐⭐

#### 4.1. Sideboard Patterns (Already Partially Done) ✅

**What**: Cards that move between mainboard/sideboard

**Implicit Signal**:
- **Flexibility**: Cards that appear in both = flexible/flex slots
- **Meta Response**: Sideboard frequency = meta-dependent
- **Matchup Tech**: Cards only in sideboard = matchup-specific

**Implementation**: ✅ `sideboard_analysis.py` exists
**Enhancement**: Add to similarity scoring (flexible cards score higher)

#### 4.2. Archetype Staples (Already Partially Done) ✅

**What**: Cards appearing in 70%+ of archetype decks

**Implicit Signal**:
- **Essentiality**: High frequency = essential to archetype
- **Substitutability**: Low frequency = replaceable
- **Archetype Identity**: Core cards define archetype

**Implementation**: ✅ `archetype_staples.py` exists
**Enhancement**: Use in similarity (staples = higher confidence)

#### 4.3. Temporal Co-occurrence ⭐⭐⭐⭐

**What**: Cards that rise/fall together in popularity

**Implicit Signal**:
- **Meta Shifts**: Cards that trend together = meta-relevant
- **Synergy Discovery**: New co-occurrences = emerging synergies
- **Ban Impact**: Cards that drop together = format-dependent

**Extraction**:
```python
# For each month:
monthly_decks = filter_decks_by_date(decks, month)
monthly_cooccurrence = compute_cooccurrence(monthly_decks)

# Compare across months:
trending_pairs = find_rising_cooccurrence(monthly_cooccurrence)
```

**Value**: **HIGH** - Discovers new relationships
**Effort**: Medium (need temporal analysis)

#### 4.4. Matchup-Specific Patterns ⭐⭐⭐⭐⭐

**What**: Cards that appear together in specific matchups

**Implicit Signal**:
- **Matchup Tech**: Cards that co-occur vs specific archetypes
- **Sideboard Patterns**: What comes in/out for matchups
- **Meta Positioning**: Cards that work against current meta

**Extraction** (if we have matchup data):
```python
# Group decks by opponent archetype (if available):
burn_vs_control = decks_where_burn_faced_control
tech_cards = find_cards_more_common_in(burn_vs_control, burn_vs_aggro)
```

**Value**: **CRITICAL** - Enables matchup-specific recommendations
**Effort**: High (requires matchup data we don't have yet)

#### 4.5. Deck Evolution Patterns ⭐⭐⭐

**What**: How individual players' decks change over time

**Implicit Signal**:
- **Substitution Patterns**: What cards replace others
- **Deck Refinement**: Cards added/removed in iterations
- **Player Preferences**: Consistent choices across decks

**Extraction** (if we track players):
```python
# For each player with multiple decks:
player_decks = group_by_player(decks)
evolution = track_card_changes(player_decks)
# "Player X replaced Lightning Bolt with Chain Lightning"
```

**Value**: Medium - Reveals substitution preferences
**Effort**: Medium (need player tracking)

#### 4.6. Format Transition Patterns ⭐⭐⭐

**What**: Cards that appear together across formats

**Implicit Signal**:
- **Format-Independent Synergy**: Cards that work in multiple formats
- **Format-Specific Tech**: Cards only together in one format
- **Power Level**: Cards that scale across formats

**Extraction**:
```python
# Compare co-occurrence across formats:
modern_pairs = cooccurrence(decks_by_format["Modern"])
legacy_pairs = cooccurrence(decks_by_format["Legacy"])
universal_pairs = modern_pairs & legacy_pairs  # Strong synergy
```

**Value**: Medium - Understands format boundaries
**Effort**: Low (format data already available)

---

## 5. Priority Matrix: What Matters Most

### Tier 0: Critical (Blocks Everything)

1. **Gold Annotations** (100+ queries)
   - **Current**: 61 queries
   - **Need**: 39 more
   - **Method**: LLM bootstrap + human verify
   - **Cost**: $2-5 LLM + 4-8 hours human
   - **Value**: Makes all evaluation trustworthy

2. **LLM-as-Judge for Evaluation**
   - **Current**: Manual annotation only
   - **Need**: Automated judgment at scale
   - **Method**: Extend `llm_annotator.py`
   - **Cost**: $40 for 20k judgments
   - **Value**: Enables large-scale evaluation

### Tier 1: High Impact (Unlocks New Capabilities)

3. **Tournament Results & Matchups**
   - **Current**: Decklists only
   - **Need**: Win rates, matchup data
   - **Method**: Scrape MTGGoldfish, tournament brackets
   - **Cost**: Medium effort (new scrapers)
   - **Value**: Enables deck quality validation

4. **Sideboard Pattern Analysis** (Enhance Existing)
   - **Current**: ✅ `sideboard_analysis.py` exists
   - **Need**: Integrate into similarity scoring
   - **Method**: Add sideboard signals to fusion
   - **Cost**: Low effort
   - **Value**: High (co-occurrence excels here)

5. **Temporal Trend Analysis**
   - **Current**: Static co-occurrence
   - **Need**: Time-series analysis
   - **Method**: Analyze deck dates, track trends
   - **Cost**: Medium effort
   - **Value**: Discovers emerging synergies

### Tier 2: Nice to Have (Quality Improvements)

6. **Archetype Analysis Enhancement**
   - **Current**: ✅ `archetype_staples.py` exists
   - **Need**: Integrate into similarity
   - **Method**: Use staple frequency as signal
   - **Cost**: Low effort
   - **Value**: Medium

7. **Player/Event Metadata Analysis**
   - **Current**: Metadata scraped but unused
   - **Need**: Quality filtering, skill-based weighting
   - **Method**: Analyze existing metadata
   - **Cost**: Low effort
   - **Value**: Medium

---

## 6. Recommended Action Plan

### Phase 1: Evaluation Foundation (Week 1)

1. **LLM Bootstrap Annotations** ($5, 2 hours)
   - Generate 500 draft annotations
   - Human verify top 100
   - Expand test set to 100+ queries

2. **LLM-as-Judge Integration** ($40, 4 hours)
   - Extend `llm_annotator.py` for batch judgment
   - Validate against human annotations (calibration)
   - Enable large-scale evaluation

**Outcome**: Reliable evaluation at scale

### Phase 2: Implicit Signal Extraction (Week 2)

3. **Sideboard Signal Integration** (4 hours)
   - Enhance `sideboard_analysis.py`
   - Add sideboard frequency to fusion weights
   - Test impact on P@10

4. **Temporal Trend Analysis** (8 hours)
   - Build temporal co-occurrence tracker
   - Identify trending pairs
   - Add temporal signals to similarity

**Outcome**: Better signals beyond static co-occurrence

### Phase 3: Explicit Data Acquisition (Week 3)

5. **Tournament Results Scraping** (12 hours)
   - Scrape MTGGoldfish meta share
   - Extract win rates by archetype
   - Build matchup database

6. **Matchup Pattern Analysis** (8 hours)
   - Analyze matchup-specific sideboard tech
   - Build matchup-aware similarity

**Outcome**: Deck quality validation + matchup recommendations

---

## 7. Cost-Benefit Summary

| Initiative | Cost | Time | Impact | Priority |
|------------|------|------|--------|----------|
| **Gold Annotations (100+)** | $5 | 8h | ⭐⭐⭐⭐⭐ | **T0** |
| **LLM-as-Judge** | $40 | 4h | ⭐⭐⭐⭐⭐ | **T0** |
| **Sideboard Signals** | $0 | 4h | ⭐⭐⭐⭐ | T1 |
| **Temporal Trends** | $0 | 8h | ⭐⭐⭐⭐ | T1 |
| **Tournament Results** | $0 | 12h | ⭐⭐⭐⭐⭐ | T1 |
| **Matchup Analysis** | $0 | 8h | ⭐⭐⭐⭐ | T2 |

**Total T0 Investment**: $45 + 12 hours = **Foundation for reliable evaluation**

**Total T1 Investment**: $0 + 24 hours = **Unlocks new capabilities**

---

## 8. Key Insights

### What Works (Reality Check)

✅ **Co-occurrence excels at**:
- Archetype staples (70%+ frequency)
- Sideboard patterns (what comes in/out)
- Meta tracking (trending cards)

❌ **Co-occurrence fails at**:
- Generic similarity (P@10 = 0.08 ceiling)
- Format-specific filtering (makes it worse)
- Cross-archetype similarity

### What We Should Focus On

1. **Use co-occurrence's strengths**: Sideboard analysis, archetype staples, meta trends
2. **Add multi-modal signals**: Text embeddings, functional tags (already done)
3. **LLM synthetic data**: Scale evaluation cheaply
4. **Implicit signals**: Temporal, matchup, evolution patterns

### What We Should Avoid

- ❌ Trying to optimize generic similarity with format tricks (reality shows it fails)
- ❌ Over-investing in co-occurrence improvements (hit ceiling)
- ❌ Ignoring implicit signals (sideboard, temporal, matchup)

---

## Next Steps

1. **Immediate** (This Week):
   - Run LLM bootstrap for 100 queries ($5)
   - Integrate LLM-as-Judge ($40)
   - Enhance sideboard signal integration

2. **Short-term** (Next 2 Weeks):
   - Build temporal trend analysis
   - Scrape tournament results
   - Integrate implicit signals into fusion

3. **Medium-term** (Next Month):
   - Matchup pattern analysis
   - Deck evolution tracking
   - Format transition analysis

**Total Investment**: ~$50 + 40 hours = **Comprehensive data foundation**

