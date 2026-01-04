# Data Collection Expansion Plan - Prioritized by Impact

**Date**: October 5, 2025
**Context**: Post deck-completion implementation; applying MoSCoW + RICE frameworks

---

## Current State (Validated)

```
MTG:      740,801 pairs, 57,322 decks, 4,205 cards ✅ Production
Pokemon:   10,987 pairs,  1,208 decks,   222 cards ✅ Usable
YGO:        3,792 pairs,     20 decks,   295 cards ⚠️ Insufficient
```

**Key Insight**: Pokemon has 1,208 decks (sufficient for embeddings) but only 222 unique cards appear in pairs. YGO has only 20 decks (insufficient).

---

## MoSCoW Prioritization

### Must-Have (P0) - Blocks Core Functionality

#### 1. YGO Tournament Deck Scaling (20 → 1,000+)
**Impact**: Critical - YGO deck completion unusable with 20 decks
**Effort**: Low - scrapers exist, just need to run with higher limits
**RICE Score**: (1000 users × 3 impact × 0.9 confidence) / 2 effort = **1,350**

**Actions**:
```bash
# yugiohmeta.com scraper exists but disabled
cd src/backend
go run cmd/dataset/main.go extract yugioh/yugiohmeta --limit 500

# ygoprodeck-tournament: increase from 10 → 50 pages
go run cmd/dataset/main.go extract yugioh/ygoprodeck-tournament --scroll-limit 50
```

**Expected**: 500-1,000 YGO decks → sufficient for embeddings and completion

#### 2. Pokemon Card Database Completion (3K → 10K+)
**Impact**: High - only 222 cards in pairs; need full card pool for completion
**Effort**: Low - Pokemon TCG API has pagination, just remove limit
**RICE Score**: (500 users × 2.5 impact × 0.95 confidence) / 1 effort = **1,187**

**Actions**:
```bash
# Pokemon TCG API currently stops at ~3K due to pagination issues
# Fix: increase pageSize, handle pagination properly
cd src/backend
go run cmd/dataset/main.go extract pokemon/pokemontcg  # Remove limit
```

**Expected**: 10,000+ Pokemon cards → better coverage for pairs/embeddings

#### 3. Pokemon Deck Scaling (1.2K → 5K+)
**Impact**: Medium - 1.2K is usable but more improves quality
**Effort**: Low - Limitless API exists, needs API key
**RICE Score**: (500 users × 2 impact × 0.8 confidence) / 2 effort = **400**

**Actions**:
```bash
# Limitless API scraper exists but requires key
export LIMITLESS_API_KEY=<get from https://play.limitlesstcg.com/account/settings/api>
go run cmd/dataset/main.go extract pokemon/limitless --limit 5000
```

**Expected**: 5,000+ Pokemon decks → robust embeddings

---

### Should-Have (P1) - Significant Quality Improvement

#### 4. MTG Deck Diversity (Format Balance)
**Impact**: Medium - improves format-specific completion
**Effort**: Low - mtgdecks.net scraper exists
**RICE Score**: (2000 users × 1.5 impact × 0.9 confidence) / 2 effort = **1,350**

**Current imbalance**:
- Modern: adequate
- Legacy/Vintage: under-represented
- Commander: adequate
- Pioneer/Standard: under-represented

**Actions**:
```bash
# mtgdecks.net scraper exists but disabled in cmd/dataset
# Re-enable and extract
go run cmd/dataset/main.go extract magic/mtgdecks --limit 10000
```

**Expected**: +10K MTG decks with better format balance

#### 5. Temporal Diversity (Meta Evolution)
**Impact**: High - enables meta-shift analysis and temporal recommendations
**Effort**: Medium - need to scrape historical data
**RICE Score**: (1500 users × 2.5 impact × 0.7 confidence) / 4 effort = **656**

**Actions**:
```bash
# MTGTop8 has historical data; scrape by date range
# Need to add date filtering to scraper
go run cmd/dataset/main.go extract mtgtop8 --date-range 2024-01-01:2024-12-31 --limit 10000
```

