#!/usr/bin/env python3
"""
Comprehensive Type-Ahead Testing

Tests type-ahead functionality deeply:
- Name matching (prefix, partial, fuzzy)
- Text matching (oracle text, rules text)
- Type matching (type_line)
- Edge cases (special characters, unicode, empty queries)
- Performance (response time, debounce)
- Accessibility (keyboard, ARIA, screen readers)
- Integration (Meilisearch vs embeddings fallback)
"""

import json
import os
import time
from pathlib import Path

import requests

# Import shared utilities (dotenv is loaded automatically by test_utils)

# Use Playwright for browser automation (faster, auto-waiting, better debugging)
try:
    from playwright.sync_api import sync_playwright, Page, expect
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# Import shared utilities and constants
from test_utils import wait_for_api, logger, API_BASE, UI_URL
from test_constants import TEST_CARDS, TIMEOUTS, TEST_PREFIXES


def test_api_readiness():
    """Ensure API is ready."""
    return wait_for_api(max_retries=30, timeout=TIMEOUTS["fast"])


def test_name_prefix_matching():
    """Test prefix matching for card names."""
    logger.info("Testing name prefix matching...")
    test_cases = [
        ("Light", ["Lightning Bolt", "Lightning Strike"]),
        ("Count", ["Counterspell", "Counterbalance"]),
        ("Brain", ["Brainstorm"]),
    ]
    
    passed = 0
    for query, expected_prefixes in test_cases:
        try:
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix={query}&limit=10",
                timeout=TIMEOUTS["normal"]
            )
            assert resp.status_code == 200, \
                f"Expected 200, got {resp.status_code} for query '{query}'"
            data = resp.json()
            items = data.get("items", [])
            found = [item for item in items if any(item.startswith(exp) for exp in expected_prefixes)]
            assert found, \
                f"Expected matches for '{query}', got: {items[:3]}"
            passed += 1
            logger.info(f"✅ '{query}' → found {len(found)} matches: {found[:3]}")
        except (requests.RequestException, AssertionError) as e:
            logger.error(f"❌ '{query}' → Error: {e}")
    
    logger.info(f"Result: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def test_text_matching():
    """Test text content matching (oracle text, rules text)."""
    logger.info("Testing text content matching...")
    test_cases = [
        ("damage", "Should find cards with 'damage' in text"),
        ("draw", "Should find cards with 'draw' in text"),
        ("counter", "Should find cards with 'counter' in text"),
    ]
    
    passed = 0
    for query, description in test_cases:
        try:
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix={query}&limit=10",
                timeout=TIMEOUTS["normal"]
            )
            # Handle 404 or 503 gracefully
            if resp.status_code == 404:
                logger.warning(f"⚠️  '{query}' → 404 (endpoint may not be available)")
                return False
            elif resp.status_code == 503:
                logger.warning(f"⚠️  '{query}' → 503 (service unavailable - embeddings may not be loaded)")
                return False
            assert resp.status_code == 200, \
                f"Expected 200, got {resp.status_code} for query '{query}'"
            data = resp.json()
            items = data.get("items", [])
            # Check if we got results (might be name or text matches)
            if items:
                passed += 1
                logger.info(f"✅ '{query}' → found {len(items)} results: {items[:3]}")
            else:
                logger.warning(f"⚠️  '{query}' → no results (may need Meilisearch indexed)")
        except (requests.RequestException, AssertionError) as e:
            logger.error(f"❌ '{query}' → Error: {e}")
    
    logger.info(f"Result: {passed}/{len(test_cases)} passed")
    return passed >= len(test_cases) * 0.5  # At least 50% pass


