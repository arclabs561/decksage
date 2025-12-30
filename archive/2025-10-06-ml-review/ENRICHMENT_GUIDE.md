# Card & Deck Enrichment Pipeline Guide

**Purpose**: Comprehensive reference for all enrichment capabilities added to DeckSage

---

## Overview

DeckSage now captures significantly more than card names and deck lists. The enrichment pipeline provides:

1. **Market Data**: Pricing across multiple currencies and formats
2. **Mechanical Data**: Keywords, color identity, legalities
3. **Functional Classification**: Role-based tags (removal, ramp, etc.)
4. **Commander Data**: EDHREC-specific enrichment
5. **Tournament Metadata**: Player, event, placement tracking

---

## 1. Market Data & Pricing

### Scryfall Pricing (Integrated)

**Captured from Scryfall API:**
- `usd`: Paper non-foil price (USD)
- `usd_foil`: Paper foil price (USD)
- `eur`: Paper non-foil price (EUR)
- `eur_foil`: Paper foil price (EUR)
- `tix`: MTGO ticket price

**Storage**: Embedded in Card model (`src/backend/games/magic/game/game.go`)

```go
type CardPrices struct {
    USD      *float64 `json:"usd,omitempty"`
    USDFoil  *float64 `json:"usd_foil,omitempty"`
    EUR      *float64 `json:"eur,omitempty"`
    EURFoil  *float64 `json:"eur_foil,omitempty"`
    TIX      *float64 `json:"tix,omitempty"`
}
```

### Price Analysis Tools

**Python utility**: `src/ml/card_market_data.py`

**Features:**
- Load prices from Scryfall card JSONs
- Classify cards into price tiers (bulk, budget, mid, premium, whale)
- Calculate deck total value
- Find budget substitutes for expensive cards
- Export unified price database

**Usage:**
```python
from card_market_data import MarketDataManager

manager = MarketDataManager()

# Get price for a card
price = manager.get_price("Lightning Bolt")
print(f"USD: ${price.usd}")

# Price a deck
deck_cards = {"Lightning Bolt": 4, "Mountain": 18}
pricing = manager.get_deck_price(deck_cards)
print(f"Total: ${pricing['total_usd']}")

# Find budget substitutes
similar = ["Chain Lightning", "Lava Spike", "Rift Bolt"]
substitutes = manager.find_budget_substitutes(
    "Lightning Bolt",
    similar,
    max_price=5.0
)
```

**Price Tiers:**
- **Bulk**: $0.00 - $0.25 (commons/uncommons)
- **Budget**: $0.25 - $5.00 (playables)
- **Mid**: $5.00 - $20.00 (staples)
- **Premium**: $20.00 - $100.00 (chase cards)
- **Whale**: $100.00+ (Reserved List, etc.)

### External APIs (Ready)

Stubs implemented for:
- **TCGPlayer API**: Requires API key from https://api.tcgplayer.com/
- **Cardmarket API**: Requires OAuth credentials from https://api.cardmarket.com/

---

## 2. Mechanical Enrichment

### Scryfall Keywords & Metadata

**Captured fields:**
- `keywords`: Array of mechanic keywords (e.g., `["Flying", "Haste"]`)
- `colors`: Color array (e.g., `["R", "G"]`)
- `color_identity`: Commander color identity
- `cmc`: Converted mana cost
- `legalities`: Map of format → legality status
- `rarity`: Common, Uncommon, Rare, Mythic
- `set`: Set code
- `set_name`: Full set name

**Storage**: Enhanced Card model

```go
type Card struct {
    // ... existing fields
    Keywords      []string            `json:"keywords,omitempty"`
    Colors        []string            `json:"colors,omitempty"`
    ColorIdentity []string            `json:"color_identity,omitempty"`
    CMC           float64             `json:"cmc,omitempty"`
    Prices        CardPrices          `json:"prices,omitempty"`
    Legalities    map[string]string   `json:"legalities,omitempty"`
    Rarity        string              `json:"rarity,omitempty"`
    Set           string              `json:"set,omitempty"`
    SetName       string              `json:"set_name,omitempty"`
}
```

**Benefits:**
- Filter cards by keywords: "Show all cards with Flash"
- Commander legality checking: Color identity compliance
- Format validation: "Is this card legal in Modern?"
- Rarity-based filtering: Pauper (commons only)

---

## 3. Functional Tagging System

### Purpose

Classify cards by **what they do** rather than just co-occurrence patterns.

**Implementation**: `src/ml/card_functional_tagger.py`

### Supported Functional Tags

**Removal (7 types):**
- `creature_removal`: Destroy/exile creatures
- `artifact_removal`: Destroy/exile artifacts
- `enchantment_removal`: Destroy/exile enchantments
- `planeswalker_removal`: Damage/destroy planeswalkers
- `land_removal`: Land destruction
- `any_permanent_removal`: Catch-all removal

**Resource Generation:**
- `card_draw`: Direct card draw
- `card_advantage`: Broader (impulse draw, selection)
- `ramp`: Permanent mana acceleration
- `mana_ritual`: One-time mana boost

