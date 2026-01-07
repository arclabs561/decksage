#!/usr/bin/env python3
"""
Test Constants

Shared constants for E2E tests:
- Test card names
- Timeout values
- Test data
"""

# Test Cards
TEST_CARDS = {
    "common": "Lightning Bolt",
    "instant": "Counterspell",
    "sorcery": "Brainstorm",
    "creature": "Serra Angel",
    "artifact": "Sol Ring",
    "land": "Command Tower",
}

# Timeout Values (in seconds)
TIMEOUTS = {
    "fast": 2,      # Health checks, simple requests
    "normal": 5,    # Standard API requests
    "slow": 10,     # Complex operations
    "very_slow": 30,  # Fusion search, deck completion
    "extreme": 60,  # Very slow operations
}

# Test Query Prefixes
TEST_PREFIXES = [
    "Light",
    "Count",
    "Brain",
    "damage",
    "instant",
]

# Security Test Payloads
XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "<img src=x onerror=alert('xss')>",
    "javascript:alert('xss')",
    "<svg onload=alert('xss')>",
]

SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE cards; --",
    "' OR '1'='1",
    "1' UNION SELECT * FROM cards--",
    "admin'--",
]

# Performance Test Parameters
PERF_PARAMS = {
    "concurrent_requests": 50,
    "concurrent_workers": 10,
    "load_test_requests": 20,
    "benchmark_iterations": 5,
}

# Result Set Sizes
RESULT_SIZES = {
    "small": 10,
    "medium": 50,
    "large": 100,
}