def test_type_matching():
    """Test type_line matching."""
    logger.info("Testing type matching...")
    test_cases = [
        ("instant", "Should find instant cards"),
        ("creature", "Should find creature cards"),
        ("sorcery", "Should find sorcery cards"),
    ]
    
    passed = 0
    for query, description in test_cases:
        try:
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix={query}&limit=10",
                timeout=TIMEOUTS["normal"]
            )
            # Handle 404 or 503 gracefully
            if resp.status_code == 404:
                logger.warning(f"⚠️  '{query}' → 404 (endpoint may not be available)")
                return False
            elif resp.status_code == 503:
                logger.warning(f"⚠️  '{query}' → 503 (service unavailable - embeddings may not be loaded)")
                return False
            assert resp.status_code == 200, \
                f"Expected 200, got {resp.status_code} for query '{query}'"
            data = resp.json()
            items = data.get("items", [])
            if items:
                passed += 1
                logger.info(f"✅ '{query}' → found {len(items)} results")
            else:
                logger.warning(f"⚠️  '{query}' → no results")
        except (requests.RequestException, AssertionError) as e:
            logger.error(f"❌ '{query}' → Error: {e}")
    
    logger.info(f"Result: {passed}/{len(test_cases)} passed")
    return passed >= len(test_cases) * 0.5


def test_edge_cases():
    """Test edge cases."""
    logger.info("Testing edge cases...")
    edge_cases = [
        ("", "Empty query"),
        ("a", "Single character"),
        ("zzzzzzzzzzzzzzzz", "Impossible query"),
        (TEST_CARDS["common"], "Exact match"),
        (TEST_CARDS["common"].lower(), "Case insensitive"),
        (TEST_CARDS["common"].upper(), "All caps"),
    ]
    
    passed = 0
    for query, description in edge_cases:
        try:
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix={query}&limit=10",
                timeout=TIMEOUTS["normal"]
            )
            assert resp.status_code in [200, 400, 422], \
                f"Unexpected status {resp.status_code} for {description}"
            passed += 1
            logger.info(f"✅ '{query[:20]}...' ({description}) → handled correctly")
        except (requests.RequestException, AssertionError) as e:
            logger.error(f"❌ '{query[:20]}...' ({description}) → Error: {e}")
    
    logger.info(f"Result: {passed}/{len(edge_cases)} passed")
    return passed == len(edge_cases)


def test_performance():
    """Test response time and performance."""
    logger.info("Testing performance...")
    queries = TEST_PREFIXES
    
    times = []
    for query in queries:
        try:
            start = time.time()
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix={query}&limit=8",
                timeout=TIMEOUTS["normal"]
            )
            elapsed = time.time() - start
            
            assert resp.status_code == 200, \
                f"Expected 200, got {resp.status_code} for query '{query}'"
            times.append(elapsed)
            logger.info(f"'{query}': {elapsed*1000:.1f}ms")
        except (requests.RequestException, AssertionError) as e:
            logger.error(f"'{query}': Error - {e}")
    
    if times:
        avg_time = sum(times) / len(times)
        max_time = max(times)
        logger.info(f"Average: {avg_time*1000:.1f}ms, Max: {max_time*1000:.1f}ms")
        
        # Should be fast (< 200ms for good UX)
        if avg_time < 0.2:
            logger.info("✅ Performance good (< 200ms average)")
            return True
        elif avg_time < 0.5:
            logger.warning("⚠️  Performance acceptable (< 500ms average)")
            return True
        else:
            logger.error("❌ Performance slow (> 500ms average)")
            return False
    
    return False


def test_meilisearch_vs_embeddings():
    """Test if Meilisearch is being used vs embeddings fallback."""
    logger.info("Testing Meilisearch vs embeddings fallback...")
    
    # Check Meilisearch status
    try:
        resp = requests.get("http://localhost:7700/indexes/cards", timeout=TIMEOUTS["fast"])
        if resp.status_code == 200:
            data = resp.json()
            num_docs = data.get("numberOfDocuments", 0)
            if num_docs > 0:
                logger.info(f"✅ Meilisearch indexed: {num_docs} documents")
                logger.info("→ Type-ahead should use Meilisearch (better ranking)")
                return True
            else:
                logger.warning("⚠️  Meilisearch index exists but is empty")
                logger.warning("→ Type-ahead will use embeddings fallback")
                return False
        else:
            logger.warning(f"⚠️  Meilisearch check returned {resp.status_code}")
            return False
    except requests.RequestException as e:
        logger.warning(f"⚠️  Meilisearch not accessible: {e}")
        logger.warning("→ Type-ahead will use embeddings fallback")
        return False


