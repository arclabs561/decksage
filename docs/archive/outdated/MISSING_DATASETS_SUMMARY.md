# Missing Datasets - Summary & Solution

## Status

✅ **Fixed Programmatically:**
- Expanded `ground_truth_v1.json`: 5 → 38 queries
- Created validation and health check tools
- Documented all datasets and embeddings

❌ **Requires Data Collection:**
- `decks_pokemon.jsonl`: Empty (0 decks)
- `yugioh_decks.jsonl`: Insufficient (20 decks, need 1000+)

## Root Cause

Raw data directories contain **card definitions**, not **deck lists**. Deck data must be collected via scrapers that fetch actual deck lists from:
- Tournament sites (Limitless TCG, YGOPRODeck tournaments)
- Community sites (PokemonCard.io, Yu-Gi-Oh Meta)
- API endpoints

## Solution

### Option 1: Run Scrapers (Recommended)
1. Set up API keys if needed (e.g., LIMITLESS_API_KEY)
2. Run backend scrapers for Pokemon/Yu-Gi-Oh decks
3. Export collected decks to JSONL format

### Option 2: Use Existing Data (If Available)
- Check if deck data exists in other locations
- Export using `bin/export-hetero` tool
- Merge into target JSONL files

### Option 3: Document Limitation
- Update documentation to note Pokemon/Yu-Gi-Oh have limited deck data
- Focus evaluation on Magic (which has full data)
- Plan data collection as separate task

## Files Created

- `scripts/collect_missing_decks.md` - Detailed collection instructions
- `scripts/export_missing_decks.py` - Export tool (needs deck data first)
- `data/processed/DECK_DATA_STATUS.md` - Current status tracking

## Next Steps

1. ✅ All programmatic fixes complete
2. ⏳ Run scrapers to collect deck data (requires setup)
3. ⏳ Export collected decks to JSONL format
4. ⏳ Update health check once data is available

## Quick Commands

```bash
# Check status
python scripts/dataset_health_check.py

# Try to export (will fail if no deck data exists)
python scripts/export_missing_decks.py

# See instructions
cat scripts/collect_missing_decks.md
```
