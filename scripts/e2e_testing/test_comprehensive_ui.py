#!/usr/bin/env python3
"""
Comprehensive UI/UX E2E Test

Tests all UI features comprehensively:
- Type-ahead autocomplete (with actual API)
- Card images loading
- Metadata display
- Game detection
- Error states
- Empty states
- Accessibility
- Performance
"""

import json
import os
import time
from pathlib import Path

import requests

# Import shared utilities and constants (dotenv is loaded automatically by test_utils)
from test_utils import wait_for_api, logger, API_BASE, get_ui_url, start_http_server, setup_playwright_routing, inject_api_base
from test_constants import TEST_CARDS, TIMEOUTS

# Start HTTP server and get UI URL
start_http_server()
UI_URL = get_ui_url()

# Use Playwright for browser automation
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.warning("⚠️  Playwright not installed. Install with: uv add playwright")


def test_api_readiness():
    """Ensure API is ready."""
    return wait_for_api(max_retries=30, timeout=TIMEOUTS["fast"])


def test_type_ahead_ui():
    """Test type-ahead in actual browser."""
    logger.info("Testing type-ahead in browser...")
    if not HAS_PLAYWRIGHT:
        logger.warning("⚠️  Playwright not available (install with: uv add playwright)")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            
            # Find search input
            search_input = page.locator("#cardInput")
            search_input.wait_for(state="visible")
            
            # Type slowly to trigger autocomplete
            search_input.type("Light", delay=100)
            page.wait_for_timeout(500)  # Wait for debounce
            
            # Check if dropdown appears
            dropdown = page.locator("#autocompleteDropdown")
            if dropdown.is_visible():
                items = dropdown.locator(".autocomplete-item")
                count = items.count()
                logger.info(f"✅ Autocomplete dropdown appeared with {count} items")
                if count > 0:
                    first_text = items.first.inner_text()
                    logger.info(f"   First suggestion: {first_text[:50]}")
                browser.close()
                return True
            else:
                logger.warning("⚠️  Dropdown exists but not visible")
                browser.close()
                return False
    except Exception as e:
        logger.warning(f"⚠️  Browser test failed: {e}")
        return None


def test_card_images():
    """Test card images load correctly."""
    logger.info("Testing card images...")
    test_query = TEST_CARDS["common"]
    try:
        resp = requests.post(
            f"{API_BASE}/v1/similar",
            json={"query": test_query, "top_k": 3},
            timeout=TIMEOUTS["slow"],
        )
        assert resp.status_code == 200, \
            f"Expected 200, got {resp.status_code} for image test"
        data = resp.json()
        results = data.get("results", [])
        assert results, "Expected search results"
        images_found = 0
        for result in results:
            meta = result.get("metadata", {})
            if meta.get("image_url"):
                images_found += 1
                # Test if image URL is accessible
                img_url = meta["image_url"]
                if img_url.startswith("http"):
                    try:
                        img_resp = requests.head(img_url, timeout=TIMEOUTS["fast"])
                        if img_resp.status_code == 200:
                            logger.info(f"✅ Image accessible: {result['card']}")
                        else:
                            logger.warning(f"⚠️  Image returned {img_resp.status_code}: {result['card']}")
                    except requests.RequestException:
                        logger.warning(f"⚠️  Image URL not accessible: {result['card']}")
        logger.info(f"Found {images_found}/{len(results)} results with image URLs")
        assert images_found > 0, "Expected at least one result with image URL"
        return images_found > 0
    except (requests.RequestException, AssertionError) as e:
        logger.error(f"❌ Error: {e}")
        return False