**Expected**: Track archetype popularity over time; "what was good 6 months ago?"

#### 6. Pokemon/YGO Pricing Integration
**Impact**: High - enables budget-aware completion for all games
**Effort**: Medium - APIs exist, need integration
**RICE Score**: (1000 users × 2 impact × 0.8 confidence) / 3 effort = **533**

**Sources**:
- Pokemon: TCGPlayer API, RapidAPI pokemon-tcg-card-prices
- YGO: YGOPRODeck API (has pricing), TCGPlayer

**Actions**:
```python
# Extend card_market_data.py
class PokemonPricing:
    def __init__(self, api_key):
        self.api = TCGPlayerAPI(api_key, game="pokemon")

    def get_price(self, card_name):
        # Query TCGPlayer Pokemon singles
        pass

# Wire into deck_completion.py
```

---

### Could-Have (P2) - Nice to Have

#### 7. Attributes CSV Generation (Faceted Jaccard)
**Impact**: Medium - enables faceted similarity (by CMC, type, color)
**Effort**: Low - just export from existing data
**RICE Score**: (800 users × 1.5 impact × 0.9 confidence) / 1 effort = **1,080**

**Actions**:
```python
# Generate from Scryfall/PokemonTCG/YGOPRODeck data
import json
from pathlib import Path

attrs = []
for card_file in Path("src/backend/data-full/games/magic/scryfall/cards").glob("*.json.zst"):
    # Decompress and extract: name, cmc, type, colors
    attrs.append({"name": name, "cmc": cmc, "type": type, "colors": colors})

pd.DataFrame(attrs).to_csv("data/attributes/magic_attrs.csv", index=False)
```

**Expected**: Enables `mode=jaccard_faceted&facet=cmc` in API

#### 8. Win Rate / Meta Share Data
**Impact**: High - enables "what's winning?" recommendations
**Effort**: High - requires parsing meta reports or MTGO/Arena data
**RICE Score**: (1500 users × 2.5 impact × 0.5 confidence) / 6 effort = **312**

**Sources**:
- MTGGoldfish meta share percentages
- MTGTop8 tournament results (placement data exists)
- Limitless meta share (available in API)

**Actions**:
- Parse MTGGoldfish meta pages for archetype percentages
- Aggregate placement data from existing decks
- Add meta_share field to deck metadata

#### 9. EDHREC Integration (Commander Enrichment)
**Impact**: Medium - improves Commander deck completion
**Effort**: Low - scraper exists
**RICE Score**: (500 users × 2 impact × 0.8 confidence) / 2 effort = **400**

**Actions**:
```bash
# EDHREC scraper exists
go run cmd/dataset/main.go extract magic/edhrec --limit 500
```

**Expected**: Commander synergies, salt scores, theme classifications

---

### Won't-Have (P3) - Future Consideration

#### 10. Arena/MTGO Data (Untapped.gg, 17Lands)
**Impact**: High for digital players
**Effort**: Very High - requires account, parsing complex formats
**RICE Score**: (1000 users × 2 impact × 0.3 confidence) / 8 effort = **75**

**Defer**: Until core games are solid

#### 11. Community Signals (Upvotes, Comments)
**Impact**: Low - nice for social features
**Effort**: Medium - requires scraping user-generated content
**RICE Score**: (500 users × 1 impact × 0.5 confidence) / 4 effort = **62**

**Defer**: Not critical for deck completion

---

## Prioritized Execution Plan

### Week 1: Scale YGO (P0)

**Goal**: 20 → 1,000+ YGO decks

```bash
cd src/backend

# 1. YGOPRODeck tournament (increase pagination)
go run cmd/dataset/main.go extract yugioh/ygoprodeck-tournament --scroll-limit 50

# 2. yugiohmeta.com (new source)
go run cmd/dataset/main.go extract yugioh/yugiohmeta --limit 500

# 3. Export and regenerate pairs
./export-hetero data-full/games/yugioh yugioh_decks_new.jsonl
mv yugioh_decks_new.jsonl ../../data/decks/yugioh_decks.jsonl

# 4. Regenerate pairs
cd ../ml
uv run python split_data_by_game.py  # Re-run with new YGO decks

# 5. Train YGO embeddings
uv run python card_similarity_pecan.py --input ../../data/pairs/yugioh_pairs.csv --output yugioh_64d
```

