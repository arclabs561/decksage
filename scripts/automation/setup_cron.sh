#!/bin/bash
set -euo pipefail
# Setup cron jobs for automated training/evaluation
# 
# This sets up:
# - Daily updates (2 AM UTC)
# - Weekly retraining (Sunday 2 AM UTC)
# - Monthly full retrain (first Sunday of month, 2 AM UTC)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "======================================================================"
echo "SETTING UP AUTOMATED TRAINING/EVALUATION CRON JOBS"
echo "======================================================================"
echo ""

# Make scripts executable
chmod +x "$SCRIPT_DIR/daily_update.sh"
chmod +x "$SCRIPT_DIR/weekly_retrain.sh"

# Create cron entries
CRON_DAILY="0 2 * * * cd $PROJECT_ROOT && $SCRIPT_DIR/daily_update.sh >> $PROJECT_ROOT/logs/cron_daily.log 2>&1"
CRON_WEEKLY="0 2 * * 0 cd $PROJECT_ROOT && $SCRIPT_DIR/weekly_retrain.sh >> $PROJECT_ROOT/logs/cron_weekly.log 2>&1"

# Check if already in crontab
if crontab -l 2>/dev/null | grep -q "daily_update.sh"; then
 echo "Warning: Daily cron job already exists"
else
 (crontab -l 2>/dev/null; echo "$CRON_DAILY") | crontab -
 echo "✓ Added daily update cron job (2 AM UTC daily)"
fi

if crontab -l 2>/dev/null | grep -q "weekly_retrain.sh"; then
 echo "Warning: Weekly cron job already exists"
else
 (crontab -l 2>/dev/null; echo "$CRON_WEEKLY") | crontab -
 echo "✓ Added weekly retraining cron job (Sunday 2 AM UTC)"
fi

echo ""
echo "Current crontab:"
crontab -l | grep -E "(daily_update|weekly_retrain)" || echo " (none found)"
echo ""
echo "======================================================================"
echo "CRON SETUP COMPLETE"
echo "======================================================================"
echo ""
echo "To view logs:"
echo " tail -f $PROJECT_ROOT/logs/cron_daily.log"
echo " tail -f $PROJECT_ROOT/logs/cron_weekly.log"
echo ""
echo "To remove cron jobs:"
echo " crontab -e # Then delete the lines"

