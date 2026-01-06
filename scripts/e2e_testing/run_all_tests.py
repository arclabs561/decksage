#!/usr/bin/env python3
"""
Unified E2E Test Runner

Runs all E2E test suites with proper HTTP server setup and result aggregation.
"""

import os
import sys
import time
import threading
import http.server
import socketserver
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass

# Add test directory to path
test_dir = Path(__file__).parent
sys.path.insert(0, str(test_dir))

# Load environment variables from .env files (handled by test_utils)
# Import test_utils first to ensure .env is loaded
from test_utils import logger

from test_utils import logger, API_BASE

# HTTP server for serving HTML files
_http_server = None
_http_server_port = None
_http_server_thread = None


def start_http_server(port=8765):
    """Start a simple HTTP server to serve HTML files."""
    global _http_server, _http_server_port, _http_server_thread
    
    if _http_server is not None:
        return _http_server_port
    
    project_root = Path(__file__).parent.parent.parent
    
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(project_root), **kwargs)
        
        def log_message(self, format, *args):
            # Suppress HTTP server logs
            pass
    
    for attempt in range(10):
        try:
            server = socketserver.TCPServer(("", port), Handler)
            server.allow_reuse_address = True
            _http_server = server
            _http_server_port = port
            
            def run_server():
                server.serve_forever()
            
            _http_server_thread = threading.Thread(target=run_server, daemon=True)
            _http_server_thread.start()
            
            # Wait for server to be ready
            import socket
            for check_attempt in range(20):
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.1)
                    result = sock.connect_ex(('localhost', port))
                    sock.close()
                    if result == 0:
                        logger.info(f"Started HTTP server on port {port}")
                        return port
                except:
                    pass
                time.sleep(0.1)
            
            return port
        except OSError:
            port += 1
            continue
    
    raise RuntimeError(f"Could not start HTTP server after trying 10 ports starting from 8765")


def stop_http_server():
    """Stop the HTTP server."""
    global _http_server, _http_server_port, _http_server_thread
    if _http_server:
        try:
            _http_server.shutdown()
            _http_server = None
            _http_server_port = None
            _http_server_thread = None
            logger.info("Stopped HTTP server")
        except:
            pass


@dataclass
class TestResult:
    """Test suite result."""
    name: str
    passed: bool
    output: str
    duration: float
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0


def run_test_suite(script_path: Path, timeout: int = 300) -> TestResult:
    """Run a single test suite and return results."""
    import subprocess
    start_time = time.time()
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "UI_URL": f"http://localhost:{_http_server_port}/test_search.html"}
        )
        
        duration = time.time() - start_time
        output = result.stdout + result.stderr
        
        # Try to extract test counts from output
        tests_run = 0
        tests_passed = 0
        tests_failed = 0
        
        for line in output.split('\n'):
            if 'Features tested:' in line or 'Tests run:' in line:
                try:
                    tests_run = int(line.split(':')[1].strip())
                except:
                    pass
            if 'Features passed:' in line or 'Tests passed:' in line:
                try:
                    tests_passed = int(line.split(':')[1].strip())
                except:
                    pass
            if 'Features failed:' in line or 'Tests failed:' in line:
                try:
                    tests_failed = int(line.split(':')[1].strip())
                except:
                    pass
        
        passed = result.returncode == 0
        
        return TestResult(
            name=script_path.stem,
            passed=passed,
            output=output,
            duration=duration,
            tests_run=tests_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return TestResult(
            name=script_path.stem,
            passed=False,
            output=f"Test timed out after {timeout}s",
            duration=duration
        )
    except Exception as e:
        duration = time.time() - start_time
        return TestResult(
            name=script_path.stem,
            passed=False,
            output=f"Error running test: {e}",
            duration=duration
        )


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run all E2E test suites")
    parser.add_argument("--suites", nargs="+", help="Specific test suites to run (by name)")
    parser.add_argument("--skip", nargs="+", help="Test suites to skip")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout per test suite (seconds)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    # Start HTTP server
    try:
        start_http_server()
    except Exception as e:
        logger.error(f"Failed to start HTTP server: {e}")
        return 1
    
    # Find all test scripts
    test_dir = Path(__file__).parent
    test_scripts = sorted(test_dir.glob("test_*.py"))
    
    # Filter by --suites if provided
    if args.suites:
        test_scripts = [s for s in test_scripts if s.stem in args.suites]
    
    # Filter out --skip
    if args.skip:
        test_scripts = [s for s in test_scripts if s.stem not in args.skip]
    
    # Exclude utility files
    test_scripts = [s for s in test_scripts if s.stem not in ["test_utils", "test_constants"]]
    
    logger.info("=" * 80)
    logger.info("UNIFIED E2E TEST RUNNER")
    logger.info("=" * 80)
    logger.info(f"Found {len(test_scripts)} test suites")
    logger.info("")
    
    results: List[TestResult] = []
    
    for script in test_scripts:
        logger.info(f"Running: {script.name}...")
        result = run_test_suite(script, timeout=args.timeout)
        results.append(result)
        
        status = "✅ PASSED" if result.passed else "❌ FAILED"
        logger.info(f"  {status} ({result.duration:.1f}s)")
        if result.tests_run > 0:
            logger.info(f"    Tests: {result.tests_passed}/{result.tests_run} passed")
        if args.verbose and not result.passed:
            logger.info(f"    Output:\n{result.output[:500]}")
        logger.info("")
    
    # Summary
    logger.info("=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    total_suites = len(results)
    passed_suites = sum(1 for r in results if r.passed)
    failed_suites = total_suites - passed_suites
    
    total_tests = sum(r.tests_run for r in results)
    total_passed = sum(r.tests_passed for r in results)
    total_failed = sum(r.tests_failed for r in results)
    
    logger.info(f"Test Suites: {passed_suites}/{total_suites} passed")
    if total_tests > 0:
        logger.info(f"Total Tests: {total_passed}/{total_tests} passed")
    logger.info("")
    
    if failed_suites > 0:
        logger.info("Failed Suites:")
        for result in results:
            if not result.passed:
                logger.info(f"  ❌ {result.name}")
        logger.info("")
    
    # Stop HTTP server
    stop_http_server()
    
    return 0 if failed_suites == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

