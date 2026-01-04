#!/bin/bash
#
# clean-docs.sh - Archive session documentation to prevent sprawl
#
# Usage: ./scripts/clean-docs.sh [date]
# Example: ./scripts/clean-docs.sh 2025-10-05

set -euo pipefail

# Get date parameter or use today
SESSION_DATE=${1:-$(date +%Y-%m-%d)}
ARCHIVE_DIR="archive/${SESSION_DATE}-session"

# Common patterns that indicate session/analysis docs
PATTERNS=(
    "*_COMPLETE*.md"
    "*_FINAL*.md"
    "*_SUMMARY*.md"
    "*_ANALYSIS*.md"
    "*_REVIEW*.md"
    "*_AUDIT*.md"
    "*_STATUS*.md"
    "*_MANIFEST*.md"
    "EVERYTHING_*.md"
    "ALL_*.md"
    "SESSION_*.md"
    "SESSION_*.txt"
    "WORK_*.txt"
)

# Count files to be moved
count=0
for pattern in "${PATTERNS[@]}"; do
    count=$((count + $(ls $pattern 2>/dev/null | wc -l)))
done

if [ $count -eq 0 ]; then
    echo "No session documents to clean up!"
    exit 0
fi

echo "Found $count session documents to archive"
echo "Creating archive: $ARCHIVE_DIR"

# Create archive directory
mkdir -p "$ARCHIVE_DIR"

# Move files
for pattern in "${PATTERNS[@]}"; do
    if ls $pattern 1> /dev/null 2>&1; then
        mv $pattern "$ARCHIVE_DIR/" 2>/dev/null || true
    fi
done

echo "Moved $count files to $ARCHIVE_DIR"
echo ""
echo "Remaining root-level docs:"
ls -1 *.md 2>/dev/null | grep -v README.md | head -10 || echo "  Just README.md and essential docs!"

# Check if we should remind about .doc-guard
if [ ! -f .doc-guard ]; then
    echo ""
    echo "Tip: Consider reading .doc-guard for documentation principles"
fi
