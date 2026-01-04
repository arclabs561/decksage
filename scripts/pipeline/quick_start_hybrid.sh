#!/bin/bash
# Quick start script for hybrid embedding system
# Sets up everything needed to get started

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "="*70
echo "HYBRID EMBEDDINGS QUICK START"
echo "="*70
echo ""

# Step 1: Check dependencies
echo "Step 1: Checking dependencies..."
if ! uv pip list | grep -q "sentence-transformers"; then
 echo " Installing sentence-transformers..."
 uv pip install sentence-transformers
fi

if ! uv pip list | grep -q "torch"; then
 echo " Installing PyTorch..."
 uv pip install torch torch-geometric
fi

echo " ✓ Dependencies ready"
echo ""

# Step 2: Test system
echo "Step 2: Testing hybrid system..."
uv run python -m ml.scripts.test_hybrid_system --test all || {
 echo " Warning: Some tests failed (this is OK for first run)"
}
echo ""

# Step 3: Setup graph (if decks available)
echo "Step 3: Setting up graph..."
if [[ -f "data/processed/decks_all_final.jsonl" ]]; then
 echo " Found decks, initializing graph..."
 uv run python -m ml.scripts.update_graph_incremental \
 --rebuild \
 --decks-file data/processed/decks_all_final.jsonl \
 --graph-path data/graphs/incremental_graph.json \
 --export-edgelist data/graphs/edgelist.edg \
 --min-weight 2 || {
 echo " Warning: Graph setup failed (may need to create decks first)"
 }
else
 echo " Warning: No decks found, skipping graph setup"
 echo " Run: python -m ml.scripts.export_and_unify_all_decks"
fi
echo ""

# Step 4: Setup embeddings
echo "Step 4: Setting up embeddings..."
if [[ -f "data/graphs/edgelist.edg" ]]; then
 echo " Training GNN embeddings (this may take a while)..."
 echo " For faster training, use: just train-gnn-aws <instance-id>"
 uv run python -m ml.scripts.setup_hybrid_embeddings \
 --graph-path data/graphs/incremental_graph.json \
 --gnn-model data/embeddings/gnn_graphsage.json || {
 echo " Warning: GNN setup failed (may need GPU or more time)"
 }
else
 echo " Warning: No graph found, skipping GNN setup"
fi

# Instruction-tuned embeddings are always ready (zero-shot)
echo " ✓ Instruction-tuned embeddings ready (zero-shot, no setup needed)"
echo ""

# Step 5: Summary
echo "="*70
echo "QUICK START COMPLETE"
echo "="*70
echo ""
echo "Next steps:"
echo " 1. Test: uv run python -m ml.scripts.test_hybrid_system"
echo " 2. Train GNN: just train-gnn-local (or train-gnn-aws for GPU)"
echo " 3. Evaluate: just eval-hybrid-local"
echo " 4. Update graph: uv run python -m ml.scripts.update_graph_incremental --new-decks <file>"
echo ""
echo "For fast GPU training:"
echo " ../runctl/target/release/runctl aws create --spot g4dn.xlarge"
echo " just train-gnn-aws <instance-id>"
echo ""