**Interaction:**
- `counterspell`: Counter target spell
- `discard`: Opponent discard effects
- `mill`: Library to graveyard

**Tutors (5 types):**
- `tutor`: Generic search
- `tutor_creature`, `tutor_instant_sorcery`, `tutor_artifact`, `tutor_enchantment`, `tutor_land`

**Board Control:**
- `board_wipe`: Mass removal
- `stax`: Resource denial/taxing
- `pillowfort`: Damage prevention

**Graveyard:**
- `recursion`: Return from graveyard
- `reanimation`: Specifically creatures
- `graveyard_hate`: Exile graveyards

**Protection:**
- `hexproof`, `indestructible`, `ward`: Specific protections
- `protection`: Catch-all

**Combat/Evasion:**
- `evasion`: General evasion
- `flying`, `unblockable`, `menace`: Specific evasion

**Win Conditions:**
- `win_condition`: General
- `combo_piece`: Known combo cards
- `alt_win_con`: "You win the game"

**Utility:**
- `token_generator`, `life_gain`, `life_loss`, `sacrifice_outlet`

**Hate Cards:**
- `tribal_hate`, `color_hate`, `artifact_hate`, `graveyard_hate_strong`

### Usage

```python
from card_functional_tagger import FunctionalTagger

tagger = FunctionalTagger()

# Tag a single card
tags = tagger.tag_card("Lightning Bolt")
print(f"Creature removal: {tags.creature_removal}")  # True
print(f"Planeswalker removal: {tags.planeswalker_removal}")  # True

# Tag all cards in deck
deck_cards = ["Lightning Bolt", "Counterspell", "Sol Ring"]
deck_tags = tagger.tag_deck_cards(deck_cards)

# Export all tags
tagger.export_tags(Path("card_functional_tags.json"))
```

### How It Works

Rule-based classification using:
1. **Oracle text patterns**: Regex matching on card text
2. **Type line analysis**: Card types inform roles
3. **Known combo lists**: Curated list of combo pieces
4. **Heuristics**: "untap" + "permanent" often = combo

**Not LLM-based** (deterministic, fast, reproducible)

---

## 4. EDHREC Commander Enrichment

### Purpose

Commander/EDH-specific data that isn't relevant to other formats.

**Implementation**: `src/backend/games/magic/dataset/edhrec`

### Data Captured

**For Commanders:**
```go
type CommanderInfo struct {
    Rank             int      `json:"rank"`              // Popularity rank
    NumDecks         int      `json:"num_decks"`         // Number of decks
    Colors           []string `json:"colors"`            // Color identity
    TopCards         []string `json:"top_cards"`         // Top 20 cards in decks
    Themes           []string `json:"themes"`            // Common themes
    AverageDeckPrice *float64 `json:"average_deck_price"`
}
```

**For All Cards:**
- `salt_score`: 0-100 annoyance rating (higher = more feel-bad)
- `rank`: Overall EDH popularity
- `num_decks`: Number of decks playing this card
- `themes`: Associated themes/archetypes
- `synergies`: Cards that synergize well (with scores)

### Usage

```bash
# Extract EDHREC data
cd src/backend
go run cmd/dataset/main.go extract magic/edhrec --limit 200
```

**Applications:**
- Commander tier lists
- Salt score filtering (avoid annoying cards)
- Theme-based deck building
- Synergy recommendations

---

## 5. Tournament Metadata Enhancement

### Enhanced Deck Metadata

All tournament decks now capture (when available):
- `player`: Player name
- `event`: Tournament/event name
- `placement`: Finishing position (1 = 1st, 0 = unknown)
- `event_date`: Event date string
- `source`: Which scraper extracted this

**Storage**: CollectionTypeDeck

```go
type CollectionTypeDeck struct {
    Name      string `json:"name"`
    Format    string `json:"format"`
    Archetype string `json:"archetype,omitempty"`
    Player    string `json:"player,omitempty"`
    Event     string `json:"event,omitempty"`
    Placement int    `json:"placement,omitempty"`
    EventDate string `json:"event_date,omitempty"`
}
```

**Benefits:**
- Track player performance over time
- Analyze event-specific metagames
- Weight decks by placement (winners matter more)
- Temporal meta analysis

---

## 6. Integration with ML Pipeline

### Enriched Features for Embeddings

**Old approach**: Card names + co-occurrence only

**New approach**: Multi-modal features
1. **Co-occurrence** (existing)
2. **Functional tags** (removal, ramp, etc.)
3. **Price tiers** (budget constraints)
4. **Keywords** (Flash, Flying, etc.)
5. **Color identity** (Commander constraints)
6. **EDHREC data** (Commander-specific)
7. **Tournament metadata** (placement weights)

### Example: Budget Substitute Finder

**Problem**: "I can't afford Force of Will ($80)"

**Solution**:
```python
from card_market_data import MarketDataManager
from card_similarity_pecan import load_similarity_model

# 1. Load market data
market = MarketDataManager()

# 2. Load similarity model (co-occurrence based)
model = load_similarity_model("vectors.kv")

# 3. Find functionally similar cards
similar_cards = model.most_similar("Force of Will", topn=20)
similar_names = [card for card, _ in similar_cards]

# 4. Filter by price
substitutes = market.find_budget_substitutes(
    "Force of Will",
    similar_names,
    max_price=5.0
)

# Results: Counterspell ($0.25), Mana Drain ($40 - excluded), etc.
```

