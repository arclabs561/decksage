#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///
"""
End-to-end testing suite for DeckSage API.

Tests:
1. Service health and readiness
2. Similarity search (embedding, jaccard, fusion)
3. Feedback collection
4. Feedback statistics
5. Feedback to annotations conversion
6. Error handling and edge cases

Usage:
    python scripts/e2e_testing/e2e_test_suite.py --base-url http://localhost:8000
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

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()

# Import shared utilities and constants
from test_utils import wait_for_api, logger, API_BASE
from test_constants import TEST_CARDS, TIMEOUTS


class E2ETestSuite:
    """End-to-end test suite for DeckSage API."""

    def __init__(self, base_url: str | None = None, author: str = "e2e_test"):
        self.base_url = (base_url or API_BASE).rstrip("/")
        self.author = author
        self.session_id = f"e2e_test_{int(time.time())}"
        self.results = {
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "feedback_submitted": 0,
            "errors": [],
        }

    def test(self, name: str, func):
        """Run a test and track results."""
        self.results["tests_run"] += 1
        try:
            result = func()
            if result:
                self.results["tests_passed"] += 1
                logger.info(f"✅ {name}")
                return True
            else:
                self.results["tests_failed"] += 1
                logger.error(f"❌ {name} (failed)")
                return False
        except Exception as e:
            self.results["tests_failed"] += 1
            self.results["errors"].append(f"{name}: {str(e)}")
            logger.error(f"❌ {name} (error: {e})")
            return False

    def test_health(self) -> bool:
        """Test service health endpoints."""
        try:
            # Test /live
            resp = requests.get(f"{self.base_url}/live", timeout=TIMEOUTS["normal"])
            if resp.status_code != 200:
                return False
            data = resp.json()
            if data.get("status") != "live":
                return False

            # Test /ready
            resp = requests.get(f"{self.base_url}/ready", timeout=TIMEOUTS["normal"])
            if resp.status_code != 200:
                return False
            data = resp.json()
            if data.get("status") != "ready":
                return False

            methods = data.get("available_methods", [])
            if not methods:
                return False

            logger.info(f"   Available methods: {', '.join(methods)}")
            return True
        except Exception as e:
            logger.error(f"   Error: {e}")
            return False

    def test_similarity_search(self, card: str, method: str = "embedding", k: int = 5, timeout: int = 30) -> bool:
        """Test similarity search."""
        try:
            # Use POST endpoint for method selection
            url = f"{self.base_url}/v1/similar"
            payload = {
                "query": card,
                "top_k": k,
                "mode": method if method in ["embedding", "jaccard", "fusion"] else None,
                "use_case": "substitute",
            }
            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code != 200:
                logger.info(f"   Status: {resp.status_code}, Response: {resp.text[:200]}")
                return False

            data = resp.json()
            if data.get("query") != card:
                return False

            results = data.get("results", [])
            if len(results) < min(k, 3):  # Allow fewer results for fusion
                logger.warning(f"   Warning: Only {len(results)} results (expected at least {min(k, 3)})")
                if len(results) == 0:
                    return False

            method_used = data.get("model_info", {}).get("method_used")
            logger.info(f"   Query: {card}, Method: {method_used}, Results: {len(results)}")
            if results:
                logger.info(f"   Top 3: {', '.join([r['card'] for r in results[:3]])}")

            return True
        except requests.exceptions.Timeout:
            logger.info(f"   Timeout after {timeout}s (method: {method})")
            return False
        except Exception as e:
            logger.error(f"   Error: {e}")
            return False

    def test_error_handling(self) -> bool:
        """Test error handling for invalid inputs."""
        try:
            # Test invalid card
            url = f"{self.base_url}/v1/cards/NonexistentCard12345/similar"
            resp = requests.get(url, timeout=TIMEOUTS["normal"])
            if resp.status_code != 404:
                logger.info(f"   Expected 404 for invalid card, got {resp.status_code}")
                return False

            # Test invalid k value (too low)
            url = f"{self.base_url}/v1/similar"
            resp = requests.post(url, json={"query": TEST_CARDS["common"], "top_k": 0}, timeout=TIMEOUTS["normal"])
            if resp.status_code != 422:
                logger.info(f"   Expected 422 for k=0, got {resp.status_code}")
                return False

            # Test invalid k value (too high)
            resp = requests.post(url, json={"query": TEST_CARDS["common"], "top_k": 200}, timeout=TIMEOUTS["normal"])
            if resp.status_code != 422:
                logger.info(f"   Expected 422 for k=200, got {resp.status_code}")
                return False

            logger.info("   Error handling: ✅")
            return True
        except Exception as e:
            logger.error(f"   Error: {e}")
            return False

    def test_feedback_submission(self, query_card: str, suggested_card: str, rating: int, is_substitute: bool) -> bool:
        """Test feedback submission."""
        try:
            url = f"{self.base_url}/v1/feedback"
            payload = {
                "query_card": query_card,
                "suggested_card": suggested_card,
                "task_type": "similarity",
                "rating": rating,
                "is_substitute": is_substitute,
                "session_id": self.session_id,
                "context": {
                    "author": self.author,
                    "test_type": "e2e",
                },
            }
            resp = requests.post(url, json=payload, timeout=TIMEOUTS["normal"])
            if resp.status_code != 200:
                logger.info(f"   Status: {resp.status_code}, Response: {resp.text[:200]}")
                return False

            data = resp.json()
            if data.get("status") != "success":
                return False

            feedback_id = data.get("feedback_id")
            if not feedback_id:
                return False

            self.results["feedback_submitted"] += 1
            logger.info(f"   Feedback ID: {feedback_id[:8]}...")
            return True
        except Exception as e:
            logger.error(f"   Error: {e}")
            return False

    def test_feedback_stats(self) -> bool:
        """Test feedback statistics."""
        try:
            url = f"{self.base_url}/v1/feedback/stats"
            resp = requests.get(url, timeout=TIMEOUTS["normal"])
            if resp.status_code != 200:
                return False

            data = resp.json()
            total = data.get("total_feedback", 0)
            logger.info(f"   Total feedback: {total}")
            if total > 0:
                by_rating = data.get("by_rating", {})
                substitution_rate = data.get("substitution_rate", 0)
                logger.info(f"   Rating distribution: {by_rating}")
                logger.info(f"   Substitution rate: {substitution_rate:.1%}")
            return True
        except Exception as e:
            logger.error(f"   Error: {e}")
            return False

    def test_batch_feedback(self) -> bool:
        """Test batch feedback submission."""
        try:
            url = f"{self.base_url}/v1/feedback/batch"
            payload = {
                "feedbacks": [
                    {
                        "query_card": TEST_CARDS["artifact"],
                        "suggested_card": "Command Tower",
                        "task_type": "similarity",
                        "rating": 4,
                        "is_substitute": True,
                        "session_id": self.session_id,
                        "context": {"author": self.author},
                    },
                    {
                        "query_card": TEST_CARDS["common"],
                        "suggested_card": "Shock",
                        "task_type": "similarity",
                        "rating": 3,
                        "is_substitute": False,
                        "session_id": self.session_id,
                        "context": {"author": self.author},
                    },
                ]
            }
            resp = requests.post(url, json=payload, timeout=TIMEOUTS["slow"])
            if resp.status_code != 200:
                logger.info(f"   Status: {resp.status_code}, Response: {resp.text[:200]}")
                return False

            data = resp.json()
            processed = data.get("processed", 0)
            failed = data.get("failed", 0)
            logger.error(f"   Processed: {processed}, Failed: {failed}")
            self.results["feedback_submitted"] += processed
            return processed > 0 and failed == 0
        except Exception as e:
            logger.error(f"   Error: {e}")
            return False

    def run_all_tests(self):
        """Run all e2e tests."""
        logger.info(f"\n{'='*60}")
        logger.info(f"DeckSage E2E Test Suite")
        logger.info(f"Base URL: {self.base_url}")
        logger.info(f"Session ID: {self.session_id}")
        logger.info(f"Author: {self.author}")
        logger.info(f"{'='*60}\n")

        # Health checks
        logger.info("1. Health Checks")
        self.test("Service /live endpoint", self.test_health)
        logger.info()

        # Similarity search tests
        logger.info("2. Similarity Search")
        self.test("Embedding search - Lightning Bolt", lambda: self.test_similarity_search(TEST_CARDS["common"], "embedding"))
        self.test("Jaccard search - Sol Ring", lambda: self.test_similarity_search(TEST_CARDS["artifact"], "jaccard"))
        self.test("Fusion search - Serra Angel (60s timeout)", lambda: self.test_similarity_search(TEST_CARDS["creature"], "fusion", timeout=TIMEOUTS["extreme"]))
        self.test("Fusion search - Counterspell (60s timeout)", lambda: self.test_similarity_search(TEST_CARDS["instant"], "fusion", timeout=TIMEOUTS["extreme"]))
        logger.info()

        # Error handling
        logger.error("3. Error Handling")
        self.test("Invalid card name", self.test_error_handling)
        logger.info()

        # Feedback tests
        logger.info("4. Feedback Collection")
        self.test(
            "Submit feedback - Lightning Bolt → Fireball (rating 4)",
            lambda: self.test_feedback_submission(TEST_CARDS["common"], "Fireball", 4, True),
        )
        self.test(
            "Submit feedback - Sol Ring → Command Tower (rating 4)",
            lambda: self.test_feedback_submission(TEST_CARDS["artifact"], "Command Tower", 4, True),
        )
        self.test(
            "Submit feedback - Lightning Bolt → Black Knight (rating 1)",
            lambda: self.test_feedback_submission(TEST_CARDS["common"], "Black Knight", 1, False),
        )
        self.test("Batch feedback submission", self.test_batch_feedback)
        logger.info()

        # Statistics
        logger.info("5. Feedback Statistics")
        self.test("Get feedback stats", self.test_feedback_stats)
        logger.info()

        # Summary
        logger.info(f"{'='*60}")
        logger.info("Test Summary")
        logger.info(f"{'='*60}")
        logger.info(f"Tests run: {self.results['tests_run']}")
        logger.info(f"Tests passed: {self.results['tests_passed']}")
        logger.error(f"Tests failed: {self.results['tests_failed']}")
        logger.info(f"Feedback submitted: {self.results['feedback_submitted']}")
        if self.results["errors"]:
            logger.error(f"\nErrors:")
            for error in self.results["errors"]:
                logger.error(f"  - {error}")

        success_rate = (
            self.results["tests_passed"] / self.results["tests_run"] * 100
            if self.results["tests_run"] > 0
            else 0
        )
        logger.info(f"\nSuccess rate: {success_rate:.1f}%")

        return self.results["tests_failed"] == 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run DeckSage E2E test suite")
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8000",
        help="Base URL for API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--author",
        type=str,
        default="e2e_test",
        help="Author name for feedback (default: e2e_test)",
    )

    args = parser.parse_args()

    suite = E2ETestSuite(base_url=args.base_url, author=args.author)
    success = suite.run_all_tests()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
