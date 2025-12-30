#!/bin/bash
echo "Resuming all paused processes..."
ps aux | grep -E "(limitless|ygoprodeck|enrich|label|s5cmd)" | grep -E "(STOP|T)" | awk '{print $2}' | xargs kill -CONT 2>/dev/null
echo "✅ Resumed all paused processes"
echo ""
echo "Check status with:"
echo "  ./check_extraction_progress.sh"
