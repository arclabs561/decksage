# Multi-Game Data Extraction - In Progress

**Started**: 2025-12-04  
**Status**: Running in background

---

## Active Extractions

### 1. Pokemon Tournament Decks
- **Command**: `pokemon/limitless-web --limit 2000`
- **Expected**: 1,208+ tournament decks
- **Status**: 🔄 Running in background
- **Output**: `data-full/games/pokemon/limitless-web/`

### 2. Yu-Gi-Oh! Tournament Decks
- **Command**: `yugioh/ygoprodeck-tournament --pages 40 --limit 5000`
- **Expected**: 520+ tournament decks (can scale to 5,000+)
- **Status**: 🔄 Running in background
- **Output**: `data-full/games/yugioh/ygoprodeck-tournament/`

---

## Monitoring Commands

### Check Progress
```bash
# Count extracted files
find data-full/games/pokemon -name "*.zst" | wc -l
find data-full/games/yugioh -name "*.zst" | wc -l

# Check process status
ps aux | grep -E "(limitless|ygoprodeck)" | grep -v grep

# Check disk usage
du -sh data-full/games/pokemon
du -sh data-full/games/yugioh
```

### Check Logs
```bash
# If running in foreground, logs appear in terminal
# Background processes: check with ps or tail log files if any
```

---

## Next Steps (After Extraction Completes)

1. **Verify extraction**:
   ```bash
   find data-full/games/pokemon -name "*.zst" | wc -l  # Should be 1,208+
   find data-full/games/yugioh -name "*.zst" | wc -l    # Should be 520+
   ```

2. **Re-run multi-game export**:
   ```bash
   ./bin/export-multi-game-graph data-full/games data/processed/pairs_multi_game.csv
   ```

3. **Expected output**: All three games (MTG, Pokemon, Yu-Gi-Oh!) in the graph

---

## Time Estimates

- **Pokemon**: ~10-20 minutes (1,208 decks)
- **Yu-Gi-Oh!**: ~15-30 minutes (520+ decks)
- **Total**: ~30-50 minutes for both

---

**Extractions running in background. Monitor progress with commands above.**