**Expected Output**:
- 1,000+ YGO decks
- 1,000+ YGO cards in pairs
- yugioh_64d_pecanpy.wv embeddings
- YGO deck completion functional

### Week 2: Complete Pokemon (P0)

**Goal**: Full Pokemon card database + more decks

```bash
cd src/backend

# 1. Pokemon TCG API (remove pagination limit)
# Edit pokemontcg/dataset.go: remove early break or increase pageSize
go run cmd/dataset/main.go extract pokemon/pokemontcg

# 2. Limitless API (with key)
export LIMITLESS_API_KEY=<key>
go run cmd/dataset/main.go extract pokemon/limitless --limit 5000

# 3. Regenerate Pokemon data
./export-hetero data-full/games/pokemon pokemon_decks_new.jsonl
cd ../ml
uv run python split_data_by_game.py
uv run python card_similarity_pecan.py --input ../../data/pairs/pokemon_pairs.csv --output pokemon_128d --dim 128
```

**Expected Output**:
- 10,000+ Pokemon cards
- 5,000+ Pokemon decks
- Robust Pokemon embeddings
- Pokemon deck completion production-ready

### Week 3: MTG Diversity (P1)

**Goal**: Format balance + temporal diversity

```bash
cd src/backend

# 1. MTGDecks.net (re-enable in cmd/dataset)
go run cmd/dataset/main.go extract magic/mtgdecks --limit 10000

# 2. EDHREC Commander enrichment
go run cmd/dataset/main.go extract magic/edhrec --limit 500

# 3. Regenerate MTG data
./export-hetero data-full/games/magic magic_decks_new.jsonl
cd ../ml
uv run python split_data_by_game.py
uv run python card_similarity_pecan.py --input ../../data/pairs/magic_pairs.csv --output magic_128d --dim 128
```

**Expected Output**:
- +10K MTG decks (better format balance)
- Commander enrichment (synergies, salt scores)
- Improved MTG embeddings

### Week 4: Enrichment (P1-P2)

**Goal**: Attributes + pricing for all games

```bash
cd src/ml

# 1. Generate attributes CSVs
uv run python generate_attributes.py --game magic --output ../data/attributes/magic_attrs.csv
uv run python generate_attributes.py --game pokemon --output ../data/attributes/pokemon_attrs.csv
uv run python generate_attributes.py --game yugioh --output ../data/attributes/yugioh_attrs.csv

# 2. Integrate Pokemon/YGO pricing
# Add TCGPlayer API keys to .env
export TCGPLAYER_API_KEY=<key>
uv run python integrate_pricing.py --game pokemon
uv run python integrate_pricing.py --game yugioh
```

**Expected Output**:
- Faceted Jaccard works for all games
- Budget-aware completion for all games

---

## Data Source Expansion Matrix

| Source | Game | Current | Target | Effort | Priority | Status |
|--------|------|---------|--------|--------|----------|--------|
| **yugiohmeta.com** | YGO | 0 | 500 | Low | P0 | Scraper exists |
| **ygoprodeck-tournament** | YGO | 20 | 500 | Low | P0 | Increase scroll-limit |
| **pokemontcg API** | Pokemon | 3K | 10K+ | Low | P0 | Fix pagination |
| **limitless API** | Pokemon | 0 | 5K | Low | P0 | Need API key |
| **mtgdecks.net** | MTG | 0 | 10K | Low | P1 | Re-enable in CLI |
| **edhrec** | MTG | 0 | 500 | Low | P1 | Scraper exists |
| **Temporal scraping** | MTG | 0 | 10K | Medium | P1 | Add date filter |
| **TCGPlayer pricing** | All | 0 | All | Medium | P1 | API integration |
| **Attributes CSV** | All | 0 | All | Low | P2 | Export from existing |
| **Meta share** | All | 0 | All | High | P2 | Parse meta pages |
| **Arena/MTGO** | MTG | 0 | ? | Very High | P3 | Deferred |

