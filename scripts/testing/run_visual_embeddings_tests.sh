#!/bin/bash
# Run all visual embeddings tests

set -euo pipefail

echo "=========================================="
echo "Visual Embeddings Test Suite"
echo "=========================================="
echo ""

# Test 1: Integration tests
echo "1. Integration Tests"
echo "-----------------------------------"
python3 scripts/testing/test_visual_embeddings_integration.py || true
echo ""

# Test 2: Usage tests
echo "2. Usage Tests"
echo "-----------------------------------"
python3 scripts/testing/test_visual_embeddings_usage.py || true
echo ""

# Test 3: Unit tests (pytest)
echo "3. Unit Tests (pytest)"
echo "-----------------------------------"
python3 -m pytest src/ml/tests/test_visual_embeddings.py -v || true
echo ""

# Test 4: Fusion integration tests (pytest)
echo "4. Fusion Integration Tests (pytest)"
echo "-----------------------------------"
python3 -m pytest src/ml/tests/test_fusion_with_visual.py -v || true
echo ""

# Test 5: Full integration tests (pytest)
echo "5. Full Integration Tests (pytest)"
echo "-----------------------------------"
python3 -m pytest src/ml/tests/test_visual_embeddings_integration.py -v || true
echo ""

echo "=========================================="
echo "Test Suite Complete"
echo "=========================================="

