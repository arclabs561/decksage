# Deep Review: Triaged Next Actions

**Date**: October 6, 2025  
**Context**: Post-critical-fixes deep dive into data pipeline, evaluation, and architecture

---

## Executive Summary

This is a **research-grade system transitioning toward production**. Core infrastructure is solid (data pipeline, validators, API, caching), but there are strategic gaps in evaluation depth, quality monitoring, and algorithmic sophistication.

**Current Status**:
- ✅ Data pipeline: Excellent (56k decks, multi-game, robust validation)
- ✅ Enrichment: Comprehensive (5 dimensions, LLM caching, functional tags)
- ✅ Infrastructure: Solid (FastAPI, Pydantic, comprehensive tests)
- ⚠️ Evaluation: Shallow (38 queries, no confidence intervals, no A/B framework)
- ⚠️ Algorithms: Naive (greedy completion, no deck quality metrics)
- ⚠️ Monitoring: Exists but fragmented (no unified dashboard)

**Honest Reality** (from `experimental/REALITY_FINDINGS.md`):
- P@10 = 0.08 is a real ceiling for co-occurrence alone
- Papers achieve 0.42 with multi-modal features
- Current approach has hit its limits

---

## Tier 0: Critical Path to Production (Do First)

### T0.1: Expand Test Set (Evaluation Confidence)
**Current**: 38 MTG queries, <20 for Pokemon/YGO  
**Gap**: Statistical significance requires 100+ queries  
**Impact**: Can't distinguish 0.088 from 0.090 with confidence

**Action**:
1. Use `src/ml/add_statistical_rigor.py` to generate independent test queries
2. Annotate 100 total queries (50 MTG, 25 Pokemon, 25 YGO)
3. Add bootstrapped confidence intervals to evaluation
4. Document: "P@10 = 0.088 ± 0.015 (95% CI, n=100)"

**Effort**: 4-8 hours annotation + 2 hours code  
**Value**: Makes all future evaluation trustworthy

**Files**:
- Run: `src/ml/add_statistical_rigor.py` 
- Update: `experiments/test_set_canonical_*.json`
- Modify: `src/ml/utils/evaluation.py` to add confidence intervals

---

### T0.2: Deck Quality Validation (Core Use Case)
**Current**: Deck completion adds cards but doesn't validate "deck quality"  
**Gap**: No metrics for whether completed decks resemble tournament decks  
**Impact**: High - this is the primary advertised feature

**Action**:
1. Define deck quality metrics:
   - Mana curve fit (compare to tournament decks in same archetype)
   - Tag diversity (not all removal, not all threats)
   - Synergy coherence (functional tag pairs that co-occur)
2. Add post-completion validation step
3. Generate report: "Completed deck scores 7.2/10 quality (vs 8.1 tournament avg)"

**Effort**: 6-10 hours  
**Value**: Validates primary use case works

**Implementation**:
```python
# New file: src/ml/deck_quality.py
class DeckQualityMetrics:
    mana_curve_score: float  # KL divergence from archetype average
    tag_balance_score: float  # Shannon entropy of tag distribution  
    synergy_score: float  # Avg pairwise functional overlap
    overall_score: float  # Weighted combination
```

---

### T0.3: Unified Quality Dashboard
**Current**: 3 separate quality validators, no centralized view  
**Gap**: Can't see data quality trends over time  
**Impact**: Silent degradation possible

**Action**:
1. Create `src/ml/quality_dashboard.py`
2. Consolidate metrics from:
   - `enrichment_quality_validator.py` → enrichment quality
   - `validate_data_quality.py` → raw data quality  
   - `validators/loader.py` → validation success rates
3. Generate single HTML dashboard with charts
4. Add to `make quality-report` target

**Effort**: 4-6 hours  
**Value**: Prevents silent data degradation

**Output**: `experiments/quality_dashboard.html` with:
- Validation success rates over time
- Enrichment coverage (functional tags, LLM, vision)
- Data quality scores (0-100)
- Alerts when quality drops below thresholds

---

## Tier 1: Strategic Improvements (Do Next)