---

## Impact Analysis (Deck Completion Focus)

### For Similar Card Prediction (Problem 1 from README_SCRATCH.md)

**Current bottleneck**: P@10 = 0.08 plateau

**Highest impact expansions**:
1. **Attributes CSV** (P2, Low effort) → Enables faceted similarity by CMC/type/color
2. **Temporal diversity** (P1, Medium effort) → Captures meta shifts; "what's good now?"
3. **Meta share data** (P2, High effort) → Weight by popularity; "what's winning?"

**Why**: More decks alone won't break P@10 plateau; need richer features (attributes, temporal, meta)

### For Deck Completion (Problem 2 from README_SCRATCH.md)

**Current bottleneck**: Pokemon/YGO insufficient data; MTG works but lacks diversity

**Highest impact expansions**:
1. **YGO deck scaling** (P0, Low effort) → Makes YGO completion functional
2. **Pokemon card completion** (P0, Low effort) → Improves Pokemon coverage
3. **Pokemon/YGO pricing** (P1, Medium effort) → Enables budget-aware completion
4. **MTG format diversity** (P1, Low effort) → Better format-specific suggestions

**Why**: Deck completion needs sufficient training data per game + game-specific enrichment (pricing, attributes)

---

## Execution Commands (Copy-Paste Ready)

### P0: YGO Scaling (Run First)

```bash
cd /Users/henry/Documents/dev/decksage/src/backend

# Extract yugiohmeta (500 decks)
go run cmd/dataset/main.go extract yugioh/yugiohmeta --limit 500

# Extract ygoprodeck-tournament (increase pages)
go run cmd/dataset/main.go extract yugioh/ygoprodeck-tournament --scroll-limit 50

# Export to hetero
./export-hetero data-full/games/yugioh ../../data/decks/yugioh_decks.jsonl

# Regenerate pairs
cd ../ml
uv run python split_data_by_game.py

# Train embeddings
uv run python card_similarity_pecan.py --input ../../data/pairs/yugioh_pairs.csv --output yugioh_64d --dim 64 --mode SparseOTF
```

### P0: Pokemon Card Completion

```bash
cd /Users/henry/Documents/dev/decksage/src/backend

# Extract all Pokemon cards (remove limit)
go run cmd/dataset/main.go extract pokemon/pokemontcg

# Optional: Limitless API for more decks
export LIMITLESS_API_KEY=<key>
go run cmd/dataset/main.go extract pokemon/limitless --limit 5000

# Regenerate
./export-hetero data-full/games/pokemon ../../data/decks/pokemon_decks.jsonl
cd ../ml
uv run python split_data_by_game.py
uv run python card_similarity_pecan.py --input ../../data/pairs/pokemon_pairs.csv --output pokemon_128d --dim 128
```

### P1: MTG Diversity

```bash
cd /Users/henry/Documents/dev/decksage/src/backend

# MTGDecks.net (need to re-enable in cmd/dataset/cmd/extract.go)
# Currently returns error "temporarily disabled"
# Fix: remove the error return for "mtgdecks" case
go run cmd/dataset/main.go extract magic/mtgdecks --limit 10000

# EDHREC Commander enrichment
go run cmd/dataset/main.go extract magic/edhrec --limit 500

# Regenerate
./export-hetero data-full/games/magic ../../data/decks/magic_decks.jsonl
cd ../ml
uv run python split_data_by_game.py
```

### P2: Attributes Generation

