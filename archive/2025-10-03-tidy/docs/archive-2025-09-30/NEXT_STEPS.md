# Next Steps - Focused Action Plan

**Generated:** October 1, 2025  
**Status:** B+ (8.5/10) - Solid foundation, ready to validate

## 🎯 Core Questions (Answer These First)

### 1. **Primary Use Case**
What problem are we solving?

**Options:**
- **A)** Deck building aid (suggest alternatives/upgrades)
- **B)** Meta analysis tool (track archetype trends)  
- **C)** Budget optimizer (find cheaper alternatives)
- **D)** Learning tool (understand card relationships)

**Why it matters:** Defines success metrics and evaluation strategy

---

### 2. **Success Metric**
How do we know it works?

**Options:**
- **A)** Expert validation (3+ MTG experts agree ≥70% of top-5)
- **B)** Click-through rate (users click ≥50% of recommendations)
- **C)** Deck win-rate (suggested cards improve deck performance)
- **D)** Precision@10 ≥ 0.7 (vs annotated ground truth)

**Why it matters:** Without this, we're guessing if quality is good

---

### 3. **Scope: Single vs Multi-Game**
MTG-only or actually multi-game?

**Current state:**
- Architecture: ✅ Multi-game ready
- Data: ⚠️ Only MTG decks (YGO/Pokemon have cards, no decks)

**Options:**
- **A)** Focus MTG, make it excellent (simpler, faster to market)
- **B)** Add YGO/Pokemon deck scraping (validate multi-game claim)

**Why it matters:** Affects data collection priorities

---

## 🔴 Immediate Actions (Do Today)

### Action 1: Validate End-to-End Pipeline
```bash
# Training is running in background...
# Once complete, test the full flow:

cd src/ml
source .venv/bin/activate

# Check if training succeeded
ls -lh ../../data/embeddings/magic_production_pecanpy.wv

# Test API
python api.py --embeddings ../../data/embeddings/magic_production_pecanpy.wv &
sleep 2

# Test similarity search
curl -X POST http://localhost:8000/similar \
  -H "Content-Type: application/json" \
  -d '{"query": "Lightning Bolt", "top_k": 5}'

# Open debug page
open ../debug/similarity-demo.html
```

**Success criteria:** 
- ✅ Training completes without errors
- ✅ API returns results
- ✅ Recommendations look reasonable

---

### Action 2: Manual Quality Check (YOU Review)

**Open:** `debug/similarity-demo.html`

**Test queries:**
1. Lightning Bolt → Should find: Lava Spike, Chain Lightning, Rift Bolt
2. Counterspell → Should find: Mana Leak, Force of Will, Archmage's Charm
3. Dark Ritual → Should find: Cabal Ritual, Lotus Petal, Dark Petition
4. Brainstorm → Should find: Ponder, Preordain, Portent

**What to check:**
- ❌ **Bad:** Totally unrelated cards (different colors/function)
- ⚠️ **Questionable:** Same color but different role
- ✅ **Good:** Functional similar or often played together
- ✅ **Excellent:** Near-substitutes or archetype staples

**Document findings** → Informs if we need better data/different model

---

### Action 3: Answer The Three Questions

Create `VISION.md`:
```markdown
# DeckSage Vision

## Primary Use Case
[Your answer: A/B/C/D]

## Success Metric
[Your answer: A/B/C/D]

## Scope
[Your answer: A/B]

## Target Users
[Write 2-3 user stories]
```

---

## 🟡 This Week (Once Basics Work)

### If Quality is Good (recommendations make sense):

**4. Create first annotation batch**
```bash
python annotate.py create \
  --pairs ../../data/processed/pairs.csv \
  --embeddings ../../data/embeddings/magic_production_pecanpy.wv \
  --num-queries 20 \
  --output ../../experiments/annotations/batch1.yaml
```

**5. Annotate yourself** (or recruit MTG player)
- Open `batch1.yaml`
- Rate each recommendation 0-4
- Takes ~30-60 minutes

**6. Measure metrics**
```bash
python compare_models.py \
  --test-set ../../experiments/batch1.json \
  --models ../../data/embeddings/*.wv \
  --output ../../experiments/results.csv
```

### If Quality is Bad (weird recommendations):

**4a. Diagnose data issues**
- Check format distribution (Modern vs Legacy vs Pauper)
- Look for edge contamination
- Verify key cards are present

**4b. Extract more balanced data**
```bash
cd src/backend
go run cmd/dataset/main.go extract magic mtgtop8 --section Modern --limit 100
go run cmd/dataset/main.go transform magic pairs
```

**4c. Re-train with better data**

---

## 🟢 Next 2 Weeks (Production Path)

**7. Add Python tests**
```bash
mkdir src/ml/tests
# test_api.py, test_evaluate.py, test_annotate.py
pytest src/ml/tests/
```

**8. Build frontend integration**
- Connect React app to API
- Card search with autocomplete
- Display similarity results

**9. Deploy**
- Docker compose (API + Redis)
- Simple frontend hosting
- Domain setup

**10. Monitor & iterate**
- Track which searches are used
- Measure click-through rates
- Refine based on usage

---

## 🎯 Decision Tree

```
START
  ↓
Run end-to-end test → Does it work?
  ├─ NO → Fix dependencies/paths → Retry
  └─ YES → Are recommendations good?
       ├─ NO → Extract better data → Retrain
       └─ YES → Create annotations → Measure metrics
              ↓
              Metrics ≥ target?
              ├─ NO → Tune hyperparameters → Retry
              └─ YES → Add tests → Deploy → Monitor
```

---

## 📊 Current Status vs Vision

| Component | Status | Vision Gap |
|-----------|--------|------------|
| **Scraping** | ✅ Working (MTG) | ⚠️ YGO/Pokemon decks missing |
| **Graph** | ✅ Co-occurrence | ❓ Other graph types? |
| **Embeddings** | ✅ Node2Vec | ❓ Try alternatives? (GNN, transformers) |
| **Evaluation** | ✅ Metrics ready | ⚠️ No ground truth yet |
| **API** | ✅ Code ready | ⚠️ Not tested |
| **Frontend** | ⚠️ React shell | ❌ No integration |
| **Multi-game** | ✅ Architecture | ⚠️ MTG data only |

---

## 🚀 The Path Forward

### Today (2-3 hours):
1. ✅ Training running (background)
2. ⏳ Wait for results
3. 🔍 Manual quality check via HTML page
4. 📝 Answer 3 core questions

### This Week (5-10 hours):
5. Create first annotation batch
6. Annotate + measure metrics
7. Decide: Good enough? Need better data?

### Next 2 Weeks (20-30 hours):
8. Add tests
9. Frontend integration
10. Deploy MVP

---

## 💡 Key Insight

**Stop here if embeddings look bad.** No point building infrastructure on broken foundation.

**The HTML demo page is your quality gate** - if recommendations don't make sense to you (a human with domain knowledge), no amount of metrics will save it.

**Next immediate step:** Wait for training to complete (~5-10 minutes), then open `debug/similarity-demo.html` and judge for yourself.

---

## 📋 Checklist Before Moving Forward

- [ ] Training completes successfully
- [ ] API serves requests
- [ ] You review 5-10 similarity searches
- [ ] Recommendations make intuitive sense
- [ ] You define primary use case
- [ ] You define success metric

**Only proceed if all checkboxes pass.**