### T1.1: Implement Multi-Modal Features (Break P@10 Ceiling)
**Current**: P@10 = 0.088 with fusion  
**Goal**: P@10 = 0.20-0.25 (as documented in README)  
**Path**: Add new signal types

**Priority Order** (by ROI):
1. **Card Text Embeddings** (Highest Impact)
   - Use sentence-transformers on card Oracle text
   - Captures functional similarity directly
   - Estimated impact: +40-60% (literature shows 0.15-0.20 from text alone)
   - Effort: 8-12 hours
   
2. **Mana Curve Similarity** (Medium Impact)
   - Cards with similar CMC often substitutable
   - Especially important for limited resources (lands, ramp)
   - Estimated impact: +10-15%
   - Effort: 3-4 hours

3. **Type/Color Filtering** (Low Impact)
   - Don't suggest red cards for blue decks
   - Baseline sanity check
   - Estimated impact: +5-10%
   - Effort: 2-3 hours

**Total Effort**: 13-19 hours  
**Expected Result**: P@10 = 0.18-0.22 (achievable with text embeddings)

**Note**: This aligns with your stated README goal of 0.20-0.25

---

### T1.2: Add A/B Testing Framework
**Current**: Grid search over fixed test set, manual weight tuning  
**Gap**: No way to compare algorithm changes rigorously  
**Impact**: Medium - slows iteration velocity

**Action**:
1. Implement train/test split for test sets
2. Add cross-validation support
3. Create comparison framework:
   ```python
   compare_models(
       baseline="fusion_v1",
       challenger="fusion_v2_with_text",
       test_set="held_out_split",
       metrics=["P@10", "nDCG@10", "MRR"]
   )
   ```
4. Generate comparison reports with statistical significance

**Effort**: 6-8 hours  
**Value**: Rigorous algorithm comparison

---

### T1.3: Deck Completion with Look-Ahead
**Current**: Greedy (pick best card each step)  
**Better**: Beam search or Monte Carlo simulation  
**Impact**: Unknown (needs measurement)

**Action**:
1. Implement beam search (width=3-5)
2. Add deck quality objective function (from T0.2)
3. Compare against greedy baseline
4. Measure: "Does look-ahead improve final deck quality?"

**Effort**: 10-15 hours  
**Risk**: Might not improve over greedy (needs testing)

**Decision**: Wait until T0.2 (deck quality metrics) is done

---

## Tier 2: Engineering Excellence (Technical Debt)

### T2.1: Remove Legacy Test Globals
**Location**: `src/ml/api.py` lines 216-234  
**Issue**: Module-level globals for backward compatibility  
**Complexity**: Medium (need to update ~5 old tests)

**Action**:
1. Update old tests to use FastAPI TestClient properly
2. Remove `_adopt_legacy_globals()` shim
3. Simplify ApiState management

**Effort**: 2-3 hours  
**Value**: Cleaner architecture, easier to understand

---

### T2.2: Centralize Path Configuration
**Issue**: Hardcoded relative path in `api.py` line 189:
```python
Path(__file__).resolve().parents[2] / "experiments" / "fusion_grid_search_latest.json"
```

**Action**:
1. Use `utils/paths.py` module (already exists!)
2. Add `FUSION_WEIGHTS_PATH` constant
3. Update all hardcoded paths to use centralized config

**Effort**: 1-2 hours  
**Value**: Robustness against refactoring

---

### T2.3: Add Type Hints to Completion Functions
**Current**: Duck-typed dicts everywhere in `deck_completion.py`  
**Better**: Pydantic models for deck operations

**Action**:
1. Create `DeckOperation` Pydantic model
2. Type all functions properly
3. Get IDE autocomplete and type checking

**Effort**: 3-4 hours  
**Value**: Fewer bugs, better DX

---

## Tier 3: Nice-to-Have (Future Work)

### T3.1: Dataset Versioning (DVC)
**When**: Before publishing results or if reproducibility becomes critical  
**Effort**: 4-6 hours  
**Value**: Reproducible experiments

### T3.2: Cost Tracking Dashboard
**When**: If LLM enrichment budget becomes constrained  
**Effort**: 2-3 hours  
**Value**: Budget management

