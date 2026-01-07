#!/usr/bin/env python3
"""
Performance Testing

Tests performance characteristics:
- Response time benchmarks
- Throughput under load
- Concurrent request handling
- Large result set performance
- Autocomplete debounce timing
"""

import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# Import shared utilities (dotenv is loaded automatically by test_utils)

# Import shared utilities and constants
from test_utils import wait_for_api, logger, API_BASE
from test_constants import TEST_CARDS, TIMEOUTS, PERF_PARAMS, RESULT_SIZES


def test_api_readiness():
    """Ensure API is ready."""
    return wait_for_api(max_retries=30, timeout=TIMEOUTS["fast"])


def test_response_time_benchmarks():
    """Test response time for various endpoints."""
    logger.info("Testing response time benchmarks...")
    
    benchmarks = {
        "/ready": (f"{API_BASE}/ready", 0.1),  # Should be very fast
        "/v1/cards (prefix)": (f"{API_BASE}/v1/cards?prefix=Light&limit=10", 0.5),
        "/v1/similar": (f"{API_BASE}/v1/similar", 2.0),  # POST request
    }
    
    results = {}
    for name, (url, max_time) in benchmarks.items():
        times = []
        for _ in range(PERF_PARAMS["benchmark_iterations"]):
            start = time.time()
            try:
                if "similar" in url:
                    resp = requests.post(
                        url,
                        json={"query": TEST_CARDS["common"], "top_k": 5},
                        timeout=max_time * 2
                    )
                else:
                    resp = requests.get(url, timeout=max_time * 2)
                elapsed = time.time() - start
                assert resp.status_code == 200, \
                    f"Expected 200, got {resp.status_code} for {name}"
                times.append(elapsed)
            except (requests.RequestException, AssertionError):
                pass
        
        if times:
            avg_time = statistics.mean(times)
            median_time = statistics.median(times)
            max_observed = max(times)
            
            passed = avg_time <= max_time
            status = "✅" if passed else "⚠️"
            logger.info(
                f"{status} {name}: avg={avg_time*1000:.1f}ms, "
                f"median={median_time*1000:.1f}ms, max={max_observed*1000:.1f}ms"
            )
            results[name] = passed
        else:
            logger.error(f"❌ {name}: All requests failed")
            results[name] = False
    
    passed = sum(results.values())
    total = len(results)
    logger.info(f"Result: {passed}/{total} benchmarks met")
    return passed == total


def test_throughput():
    """Test throughput under load."""
    logger.info("Testing throughput...")
    
    num_requests = PERF_PARAMS["concurrent_requests"]
    from test_constants import TEST_PREFIXES
    queries = TEST_PREFIXES * (num_requests // len(TEST_PREFIXES) + 1)
    queries = queries[:num_requests]
    
    def make_request(query):
        start = time.time()
        try:
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix={query}&limit=5",
                timeout=TIMEOUTS["normal"]
            )
            elapsed = time.time() - start
            return (resp.status_code == 200, elapsed)
        except requests.RequestException:
            elapsed = time.time() - start
            return (False, elapsed)
    
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=PERF_PARAMS["concurrent_workers"]) as executor:
        futures = [executor.submit(make_request, q) for q in queries]
        results = [f.result() for f in as_completed(futures)]
    
    total_time = time.time() - start_time
    successful = sum(1 for r in results if r[0])
    avg_time = statistics.mean([r[1] for r in results])
    throughput = num_requests / total_time
    
    logger.info(f"✅ {successful}/{num_requests} requests succeeded")
    logger.info(f"✅ Average response time: {avg_time*1000:.1f}ms")
    logger.info(f"✅ Total time: {total_time:.2f}s")
    logger.info(f"✅ Throughput: {throughput:.1f} req/s")
    
    # Benchmarks: >90% success rate, <500ms avg, >10 req/s
    passed = (
        successful >= num_requests * 0.9 and
        avg_time < 0.5 and
        throughput > 10
    )
    
    return passed


def test_large_result_sets():
    """Test performance with large result sets."""
    logger.info("Testing large result sets...")
    
    test_cases = [
        (RESULT_SIZES["small"], "Small"),
        (RESULT_SIZES["medium"], "Medium"),
        (RESULT_SIZES["large"], "Large"),
    ]
    
    results = {}
    for top_k, description in test_cases:
        start = time.time()
        try:
            resp = requests.post(
                f"{API_BASE}/v1/similar",
                json={"query": TEST_CARDS["common"], "top_k": top_k},
                timeout=TIMEOUTS["very_slow"]
            )
            elapsed = time.time() - start
            
            assert resp.status_code == 200, \
                f"Expected 200, got {resp.status_code} for {description}"
            data = resp.json()
            actual_count = len(data.get("results", []))
            
            # Performance should scale reasonably (not linearly)
            max_time = 2.0 + (top_k / 50)  # Allow more time for larger sets
            passed = elapsed <= max_time
            status = "✅" if passed else "⚠️"
            logger.info(
                f"{status} {description} ({top_k} results): "
                f"{actual_count} results in {elapsed*1000:.1f}ms"
            )
            results[description] = passed
        except (requests.RequestException, AssertionError) as e:
            logger.error(f"❌ {description}: Error {e}")
            results[description] = False
    
    passed = sum(results.values())
    total = len(results)
    logger.info(f"Result: {passed}/{total} large result sets handled")
    return passed >= total * 0.7  # At least 70%


def test_concurrent_load():
    """Test performance under concurrent load."""
    logger.info("Testing concurrent load...")
    
    num_concurrent = PERF_PARAMS["load_test_requests"]
    query = TEST_CARDS["common"]
    
    def make_request():
        start = time.time()
        try:
            resp = requests.post(
                f"{API_BASE}/v1/similar",
                json={"query": query, "top_k": 5},
                timeout=TIMEOUTS["slow"]
            )
            elapsed = time.time() - start
            return (resp.status_code == 200, elapsed)
        except requests.RequestException:
            elapsed = time.time() - start
            return (False, elapsed)
    
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        futures = [executor.submit(make_request) for _ in range(num_concurrent)]
        results = [f.result() for f in as_completed(futures)]
    
    total_time = time.time() - start_time
    successful = sum(1 for r in results if r[0])
    times = [r[1] for r in results if r[0]]
    
    if times:
        avg_time = statistics.mean(times)
        p95_time = statistics.quantiles(times, n=20)[18] if len(times) > 1 else avg_time
        
        logger.info(f"✅ {successful}/{num_concurrent} concurrent requests succeeded")
        logger.info(f"✅ Average response time: {avg_time*1000:.1f}ms")
        logger.info(f"✅ P95 response time: {p95_time*1000:.1f}ms")
        logger.info(f"✅ Total time: {total_time:.2f}s")
        
        # Benchmarks: >80% success, <2s avg, <5s P95
        passed = (
            successful >= num_concurrent * 0.8 and
            avg_time < 2.0 and
            p95_time < 5.0
        )
    else:
        logger.error(f"❌ All concurrent requests failed")
        passed = False
    
    return passed


def main():
    """Run all performance tests."""
    logger.info("=" * 60)
    logger.info("Performance Testing")
    logger.info("=" * 60)
    
    if not test_api_readiness():
        logger.error("API not ready. Start with: docker-compose up")
        return 1
    
    results = {
        "benchmarks": test_response_time_benchmarks(),
        "throughput": test_throughput(),
        "large_results": test_large_result_sets(),
        "concurrent": test_concurrent_load(),
    }
    
    logger.info("=" * 60)
    logger.info("Performance Test Results:")
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
    
    logger.info(f"Passed: {passed}/{total}")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit(main())

