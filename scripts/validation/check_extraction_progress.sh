#!/bin/bash
# Check extraction progress for all games

set -euo pipefail

echo "=== Multi-Game Extraction Progress ==="
echo ""
echo "Pokemon:"
find data-full/games/pokemon -name "*.zst" 2>/dev/null | wc -l | awk '{printf "  %d files extracted\n", $1}'
du -sh data-full/games/pokemon 2>/dev/null | awk '{printf "  %s total size\n", $1}'
echo ""
echo "Yu-Gi-Oh!:"
find data-full/games/yugioh -name "*.zst" 2>/dev/null | wc -l | awk '{printf "  %d files extracted\n", $1}'
du -sh data-full/games/yugioh 2>/dev/null | awk '{printf "  %s total size\n", $1}'
echo ""
echo "Processes:"
ps aux | grep -E "(limitless|ygoprodeck)" | grep -v grep | wc -l | awk '{printf "  %d extraction processes running\n", $1}'
echo ""
echo "All Games:"
du -sh data-full/games/* 2>/dev/null | sort