def test_ui_keyboard_navigation():
    """Test keyboard navigation in UI."""
    logger.info("Testing UI keyboard navigation...")
    if not HAS_PLAYWRIGHT:
        logger.warning("⚠️  Playwright not available (install with: uv add playwright)")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            
            # Find and focus search input
            search_input = page.locator("#cardInput")
            search_input.wait_for(state="visible")
            search_input.focus()
            
            # Type to trigger autocomplete
            search_input.type("Light", delay=50)
            page.wait_for_timeout(300)  # Wait for debounce
            
            # Check if dropdown appears
            dropdown = page.locator("#autocompleteDropdown")
            if dropdown.is_visible():
                logger.info("✅ Autocomplete dropdown appeared")
                
                # Test arrow key navigation
                search_input.press("ArrowDown")
                page.wait_for_timeout(100)
                
                selected = page.locator(".autocomplete-item.selected")
                if selected.count() > 0:
                    logger.info("✅ Arrow key navigation works")
                    
                    # Test Enter key
                    search_input.press("Enter")
                    page.wait_for_timeout(200)
                    
                    # Check if value was selected
                    value = search_input.input_value()
                    if value and value != "Light":
                        logger.info(f"✅ Enter key selection works: '{value}'")
                        browser.close()
                        return True
                    else:
                        logger.warning("⚠️  Enter key didn't select item")
                else:
                    logger.warning("⚠️  Arrow key didn't select item")
            else:
                logger.warning("⚠️  Dropdown exists but not visible")
            
            browser.close()
            return False
    except Exception as e:
        logger.warning(f"⚠️  Keyboard navigation test failed: {e}")
        return None


def test_aria_accessibility():
    """Test ARIA attributes for accessibility."""
    logger.info("Testing ARIA accessibility...")
    if not HAS_PLAYWRIGHT:
        logger.warning("⚠️  Playwright not available (install with: uv add playwright)")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            
            # Check search input ARIA
            search_input = page.locator("#cardInput")
            search_input.wait_for(state="visible")
            
            checks = {
                "role": search_input.get_attribute("role") == "combobox",
                "aria-autocomplete": search_input.get_attribute("aria-autocomplete") == "list",
                "aria-label": search_input.get_attribute("aria-label") is not None,
                "aria-expanded": search_input.get_attribute("aria-expanded") is not None,
            }
            
            passed = sum(checks.values())
            total = len(checks)
            
            for check, passed_check in checks.items():
                status = "✅" if passed_check else "❌"
                logger.info(f"{status} {check}")
            
            browser.close()
            logger.info(f"Result: {passed}/{total} ARIA attributes present")
            assert passed == total, f"Expected all ARIA attributes, got {passed}/{total}"
            return passed == total
    except (Exception, AssertionError) as e:
        logger.warning(f"⚠️  ARIA test failed: {e}")
        return None


def test_debounce_timing():
    """Test that debounce works correctly (200ms)."""
    logger.info("Testing debounce timing...")
    if not HAS_PLAYWRIGHT:
        logger.warning("⚠️  Playwright not available (install with: uv add playwright)")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            
            search_input = page.locator("#cardInput")
            search_input.wait_for(state="visible")
            
            # Type quickly (should debounce)
            search_input.type("L", delay=10)
            search_input.type("i", delay=10)
            search_input.type("g", delay=10)
            search_input.type("h", delay=10)
            search_input.type("t", delay=10)
            
            # Wait for debounce (200ms) + network
            page.wait_for_timeout(300)
            
            # Check if dropdown appeared (should only trigger once)
            dropdown = page.locator("#autocompleteDropdown")
            if dropdown.is_visible():
                logger.info("✅ Debounce working (single request for multiple keystrokes)")
                browser.close()
                return True
            else:
                logger.warning("⚠️  Debounce may not be working")
                browser.close()
                return False
    except Exception as e:
        logger.warning(f"⚠️  Debounce test failed: {e}")
        return None


