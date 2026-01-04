# All Extractions Running

**Date**: 2025-12-04
**Status**: All extractions started and running in background

---

## ✅ Completed

1. **AimStack Integration**: Fully integrated into all scripts
2. **Card Enrichment**: 100% complete (26,960 cards)
3. **MTG Multi-Game Export**: 53,478 decks, 24.6M edges exported

---

## 🔄 Currently Running

### 1. Pokemon Tournament Decks
- **Command**: `pokemon/limitless-web --limit 2000`
- **Process**: Running in background (PID visible in `ps aux`)
- **Expected**: 1,208+ tournament decks
- **Output**: `data-full/games/pokemon/limitless-web/`
- **Status**: Just started (0 files extracted so far)

### 2. Yu-Gi-Oh! Tournament Decks
- **Command**: `yugioh/ygoprodeck-tournament --pages 40 --limit 5000`
- **Process**: Running in background (PID visible in `ps aux`)
- **Expected**: 520+ tournament decks (can scale to 5,000+)
- **Output**: `data-full/games/yugioh/ygoprodeck-tournament/`
- **Status**: Just started (0 files extracted so far)

### 3. Test Set Labeling
- **Status**: 38/100 queries labeled (38%)
- **Process**: Background process (may have completed or stalled)

---

## 📊 Monitoring

### Check Extraction Progress
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

### Check Overall Status
```bash
# All games
du -sh data-full/games/*

# All processes
ps aux | grep -E "(limitless|ygoprodeck|enrich|label)" | grep -v grep
```

---

## ⏳ Next Steps (After Extractions Complete)

1. **Verify extractions**:
   - Pokemon: Should have 1,208+ `.zst` files
   - Yu-Gi-Oh!: Should have 520+ `.zst` files

2. **Re-run multi-game export**:
   ```bash
   ./bin/export-multi-game-graph data-full/games data/processed/pairs_multi_game.csv
   ```

3. **Expected output**: All three games in the graph
   - MTG: 53,478 decks
   - Pokemon: 1,208+ decks
   - Yu-Gi-Oh!: 520+ decks

4. **Train unified embeddings** on complete multi-game graph

---

## ⏱️ Time Estimates

- **Pokemon**: ~10-20 minutes (1,208 decks)
- **Yu-Gi-Oh!**: ~15-30 minutes (520+ decks)
- **Total**: ~30-50 minutes for both extractions

---

## 🎯 Summary

**All systems operational:**
- ✅ AimStack ready
- ✅ Card enrichment complete
- ✅ MTG data exported
- 🔄 Pokemon extraction running
- 🔄 Yu-Gi-Oh! extraction running
- 🔄 Test set labeling in progress

**Next milestone**: Complete multi-game graph with all three games!
