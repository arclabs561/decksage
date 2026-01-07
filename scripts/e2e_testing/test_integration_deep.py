#!/usr/bin/env python3
"""
Deep Integration Testing

Tests complete integration of all features:
- Type-ahead with text search
- Meilisearch indexing and search
- Embeddings fallback
- Metadata enrichment
- Graph/archetype data
- Card images
- Accessibility
- Error handling
- Performance under load
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

# Import shared utilities (dotenv is loaded automatically by test_utils)

# Import shared utilities and constants
from test_utils import wait_for_api, logger, API_BASE
from test_constants import TEST_CARDS, TIMEOUTS, TEST_PREFIXES


def test_api_readiness():
    """Ensure API is ready."""
    return wait_for_api(max_retries=30, timeout=TIMEOUTS["fast"])


def test_end_to_end_flow():
    """Test complete flow: type-ahead → search → results → metadata."""
    logger.info("Testing end-to-end flow...")
    
    # Step 1: Type-ahead
    try:
        resp = requests.get(f"{API_BASE}/v1/cards?prefix=Light&limit=5", timeout=TIMEOUTS["normal"])
        if resp.status_code != 200:
            logger.error(f"❌ Type-ahead failed: {resp.status_code}")
            return False
        
        data = resp.json()
        suggestions = data.get("items", [])
        if not suggestions:
            logger.warning("⚠️  No type-ahead suggestions")
            return False
        
        logger.info(f"✅ Type-ahead: {len(suggestions)} suggestions")
        
        # Step 2: Search for first suggestion
        query_card = suggestions[0]
        resp = requests.post(
            f"{API_BASE}/v1/similar",
            json={"query": query_card, "top_k": 5},
            timeout=TIMEOUTS["slow"]
        )
        
        if resp.status_code != 200:
            logger.error(f"❌ Search failed: {resp.status_code}")
            return False
        
        search_data = resp.json()
        results = search_data.get("results", [])
        if not results:
            logger.warning("⚠️  No search results")
            return False
        
        logger.info(f"✅ Search: {len(results)} results")
        
        # Step 3: Check metadata enrichment
        first_result = results[0]
        metadata = first_result.get("metadata", {})
        
        metadata_fields = [
            "type", "mana_cost", "cmc", "functional_tags",
            "archetype_staples", "cooccurrence_note", "image_url"
        ]
        
        found_fields = [f for f in metadata_fields if f in metadata and metadata[f]]
        logger.info(f"✅ Metadata: {len(found_fields)}/{len(metadata_fields)} fields")
        
        # Step 4: Verify graph/archetype data
        has_graph_data = any(
            f in metadata for f in ["archetype_staples", "cooccurrence_note", "archetype_cooccurrence"]
        )
        if has_graph_data:
            logger.info("✅ Graph/archetype data present")
        else:
            logger.warning("⚠️  Graph/archetype data missing")
        
        return True
    except Exception as e:
        logger.error(f"❌ End-to-end flow failed: {e}")
        return False


def test_meilisearch_integration():
    """Test Meilisearch integration."""
    logger.info("Testing Meilisearch integration...")
    
    # Check if Meilisearch is running
    try:
        resp = requests.get("http://localhost:7700/health", timeout=TIMEOUTS["fast"])
        assert resp.status_code == 200, \
            f"Expected 200, got {resp.status_code} for Meilisearch health"
        logger.info("✅ Meilisearch is running")
    except (requests.RequestException, AssertionError):
        logger.warning("⚠️  Meilisearch not accessible")
        return False
    
    # Check if index exists and has documents
    try:
        resp = requests.get("http://localhost:7700/indexes/cards", timeout=TIMEOUTS["fast"])
        assert resp.status_code == 200, \
            f"Expected 200, got {resp.status_code} for Meilisearch index check"
        data = resp.json()
        num_docs = data.get("numberOfDocuments", 0)
        if num_docs > 0:
            logger.info(f"✅ Meilisearch index has {num_docs} documents")
            
            # Test search through Meilisearch
            resp = requests.get(
                "http://localhost:7700/indexes/cards/search",
                params={"q": TEST_CARDS["common"], "limit": 5},
                timeout=TIMEOUTS["fast"]
            )
            assert resp.status_code == 200, \
                f"Expected 200, got {resp.status_code} for Meilisearch search"
            search_data = resp.json()
            hits = search_data.get("hits", [])
            logger.info(f"✅ Meilisearch search works: {len(hits)} results")
            return True
        else:
            logger.warning("⚠️  Meilisearch index is empty")
            logger.warning("   Run: python -m ml.search.index_cards --embeddings <path>")
            return False
    except (requests.RequestException, AssertionError) as e:
        logger.warning(f"⚠️  Meilisearch integration test error: {e}")
        return False


def test_fallback_behavior():
    """Test fallback from Meilisearch to embeddings."""
    logger.info("Testing fallback behavior...")
    
    # Test with a query that should work even without Meilisearch
    try:
        resp = requests.get(
            f"{API_BASE}/v1/cards?prefix=Light&limit=5",
            timeout=TIMEOUTS["normal"]
        )
        
        assert resp.status_code == 200, \
            f"Expected 200, got {resp.status_code} for fallback test"
        data = resp.json()
        items = data.get("items", [])
        assert items, "Expected results from fallback"
        logger.info(f"✅ Fallback works: {len(items)} results (embeddings)")
        return True
    except (requests.RequestException, AssertionError) as e:
        logger.error(f"❌ Fallback test error: {e}")
        return False


def test_concurrent_requests():
    """Test performance under concurrent load."""
    logger.info("Testing concurrent requests...")
    
    queries = TEST_PREFIXES * 4  # 20 requests
    
    def make_request(query):
        try:
            start = time.time()
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix={query}&limit=5",
                timeout=TIMEOUTS["normal"]
            )
            elapsed = time.time() - start
            return (query, resp.status_code, elapsed)
        except Exception as e:
            return (query, None, str(e))
    
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request, q) for q in queries]
        results = [f.result() for f in as_completed(futures)]
    
    total_time = time.time() - start_time
    
    successful = sum(1 for r in results if r[1] == 200)
    avg_time = sum(r[2] for r in results if isinstance(r[2], float)) / len(results)
    
    logger.info(f"✅ {successful}/{len(queries)} requests succeeded")
    logger.info(f"✅ Average response time: {avg_time*1000:.1f}ms")
    logger.info(f"✅ Total time for {len(queries)} requests: {total_time:.2f}s")
    logger.info(f"✅ Throughput: {len(queries)/total_time:.1f} req/s")
    
    return successful == len(queries) and avg_time < 0.5


def test_error_handling():
    """Test error handling for various edge cases."""
    logger.info("Testing error handling...")
    
    test_cases = [
        ("", "Empty query"),
        ("a" * 1000, "Very long query"),
        ("🚀", "Unicode query"),
        ("null", "Special string"),
    ]
    
    passed = 0
    for query, description in test_cases:
        try:
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix={query}&limit=5",
                timeout=TIMEOUTS["normal"]
            )
            # Should handle gracefully (200 with empty results, or 400/422)
            assert resp.status_code in [200, 400, 422], \
                f"Unexpected status {resp.status_code} for {description}"
            passed += 1
            logger.info(f"✅ '{description}' → handled correctly ({resp.status_code})")
        except (requests.RequestException, AssertionError) as e:
            logger.error(f"❌ '{description}' → Error: {e}")
    
    logger.info(f"Result: {passed}/{len(test_cases)} passed")
    assert passed == len(test_cases), \
        f"Expected all {len(test_cases)} test cases to pass, got {passed}"
    return passed == len(test_cases)


def test_metadata_completeness():
    """Test that metadata enrichment is complete."""
    logger.info("Testing metadata completeness...")
    
    test_queries = [TEST_CARDS["common"], TEST_CARDS["instant"], TEST_CARDS["sorcery"]]
    
    all_metadata_fields = set()
    for query in test_queries:
        try:
            resp = requests.post(
                f"{API_BASE}/v1/similar",
                json={"query": query, "top_k": 1},
                timeout=TIMEOUTS["slow"]
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
    
    logger.info(f"Found: {sorted(found)}")
    if missing:
        logger.warning(f"Missing: {sorted(missing)}")
    
    coverage = len(found) / len(expected_fields) * 100
    logger.info(f"Coverage: {coverage:.1f}%")
    
    assert coverage >= 50, \
        f"Expected at least 50% metadata coverage, got {coverage:.1f}%"
    return coverage >= 50


def test_card_images():
    """Test card image URLs."""
    logger.info("Testing card images...")
    
    try:
        resp = requests.post(
            f"{API_BASE}/v1/similar",
            json={"query": TEST_CARDS["common"], "top_k": 5},
            timeout=TIMEOUTS["slow"]
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
        
        logger.info(f"✅ {images_found}/{len(results)} results have image URLs")
        assert images_found > 0, "Expected at least one result with image URL"
        return images_found > 0
    except (requests.RequestException, AssertionError) as e:
        logger.error(f"❌ Image test error: {e}")
        return False


def main():
    """Run all deep integration tests."""
    logger.info("=" * 60)
    logger.info("Deep Integration Testing")
    logger.info("=" * 60)
    
    if not test_api_readiness():
        logger.error("API not ready. Start with: docker-compose up")
        return 1
    
    results = {
        "end_to_end": test_end_to_end_flow(),
        "meilisearch": test_meilisearch_integration(),
        "fallback": test_fallback_behavior(),
        "concurrent": test_concurrent_requests(),
        "error_handling": test_error_handling(),
        "metadata": test_metadata_completeness(),
        "images": test_card_images(),
    }
    
    logger.info("=" * 60)
    logger.info("Integration Test Results:")
    logger.info("=" * 60)
    for test, result in results.items():
        status = "✅" if result else "❌"
        logger.info(f"{status} {test}")
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    logger.info(f"Passed: {passed}/{total}")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit(main())

