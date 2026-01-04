#!/bin/bash
# Apply GitHub repository metadata recommendations (revised)
# Usage: ./apply_metadata.sh

set -euo pipefail

DESCRIPTION="ML-powered card recommendations for trading card games: budget substitutions, deck completion, and similarity search using graph neural networks and tournament deck co-occurrence analysis"

TOPICS=(
  "python"
  "machine-learning"
  "recommendation-system"
  "graph-neural-networks"
  "trading-card-games"
  "deck-building"
  "card-game"
  "embeddings"
  "node2vec"
  "similarity-search"
)

echo "Applying GitHub repository metadata (revised recommendations)..."
echo ""
echo "Description: $DESCRIPTION"
echo ""
echo "Topics (10):"
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