### T3.3: Consolidate Functional Taggers
**When**: If maintenance burden grows (currently acceptable)  
**Effort**: 8-12 hours  
**Risk**: High (breaks existing code, may not be worth it)

---

## Detailed Priority Matrix

| ID | Action | Effort | Value | Urgency | Score |
|----|--------|--------|-------|---------|-------|
| **T0.1** | Expand test set to 100+ queries | 6-10h | 🔥 Critical | 🔴 High | **P0** |
| **T0.2** | Add deck quality validation | 6-10h | 🔥 Critical | 🔴 High | **P0** |
| **T0.3** | Unified quality dashboard | 4-6h | 🟠 High | 🟡 Medium | **P1** |
| **T1.1** | Multi-modal features (text embeddings) | 13-19h | 🔥 Critical | 🟡 Medium | **P1** |
| **T1.2** | A/B testing framework | 6-8h | 🟠 High | 🟢 Low | **P2** |
| **T1.3** | Beam search completion | 10-15h | 🟡 Medium | 🟢 Low | **P3** |
| **T2.1** | Remove legacy globals | 2-3h | 🟡 Medium | 🟢 Low | **P3** |
| **T2.2** | Centralize paths | 1-2h | 🟡 Medium | 🟢 Low | **P3** |
| **T2.3** | Add type hints | 3-4h | 🟡 Medium | 🟢 Low | **P3** |

**Legend**: 
- Effort: Estimated hours
- Value: 🔥 Critical / 🟠 High / 🟡 Medium / ⚪ Low
- Urgency: 🔴 Blocks production / 🟡 Important / 🟢 Can wait

---

## Recommended Sprint Plan

### Sprint 1: Evaluation Foundation (12-16 hours)
**Goal**: Make evaluation trustworthy
1. T0.1: Expand test set → 100+ queries with bootstrapped CIs
2. T0.2: Add deck quality validation
3. Document honest baseline with confidence intervals

**Outcome**: Can rigorously measure future improvements

### Sprint 2: Break the Plateau (15-20 hours)
**Goal**: Achieve P@10 = 0.18-0.22
1. T1.1: Implement card text embeddings
2. Update fusion to include text signal
3. Re-tune weights with expanded test set
4. Generate comparison report vs baseline

**Outcome**: Demonstrable improvement toward stated goal

### Sprint 3: Production Readiness (8-12 hours)
**Goal**: Make system production-reliable
1. T0.3: Unified quality dashboard
2. T2.2: Centralize path configuration
3. Add monitoring/alerting for quality degradation

**Outcome**: System ready for real users

---

## What NOT to Do (Based on Reality Findings)

❌ **Don't**: Try to improve P@10 with more graph algorithms  
**Why**: Co-occurrence ceiling is real, you'll waste time

❌ **Don't**: Implement format-specific filtering for generic queries  
**Why**: Makes performance worse (-58% to -94%)

❌ **Don't**: Add more deck scraping without validation  
**Why**: Quality > quantity. Current 56k decks is plenty

