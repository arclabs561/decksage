#!/bin/bash
# Resume all machines and processes

set -e

echo "▶️  Resuming all machines and processes..."
echo ""

# 1. Start AWS EC2 instances
echo "📦 Checking stopped AWS EC2 instances..."
INSTANCES=$(aws ec2 describe-instances \
    --filters "Name=instance-state-name,Values=stopped" \
    --query 'Reservations[*].Instances[*].InstanceId' \
    --output text 2>/dev/null || echo "")

if [ -n "$INSTANCES" ]; then
    echo "Found stopped instances:"
    for INSTANCE in $INSTANCES; do
        echo "  - $INSTANCE"
        aws ec2 start-instances --instance-ids "$INSTANCE" > /dev/null 2>&1 && \
        echo "    ✅ Starting..." || \
        echo "    ⚠️  Could not start $INSTANCE"
    done
    echo "✅ AWS instances starting"
else
    echo "  No stopped instances found"
fi

# 2. Resume local background processes
echo ""
echo "🔄 Resuming local background processes..."

# Find stopped Python processes
PYTHON_PROCS=$(ps aux | grep -E "(enrich_attributes_with_scryfall_optimized|generate_labels_for_new_queries_optimized|export-multi-game-graph)" | grep -v grep | awk '{print $2}' || echo "")

if [ -n "$PYTHON_PROCS" ]; then
    echo "Found paused processes:"
    for PID in $PYTHON_PROCS; do
        PROC_INFO=$(ps -p "$PID" -o command=,state= 2>/dev/null || echo "")
        if [ -n "$PROC_INFO" ]; then
            STATE=$(echo "$PROC_INFO" | awk '{print $NF}')
            if [ "$STATE" = "T" ]; then  # T = stopped
                echo "  - PID $PID: $(echo "$PROC_INFO" | cut -c1-60)..."
                kill -CONT "$PID" 2>/dev/null && echo "    ✅ Resumed" || echo "    ⚠️  Could not resume"
            fi
        fi
    done
    echo "✅ Background processes resumed"
else
    echo "  No paused processes found"
fi

echo ""
echo "✅ All machines and processes resumed!"


