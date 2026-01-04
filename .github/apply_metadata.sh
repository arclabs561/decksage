#!/bin/bash
# Apply GitHub repository metadata recommendations
# Usage: ./apply_metadata.sh

set -euo pipefail

DESCRIPTION="Card similarity search using tournament deck co-occurrence, graph embeddings, and hybrid ML models for trading card games"

TOPICS=(
  "python"
  "go"
  "machine-learning"
  "graph-neural-networks"
  "embeddings"
  "trading-card-games"
  "deck-building"
  "similarity-search"
  "magic-the-gathering"
  "node2vec"
)

echo "Applying GitHub repository metadata..."
echo ""
echo "Description: $DESCRIPTION"
echo ""
echo "Topics:"
for topic in "${TOPICS[@]}"; do
  echo "  - $topic"
done
echo ""

# Check if gh CLI is available
if ! command -v gh &> /dev/null; then
  echo "Error: GitHub CLI (gh) is not installed"
  echo "Install: https://cli.github.com/"
  exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
  echo "Error: Not authenticated with GitHub CLI"
  echo "Run: gh auth login"
  exit 1
fi

# Apply description
echo "Setting description..."
gh repo edit --description "$DESCRIPTION"

# Apply topics
echo "Adding topics..."
gh repo edit --add-topic "${TOPICS[@]}"

echo ""
echo "✅ Metadata applied successfully!"
echo ""
echo "Verify with: gh repo view --json description,repositoryTopics"