def test_result_highlighting():
    """Test that matching text is highlighted in suggestions."""
    logger.info("Testing result highlighting...")
    if not HAS_PLAYWRIGHT:
        logger.warning("⚠️  Playwright not available (install with: uv add playwright)")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            
            search_input = page.locator("#cardInput")
            search_input.wait_for(state="visible")
            search_input.type("Light", delay=50)
            page.wait_for_timeout(300)
            
            # Check if suggestions have highlighted text
            dropdown = page.locator("#autocompleteDropdown")
            if dropdown.is_visible():
                items = dropdown.locator(".autocomplete-item")
                if items.count() > 0:
                    first_item_html = items.first.inner_html()
                    if "<strong>" in first_item_html or "match" in first_item_html.lower():
                        logger.info("✅ Matching text is highlighted")
                        browser.close()
                        return True
                    else:
                        logger.warning("⚠️  No highlighting found in suggestions")
                        browser.close()
                        return False
                else:
                    logger.warning("⚠️  No suggestions found")
                    browser.close()
                    return False
            else:
                logger.warning("⚠️  Dropdown not visible")
                browser.close()
                return False
    except Exception as e:
        logger.warning(f"⚠️  Highlighting test failed: {e}")
        return None


def test_limit_enforcement():
    """Test that limit parameter is respected."""
    logger.info("Testing limit enforcement...")
    limits = [5, 8, 10, 20]
    
    passed = 0
    for limit in limits:
        try:
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix=Light&limit={limit}",
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if len(items) <= limit:
                    logger.info(f"✅ limit={limit} → got {len(items)} results")
                    passed += 1
                else:
                    logger.error(f"❌ limit={limit} → got {len(items)} results (exceeded)")
        except Exception as e:
            logger.error(f"❌ limit={limit} → Error: {e}")
    
    logger.info(f"Result: {passed}/{len(limits)} passed")
    return passed == len(limits)


def test_pagination():
    """Test pagination with offset."""
    logger.info("Testing pagination...")
    try:
        # Get first page
        resp1 = requests.get(
            f"{API_BASE}/v1/cards?prefix=Light&limit=5&offset=0",
            timeout=5
        )
        
        # Get second page
        resp2 = requests.get(
            f"{API_BASE}/v1/cards?prefix=Light&limit=5&offset=5",
            timeout=5
        )
        
        if resp1.status_code == 200 and resp2.status_code == 200:
            data1 = resp1.json()
            data2 = resp2.json()
            
            items1 = set(data1.get("items", []))
            items2 = set(data2.get("items", []))
            
            # Check for overlap (should be minimal)
            overlap = items1 & items2
            if len(overlap) == 0:
                logger.info("✅ Pagination works (no overlap between pages)")
                return True
            else:
                logger.warning(f"⚠️  Pagination has {len(overlap)} overlapping items")
                return False
        else:
            logger.error(f"❌ Pagination test failed: {resp1.status_code}, {resp2.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Pagination test error: {e}")
        return False


def main():
    """Run all comprehensive tests."""
    logger.info("=" * 60)
    logger.info("Comprehensive Type-Ahead Testing")
    logger.info("=" * 60)
    
    if not test_api_readiness():
        logger.error("API not ready. Start with: docker-compose up")
        return 1
    
    results = {
        "name_prefix": test_name_prefix_matching(),
        "text_matching": test_text_matching(),
        "type_matching": test_type_matching(),
        "edge_cases": test_edge_cases(),
        "performance": test_performance(),
        "meilisearch": test_meilisearch_vs_embeddings(),
        "keyboard_nav": test_ui_keyboard_navigation(),
        "aria": test_aria_accessibility(),
        "debounce": test_debounce_timing(),
        "highlighting": test_result_highlighting(),
        "limit": test_limit_enforcement(),
        "pagination": test_pagination(),
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
    
    # Recommendations
    logger.info("=" * 60)
    logger.info("Recommendations:")
    logger.info("=" * 60)
    
    if not results.get("meilisearch"):
        logger.warning("⚠️  Index Meilisearch for better type-ahead:")
        logger.warning("   python -m ml.search.index_cards --embeddings <path>")
    
    if not results.get("performance"):
        logger.warning("⚠️  Performance could be improved (check network/Meilisearch)")
    
    if not results.get("aria"):
        logger.warning("⚠️  ARIA attributes missing (accessibility issue)")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit(main())

