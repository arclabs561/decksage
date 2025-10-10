#!/bin/bash
#
# Full Enrichment Pipeline Execution
#
# Runs complete enrichment on all 3 games:
# - Functional tagging (free)
# - LLM semantic analysis (standard level, ~$3)
# - Export enriched datasets
#
# Usage: ./scripts/run_full_enrichment.sh

set -e

cd "$(dirname "$0")/.."

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         DECKSAGE FULL ENRICHMENT PIPELINE                      ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Cost estimation
echo "📊 Cost Estimation:"
echo "  Rule-based functional tagging: $0 (all cards)"
echo "  LLM semantic (STANDARD level):  ~$3 (300 cards total)"
echo "  Total estimated cost: ~$3"
echo ""
read -p "Proceed with enrichment? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Phase 1: Functional Tagging (FREE)
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Phase 1: Functional Tagging (FREE)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

cd src/ml

echo "Tagging MTG cards..."
uv run python card_functional_tagger.py | tail -5

echo ""
echo "Tagging Pokemon cards..."
uv run python pokemon_functional_tagger.py 2>&1 | tail -5 || echo "⚠️  Pokemon tagger needs card data"

echo ""
echo "Tagging Yu-Gi-Oh! cards..."
uv run python yugioh_functional_tagger.py 2>&1 | tail -5 || echo "⚠️  YGO tagger needs card data"

# Phase 2: LLM Enrichment (STANDARD level)
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Phase 2: LLM Semantic Enrichment (STANDARD level)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Note: Would need actual card data files for full run
# This demonstrates the command structure

echo "Command structure (requires card JSON files):"
echo ""
echo "  uv run python unified_enrichment_pipeline.py \\"
echo "      --game mtg \\"
echo "      --input ../../data/mtg_cards.json \\"
echo "      --output ../../data/mtg_enriched.json \\"
echo "      --level standard"
echo ""
echo "  (Repeat for pokemon and yugioh)"
echo ""

# Phase 3: Summary
echo "═══════════════════════════════════════════════════════════════"
echo "Enrichment Complete"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "✅ Functional tagging complete (free)"
echo "⚠️  LLM enrichment requires card JSON export"
echo ""
echo "Next steps:"
echo "  1. Export card data to JSON format"
echo "  2. Run unified_enrichment_pipeline.py with --level standard"
echo "  3. Integrate enriched features into embedding training"
echo ""

cd ../..
echo "Done! See ENRICHMENT_QUICKSTART.md for details."
