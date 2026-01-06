#!/usr/bin/env python3
"""
Comprehensive API Endpoint Testing

Tests all API endpoints for completeness:
- Health and diagnostics
- Similarity search variants
- Card listing and autocomplete
- Contextual discovery
- Deck operations
- Feedback collection
- Error handling
"""

import json
import os
from pathlib import Path

import requests

# Import shared utilities (dotenv is loaded automatically by test_utils)

# Import shared utilities and constants
from test_utils import wait_for_api, logger, API_BASE
from test_constants import TEST_CARDS, TIMEOUTS


def test_api_readiness():
    """Ensure API is ready."""
    return wait_for_api(max_retries=30, timeout=TIMEOUTS["fast"])


def test_health_endpoints():
    """Test all health-related endpoints."""
    logger.info("Testing health endpoints...")
    
    checks = {}
    
    # /live
    try:
        resp = requests.get(f"{API_BASE}/live", timeout=TIMEOUTS["fast"])
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data.get("status") == "live", f"Expected 'live', got {data.get('status')}"
        checks["/live"] = True
        logger.info("✅ /live endpoint working")
    except (requests.RequestException, AssertionError) as e:
        checks["/live"] = False
        logger.error(f"❌ /live failed: {e}")
    
    # /ready
    try:
        resp = requests.get(f"{API_BASE}/ready", timeout=TIMEOUTS["fast"])
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data.get("status") == "ready", f"Expected 'ready', got {data.get('status')}"
        assert "available_methods" in data, "Missing 'available_methods' in response"
        checks["/ready"] = True
        methods = data.get("available_methods", [])
        logger.info(f"✅ /ready: methods={methods}")
    except (requests.RequestException, AssertionError) as e:
        checks["/ready"] = False
        logger.error(f"❌ /ready failed: {e}")
    
    # /v1/health
    try:
        resp = requests.get(f"{API_BASE}/v1/health", timeout=TIMEOUTS["fast"])
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "status" in data, "Missing 'status' in response"
        assert "num_cards" in data, "Missing 'num_cards' in response"
        checks["/v1/health"] = True
        logger.info("✅ /v1/health endpoint working")
    except (requests.RequestException, AssertionError) as e:
        checks["/v1/health"] = False
        logger.error(f"❌ /v1/health failed: {e}")
    
    passed = sum(checks.values())
    total = len(checks)
    logger.info(f"Result: {passed}/{total} health endpoints working")
    return passed == total


def test_diagnostics():
    """Test diagnostics endpoint."""
    logger.info("Testing diagnostics endpoint...")
    
    try:
        resp = requests.get(f"{API_BASE}/v1/diagnostics", timeout=TIMEOUTS["normal"])
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        
        # Check for expected fields
        expected_fields = ["embeddings", "graph_data", "card_attrs"]
        found = [f for f in expected_fields if f in data]
        
        assert len(found) > 0, f"Expected at least one field from {expected_fields}, found {found}"
        logger.info(f"✅ Diagnostics available: {', '.join(found)}")
        
        # Check asset versioning if available
        if "asset_metadata" in data:
            version = data['asset_metadata'].get('version', 'unknown')
            logger.info(f"✅ Asset versioning: {version}")
        
        return True
    except (requests.RequestException, AssertionError) as e:
        logger.error(f"❌ Diagnostics failed: {e}")
        return False


