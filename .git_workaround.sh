#!/bin/bash
# Git workaround script for iCloud Drive issues
# Use this when git operations hang

set -e

echo "Git Workaround Script"
echo "===================="

# Kill any hanging git processes
echo "1. Killing hanging git processes..."
pkill -9 git || true
sleep 2

# Remove lock files
echo "2. Removing lock files..."
rm -f .git/index.lock
rm -f .git/*.lock

# Configure git to skip untracked files
echo "3. Configuring git..."
git config status.showUntrackedFiles no

# Add files in batches (smaller operations)
echo "4. Adding files in batches..."

# Analysis tools
git add src/ml/analysis/ 2>&1 || echo "Analysis tools add failed"
sleep 1

# Similarity improvements
git add src/ml/similarity/text_embeddings.py 2>&1 || echo "Text embeddings add failed"
git add src/ml/similarity/fusion_integration.py 2>&1 || echo "Fusion integration add failed"
git add src/ml/similarity/format_aware_similarity.py 2>&1 || echo "Format aware add failed"
sleep 1

# Deck building improvements
git add src/ml/deck_building/beam_search.py 2>&1 || echo "Beam search add failed"
sleep 1

# Utils
git add src/ml/utils/evaluation_with_ci.py 2>&1 || echo "Evaluation CI add failed"
sleep 1

# Tests
git add src/ml/tests/test_text_embeddings.py 2>&1 || echo "Tests add failed"
sleep 1

# Documentation (in batches)
git add *METHODOLOGY*.md *ANALYSIS*.md *FINDINGS*.md 2>&1 || echo "Methodology docs add failed"
sleep 1

git add SOTA_*.md RESEARCH_*.md DATA_*.md 2>&1 || echo "Research docs add failed"
sleep 1

git add CRITICAL_*.md TARGETED_*.md INTEGRATION_*.md 2>&1 || echo "Action plan docs add failed"
sleep 1

git add COMMIT_*.md IMPLEMENTATION_*.md README_IMPROVEMENTS.md 2>&1 || echo "Status docs add failed"
sleep 1

# Check status
echo "5. Checking status..."
git status -uno 2>&1 | head -20 || echo "Status check failed"

echo ""
echo "Done! If successful, you can now commit and push."
echo "If operations still hang, try moving repo outside iCloud Drive."







