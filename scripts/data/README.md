# Data Processing Scripts

Scripts for downloading, enriching, and transforming card data for the DeckSage search and recommendation system.

## Data Flow

```
YGOProDeck API ──> cardinfo.json ──> enrich_yugioh_cards.py ──> card_attributes_yugioh_enriched.csv
                   (raw download)    (enrichment)               (loaded at server startup)
```

For Magic and Pokemon, equivalent enrichment scripts exist in this directory. The general pattern:

1. **Download**: Raw card data from external APIs cached in `data/raw/`
2. **Enrich**: Scripts in `scripts/data/` join API fields, classify card types, and generate oracle text
3. **Load**: `src/ml/api/api.py` loads enriched CSVs into `ApiState.card_metadata` at startup

## Scripts

### `enrich_yugioh_cards.py`

Enriches `card_attributes_yugioh.csv` with fields from the YGOProDeck bulk API.

```sh
uv run scripts/data/enrich_yugioh_cards.py
uv run scripts/data/enrich_yugioh_cards.py --input data/processed/card_attributes_yugioh.csv --output /tmp/test.csv
```

**Input**: `data/processed/card_attributes_yugioh.csv` (base card names + embeddings metadata)
**API cache**: `data/raw/ygoprodeck/cardinfo.json` (downloaded on first run, ~80 MB)
**Output**: `data/processed/card_attributes_yugioh_enriched.csv`

#### Output fields

| Field | Source | Description |
|-------|--------|-------------|
| `atk` | API `atk` | Attack points |
| `def_stat` | API `def` | Defense points |
| `level_rank_link` | API `level`/`linkval` | Level, Rank, or Link rating |
| `card_category` | Derived from `type` | Monster/Spell/Trap/Token |
| `monster_type` | Derived from `type` | Effect/Fusion/Synchro/Xyz/Link/Pendulum/Normal/... |
| `attribute_enriched` | API `attribute` | DARK/LIGHT/EARTH/WATER/FIRE/WIND/DIVINE |
| `race_enriched` | API `race` | Spellcaster/Dragon/Warrior/... (for Spells/Traps: property) |
| `archetype_enriched` | API `archetype` | Card archetype (e.g., "Blue-Eyes", "Stardust") |
| `pendulum_scale` | API `scale` | Pendulum Scale value |
| `link_markers` | API `linkmarkers` | Comma-separated link arrow directions |
| `oracle_text_enriched` | Derived from `desc` | Full effect text with stat summary line |
| `summoning_requirements` | Text-mined from `desc` | Material requirements for Extra Deck/Ritual monsters |
| `effect_types` | Text-mined from `desc` | Comma-separated: Quick Effect, Flip, Trigger, Continuous, Ritual |

### `build_deck_frequency.py`

Builds card co-occurrence frequency data from deck lists.

## Known Gaps

Compared to wiki-sourced data (e.g., the archived `yugi` scraper), this pipeline lacks:

| Missing dimension | Why | Feasibility |
|-------------------|-----|-------------|
| Multilingual card names | YGOProDeck API returns English only | Would need yugipedia wiki or alternative source |
| Per-card release dates | API has `card_sets` but not consumed yet | Available — future work |
| Banlist status | API has `banlist_info` but not consumed yet | Available — future work |
| Wiki categories | Not in API | Would need wiki scraping |
| Reverse relationships (summoned-by) | Would need cross-card index | Can build from summoning_requirements |

See `memory/yugi-reference-schema.md` for the full comparison with yugi's Card schema.
