# Paused for Bed - Resume Guide

**Date**: 2025-12-04  
**Status**: All processes paused

---

## Paused Processes

### Local Background Processes
- **Pokemon Extraction**: `pokemon/limitless-web` (paused with SIGSTOP)
- **Yu-Gi-Oh! Extraction**: `yugioh/ygoprodeck-tournament` (paused with SIGSTOP)
- **Card Enrichment**: `enrich_attributes_with_scryfall_optimized.py` (paused if running)
- **Test Set Labeling**: `generate_labels_for_new_queries_optimized.py` (paused if running)
- **S3 Download**: `s5cmd` (paused if running)

### AWS EC2 Instances
- **Instance**: `i-0388197edd52b11f2` (check status with AWS CLI)

---

## Resume Commands

### Resume Local Processes
```bash
# Find paused processes
ps aux | grep -E "(limitless|ygoprodeck|enrich|label|s5cmd)" | grep -E "(STOP|T)"

# Resume by PID (replace PID with actual process ID)
kill -CONT <PID>

# Or resume all paused processes
ps aux | grep -E "(limitless|ygoprodeck|enrich|label|s5cmd)" | grep -E "(STOP|T)" | awk '{print $2}' | xargs kill -CONT
```

### Resume AWS Instance
```bash
# Check status
aws ec2 describe-instances --instance-ids i-0388197edd52b11f2 --query 'Reservations[0].Instances[0].State.Name' --output text

# Start if stopped
aws ec2 start-instances --instance-ids i-0388197edd52b11f2

# Wait for running
aws ec2 wait instance-running --instance-ids i-0388197edd52b11f2
```

---

## Current Status

### ✅ Completed
- AimStack: Installed and integrated
- Card Enrichment: 100% (26,960 cards)
- MTG Export: 53,478 decks, 24.6M edges

### ⏸️ Paused
- Pokemon Extraction: Started but paused (0 files extracted)
- Yu-Gi-Oh! Extraction: Started but paused (0 files extracted)
- Test Set Labeling: 38/100 (38%) - may have completed or paused

### 📊 Data Status
- **MTG**: 53,482 files (210MB) in `data-full/games/magic/`
- **Pokemon**: 0 files (extraction paused)
- **Yu-Gi-Oh!**: 0 files (extraction paused)

---

## Quick Resume Script

```bash
#!/bin/bash
# Resume all paused processes
ps aux | grep -E "(limitless|ygoprodeck|enrich|label|s5cmd)" | grep -E "(STOP|T)" | awk '{print $2}' | xargs kill -CONT 2>/dev/null
echo "Resumed all paused processes"
```

---

## Next Steps (After Resuming)

1. **Resume extractions** (Pokemon and Yu-Gi-Oh!)
2. **Monitor progress**: `./check_extraction_progress.sh`
3. **Once complete**: Re-run multi-game export
4. **Train unified embeddings** on complete multi-game graph

---

**All processes paused. Sleep well! 🌙**

