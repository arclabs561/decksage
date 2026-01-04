# 🚀 Run This Next - Quick Quality Check

## Current Status ✅

- Repository reorganized ✅
- Go tests passing ✅
- Python environment ready ✅
- API key loaded ✅
- Embeddings exist (from previous training) ✅
- Quality dashboard created ✅

## 🎯 Your Next Actions

### 1. Review Quality Dashboard (2 mins)
```bash
open debug/index.html
open debug/gaps.html
```

**Look for:**
- Overall system status
- What's working vs needs work
- Key questions to answer

### 2. Answer Core Questions (5 mins)

Open `debug/gaps.html` and answer these 3 questions:

**Q1: Primary use case?**
- [ ] A) Deck building aid (find card alternatives)
- [ ] B) Meta analysis (track trends)
- [ ] C) Budget optimizer (cheaper alternatives)
- [ ] D) Learning tool (understand relationships)

**Q2: Success metric?**
- [ ] A) Expert validation (70%+ agreement)
- [ ] B) Click-through rate (50%+ clicks)
- [ ] C) Deck performance (win rate improvement)
- [ ] D) Precision@10 ≥ 0.7

**Q3: Scope?**
- [ ] A) MTG-only (simpler, faster)
- [ ] B) Multi-game (MTG + YGO + Pokemon)

### 3. Check Existing Similarity Results (2 mins)

We already have embeddings! Let's see what they produce:

```bash
cd src/ml
source .venv/bin/activate

# Load existing embeddings and test
python3 -c "
from gensim.models import KeyedVectors
import os

# Check if we have embeddings
if os.path.exists('../../data/embeddings/magic_pecanpy.wv'):
    wv = KeyedVectors.load('../../data/embeddings/magic_pecanpy.wv')
    print(f'✅ Loaded {len(wv):,} card embeddings')

    # Test some queries
    test_cards = ['Lightning Bolt', 'Brainstorm', 'Counterspell']
    for card in test_cards:
        if card in wv:
            similar = wv.most_similar(card, topn=5)
            print(f'\n{card} →')
            for sim_card, score in similar:
                print(f'  {score:.3f} {sim_card}')
else:
    print('⚠️  No embeddings found - need to train first')
"
```

**Judge the results yourself:**
- Do they make sense?
- Are they too narrow (same deck type)?
- Are they too broad (unrelated cards)?

### 4. Decision Point

**If results look GOOD (recommendations make sense):**
```bash
# Path A: Ship it! 🚀
# 1. Deploy API
python api.py --embeddings ../../data/embeddings/magic_pecanpy.wv

# 2. Test in browser
open debug/similarity-demo.html

# 3. Create first annotation batch
python annotate.py create \
  --pairs ../../data/processed/pairs.csv \
  --embeddings ../../data/embeddings/*.wv \
  --num-queries 20 \
  --output ../../experiments/annotations/batch1.yaml
```

**If results look BAD (weird recommendations):**
```bash
# Path B: Fix data first 🔧
# Check what's in your data
cd ../../data/processed
head -20 pairs_decks_only.csv

# Look for:
# - Format imbalance (all Legacy? all Modern?)
# - Missing key cards
# - Weird edge cases
```

**If stuck on dependencies (can't load embeddings):**
```bash
# Path C: Switch to PyG 🎓
# See STRATEGY.md for details
uv pip install torch torch-geometric

# Modern GNN > old Node2Vec
# 30 min to working model
```

## 🐛 If Things Break

### Can't load embeddings?
```bash
# Check what embeddings exist
ls -lh ../../data/embeddings/

# If none, train new ones:
# (But fix dependencies first - see STRATEGY.md for PyG option)
```

### API key not working?
```bash
# Check it's set
grep OPENROUTER .env

# Test it
curl https://openrouter.ai/api/v1/auth/key \
  -H "Authorization: Bearer $(grep OPENROUTER .env | cut -d= -f2)"
```

### LLM judge failing?
```bash
# We have a manual review option!
# Just open similarity-demo.html and judge yourself
# Your domain knowledge > LLM anyway for spotting issues
```

## 📊 Quality Check Questions

As you review results, ask:

**Data Quality:**
- [ ] Are key MTG staples present? (Bolt, Brainstorm, Sol Ring)
- [ ] Multiple formats or just one?
- [ ] Recent cards or old only?

**Model Quality:**
- [ ] Do similar cards make intuitive sense?
- [ ] Any obvious errors (wrong colors, wrong function)?
- [ ] Missing any obvious similarities?

**Architecture Quality:**
- [ ] Is the system fast enough?
- [ ] Easy to iterate?
- [ ] Clear what to improve next?

## 🎯 Decision Tree

```
START: Review dashboard → Check embeddings exist?
  ├─ YES → Load and test → Quality good?
  │    ├─ YES → Ship it! (deploy API)
  │    └─ NO → Fix data or switch to PyG
  └─ NO → Train embeddings first
       ├─ PecanPy working? → Use it
       └─ Dependencies broken? → Switch to PyG (STRATEGY.md)
```

## 🚀 Fastest Path to Results

**Option 1: If you want to see it working NOW (15 mins)**
```bash
# 1. Check what embeddings exist
ls ../../data/embeddings/

# 2. If any exist, run API
python api.py --embeddings ../../data/embeddings/magic_pecanpy.wv &

# 3. Open demo
open debug/similarity-demo.html

# 4. Judge quality yourself
```

**Option 2: If you want best quality (1-2 hours)**
```bash
# See STRATEGY.md
# TL;DR: Switch to PyTorch Geometric
# Modern GNN architecture > random walks
# Better results, easier to use
```

## 📝 What to Tell Me After Review

1. **What you chose:** Use case (A/B/C/D), Success metric, Scope
2. **Similarity quality:** Good/OK/Bad based on your domain knowledge
3. **Blocker (if any):** Can't load embeddings? API not working?
4. **Next:** Ship current? Fix data? Switch to PyG?

---

**Bottom line:** We have a B+ system ready to test. Review the dashboard, check if recommendations make sense, then decide: ship it, fix data, or modernize with PyG.

You're in a good spot - just need to validate quality and choose direction! 🎴
