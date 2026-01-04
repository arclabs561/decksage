# Data Validators

Comprehensive validation system for multi-game card data with Pydantic models, format-specific deck construction rules, and deterministic legality checking.

## Architecture

```
validators/
├── models.py       # Pydantic models with format-specific rules
├── legality.py     # Deterministic ban list / legality checking
├── loader.py       # Validated data loading for ML pipeline
└── README.md       # This file
```

## Design Principles

### What Validators Do

Deterministic structural validation
- Card name quality (Unicode normalization, no control chars)
- Deck size constraints (60-card, 100-card, etc.)
- Copy limits (4-of rule, singleton, etc.)
- Format-specific construction rules

Deterministic legality checking
- Ban lists from authoritative sources (Scryfall, YGOProDeck API)
- Format legality (set rotation, rarity restrictions)
- Cached for performance (7-day TTL)

Type safety
- Pydantic models ensure type correctness
- Validation errors show exact field and reason
- IDE autocomplete and type checking

### What Validators Don't Do

❌ **Semantic validation** (use `llm_data_validator.py` for this)
- Archetype coherence ("does this deck make sense?")
- Card synergy assessment
- Metagame analysis

These require LLMs and should be **optional batch processes**, not in the critical path.

## ⚠️ Important: Which Data File to Use

**Use:** `data/processed/decks_with_metadata.jsonl`
- format field populated (Modern, Legacy, Standard, Pauper, etc.)
- archetype field populated (UR Aggro, Burn, Control, etc.)
- ~500K decks with full metadata
- Success rate: ~96% (validators catch bad decks)

**Don't use:** `src/backend/decks_hetero.jsonl`
- ❌ format field empty (all become "Unknown")
- ❌ archetype field empty
- ❌ No format-specific validation possible
- Success rate: 100% (but no format rules enforced)

**Note:** Both files have `source: null`. Game detection uses URL instead.

## Usage

### Basic Validation

```python
from validators.models import MTGDeck, CardDesc, Partition

# Create a valid Modern deck
deck = MTGDeck(
    deck_id="modern_burn_1",
    format="Modern",
    partitions=[
        Partition(
            name="Main",
            cards=[
                CardDesc(name="Lightning Bolt", count=4),
                CardDesc(name="Lava Spike", count=4),
                CardDesc(name="Monastery Swiftspear", count=4),
                CardDesc(name="Mountain", count=20),
                # ... more cards
            ],
        ),
        Partition(
            name="Sideboard",
            cards=[
                CardDesc(name="Path to Exile", count=4),
                CardDesc(name="Rest in Peace", count=4),
                # ...
            ],
        ),
    ],
)

# Validation happens automatically on construction
print(deck.get_main_deck().total_cards())  # 32
print(deck.get_sideboard().total_cards())  # 8
```

### Validation Errors

```python
from pydantic import ValidationError

try:
    deck = MTGDeck(
        deck_id="bad_deck",
        format="Modern",
        partitions=[
            Partition(
                name="Main",
                cards=[
                    CardDesc(name="Lightning Bolt", count=5),  # Too many!
                    CardDesc(name="Mountain", count=55),
                ],
            ),
        ],
    )
except ValidationError as e:
    print(e)
    # Output:
    # Modern allows max 4 copies per card, but Lightning Bolt appears 5 times
```

### Loading Data for ML Pipeline

```python
from pathlib import Path
from validators.loader import load_decks_lenient

# Lenient mode: Skip invalid decks, log errors, maximize data usage
decks = load_decks_lenient(
    Path("decks_hetero.jsonl"),
    check_legality=False,  # Skip expensive API calls
    game="magic",          # Or "auto" to detect
    verbose=True,
)

# Output:
# Loaded 9847/10000 decks successfully
#   Parse failures: 23
#   Schema violations: 130
#   Legality issues: 0
#   Total processed: 10000
#
# Sample schema violations:
#   line_457: cards: Partition must have at least one card
#   line_892: format: Modern allows max 4 copies per card, but Lightning Bolt appears 5 times
```

### Strict Mode (For Critical Pipelines)

```python
from validators.loader import load_decks_strict

try:
    decks = load_decks_strict(
        Path("tournament_data.jsonl"),
        check_legality=True,  # Enforce ban lists
        game="magic",
    )
except ValidationError as e:
    print(f"Invalid deck found: {e}")
    # Fail fast on first error
```

### Ban List Checking

```python
from validators.legality import check_deck_legality

issues = check_deck_legality(deck)

if issues:
    print("Deck has legality issues:")
    for issue in issues:
        print(f"  - {issue}")
    # Example:
    #   - Oko, Thief of Crowns is banned in Modern
    #   - Once Upon a Time is banned in Modern
else:
    print("Deck is legal!")
```

