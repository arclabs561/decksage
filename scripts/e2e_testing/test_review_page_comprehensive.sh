#!/bin/bash
# Comprehensive E2E test for review page with visual AI testing

set -euo pipefail

echo "=========================================="
echo "Review Page Comprehensive E2E Test"
echo "=========================================="
echo ""

# Check prerequisites
echo "🔍 Checking prerequisites..."

# Check Playwright
if python3 -c "import playwright" 2>/dev/null; then
    echo "✅ Playwright installed"
else
    echo "❌ Playwright not installed"
    echo "   Installing..."
    uv add playwright || pip install playwright
    playwright install chromium
fi

# Check API
API_BASE="${API_BASE:-http://localhost:8000}"
if curl -s "${API_BASE}/ready" > /dev/null 2>&1; then
    echo "✅ API is live"
else
    echo "❌ API not running"
    echo "   Start with: ./scripts/start_api.sh"
    exit 1
fi

# Check AI visual test (optional)
if npx --yes @arclabs561/ai-visual-test --help > /dev/null 2>&1; then
    echo "✅ AI visual test available"
    HAS_VISUAL=true
else
    echo "⚠️  AI visual test not available (optional)"
    echo "   Install with: npm install -g @arclabs561/ai-visual-test"
    HAS_VISUAL=false
fi

echo ""
echo "🚀 Running tests..."
echo "=========================================="
echo ""

# Run regular e2e tests
echo "1. Running standard E2E tests..."
python3 scripts/e2e_testing/test_review_page.py
REGULAR_EXIT=$?

echo ""
echo "2. Running E2E tests with visual AI validation..."
if [ "$HAS_VISUAL" = true ]; then
    python3 scripts/e2e_testing/test_review_page_visual.py
    VISUAL_EXIT=$?
else
    echo "⚠️  Skipping visual tests (not installed)"
    VISUAL_EXIT=0
fi

echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo "Regular E2E: $([ $REGULAR_EXIT -eq 0 ] && echo '✅ PASSED' || echo '❌ FAILED')"
echo "Visual E2E:  $([ $VISUAL_EXIT -eq 0 ] && echo '✅ PASSED' || echo '❌ FAILED')"
echo ""

if [ $REGULAR_EXIT -eq 0 ] && [ $VISUAL_EXIT -eq 0 ]; then
    echo "✅ All tests passed!"
    exit 0
else
    echo "❌ Some tests failed"
    exit 1
fi

