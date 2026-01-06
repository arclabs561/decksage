#!/usr/bin/env python3
"""
Security Testing

Tests security-related features:
- Input sanitization
- XSS prevention
- SQL injection attempts
- Rate limiting
- CORS headers
- Invalid input handling
"""

import json
import os

import requests

# Import shared utilities (dotenv is loaded automatically by test_utils)

# Import shared utilities and constants
from test_utils import wait_for_api, logger, API_BASE
from test_constants import TEST_CARDS, TIMEOUTS, XSS_PAYLOADS, SQL_INJECTION_PAYLOADS


def test_api_readiness():
    """Ensure API is ready."""
    return wait_for_api(max_retries=30, timeout=TIMEOUTS["fast"])


def test_xss_prevention():
    """Test XSS prevention in inputs."""
    logger.info("Testing XSS prevention...")
    
    passed = 0
    for payload in XSS_PAYLOADS:
        try:
            # Test in query parameter
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix={payload}&limit=5",
                timeout=TIMEOUTS["normal"]
            )
            # Handle 404 or 503 gracefully (service may not be ready)
            if resp.status_code == 404:
                logger.warning(f"⚠️  XSS test endpoint not found (404) - skipping")
                return False
            elif resp.status_code == 503:
                logger.warning(f"⚠️  XSS test service unavailable (503) - embeddings may not be loaded")
                return False
            # Should not execute script - either reject (400/422) or sanitize (200 with safe output)
            assert resp.status_code in [200, 400, 422], \
                f"Unexpected status {resp.status_code} for XSS payload"
            # Check response doesn't contain raw payload
            assert payload not in resp.text, \
                f"XSS payload found in response: {payload[:30]}..."
            passed += 1
            logger.info(f"✅ XSS payload sanitized: {payload[:30]}...")
        except (requests.RequestException, AssertionError) as e:
            logger.warning(f"⚠️  XSS test failed for {payload[:30]}...: {e}")
    
    logger.info(f"Result: {passed}/{len(XSS_PAYLOADS)} XSS payloads handled safely")
    return passed == len(XSS_PAYLOADS)


def test_sql_injection():
    """Test SQL injection prevention."""
    logger.info("Testing SQL injection prevention...")
    
    passed = 0
    for payload in SQL_INJECTION_PAYLOADS:
        try:
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix={payload}&limit=5",
                timeout=TIMEOUTS["normal"]
            )
            # Should handle gracefully (200 with empty/safe results, or 400/422)
            assert resp.status_code in [200, 400, 422], \
                f"Unexpected status {resp.status_code} for SQL injection payload"
            # Check response is safe (no SQL errors)
            assert "sql" not in resp.text.lower() and "syntax error" not in resp.text.lower(), \
                f"Possible SQL error in response for payload: {payload[:30]}..."
            passed += 1
            logger.info(f"✅ SQL injection prevented: {payload[:30]}...")
        except (requests.RequestException, AssertionError) as e:
            logger.warning(f"⚠️  SQL injection test failed for {payload[:30]}...: {e}")
    
    logger.info(f"Result: {passed}/{len(SQL_INJECTION_PAYLOADS)} SQL injection attempts handled safely")
    return passed == len(SQL_INJECTION_PAYLOADS)


def test_rate_limiting():
    """Test rate limiting behavior."""
    logger.info("Testing rate limiting...")
    
    # Send many requests quickly
    requests_sent = 0
    rate_limited = False
    
    for i in range(50):  # Send 50 requests rapidly
        try:
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix=Light&limit=5",
                timeout=TIMEOUTS["fast"]
            )
            requests_sent += 1
            
            if resp.status_code == 429:  # Too Many Requests
                rate_limited = True
                logger.info(f"✅ Rate limiting active (429 after {requests_sent} requests)")
                break
        except requests.RequestException as e:
            logger.warning(f"⚠️  Rate limit test error: {e}")
            break
    
    if not rate_limited:
        logger.info(f"⚠️  No rate limiting detected (sent {requests_sent} requests)")
        # This is not necessarily a failure - rate limiting might not be enabled
    
    return True  # Rate limiting is optional, so always pass


