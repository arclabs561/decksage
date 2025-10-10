# DeckSage Commands Reference

Quick reference for common operations.

---

## Enrichment Pipeline (NEW ⭐)

### Test All Systems
```bash
uv run python test_enrichment_pipeline.py
# Expected: 🎉 ALL ENRICHMENT SYSTEMS OPERATIONAL
```

### Generate Functional Tags (Free)
```bash
cd src/ml
uv run python card_functional_tagger.py        # MTG: 30+ tags
uv run python pokemon_functional_tagger.py     # Pokemon: 25+ tags  
uv run python yugioh_functional_tagger.py      # Yu-Gi-Oh!: 35+ tags
```

### Run LLM Enrichment (Recommended: ~$0.20)
```bash
cd src/ml
uv run python unified_enrichment_pipeline.py \
    --game pokemon \
    --input pokemon_cards.json \
    --output pokemon_enriched.json \
    --level standard

# Levels: basic (free), standard ($0.20), comprehensive ($5), full ($$$)
```

---

## Data Extraction

### MTG - All Sources
```bash
cd src/backend

# Cards with pricing/keywords (enhanced)
go run cmd/dataset/main.go extract magic/scryfall --section cards --reparse

# Tournament decks
go run cmd/dataset/main.go extract magic/mtgtop8 --limit 60000
go run cmd/dataset/main.go extract magic/mtgdecks --limit 10000  # NEW

# Commander enrichment
go run cmd/dataset/main.go extract magic/edhrec --limit 200  # NEW
```

### Pokemon - All Sources
```bash
cd src/backend

# Cards
go run cmd/dataset/main.go extract pokemon/pokemontcg

# Tournament decks
go run cmd/dataset/main.go extract pokemon/limitless-web --limit 2000
go run cmd/dataset/main.go extract pokemon/limitless --limit 1000  # API-based
```

### Yu-Gi-Oh! - All Sources  
```bash
cd src/backend

# Cards with pricing (enhanced)
go run cmd/dataset/main.go extract yugioh/ygoprodeck --section cards --reparse

# Tournament decks (enhanced + new)
go run cmd/dataset/main.go extract yugioh/ygoprodeck-tournament --scroll-limit 50
go run cmd/dataset/main.go extract yugioh/yugiohmeta --limit 500  # NEW
```

---

## Embeddings & Similarity

### Train Embeddings
```bash
cd src/backend
go run cmd/export-graph/main.go pairs.csv

cd ../ml
uv run python card_similarity_pecan.py --input ../backend/pairs.csv
```

### Run API Server
```bash
cd src/ml
uv run python api.py --embeddings vectors.kv --pairs ../backend/pairs.csv --port 8000

# Health checks
curl -s localhost:8000/live
curl -s localhost:8000/ready

# Query similarity
curl -s "localhost:8000/v1/cards/Lightning%20Bolt/similar?mode=synergy&k=5"
```

---

## Analysis & Validation

### Deck Analysis
```bash
cd src/backend
go run cmd/analyze-decks/main.go data-full/
```

### Data Quality
```bash
cd src/ml
uv run python validators/test_validators.py
```

### Archetype Staples
```bash
cd src/ml
uv run python archetype_staples.py --archetype Burn --format Modern
```

### Card Companions
```bash
cd src/ml
uv run python card_companions.py --card "Lightning Bolt"
```

---

## Testing

### Python Tests
```bash
make test
# or
cd src/ml
uv run pytest
```

### Go Tests
```bash
cd src/backend
go test ./...
```

### API Integration Tests
```bash
make test-api
```

---

## Data Management

### Backup Data
```bash
# Backup Badger cache
tar -czf backups/badger-cache-$(date +%Y%m%d_%H%M%S).tar.gz src/backend/badger-cache/

# Backup full data
tar -czf backups/data-full-$(date +%Y%m%d_%H%M%S).tar.gz src/backend/data-full/
```

### Restore Cache
```bash
./scripts/recover_cache.sh backups/badger-cache-XXXXXX.tar.gz
```

---

## Enrichment Cost Estimates

| Operation | Cards | Cost | Time |
|-----------|-------|------|------|
| Functional tags (all) | 52,330 | $0 | < 1 min |
| LLM sample (100/game) | 300 | $0.60 | 10 min |
| LLM comprehensive | 5,000 | $10 | 1 hour |
| Vision sample (50/game) | 150 | $1.50 | 20 min |

---

## Quick Workflows

### Development (Free)
```bash
# Just functional tags
cd src/ml
uv run python card_functional_tagger.py
uv run python pokemon_functional_tagger.py
uv run python yugioh_functional_tagger.py
```

### Production ($3)
```bash
# Standard enrichment all games
cd src/ml
for game in mtg pokemon yugioh; do
    uv run python unified_enrichment_pipeline.py \
        --game $game --level standard \
        --input ${game}.json --output ${game}_enriched.json
done
```

### Research ($10-30)
```bash
# Comprehensive enrichment
cd src/ml
uv run python unified_enrichment_pipeline.py \
    --game mtg \
    --level comprehensive \
    --input mtg_full.json \
    --output mtg_comprehensive.json
```

---

## Troubleshooting

### Missing Dependencies
```bash
uv pip install pillow  # For vision models
```

### API Keys
```bash
# Check .env file has:
OPENROUTER_API_KEY=sk-or-v1-...
RAPIDAPI_KEY=...
LIMITLESS_API_KEY=...  # For Limitless TCG API
```

### Go Module Issues
```bash
cd src/backend
go mod tidy
go mod download
```

---

See `ENRICHMENT_QUICKSTART.md` for detailed enrichment guide.