```bash
cd /Users/henry/Documents/dev/decksage/src/ml

# Create attributes export script
cat > generate_attributes.py << 'EOF'
import json, subprocess
from pathlib import Path
import pandas as pd

def extract_mtg_attrs():
    attrs = []
    scryfall = Path("../backend/data-full/games/magic/scryfall/cards")
    for zst in list(scryfall.glob("*.json.zst"))[:1000]:
        result = subprocess.run(["zstd", "-d", "-c", str(zst)], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            attrs.append({
                "name": data.get("name"),
                "cmc": data.get("cmc", 0),
                "type": data.get("type_line", ""),
                "colors": ",".join(data.get("colors", [])),
            })
    pd.DataFrame(attrs).to_csv("../../data/attributes/magic_attrs.csv", index=False)
    print(f"Exported {len(attrs)} MTG card attributes")

extract_mtg_attrs()
EOF

uv run python generate_attributes.py
```

---

## Expected Outcomes by Priority

### After P0 (YGO + Pokemon scaling):
```
MTG:      740K pairs, 57K decks, 4.2K cards ✅
Pokemon:   50K+ pairs, 5K+ decks, 1K+ cards ✅
YGO:       20K+ pairs, 1K+ decks, 1K+ cards ✅

All games: Production-ready deck completion
```

### After P1 (MTG diversity + pricing):
```
MTG:      800K+ pairs, 67K+ decks (balanced formats)
Pokemon:  Budget-aware completion ✅
YGO:      Budget-aware completion ✅

All games: Format-specific + budget-aware completion
```

### After P2 (Attributes + meta):
```
All games: Faceted similarity ✅
All games: Meta-aware suggestions ✅
MTG:       Temporal meta tracking ✅
```

---

## Kano Model Classification

### Basic Needs (Expected; absence causes dissatisfaction)
- ✅ Sufficient decks per game (YGO currently fails this)
- ✅ Card database completeness
- ✅ Format rule validation

### Performance Needs (More = Better)
- Deck count (linear improvement)
- Card coverage (linear improvement)
- Format diversity (diminishing returns after balance)

### Excitement Needs (Delight users)
- Temporal meta tracking ("what was good 6 months ago?")
- Cross-game transfer learning ("Pokemon equivalent of Lightning Bolt")
- Win rate integration ("what's winning right now?")

---

## Risk Assessment

### Low Risk, High Impact (Do First)
- YGO deck scaling (scrapers exist, just run with higher limits)
- Pokemon card completion (API exists, just paginate properly)
- Attributes CSV (export from existing data)

### Medium Risk, High Impact (Do Next)
- MTG diversity (mtgdecks.net scraper disabled; need to debug)
- Pricing integration (APIs exist; need keys + integration)
- Temporal scraping (need date filtering logic)

### High Risk, Medium Impact (Defer)
- Arena/MTGO data (complex parsing, account requirements)
- Meta share parsing (fragile HTML scraping)
- Community signals (low signal-to-noise)

---

## Immediate Next Steps (This Session)

1. **Check why extractors are disabled**:
   ```bash
   rg "temporarily disabled" src/backend/cmd/dataset/cmd/extract.go
   ```

2. **Re-enable Pokemon/YGO extractors** (if safe)

3. **Run YGO scaling** (P0):
   ```bash
   go run cmd/dataset/main.go extract yugioh/yugiohmeta --limit 500
   ```

4. **Document extraction status** in DATA_SOURCES.md

---

## Success Metrics

### P0 Complete When:
- YGO: 1,000+ decks, 1,000+ cards in embeddings
- Pokemon: 5,000+ decks, 1,000+ cards in embeddings
- All games: Deck completion functional with sensible suggestions

### P1 Complete When:
- MTG: 67K+ decks with format balance
- All games: Budget-aware completion working
- All games: Attributes CSV generated

### P2 Complete When:
- Faceted similarity works for all games
- Meta share data integrated
- Temporal tracking for MTG

---

## Conclusion

**Immediate focus**: Scale YGO (P0) and complete Pokemon cards (P0) using existing scrapers with higher limits. This unblocks multi-game deck completion.

**Short-term**: Add MTG diversity (P1) and pricing for all games (P1).

**Medium-term**: Generate attributes (P2) and add temporal/meta tracking (P2).

**Defer**: Arena/MTGO data and community signals until core is solid.

The extraction infrastructure exists; we just need to run it with appropriate limits and re-enable disabled extractors.