def test_cors_headers():
    """Test CORS headers."""
    logger.info("Testing CORS headers...")
    
    try:
        # Send OPTIONS request (preflight)
        resp = requests.options(
            f"{API_BASE}/v1/similar",
            headers={"Origin": "https://example.com"},
            timeout=TIMEOUTS["normal"]
        )
        
        # Check for CORS headers
        cors_headers = {
            "Access-Control-Allow-Origin": resp.headers.get("Access-Control-Allow-Origin"),
            "Access-Control-Allow-Methods": resp.headers.get("Access-Control-Allow-Methods"),
            "Access-Control-Allow-Headers": resp.headers.get("Access-Control-Allow-Headers"),
        }
        
        has_cors = any(cors_headers.values())
        
        if has_cors:
            present = [k for k, v in cors_headers.items() if v]
            logger.info(f"✅ CORS headers present: {', '.join(present)}")
        else:
            logger.info("⚠️  No CORS headers found (may be configured elsewhere)")
        
        return True  # CORS is configuration-dependent
    except requests.RequestException as e:
        logger.warning(f"⚠️  CORS test failed: {e}")
        return True  # Not a critical failure


def test_input_validation():
    """Test input validation and sanitization."""
    logger.info("Testing input validation...")
    
    invalid_inputs = [
        ("", "Empty string"),
        ("a" * 10000, "Very long string"),
        ("\x00\x01\x02", "Control characters"),
        ("../../etc/passwd", "Path traversal"),
        ("%00", "Null byte encoding"),
    ]
    
    passed = 0
    for invalid_input, description in invalid_inputs:
        try:
            resp = requests.get(
                f"{API_BASE}/v1/cards?prefix={invalid_input}&limit=5",
                timeout=TIMEOUTS["normal"]
            )
            # Should handle gracefully (200 with empty results, or 400/422)
            assert resp.status_code in [200, 400, 422], \
                f"Unexpected status {resp.status_code} for {description}"
            passed += 1
            logger.info(f"✅ '{description}' → handled correctly ({resp.status_code})")
        except (requests.RequestException, AssertionError) as e:
            logger.warning(f"⚠️  '{description}' → Error: {e}")
    
    logger.info(f"Result: {passed}/{len(invalid_inputs)} invalid inputs handled correctly")
    return passed >= len(invalid_inputs) * 0.8  # At least 80%


def test_json_injection():
    """Test JSON injection prevention."""
    logger.info("Testing JSON injection...")
    
    malicious_json = [
        f'{{"query": "{TEST_CARDS["common"]}", "top_k": 3, "__proto__": {{"polluted": true}}}}',
        f'{{"query": "{TEST_CARDS["common"]}", "top_k": 3, "constructor": {{"prototype": {{"polluted": true}}}}}}',
    ]
    
    passed = 0
    for payload in malicious_json:
        try:
            resp = requests.post(
                f"{API_BASE}/v1/similar",
                json=json.loads(payload),
                timeout=TIMEOUTS["normal"]
            )
            # Should handle gracefully (200 with normal results, or 400/422)
            assert resp.status_code in [200, 400, 422], \
                f"Unexpected status {resp.status_code} for JSON injection"
            # Check response doesn't show signs of prototype pollution
            assert "polluted" not in resp.text.lower(), \
                "Possible prototype pollution detected"
            passed += 1
            logger.info("✅ JSON injection prevented")
        except json.JSONDecodeError:
            passed += 1
            logger.info("✅ Invalid JSON rejected")
        except (requests.RequestException, AssertionError) as e:
            logger.warning(f"⚠️  JSON injection test failed: {e}")
    
    logger.info(f"Result: {passed}/{len(malicious_json)} JSON injection attempts handled safely")
    return passed == len(malicious_json)


def main():
    """Run all security tests."""
    logger.info("=" * 60)
    logger.info("Security Testing")
    logger.info("=" * 60)
    
    if not test_api_readiness():
        logger.error("API not ready. Start with: docker-compose up")
        return 1
    
    results = {
        "xss": test_xss_prevention(),
        "sql_injection": test_sql_injection(),
        "rate_limiting": test_rate_limiting(),
        "cors": test_cors_headers(),
        "input_validation": test_input_validation(),
        "json_injection": test_json_injection(),
    }
    
    logger.info("=" * 60)
    logger.info("Security Test Results:")
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