## Supported Games and Formats

### Magic: The Gathering

**Formats with validation:**
- Modern (60+ cards, 15 sideboard, 4-of limit)
- Legacy (60+ cards, 15 sideboard, 4-of limit)
- Vintage (60+ cards, 15 sideboard, 4-of limit, restricted list)
- Pauper (60+ cards, 15 sideboard, 4-of limit, commons only)
- Pioneer (60+ cards, 15 sideboard, 4-of limit)
- Standard (60+ cards, 15 sideboard, 4-of limit)
- Commander (100 cards exactly, singleton, no sideboard)
- cEDH (100 cards exactly, singleton, no sideboard)
- Brawl (60 cards exactly, singleton, no sideboard)

**Special rules:**
- Basic lands exempt from copy limits
- Restricted cards in Vintage (1 copy max)
- Ban list checking via Scryfall API

### Yu-Gi-Oh!

**Rules:**
- Main Deck: 40-60 cards
- Extra Deck: 0-15 cards
- Side Deck: 0-15 cards
- 3-copy limit per card (no exceptions)

**Ban Lists:**
- TCG and OCG formats
- Limited/Semi-Limited/Forbidden lists

### Pokemon TCG

**Rules:**
- Deck: exactly 60 cards
- 4-copy limit per card
- Basic Energy unlimited

**Formats:**
- Standard
- Expanded
- Unlimited

## Performance

### Validation Speed

- **Structural validation**: ~10,000 decks/second (Pydantic is fast)
- **Ban list checking**: ~100 decks/second (API calls cached)

### Caching

Ban lists are cached in `.cache/ban_lists/` with 7-day TTL:
- `mtg_legality.json` (~100MB from Scryfall bulk data)
- `yugioh_banlist.json` (~5MB from YGOProDeck)
- `pokemon_legality.json` (~10MB from Pokemon TCG API)

Delete cache files to force refresh.

## Testing

Run the test suite:

```bash
uv run pytest src/ml/tests/test_validators.py -v
```

**Coverage:**
- Card name validation (Unicode, whitespace, control chars)
- Partition validation
- Format-specific deck rules (27 test cases)
- All 3 games (MTG, YGO, Pokemon)

## Integration with Existing Code

### Before (Unvalidated)

```python
with open(PATHS.decks_with_metadata) as f:
    for line in f:
        deck = json.loads(line)  # No validation!
        # Hope the data is good...
```

### After (Validated)

```python
from validators.loader import load_decks_lenient

decks = load_decks_lenient(
    PATHS.decks_with_metadata,
    check_legality=False,
    verbose=True,
)

# Now you have type-safe, validated decks
for deck in decks:
    main = deck.get_main_deck()
    print(f"{deck.format} deck with {main.total_cards()} cards")
```

## When to Use LLM Validators

Use `llm_data_validator.py` (optional batch auditing) for:

- Finding mislabeled archetypes
- Detecting incoherent decks (scraping errors)
- Card relationship analysis
- Quality scoring for human review

**Do NOT use LLMs for:**
- Ban list checking (they hallucinate)
- Format legality (use deterministic rules)
- Deck construction rules (use Pydantic models)

## Design Rationale

### Why Pydantic?

1. **Type safety** - Catch errors at validation time, not runtime
2. **Performance** - Rust-backed validation is fast
3. **Ergonomics** - Clean Python syntax, IDE support
4. **Composability** - Validators compose naturally
5. **Error messages** - Clear, actionable errors with field paths

### Why Deterministic Legality?

LLMs are terrible at factual recall:
- They hallucinate ban lists
- They don't know recent changes
- They're slow and expensive
- They're non-deterministic

Use authoritative data sources instead:
- Scryfall API (MTG, updated daily)
- YGOProDeck API (YGO, official Konami data)
- Pokemon TCG API (Pokemon, official data)

### Why Lenient by Default?

ML pipelines benefit from **maximizing data usage**:
- Some decks have minor errors (extra comma, formatting)
- Better to include 9,800 valid decks than fail on 200 errors
- Log errors for investigation but don't block training

Strict mode available for critical pipelines (tournament reporting, etc).

## Future Enhancements

Potential additions:
- [ ] Mana curve validation (warn if curve is suspicious)
- [ ] Color identity validation (Commander color restrictions)
- [ ] Rarity validation (Pauper commons-only check)
- [ ] Historical ban list support (validate old decks)
- [ ] Performance metrics (validation time, cache hit rate)
- [ ] Integration with Go backend (shared validation logic)
- [ ] Property-based testing (Hypothesis)
