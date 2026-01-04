# Next Actions - October 2, 2025

## What We Have Now

✅ **Fixed metadata bug** - 4,718 decks with 100% metadata coverage
✅ **Honest baseline** - P@10 = 0.08 (not inflated)
✅ **Specific use cases** - Format-specific, archetype staples, budget substitutes
✅ **LLM validation system** - Ready to check data quality at scale
✅ **Scraping expansion plan** - Path to 20K+ decks

---

## Immediate Actions (Today)

### 1. Expand Data Collection ⚡
```bash
# Quick mode - add 2K decks (30 mins)
./scripts/expand_scraping.sh quick

# OR Full mode - add 10K decks (2 hours)
./scripts/expand_scraping.sh full
```

**Expected**: 10K-15K total decks

---

### 2. Run LLM Quality Validation 🤖
```bash
cd src/ml

# Set API key
export OPENAI_API_KEY=your-key

# Run validation (~$2 for sample, ~$20 for full)
uv run python llm_data_validator.py
```

**Output**: Quality report with:
- Archetype consistency scores
- Suspicious card pairs
- Format legality issues
- Actionable recommendations

**Expected findings**:
- ~10-15% mislabeled archetypes (fix with LLM suggestions)
- ~5% suspicious pairs (data quality issues)
- ~2-3% format violations (remove or relabel)

---

### 3. Implement Format-Specific Use Case 🎯
```python
# Quick win - format-specific suggestions
# File: src/ml/format_specific_suggestions.py

def suggest_for_format(card: str, format: str, top_k: int = 10):
    """Suggest cards that co-occur in specific format."""
    format_decks = [d for d in decks if d['format'] == format]
    # Build format-specific graph
    # Find co-occurring cards
    # Return suggestions
```

**Test**:
```python
>>> suggest_for_format("Lightning Bolt", "Modern")
['Monastery Swiftspear', 'Rift Bolt', 'Lava Spike', ...]

>>> suggest_for_format("Lightning Bolt", "Legacy")
['Brainstorm', 'Ponder', 'Delver of Secrets', ...]  # Different!
```

**Expected**: Better results than generic similarity (context helps)

---

## This Week

### Day 1-2: Data Expansion
- [x] Fix metadata bug
- [ ] Scrape 10K more decks
- [ ] Run LLM validation
- [ ] Clean dataset based on findings

### Day 3-4: Use Case Implementation
- [ ] Format-specific suggestions (Modern, Legacy, Pauper)
- [ ] Archetype staples (top 5 archetypes)
- [ ] Budget alternatives (price-aware filtering)

### Day 5: Testing & Iteration
- [ ] Test each use case on real queries
- [ ] Measure accuracy (not generic P@10, use case-specific metrics)
- [ ] Iterate based on results

---

## Week 2

### Data Pipeline
- [ ] Set up continuous scraping (weekly updates)
- [ ] LLM validation on new batches
- [ ] Quality monitoring dashboard

### API Development
- [ ] Simple REST API for format-specific suggestions
- [ ] Archetype staples endpoint
- [ ] Budget alternatives endpoint

### Evaluation
- [ ] Use case-specific metrics (not just P@10)
- [ ] User study (if possible): "Are these suggestions helpful?"
- [ ] Compare to baseline (MTGGoldfish metagame stats)

---

## Month 2

### Advanced Features
- [ ] Text embeddings (Scryfall oracle text)
- [ ] Multi-modal (text + graph + metadata)
- [ ] Temporal trends (cards gaining/losing popularity)

### Paper/Publication
- [ ] Document honest baseline (P@10 = 0.08)
- [ ] Focus on specific use cases (not generic similarity)
- [ ] Show: More data + better context → better results

---

## Success Metrics

### Data Quality
- ✅ 20K+ decks
- ✅ Quality score > 0.85
- ✅ < 5% mislabeled data

### Use Case Performance
- **Format-specific**: "Are suggestions legal in format?" → 100%
- **Archetype staples**: "Do experts agree these are staples?" → 70%+
- **Budget alternatives**: "Under budget AND playable?" → 90%+

### Not success metrics
- ❌ Generic P@10 (we know it's ~0.08)
- ❌ "Beats papers" (different problem)
- ❌ "Production ready" (research tool)

---

## Decision Points

### After Data Expansion
**If P@10 improves to 0.12+**: More data helps! Keep expanding.
**If P@10 stays at 0.08**: Plateau is real, focus on use cases.

### After LLM Validation
**If quality score > 0.85**: Dataset is good, proceed.
**If quality score < 0.80**: Clean data first, then re-evaluate.

### After Use Case Tests
**If format-specific works well**: Focus here, ship it.
**If use cases also struggle**: Rethink problem formulation.

---

## Commands to Run Now

```bash
# 1. Expand data (do this first)
./scripts/expand_scraping.sh quick

# 2. Validate quality
cd src/ml
export OPENAI_API_KEY=your-key
uv run python llm_data_validator.py

# 3. Test baseline on expanded data
uv run python exp_057_expanded_baseline.py

# 4. Implement format-specific (quick win)
# Create: format_specific_suggestions.py
# Test: Does context help?
```

---

## Philosophy

**Accept reality**: Co-occurrence alone → P@10 ~ 0.08
**Add context**: Format + archetype + use case → Better results
**Measure honestly**: Use case-specific metrics, not generic
**Ship incrementally**: Format-specific first, then expand

**Don't**:
- Chase papers' 42% without their features
- Claim "production ready" prematurely
- Inflate metrics with small test sets
- Build features users don't need

**Do**:
- Solve specific problems well
- Measure what matters
- Be honest about limitations
- Iterate based on data
