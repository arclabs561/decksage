# Scaling Up: Data + Annotations - October 2, 2025

## What's Running Now

### Data Expansion (Background Jobs)
```bash
# MTGTop8: +50 pages (~1K decks) - RUNNING
# MTGGoldfish: +200 decks - RUNNING
```

**Monitor with**:
```bash
watch -n 10 'find src/backend/data-full/games/magic -name "*.zst" | wc -l'
```

**Expected completion**: 20-30 mins

---

## While Scraping Runs: Prepare Annotation

### Python 3.12 Environment Setup
```bash
# Install Python 3.12 if needed
brew install python@3.12

# Create venv with correct version
cd src/ml
rm -rf .venv
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Test LLM
python test_openrouter_simple.py
```

### Test Data Quality Validator (Smaller Scope)
```python
# Quick 10-deck validation to test system
python llm_data_validator.py --sample 10
# Cost: ~$0.10
# Time: 1 min
```

---

## Parallel Work Streams

### Stream 1: Data Expansion (Automated)
```
[RUNNING] MTGTop8 scraping → +1K decks
[RUNNING] Goldfish scraping → +200 decks
[NEXT]    Deckbox sample → +100 decks
[NEXT]    Export all with metadata
```

### Stream 2: LLM Annotation (Manual Setup)
```
[READY]   Code complete
[BLOCKED] Python 3.12 venv needed
[THEN]    Test with 5 annotations
[THEN]    Scale to 100 annotations
```

### Stream 3: Use Case Implementation
```
[READY]   Format-specific suggestions (code exists)
[READY]   Archetype staples (metadata available)
[NEXT]    Budget alternatives with LLM
```

---

## Expected State in 1 Hour

### Data
- **Decks**: 4,718 → 6,000+ (27% growth)
- **Sources**: MTGTop8 (expanded) + Goldfish (new)
- **Metadata**: 100% coverage on all

### Annotations  
- **Quality validation**: 50 deck sample
- **Similarity judgments**: 20-50 pairs
- **Archetype descriptions**: 5-10 archetypes

### Experiments
- **Baseline on expanded data**: Does P@10 improve?
- **Format-specific test**: Does context help?

---

## Commands Queue

Execute in order as prerequisites complete:

```bash
# 1. Wait for scraping (check progress)
watch -n 10 'find src/backend/data-full -name "*.zst" | wc -l'

# 2. Export when done
cd src/backend
go run cmd/export-hetero/main.go \
  data-full/games/magic/mtgtop8/collections \
  ../../data/processed/decks_expanded_mtgtop8.jsonl

go run cmd/export-hetero/main.go \
  data-full/games/magic/goldfish/collections \
  ../../data/processed/decks_goldfish.jsonl

# 3. Merge exports
cat data/processed/decks_expanded_mtgtop8.jsonl \
    data/processed/decks_goldfish.jsonl \
    > data/processed/decks_all_sources.jsonl

# 4. Check stats
python3 -c "
import json
decks = [json.loads(l) for l in open('data/processed/decks_all_sources.jsonl')]
print(f'Total: {len(decks)} decks')
from collections import Counter
print('Formats:', Counter(d.get('format') for d in decks).most_common(5))
print('Sources:', Counter(d.get('url', '')[:25] for d in decks).most_common(3))
"

# 5. Run baseline on expanded data
cd src/ml
python exp_057_expanded_baseline.py  # Does more data → better P@10?

# 6. LLM annotation (once env ready)
python llm_annotator.py --similarity 50 --archetypes 10

# 7. LLM validation
python llm_data_validator.py --sample 50
```

---

## Success Metrics

### Data Expansion
- ✅ 6K+ total decks (goal: 20K eventually)
- ✅ Multiple sources (MTGTop8 + Goldfish working)
- ✅ Goldfish data has different meta (Modern/Pioneer focused)

### LLM Annotations
- ✅ 50+ similarity pairs annotated
- ✅ Quality score > 0.80
- ✅ Actionable cleaning recommendations

### Performance
- 🎯 P@10 > 0.09 on expanded data (beat 0.08)
- 🎯 Format-specific > 0.10 (use case helps)
- 🎯 With LLM annotations > 0.12 (rich labels help)

---

## Cost Tracker

| Task | Amount | Cost |
|------|--------|------|
| MTGTop8 scraping | 50 pages | Free (cached) |
| Goldfish scraping | 200 decks | Free (cached) |
| LLM annotations (50 pairs) | 50 calls | ~$0.50 |
| Quality validation (50 decks) | 50 calls | ~$0.50 |
| **Total** | **6K decks + 100 annotations** | **~$1** |

---

## Monitoring

```bash
# Check scraping progress
tail -f logs/mtgtop8_expand_*.log

# Check deck counts
find src/backend/data-full/games/magic/*/collections -name "*.zst" | wc -l

# Check metadata coverage
python -c "
import json
decks = [json.loads(l) for l in open('data/processed/decks_with_metadata.jsonl')]
print(f'With archetype: {sum(1 for d in decks if d.get(\"archetype\"))}/{len(decks)}')
"
```

---

## Next Decision Point

**After scraping completes:**

**If we got 6K+ decks:**
- ✅ Data expansion working
- → Continue to 20K
- → Run expanded baseline experiment

**If still at 4.7K:**
- ⚠️ Scraping not finding new data
- → Check if we've exhausted MTGTop8
- → Focus on Goldfish/other sources

**After LLM validation:**

**If quality score > 0.85:**
- ✅ Data is good
- → Create more annotations for training

**If quality score < 0.80:**
- ⚠️ Data has issues
- → Clean before expanding further
- → Use LLM suggestions to fix

---

## Philosophy

**Scale both dimensions:**
1. **More data** → More coverage, better graph
2. **Better annotations** → Richer signal, better evaluation

**Test honestly:**
- Run baseline on expanded data
- Check if "more data" actually helps
- Don't assume - measure

**Use LLMs wisely:**
- Validate at scale (find issues)
- Annotate strategically (hard cases)
- Create training labels (similarity pairs)

**Ship incrementally:**
- 6K decks > 4.7K decks → Ship it
- Some annotations > No annotations → Use them
- One working use case > Many designs → Build it