❌ **Don't**: Consolidate functional taggers yet  
**Why**: Domain complexity justifies separation (Chesterton's fence)

❌ **Don't**: Refactor directory structure  
**Why**: Import fragility makes this risky. Works fine now.

---

## Critical Design Questions (Needs Answering)

### Q1: What is the Primary Use Case?
**Current ambiguity**: System supports both:
- **Generic similarity**: "What's similar to Lightning Bolt?" (P@10 = 0.08, plateaued)
- **Deck completion**: "Finish my partial Burn deck" (quality unmeasured)

**Reality**: These need different signals!
- Generic similarity → needs card text embeddings
- Deck completion → needs archetype awareness

**Recommendation**: Pick ONE as primary, optimize for it, document the other as secondary

---

### Q2: What is "Good Enough" for Deck Completion?
**Current**: Adds legal cards until target size reached  
**Missing**: Definition of "good deck"

**Questions to answer**:
1. Should completed decks match tournament meta patterns?
2. Should they optimize for consistency (low variance)?
3. Should they maximize functional coverage?
4. Should they stay within budget constraints?

**Action**: Define success criteria, then implement validation

---

### Q3: Is P@10 = 0.088 Actually Good?
**Context**: 
- Random baseline: P@10 = ~0.001 (1000+ cards)
- Co-occurrence: P@10 = 0.088 (88x improvement)
- Papers with text: P@10 = 0.42 (380x improvement)

**Question**: For your use case, is 8.8% precision enough?

**Consider**:
- Users see 10 results
- ~1 is highly/relevant per query
- For "budget alternatives", this might be fine
- For "build my deck", might need higher

**Action**: User test! See if real people find results useful at current precision.

---

## Implementation Priorities (If Resources Limited)

### Minimum Viable Product (MVP)
**Goal**: Ship something useful quickly

**Do**:
1. T0.2: Deck quality validation (proves core use case)
2. T0.1: Basic test set expansion (50 queries is enough for MVP)
3. T2.2: Fix hardcoded paths (robustness)

**Skip** (for now):
- Text embeddings (big lift, needs validation first)
- A/B framework (premature)
- Quality dashboard (manual checks OK for MVP)

**Time**: 10-15 hours  
**Outcome**: Validated deck completion feature ready for users

---

### Full Product
**Goal**: Multi-modal similarity achieving P@10 = 0.20+

**Do**:
1. All T0 items (evaluation + quality foundation)
2. T1.1: Card text embeddings (big performance jump)
3. T1.2: A/B testing framework (measure improvements)
4. T0.3: Quality dashboard (production monitoring)

**Time**: 35-45 hours  
**Outcome**: Production-grade system meeting README goals

---

## Specific Code-Level Improvements

### Improvement 1: Deck Completion Scoring Function
**Current**: Picks candidate with highest similarity score  
**Better**: Multi-objective scoring

```python
# Add to src/ml/deck_completion.py

def score_candidate(
    card: str,
    similarity: float,
    deck: dict,
    *,
    tag_set_fn: TagSetFn | None = None,
    coverage_weight: float = 0.15,
    cmc_fn: CMCFn | None = None,
    curve_target: dict[int, float] | None = None,
    curve_weight: float = 0.0,
) -> float:
    """
    Multi-objective candidate scoring.
    
    Components:
    1. Base similarity (0.60 weight)
    2. Coverage bonus (0.20 weight) - adds new functional tags
    3. Curve fit bonus (0.20 weight) - improves mana curve
    """
    score = similarity * 0.60
    
    # Coverage bonus
    if tag_set_fn and coverage_weight > 0:
        deck_tags = _get_all_tags(deck, tag_set_fn)
        cand_tags = tag_set_fn(card)
        new_tags = cand_tags - deck_tags
        score += coverage_weight * len(new_tags) * 0.20
    
    # Curve fit bonus  
    if cmc_fn and curve_target and curve_weight > 0:
        cmc = cmc_fn(card)
        if cmc is not None:
            current_curve = _get_mana_curve(deck, cmc_fn)
            gap = curve_target.get(cmc, 0) - current_curve.get(cmc, 0)
            score += curve_weight * max(0, gap) * 0.20
    
    return score
```

---

### Improvement 2: Confidence Intervals in Evaluation
**Current**: `P@10 = 0.088` (point estimate)  
**Better**: `P@10 = 0.088 ± 0.012 (95% CI)`

```python
# Add to src/ml/utils/evaluation.py

def evaluate_with_confidence(
    test_set: dict,
    similarity_func: Callable,
    top_k: int = 10,
    n_bootstrap: int = 1000,
) -> dict:
    """Evaluate with bootstrapped confidence intervals."""
    import numpy as np
    
    # Compute scores per query
    scores = []
    for query, labels in test_set.items():
        predictions = similarity_func(query, top_k)
        score = compute_precision_at_k(predictions, labels, k=top_k)
        scores.append(score)
    
    # Bootstrap confidence intervals
    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = np.random.choice(scores, size=len(scores), replace=True)
        bootstrap_means.append(np.mean(sample))
    
    ci_lower = np.percentile(bootstrap_means, 2.5)
    ci_upper = np.percentile(bootstrap_means, 97.5)
    
    return {
        "mean": np.mean(scores),
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "n_queries": len(scores),
    }
```

---

### Improvement 3: Quality Alert System
**Trigger**: When validation success rate drops below threshold

```python
# Add to src/ml/quality_dashboard.py

class QualityAlert:
    THRESHOLDS = {
        "validation_success_rate": 0.95,  # 95% of decks should validate
        "enrichment_coverage": 0.90,      # 90% should have enrichment
        "llm_confidence_avg": 0.70,       # Avg LLM confidence > 0.70
    }
    
    @staticmethod
    def check_quality(metrics: dict) -> list[str]:
        """Return list of alerts if quality degraded."""
        alerts = []
        for metric, threshold in QualityAlert.THRESHOLDS.items():
            if metrics.get(metric, 0) < threshold:
                alerts.append(
                    f"⚠️  {metric} = {metrics[metric]:.2f} < {threshold:.2f}"
                )
        return alerts
```

---

## Architecture-Level Observations

### What's Well Designed
1. **Fusion abstraction** - Supports 4 aggregators (weighted, RRF, CombSUM, CombMNZ)
2. **Graceful degradation** - Works with missing signals
3. **Multi-game architecture** - Clean abstraction without over-engineering
4. **Pydantic validation** - Type-safe, clear errors
5. **LLM caching** - 30-day TTL, concurrent-safe, transparent

### What Needs Work
1. **Evaluation is shallow** - 38 queries, no confidence intervals
2. **Deck completion is naive** - Greedy, no quality objective
3. **Quality monitoring is fragmented** - 3 separate validators, no unified view
4. **Missing key signals** - No card text embeddings (biggest gap!)
5. **No A/B framework** - Can't compare algorithms rigorously

### What's Acceptable (Don't Fix)
1. **Flat directory** - 60+ files is navigable, refactoring is risky
2. **Functional tagger duplication** - Domain complexity justifies it
3. **Legacy test globals** - Minor technical debt, not blocking
4. **Some TODO comments** - Mostly in analysis scripts, not production code

---

## Strategic Recommendation

**If you had 40 hours total**, allocate:

**Phase 1: Evaluation (10h)** - T0.1 + T0.2
- Expand test set to 100 queries
- Add deck quality validation
- Outcome: Know if system works

**Phase 2: Performance (18h)** - T1.1
- Implement card text embeddings
- Integrate into fusion
- Re-tune weights
- Outcome: P@10 = 0.18-0.22 (meet README goal)

**Phase 3: Production (12h)** - T0.3 + T2.2
- Quality dashboard
- Path centralization
- A/B framework basics
- Outcome: Monitoring & rigor for production

**Result**: System achieving stated goals with production-grade reliability

---

## What Makes This Review Different

**Macro → Meso → Micro** analysis revealed:
- **Macro**: Architecture is sound, documentation was cluttered ✅
- **Meso**: Evaluation is too shallow, algorithms are naive ⚠️
- **Micro**: Code quality is high, minor technical debt acceptable ✅

**Honest assessment**: 
- This is an **85% complete research system**
- Needs 15% more work to be production-ready
- The 15% is in **evaluation rigor** and **algorithmic sophistication**, not infrastructure

**The README says**: "P@10 = 0.20-0.25 expected with multi-modal"  
**The reality**: P@10 = 0.088 with current signals  
**The gap**: Text embeddings (biggest missing signal)

**Principle applied**: "All models are wrong, some are useful." The current model IS useful for specific tasks (archetype staples, sideboard analysis), but not for generic similarity. Documentation should reflect this reality.

---

## Final Recommendation

**Start with T0.1 + T0.2** (12-20 hours):
1. Expand test set
2. Add deck quality metrics
3. Validate the core use case actually works

**Then decide**:
- If deck completion quality is good → ship it (MVP)
- If similarity needs improvement → T1.1 (text embeddings)
- If both → allocate time accordingly

**Don't**: Try to optimize current signals further. The plateau is real.