### Example: Role-Based Deck Analysis

```python
from card_functional_tagger import FunctionalTagger

tagger = FunctionalTagger()

# Tag all cards in a Burn deck
burn_deck = ["Lightning Bolt", "Monastery Swiftspear", "Eidolon of the Great Revel", ...]
tags = tagger.tag_deck_cards(burn_deck)

# Count removal vs threats vs resources
removal_count = sum(1 for t in tags.values() if t.creature_removal)
card_draw = sum(1 for t in tags.values() if t.card_draw)

print(f"Removal spells: {removal_count}")
print(f"Card advantage: {card_draw}")
```

---

## 7. Data Quality & Validation

### Validators

Existing validators (`src/ml/validators/`) now integrate with enrichment:
- **Price validation**: Reject cards with invalid prices
- **Legality checking**: Cross-reference with enriched legality data
- **Format rules**: Use captured format legalities

### Ban List Integration

Enriched legalities include ban status:
- `"banned"`: Card is banned
- `"restricted"`: Limited to 1 copy (Vintage)
- `"legal"`: Legal in format
- `"not_legal"`: Not in card pool for format

---

## 8. Recommended Workflow

### Initial Setup
```bash
# 1. Extract enhanced card data
cd src/backend
go run cmd/dataset/main.go extract magic/scryfall --section cards --reparse

# 2. Extract EDHREC data
go run cmd/dataset/main.go extract magic/edhrec --limit 200

# 3. Generate functional tags
cd ../ml
uv run python card_functional_tagger.py

# 4. Generate price database
uv run python card_market_data.py
```

### Regular Updates
```bash
# Weekly: Update tournament decks
go run cmd/dataset/main.go extract magic/mtgtop8 --limit 1000
go run cmd/dataset/main.go extract magic/mtgdecks --limit 1000

# Monthly: Refresh card data (prices update)
go run cmd/dataset/main.go extract magic/scryfall --section cards --reparse

# Monthly: Refresh EDHREC
go run cmd/dataset/main.go extract magic/edhrec --limit 200 --reparse
```

---

## 9. Performance Considerations

- **Scryfall parsing**: ~1000 cards/min (API rate limit)
- **Functional tagging**: ~1000 cards/sec (pure Python)
- **Price loading**: Limited by disk I/O (~1000 cards/sec)
- **EDHREC scraping**: ~10-20 commanders/min (rate limiting)

**Storage impact**:
- Enriched card data: ~2-3x larger than minimal (still <500MB total)
- Price database: ~5MB JSON
- Functional tags: ~10MB JSON
- EDHREC data: ~2MB JSON

---

## 10. Breaking the P@10 = 0.08 Plateau

**Hypothesis**: Co-occurrence alone plateaus because it lacks semantic understanding.

**Enrichment strategies to improve P@10:**

1. **Functional similarity**: "Both are removal spells" (functional tags)
2. **Price-aware**: "Budget substitutes in same role" (market data)
3. **Mechanical similarity**: "Both have Flash" (keywords)
4. **Role-based clustering**: Group by function, then co-occurrence within groups

**Next experiments**:
- Hybrid similarity: 50% co-occurrence + 30% functional + 20% mechanical
- Price-tier aware: Separate embeddings for budget/premium cards
- Commander-specific: Use EDHREC synergies as ground truth

---

## Questions & Future Work

### Answered by Enrichment
✅ "What's a budget alternative to Force of Will?" → Price + functional tags  
✅ "What removal spells are legal in Pauper?" → Functional tags + rarity + legalities  
✅ "What are the saltiest cards in EDH?" → EDHREC salt scores  
✅ "Which cards have Flash?" → Keywords enrichment

### Not Yet Answered
⚠️ "How has the meta shifted over time?" → Need temporal tracking  
⚠️ "What's the win rate of this deck?" → Need tournament results scraping  
⚠️ "Is this card trending up in price?" → Need price history

### Extensibility

All enrichment systems are **modular**:
- Add new functional tags: Edit `card_functional_tagger.py` rules
- Add new price sources: Implement in `card_market_data.py`
- Add new scrapers: Follow pattern in `src/backend/games/*/dataset/`

---

## Summary

DeckSage now captures:
- ✅ **10 data sources** (up from 5)
- ✅ **Pricing** for all MTG cards (USD, EUR, foil, MTGO)
- ✅ **30+ functional tags** (removal, ramp, tutors, etc.)
- ✅ **Keywords & mechanics** (Flash, Flying, etc.)
- ✅ **Format legalities** (all formats)
- ✅ **EDHREC data** (salt scores, synergies, themes)
- ✅ **Tournament metadata** (player, event, placement)
- ✅ **Budget analysis** (substitute finder, deck pricing)

**Impact on P@10**: TBD - requires re-training with enriched features

See `experiments/DATA_SOURCES.md` for comprehensive source documentation.
