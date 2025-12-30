#!/bin/bash
# Pause all machines and processes before going to bed

set -e

echo "🛑 Pausing all machines and processes..."
echo ""

# 1. Stop AWS EC2 instances
echo "📦 Checking AWS EC2 instances..."
INSTANCES=$(aws ec2 describe-instances \
    --filters "Name=instance-state-name,Values=running" \
    --query 'Reservations[*].Instances[*].InstanceId' \
    --output text 2>/dev/null || echo "")

if [ -n "$INSTANCES" ]; then
    echo "Found running instances:"
    for INSTANCE in $INSTANCES; do
        echo "  - $INSTANCE"
        # Stop (not terminate) so we can resume later
        aws ec2 stop-instances --instance-ids "$INSTANCE" > /dev/null 2>&1 || \
        echo "    ⚠️  Could not stop $INSTANCE (may need terminate instead)"
    done
    echo "✅ AWS instances stopped (can resume later)"
else
    echo "  No running instances found"
fi

# 2. Pause local background processes
echo ""
echo "🔄 Checking local background processes..."

# Find Python processes related to our scripts
PYTHON_PROCS=$(ps aux | grep -E "(enrich_attributes_with_scryfall_optimized|generate_labels_for_new_queries_optimized|export-multi-game-graph)" | grep -v grep | awk '{print $2}' || echo "")

if [ -n "$PYTHON_PROCS" ]; then
    echo "Found background processes:"
    for PID in $PYTHON_PROCS; do
        PROC_INFO=$(ps -p "$PID" -o command= 2>/dev/null || echo "")
        if [ -n "$PROC_INFO" ]; then
            echo "  - PID $PID: $(echo "$PROC_INFO" | cut -c1-60)..."
            # Send SIGSTOP to pause (can resume with SIGCONT)
            kill -STOP "$PID" 2>/dev/null && echo "    ✅ Paused" || echo "    ⚠️  Could not pause"
        fi
    done
    echo "✅ Background processes paused (can resume with resume_all_machines.sh)"
else
    echo "  No background processes found"
fi

echo ""
echo "✅ All machines and processes paused!"
echo ""
echo "To resume later, run: ./resume_all_machines.sh"