def test_similarity_variants():
    """Test all similarity search variants."""
    logger.info("Testing similarity search variants...")
    
    test_card = TEST_CARDS["common"]
    checks = {}
    
    # POST /v1/similar (default)
    try:
        resp = requests.post(
            f"{API_BASE}/v1/similar",
            json={"query": test_card, "top_k": 3},
            timeout=TIMEOUTS["slow"]
        )
        assert resp.status_code == 200, \
            f"Expected 200, got {resp.status_code} for POST /v1/similar"
        data = resp.json()
        assert "results" in data, "Response missing 'results' field"
        checks["POST /v1/similar"] = True
    except (requests.RequestException, AssertionError) as e:
        checks["POST /v1/similar"] = False
        logger.error(f"❌ POST /v1/similar failed: {e}")
    
    # GET /v1/cards/{name}/similar
    try:
        resp = requests.get(
            f"{API_BASE}/v1/cards/{test_card}/similar",
            params={"top_k": 3},
            timeout=TIMEOUTS["slow"]
        )
        assert resp.status_code == 200, \
            f"Expected 200, got {resp.status_code} for GET /v1/cards/{{name}}/similar"
        data = resp.json()
        assert "results" in data, "Response missing 'results' field"
        checks["GET /v1/cards/{name}/similar"] = True
    except (requests.RequestException, AssertionError) as e:
        checks["GET /v1/cards/{name}/similar"] = False
        logger.error(f"❌ GET /v1/cards/{{name}}/similar failed: {e}")
    
    # Different methods
    methods = ["embedding", "jaccard", "fusion"]
    for method in methods:
        try:
            resp = requests.post(
                f"{API_BASE}/v1/similar",
                json={"query": test_card, "top_k": 3, "mode": method},
                timeout=TIMEOUTS["very_slow"]
            )
            assert resp.status_code == 200, \
                f"Expected 200, got {resp.status_code} for method={method}"
            data = resp.json()
            method_used = data.get("model_info", {}).get("method_used", "")
            checks[f"method={method}"] = method in method_used.lower() or method_used == method
        except (requests.RequestException, AssertionError) as e:
            checks[f"method={method}"] = False
            logger.warning(f"⚠️  method={method} failed: {e}")
    
    passed = sum(checks.values())
    total = len(checks)
    logger.info(f"Result: {passed}/{total} similarity variants working")
    return passed >= total * 0.7  # At least 70%


