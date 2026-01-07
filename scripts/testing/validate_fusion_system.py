#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///
"""
Comprehensive validation and testing of the fusion system.

Tests:
1. API health and readiness
2. All similarity methods (embedding, jaccard, fusion)
3. Aggregator options (RRF, weighted)
4. Custom weights
5. Error handling
6. Performance consistency
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("Error: requests not installed. Install with: pip install requests")
    sys.exit(1)


def test_health(base_url: str) -> dict[str, Any]:
    """Test health endpoints."""
    results = {}
    
    # Test /ready
    try:
        resp = requests.get(f"{base_url}/ready", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        results["ready"] = {
            "status": "pass",
            "data": data,
            "available_methods": data.get("available_methods", []),
        }
    except Exception as e:
        results["ready"] = {"status": "fail", "error": str(e)}
    
    # Test /health
    try:
        resp = requests.get(f"{base_url}/v1/health", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        results["health"] = {
            "status": "pass",
            "data": data,
            "num_cards": data.get("num_cards", 0),
        }
    except Exception as e:
        results["health"] = {"status": "fail", "error": str(e)}
    
    # Test /live
    try:
        resp = requests.get(f"{base_url}/live", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        results["live"] = {"status": "pass", "data": data}
    except Exception as e:
        results["live"] = {"status": "fail", "error": str(e)}
    
    return results


def test_diagnostics(base_url: str) -> dict[str, Any]:
    """Test diagnostics endpoint."""
    try:
        resp = requests.get(f"{base_url}/v1/diagnostics", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {"status": "pass", "data": data}
    except Exception as e:
        return {"status": "fail", "error": str(e)}


def test_similarity_methods(base_url: str, query: str = "Lightning Bolt", top_k: int = 5) -> dict[str, Any]:
    """Test all similarity methods."""
    results = {}
    
    methods = ["embedding", "jaccard", "fusion"]
    
    for method in methods:
        try:
            resp = requests.post(
                f"{base_url}/v1/similar",
                json={"query": query, "top_k": top_k, "mode": method},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            
            results[method] = {
                "status": "pass",
                "num_results": len(data.get("results", [])),
                "method_used": data.get("model_info", {}).get("method_used"),
                "has_results": len(data.get("results", [])) > 0,
            }
        except Exception as e:
            results[method] = {"status": "fail", "error": str(e)}
    
    return results


def test_aggregators(base_url: str, query: str = "Lightning Bolt", top_k: int = 5) -> dict[str, Any]:
    """Test different aggregators."""
    results = {}
    
    aggregators = ["rrf", "weighted"]
    
    for agg in aggregators:
        try:
            resp = requests.post(
                f"{base_url}/v1/similar",
                json={"query": query, "top_k": top_k, "mode": "fusion", "aggregator": agg},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            
            results[agg] = {
                "status": "pass",
                "num_results": len(data.get("results", [])),
                "method_used": data.get("model_info", {}).get("method_used"),
            }
        except Exception as e:
            results[agg] = {"status": "fail", "error": str(e)}
    
    return results


def test_custom_weights(base_url: str, query: str = "Lightning Bolt", top_k: int = 5) -> dict[str, Any]:
    """Test custom weight specification."""
    test_weights = [
        {"embed": 0.75, "jaccard": 0.25},
        {"embed": 0.5, "jaccard": 0.5},
        {"embed": 1.0, "jaccard": 0.0},
    ]
    
    results = {}
    
    for i, weights in enumerate(test_weights):
        try:
            resp = requests.post(
                f"{base_url}/v1/similar",
                json={"query": query, "top_k": top_k, "mode": "fusion", "weights": weights},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            
            results[f"weights_{i+1}"] = {
                "status": "pass",
                "weights": weights,
                "num_results": len(data.get("results", [])),
            }
        except Exception as e:
            results[f"weights_{i+1}"] = {"status": "fail", "error": str(e), "weights": weights}
    
    return results


def test_error_handling(base_url: str) -> dict[str, Any]:
    """Test error handling."""
    results = {}
    
    # Invalid card name
    try:
        resp = requests.post(
            f"{base_url}/v1/similar",
            json={"query": "Nonexistent Card Name 12345", "top_k": 5, "mode": "fusion"},
            timeout=10,
        )
        results["invalid_card"] = {
            "status": "pass" if resp.status_code in [200, 404, 422] else "fail",
            "status_code": resp.status_code,
        }
    except Exception as e:
        results["invalid_card"] = {"status": "fail", "error": str(e)}
    
    # Invalid top_k
    try:
        resp = requests.post(
            f"{base_url}/v1/similar",
            json={"query": "Lightning Bolt", "top_k": 200, "mode": "fusion"},
            timeout=10,
        )
        results["invalid_top_k"] = {
            "status": "pass" if resp.status_code in [200, 422] else "fail",
            "status_code": resp.status_code,
        }
    except Exception as e:
        results["invalid_top_k"] = {"status": "fail", "error": str(e)}
    
    return results


def test_performance_consistency(base_url: str, query: str = "Lightning Bolt", num_runs: int = 5) -> dict[str, Any]:
    """Test performance consistency across multiple runs."""
    results = []
    
    for i in range(num_runs):
        try:
            start = time.time()
            resp = requests.post(
                f"{base_url}/v1/similar",
                json={"query": query, "top_k": 10, "mode": "fusion"},
                timeout=30,
            )
            resp.raise_for_status()
            elapsed = time.time() - start
            
            data = resp.json()
            results.append({
                "run": i + 1,
                "status": "pass",
                "latency_ms": elapsed * 1000,
                "num_results": len(data.get("results", [])),
            })
        except Exception as e:
            results.append({"run": i + 1, "status": "fail", "error": str(e)})
    
    if results:
        latencies = [r["latency_ms"] for r in results if r.get("status") == "pass"]
        return {
            "status": "pass" if all(r.get("status") == "pass" for r in results) else "partial",
            "runs": results,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "min_latency_ms": min(latencies) if latencies else 0.0,
            "max_latency_ms": max(latencies) if latencies else 0.0,
        }
    else:
        return {"status": "fail", "error": "No successful runs"}


def main():
    parser = argparse.ArgumentParser(description="Validate and test fusion system")
    parser.add_argument("--base-url", type=str, default="http://localhost:8000", help="API base URL")
    parser.add_argument("--query", type=str, default="Lightning Bolt", help="Test query")
    parser.add_argument("--output", type=str, help="Output JSON file for results")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Fusion System Validation & Testing")
    print("=" * 80)
    print(f"Base URL: {args.base_url}")
    print(f"Test Query: {args.query}")
    print("")
    
    all_results = {}
    
    # Test 1: Health endpoints
    print("Test 1: Health Endpoints")
    print("-" * 80)
    health_results = test_health(args.base_url)
    all_results["health"] = health_results
    
    for endpoint, result in health_results.items():
        status = "✓" if result.get("status") == "pass" else "✗"
        print(f"  {status} {endpoint}: {result.get('status', 'unknown')}")
        if args.verbose and result.get("status") == "pass":
            print(f"    Data: {json.dumps(result.get('data', {}), indent=4)}")
    
    print("")
    
    # Test 2: Diagnostics
    print("Test 2: Diagnostics Endpoint")
    print("-" * 80)
    diag_results = test_diagnostics(args.base_url)
    all_results["diagnostics"] = diag_results
    
    status = "✓" if diag_results.get("status") == "pass" else "✗"
    print(f"  {status} Diagnostics: {diag_results.get('status', 'unknown')}")
    if args.verbose and diag_results.get("status") == "pass":
        data = diag_results.get("data", {})
        signals = data.get("signals", {})
        print(f"    Available signals: {sum(1 for v in signals.values() if v)}/{len(signals)}")
        weights = data.get("fusion_weights", {})
        if weights:
            print(f"    Fusion weights: {', '.join(f'{k}={v:.3f}' for k, v in weights.items() if v > 0)}")
    
    print("")
    
    # Test 3: Similarity methods
    print("Test 3: Similarity Methods")
    print("-" * 80)
    method_results = test_similarity_methods(args.base_url, args.query)
    all_results["methods"] = method_results
    
    for method, result in method_results.items():
        status = "✓" if result.get("status") == "pass" and result.get("has_results") else "✗"
        print(f"  {status} {method}: {result.get('status', 'unknown')} ({result.get('num_results', 0)} results)")
    
    print("")
    
    # Test 4: Aggregators
    print("Test 4: Aggregators")
    print("-" * 80)
    agg_results = test_aggregators(args.base_url, args.query)
    all_results["aggregators"] = agg_results
    
    for agg, result in agg_results.items():
        status = "✓" if result.get("status") == "pass" else "✗"
        print(f"  {status} {agg}: {result.get('status', 'unknown')} ({result.get('num_results', 0)} results)")
    
    print("")
    
    # Test 5: Custom weights
    print("Test 5: Custom Weights")
    print("-" * 80)
    weight_results = test_custom_weights(args.base_url, args.query)
    all_results["custom_weights"] = weight_results
    
    for test_name, result in weight_results.items():
        status = "✓" if result.get("status") == "pass" else "✗"
        weights = result.get("weights", {})
        weights_str = ", ".join(f"{k}={v}" for k, v in weights.items())
        print(f"  {status} {test_name} ({weights_str}): {result.get('status', 'unknown')}")
    
    print("")
    
    # Test 6: Error handling
    print("Test 6: Error Handling")
    print("-" * 80)
    error_results = test_error_handling(args.base_url)
    all_results["error_handling"] = error_results
    
    for test_name, result in error_results.items():
        status = "✓" if result.get("status") == "pass" else "✗"
        print(f"  {status} {test_name}: {result.get('status', 'unknown')}")
    
    print("")
    
    # Test 7: Performance consistency
    print("Test 7: Performance Consistency")
    print("-" * 80)
    perf_results = test_performance_consistency(args.base_url, args.query)
    all_results["performance"] = perf_results
    
    status = "✓" if perf_results.get("status") == "pass" else "✗"
    print(f"  {status} Consistency: {perf_results.get('status', 'unknown')}")
    if perf_results.get("status") in ["pass", "partial"]:
        print(f"    Average latency: {perf_results.get('avg_latency_ms', 0):.1f}ms")
        print(f"    Min latency: {perf_results.get('min_latency_ms', 0):.1f}ms")
        print(f"    Max latency: {perf_results.get('max_latency_ms', 0):.1f}ms")
    
    print("")
    
    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    
    total_tests = 0
    passed_tests = 0
    
    for category, results in all_results.items():
        if isinstance(results, dict):
            for test_name, result in results.items():
                if isinstance(result, dict) and "status" in result:
                    total_tests += 1
                    if result.get("status") == "pass":
                        passed_tests += 1
    
    print(f"Tests passed: {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%)")
    
    if passed_tests == total_tests:
        print("✓ All tests passed!")
        exit_code = 0
    else:
        print("✗ Some tests failed")
        exit_code = 1
    
    # Save results
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nResults saved to {output_path}")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

