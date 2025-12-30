#!/bin/bash
echo "=== Simple Harmonization Test ==="
echo ""
echo "1. Go compiles..."
cd src/backend && go build ./games/... && echo "✅ Go types compile" || exit 1

echo "2. Export tool has new fields..."
grep -q "Player.*string" cmd/export-hetero/main.go && echo "✅ Export has Player field" || exit 1
grep -q "Source.*string" cmd/export-hetero/main.go && echo "✅ Export has Source field" || exit 1

echo "3. Python utilities have filtering..."
cd ../ml
grep -q "def load_tournament_decks" utils/data_loading.py && echo "✅ Python has load_tournament_decks()" || exit 1
grep -q "def group_by_source" utils/data_loading.py && echo "✅ Python has group_by_source()" || exit 1

echo "4. Tests pass..."
uv run pytest tests/ -q && echo "✅ All Python tests pass" || exit 1

echo "5. Analysis tools work..."
uv run python archetype_staples.py 2>&1 | grep -q "Analyzing" && echo "✅ archetype_staples works" || exit 1

echo "6. Experiment suite runs..."
uv run python run_experiment_suite.py 2>&1 | grep -q "SUITE SUMMARY" && echo "✅ Suite orchestration works" || exit 1

echo ""
echo "✅ ALL HARMONIZATION CHECKS PASS"