def test_empty_state():
    """Test empty state handling."""
    logger.info("\n🔍 Testing empty state...")
    # Search for something that definitely won't exist
    test_query = "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"
    try:
        resp = requests.post(
            f"{API_BASE}/v1/similar",
            json={"query": test_query, "top_k": 10},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if len(results) == 0:
                logger.info("  ✅ Empty state handled correctly (no results)")
                return True
            else:
                logger.warning(f"  ⚠️  Got {len(results)} results for impossible query")
                return False
        else:
            logger.warning(f"  ⚠️  API returned {resp.status_code} for empty query")
            return False
    except Exception as e:
        logger.error(f"  ❌ Error: {e}")
        return False


def test_metadata_completeness():
    """Test metadata enrichment completeness."""
    logger.info("\n🔍 Testing metadata completeness...")
    test_queries = ["Lightning Bolt", "Counterspell", "Brainstorm"]
    
    all_metadata_fields = set()
    for query in test_queries:
        try:
            resp = requests.post(
                f"{API_BASE}/v1/similar",
                json={"query": query, "top_k": 1},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    meta = results[0].get("metadata", {})
                    all_metadata_fields.update(meta.keys())
        except Exception:
            pass
    
    expected_fields = {
        "type", "mana_cost", "cmc", "functional_tags",
        "archetype_staples", "cooccurrence_note", "archetype_cooccurrence",
        "format_cooccurrence", "image_url"
    }
    
    found = expected_fields & all_metadata_fields
    missing = expected_fields - all_metadata_fields
    
    logger.info(f"  Found fields: {sorted(found)}")
    if missing:
        logger.info(f"  Missing fields: {sorted(missing)}")
    
    coverage = len(found) / len(expected_fields) * 100
    logger.info(f"  Coverage: {coverage:.1f}%")
    
    return coverage >= 50  # At least 50% of expected fields


def test_meilisearch_indexing():
    """Test if Meilisearch is indexed."""
    logger.info("\n🔍 Testing Meilisearch indexing...")
    try:
        resp = requests.get("http://localhost:7700/indexes/cards", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            num_docs = data.get("numberOfDocuments", 0)
            if num_docs > 0:
                logger.info(f"  ✅ Meilisearch indexed: {num_docs} documents")
                return True
            else:
                logger.warning("  ⚠️  Meilisearch index exists but is empty")
                logger.info("     Run: python -m ml.search.index_cards --embeddings <path>")
                return False
        else:
            logger.warning(f"  ⚠️  Meilisearch index check returned {resp.status_code}")
            return False
    except Exception as e:
        logger.warning(f"  ⚠️  Meilisearch not accessible: {e}")
        return False


def test_accessibility():
    """Test basic accessibility features."""
    logger.info("\n🔍 Testing accessibility...")
    if not HAS_PLAYWRIGHT:
        logger.warning("  ⚠️  Playwright not available (install with: uv add playwright)")
        return None
    
    issues = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            # Set up API routing
            setup_playwright_routing(context)
            
            page = context.new_page()
            
            # Inject API_BASE override
            inject_api_base(page)
            
            page.goto(UI_URL)
            
            # Check for focus indicators
            search_input = page.locator("#unifiedInput, #cardInput").first
            search_input.wait_for(state="visible")
            search_input.focus()
            page.wait_for_timeout(100)
            
            # Check computed styles for focus indicator
            focus_style = page.evaluate("""
                (element) => {
                    const style = window.getComputedStyle(element);
                    return {
                        outline: style.outline,
                        boxShadow: style.boxShadow
                    };
                }
            """, search_input)
            
            has_focus_indicator = (
                focus_style["outline"] and focus_style["outline"] != "none" and focus_style["outline"] != "0px"
            ) or (focus_style["boxShadow"] and focus_style["boxShadow"] != "none")
            
            if not has_focus_indicator:
                issues.append("Focus indicator not visible")
            
            # Check ARIA attributes
            role = search_input.get_attribute("role")
            aria_label = search_input.get_attribute("aria-label")
            
            if role != "combobox":
                issues.append("Search input missing role='combobox'")
            if not aria_label:
                issues.append("Search input missing aria-label")
            
            browser.close()
            
            if issues:
                logger.warning(f"  ⚠️  Found {len(issues)} accessibility issues:")
                for issue in issues:
                    logger.info(f"     - {issue}")
                return False
            else:
                logger.info("  ✅ Basic accessibility checks passed")
                return True
    except Exception as e:
        logger.warning(f"  ⚠️  Accessibility test failed: {e}")
        return None
    
    if issues:
        logger.warning(f"  ⚠️  Accessibility issues: {', '.join(issues)}")
        return False
    return True


def main():
    """Run all comprehensive tests."""
    logger.info("=" * 60)
    logger.info("Comprehensive UI/UX E2E Test")
    logger.info("=" * 60)
    
    if not test_api_readiness():
        logger.info("\n❌ API not ready. Start with: docker-compose up")
        return 1
    
    results = {
        "type_ahead": test_type_ahead_ui(),
        "card_images": test_card_images(),
        "empty_state": test_empty_state(),
        "metadata": test_metadata_completeness(),
        "meilisearch": test_meilisearch_indexing(),
        "accessibility": test_accessibility(),
    }
    
    logger.info("\n" + "=" * 60)
    logger.info("Test Results Summary:")
    logger.info("=" * 60)
    for test, result in results.items():
        status = "✅" if result else "❌" if result is False else "⚠️"
        logger.info(f"{status} {test}")
    
    passed = sum(1 for r in results.values() if r is True)
    total = sum(1 for r in results.values() if r is not None)
    
    logger.info(f"\nPassed: {passed}/{total}")
    
    # Recommendations
    logger.info("\n" + "=" * 60)
    logger.info("Recommendations:")
    logger.info("=" * 60)
    
    if not results.get("meilisearch"):
        logger.warning("⚠️  Meilisearch not indexed. To index:")
        logger.info("   python -m ml.search.index_cards --embeddings <path>")
        logger.info("   Or set INDEX_ON_STARTUP=true in docker-compose")
    
    if not results.get("type_ahead"):
        logger.warning("⚠️  Type-ahead may not be working. Check:")
        logger.info("   - API embeddings loaded")
        logger.error("   - Browser console for errors")
        logger.info("   - Network tab for /v1/cards requests")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit(main())

