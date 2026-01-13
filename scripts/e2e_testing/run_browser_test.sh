#!/bin/bash
# Run comprehensive browser E2E test with prerequisites check

set -euo pipefail

echo "=========================================="
echo "Comprehensive Browser E2E Test"
echo "=========================================="
echo ""

# Check Playwright
echo "🔍 Checking Playwright..."
if python3 -c "import playwright" 2>/dev/null; then
    echo "✅ Playwright installed"
else
    echo "❌ Playwright not installed"
    echo "   Installing..."
    uv add playwright
    playwright install chromium
fi

# Check API
echo ""
echo "🔍 Checking API..."
API_BASE="${API_BASE:-http://localhost:8000}"
if curl -s "${API_BASE}/live" > /dev/null 2>&1; then
    echo "✅ API is live"
else
    echo "❌ API not running"
    echo "   Start with: docker-compose up -d"
    exit 1
fi

# Check UI
echo ""
echo "🔍 Checking UI..."
UI_URL="${UI_URL:-http://localhost:8000}"
if curl -s "${UI_URL}/" > /dev/null 2>&1; then
    echo "✅ UI is accessible"
else
    echo "❌ UI not accessible"
    exit 1
fi

# Run test
echo ""
echo "🚀 Running comprehensive browser test..."
echo "=========================================="
python3 scripts/e2e_testing/test_browser_comprehensive.py
