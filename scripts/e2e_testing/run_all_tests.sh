#!/bin/bash
# Run all comprehensive tests

set -euo pipefail

echo "=========================================="
echo "Running All Comprehensive Tests"
echo "=========================================="
echo ""

# Test 1: API Endpoints
echo "1. API Endpoints Comprehensive Tests"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_api_endpoints_comprehensive.py || true
echo ""

# Test 2: Type-ahead comprehensive
echo "2. Type-Ahead Comprehensive Tests"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_type_ahead_comprehensive.py || true
echo ""

# Test 3: Deep integration
echo "3. Deep Integration Tests"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_integration_deep.py || true
echo ""

# Test 4: Accessibility deep
echo "4. Deep Accessibility Tests"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_accessibility_deep.py || true
echo ""

# Test 5: Comprehensive UI
echo "5. Comprehensive UI Tests"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_comprehensive_ui.py || true
echo ""

# Test 6: Security
echo "6. Security Tests"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_security.py || true
echo ""

# Test 7: Performance
echo "7. Performance Tests"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_performance.py || true
echo ""

# Test 8: AI Visual Tests
echo "8. AI Visual Tests (using @arclabs561/ai-visual-test)"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_visual_ai.py || true
echo ""

# Test 9: Review Page E2E Tests
echo "9. Review Page E2E Tests"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_review_page.py || true
echo ""

# Test 10: Review Page Visual Tests
echo "10. Review Page Visual Tests (with AI validation)"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_review_page_visual.py || true
echo ""

# Test 11: Review Page MCP Browser Tests
echo "11. Review Page MCP Browser Tests (using MCP browser tools)"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_review_page_mcp.py || true
echo ""

# Test 12: All Pages Visual Tests (AI-powered)
echo "12. All Pages Visual Tests (AI-powered with @arclabs561/ai-visual-test)"
echo "-----------------------------------"
python3 scripts/e2e_testing/test_all_pages_visual.py || true
echo ""

echo "=========================================="
echo "All Tests Complete"
echo "=========================================="