def test_contextual_discovery():
    """Test contextual discovery endpoint."""
    logger.info("Testing contextual discovery...")
    
    test_card = TEST_CARDS["common"]
    
    try:
        resp = requests.get(
            f"{API_BASE}/v1/cards/{test_card}/contextual",
            timeout=TIMEOUTS["slow"]
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        has_synergies = "synergies" in data
        has_alternatives = "alternatives" in data
        has_upgrades = "upgrades" in data
        
        assert has_synergies or has_alternatives or has_upgrades, \
            "Expected at least one of: synergies, alternatives, upgrades"
        logger.info(f"✅ Contextual data: synergies={has_synergies}, alternatives={has_alternatives}, upgrades={has_upgrades}")
        return True
    except (requests.RequestException, AssertionError) as e:
        logger.warning(f"⚠️  Contextual discovery failed: {e}")
        return None  # Optional endpoint


def test_deck_operations():
    """Test deck-related endpoints."""
    logger.info("Testing deck operations...")
    
    # Test deck completion
    test_deck = [TEST_CARDS["common"], TEST_CARDS["instant"], TEST_CARDS["sorcery"]]
    checks = {}
    
    try:
        resp = requests.post(
            f"{API_BASE}/v1/deck/complete",
            json={"deck": test_deck, "target_size": 10},
            timeout=TIMEOUTS["very_slow"]
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "suggestions" in data or "results" in data, \
            "Missing 'suggestions' or 'results' in response"
        checks["deck/complete"] = True
        logger.info("✅ deck/complete working")
    except (requests.RequestException, AssertionError) as e:
        checks["deck/complete"] = False
        logger.warning(f"⚠️  deck/complete failed: {e}")
    
    # Test deck search (if available)
    try:
        resp = requests.post(
            f"{API_BASE}/v1/search",
            json={"query": TEST_CARDS["common"], "top_k": 5},
            timeout=TIMEOUTS["slow"]
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "results" in data or "items" in data, \
            "Missing 'results' or 'items' in response"
        checks["POST /v1/search"] = True
        logger.info("✅ POST /v1/search working")
    except (requests.RequestException, AssertionError) as e:
        checks["POST /v1/search"] = False
        logger.warning(f"⚠️  POST /v1/search failed: {e}")
    
    passed = sum(checks.values())
    total = len(checks)
    logger.info(f"Result: {passed}/{total} deck operations working")
    return passed > 0  # At least one should work


def test_feedback_endpoints():
    """Test feedback collection endpoints."""
    logger.info("Testing feedback endpoints...")
    
    checks = {}
    
    # Submit feedback
    try:
        resp = requests.post(
            f"{API_BASE}/v1/feedback",
            json={
                "query_card": TEST_CARDS["common"],
                "suggested_card": "Fireball",
                "task_type": "similarity",
                "rating": 4,
                "is_substitute": True,
                "session_id": "test_session"
            },
            timeout=TIMEOUTS["normal"]
        )
        assert resp.status_code in [200, 201], \
            f"Expected 200 or 201, got {resp.status_code}"
        checks["POST /v1/feedback"] = True
        logger.info("✅ POST /v1/feedback working")
    except (requests.RequestException, AssertionError) as e:
        checks["POST /v1/feedback"] = False
        logger.error(f"❌ POST /v1/feedback failed: {e}")
    
    # Get feedback stats
    try:
        resp = requests.get(f"{API_BASE}/v1/feedback/stats", timeout=TIMEOUTS["normal"])
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        checks["GET /v1/feedback/stats"] = True
        logger.info("✅ GET /v1/feedback/stats working")
    except (requests.RequestException, AssertionError) as e:
        checks["GET /v1/feedback/stats"] = False
        logger.warning(f"⚠️  GET /v1/feedback/stats failed: {e}")
    
    passed = sum(checks.values())
    total = len(checks)
    logger.info(f"Result: {passed}/{total} feedback endpoints working")
    return passed > 0


def test_error_responses():
    """Test error response handling."""
    logger.info("Testing error responses...")
    
    checks = {}
    
    # 404 for invalid card
    try:
        resp = requests.get(
            f"{API_BASE}/v1/cards/NonexistentCard12345/similar",
            timeout=TIMEOUTS["normal"]
        )
        assert resp.status_code == 404, \
            f"Expected 404 for invalid card, got {resp.status_code}"
        checks["404 invalid card"] = True
        logger.info("✅ 404 error handling correct")
    except (requests.RequestException, AssertionError) as e:
        checks["404 invalid card"] = False
        logger.warning(f"⚠️  404 test failed: {e}")
    
    # 422 for invalid parameters
    try:
        resp = requests.post(
            f"{API_BASE}/v1/similar",
            json={"query": TEST_CARDS["common"], "top_k": 0},  # Invalid: top_k must be >= 1
            timeout=TIMEOUTS["normal"]
        )
        assert resp.status_code == 422, \
            f"Expected 422 for invalid top_k, got {resp.status_code}"
        checks["422 invalid top_k"] = True
        logger.info("✅ 422 error handling correct")
    except (requests.RequestException, AssertionError) as e:
        checks["422 invalid top_k"] = False
        logger.warning(f"⚠️  422 test failed: {e}")
    
    # 400 for missing required fields
    try:
        resp = requests.post(
            f"{API_BASE}/v1/similar",
            json={},  # Missing required "query"
            timeout=TIMEOUTS["normal"]
        )
        assert resp.status_code == 400, \
            f"Expected 400 for missing query, got {resp.status_code}"
        checks["400 missing query"] = True
        logger.info("✅ 400 error handling correct")
    except (requests.RequestException, AssertionError) as e:
        checks["400 missing query"] = False
        logger.warning(f"⚠️  400 test failed: {e}")
    
    passed = sum(checks.values())
    total = len(checks)
    logger.info(f"Result: {passed}/{total} error responses correct")
    return passed == total


def main():
    """Run all API endpoint tests."""
    logger.info("=" * 60)
    logger.info("Comprehensive API Endpoint Testing")
    logger.info("=" * 60)
    
    if not test_api_readiness():
        logger.error("API not ready. Start with: docker-compose up")
        return 1
    
    results = {
        "health": test_health_endpoints(),
        "diagnostics": test_diagnostics(),
        "similarity": test_similarity_variants(),
        "contextual": test_contextual_discovery(),
        "deck_ops": test_deck_operations(),
        "feedback": test_feedback_endpoints(),
        "errors": test_error_responses(),
    }
    
    logger.info("=" * 60)
    logger.info("Test Results Summary:")
    logger.info("=" * 60)
    for test, result in results.items():
        if result is None:
            status = "⚠️"
        elif result:
            status = "✅"
        else:
            status = "❌"
        logger.info(f"{status} {test}")
    
    passed = sum(1 for r in results.values() if r is True)
    total = sum(1 for r in results.values() if r is not None)
    skipped = sum(1 for r in results.values() if r is None)
    
    logger.info(f"Passed: {passed}/{total} (skipped: {skipped})")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit(main())

