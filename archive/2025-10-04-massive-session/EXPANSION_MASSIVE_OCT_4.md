# Massive Dataset Expansion - October 4, 2025

## Strategy: Maximum Extraction

Running aggressive parallel extraction across all sources to maximize dataset size.

## Expansion Targets

### Pokemon (Limitless Web)
- **Target**: 5,000 decks
- **Pages**: 100
- **Current**: 401
- **Expected**: +4,500-4,600 decks
- **Time**: ~60-90 minutes
- **Command**: `extract limitless-web --pages 100 --limit 5000`

### Yu-Gi-Oh (YGOPRODeck Tournament)
- **Target**: 1,000 decks
- **Pages**: 50
- **Current**: 20
- **Expected**: +200-500 decks (depends on available tournament decks)
- **Time**: ~30-45 minutes
- **Command**: `extract ygoprodeck-tournament --pages 50 --limit 1000`

### MTG Pioneer (Format Balance)
- **Target**: 200 decks
- **Current**: ~15
- **Expected**: +185 decks
- **Time**: ~15-20 minutes
- **Command**: `extract mtgtop8 --section pioneer --limit 200`

### MTG Vintage (Format Balance)
- **Target**: 200 decks
- **Current**: ~20
- **Expected**: +180 decks
- **Time**: ~15-20 minutes
- **Command**: `extract mtgtop8 --section vintage --limit 200`

## Expected Final State

| Game | Cards | Decks Before | Decks After | Change |
|------|-------|--------------|-------------|--------|
| **MTG** | 35,400 | 55,293 | ~55,658 | **+365** |
| **Pokemon** | 3,000 | 401 | ~5,000 | **+4,599** |
| **Yu-Gi-Oh** | 13,930 | 20 | ~220-520 | **+200-500** |

**Total Expected**: 60,878-61,178 tournament decks (+5,164-5,464)

## Parallel Execution

All 4 extraction jobs running simultaneously:
1. Pokemon (Limitless web) - Background PID 1
2. Yu-Gi-Oh (YGOPRODeck) - Background PID 2
3. MTG Pioneer - Background PID 3
4. MTG Vintage - Background PID 4

## Monitoring

```bash
# Check progress
tail -f logs/limitless_MASSIVE_*.log
tail -f logs/ygoprodeck_MASSIVE_*.log
tail -f logs/mtgtop8_pioneer_*.log
tail -f logs/mtgtop8_vintage_*.log

# Check counts (live)
watch -n 10 'fd -e zst . src/backend/data-full/games -t f | wc -l'

# Per-game counts
fd -e zst . src/backend/data-full/games/pokemon/limitless-web -t f | wc -l
fd -e zst . src/backend/data-full/games/yugioh/ygoprodeck-tournament -t f | wc -l
```

## Rate Limiting

- Pokemon: 30 req/min (conservative, respectful)
- Yu-Gi-Oh: 30 req/min (conservative)
- MTGTop8: 100 req/min (default, proven safe)

Total bandwidth: ~160 requests/minute across all sources

## Data Quality Checks

After extraction completes:
```bash
# Validate all data
cd src/ml
uv run python llm_data_validator.py

# Check for duplicates
cd ../backend
go run cmd/analyze-decks/main.go data-full/games

# Export expanded dataset
go run cmd/export-hetero/main.go data-full/games/pokemon/limitless-web ../../data/pokemon_all.jsonl
go run cmd/export-hetero/main.go data-full/games/yugioh/ygoprodeck-tournament ../../data/yugioh_all.jsonl
```

## Timeline

**Start**: 7:24 PM Oct 4, 2025
**Pokemon ETA**: 9:00 PM (90 min)
**YGO ETA**: 8:00 PM (35 min)
**MTG Pioneer ETA**: 7:45 PM (20 min)
**MTG Vintage ETA**: 7:45 PM (20 min)
**All Complete ETA**: ~9:00 PM

## Success Metrics

**Minimum Success**:
- Pokemon: 2,000+ decks
- YGO: 100+ decks
- MTG formats: +300 decks

**Target Success**:
- Pokemon: 5,000 decks
- YGO: 500 decks
- MTG formats: +365 decks

**Stretch Goal**:
- Pokemon: 10,000 decks (if pagination allows)
- YGO: 1,000 decks
- MTG: Balanced coverage across all formats

## Risk Assessment

**Low Risk**:
- All scrapers tested and working
- Rate limiting conservative
- HTTP caching prevents duplicates
- Graceful error handling

**Potential Issues**:
- YGOPRODeck might have fewer tournament decks than expected
- Limitless might hit pagination limit
- Network interruptions (resume capability exists)

## Fallback Plan

If any scraper fails:
1. Check logs for error patterns
2. Reduce `--pages` and retry
3. Use `--start` flag to resume from checkpoint
4. Acceptable to get partial data (e.g., 2,000 Pokemon instead of 5,000)

---

**Status**: 🚀 **EXTRACTION IN PROGRESS**

Monitor with: `ps aux | grep "go run cmd/dataset"`
