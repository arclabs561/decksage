#!/usr/bin/env python3
"""
Test Utilities

Shared utilities for E2E tests:
- API readiness checking
- Retry logic
- Response validation
- Test data generation
- HTTP server for serving HTML files
- Playwright routing setup
"""

import logging
import os
import sys
import time
import threading
import http.server
import socketserver
from pathlib import Path
from typing import Any, Callable

import requests

# Load environment variables from .env files
# Try multiple locations: current dir, parent dirs, and common locations
try:
    from dotenv import load_dotenv
    from pathlib import Path
    
    # Try loading from multiple locations
    project_root = Path(__file__).parent.parent.parent
    env_locations = [
        project_root / ".env",                    # Project root
        project_root / "scripts" / "e2e_testing" / ".env",  # Test dir
        Path.cwd() / ".env",                      # Current working directory
        Path.home() / ".decksage.env",            # Home directory
    ]
    
    # Also check parent repos (for VLM API keys)
    parent_dirs = [
        project_root.parent / "ai-visual-test" / ".env",
        project_root.parent / "developer" / ".env",
    ]
    env_locations.extend(parent_dirs)
    
    # Load all found .env files
    loaded = False
    for env_path in env_locations:
        if env_path.exists():
            load_dotenv(env_path, override=False)  # Don't override existing vars
            loaded = True
    
    # If no .env found, try default load_dotenv() which searches current dir
    if not loaded:
        load_dotenv(override=False)
except ImportError:
    # dotenv not available - that's okay, use environment variables directly
    pass
except Exception as e:
    # Log but don't fail if .env loading has issues
    import logging
    logging.getLogger(__name__).debug(f"Note: Could not load some .env files: {e}")

# Configuration from .env
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
UI_URL = os.getenv("UI_URL", "http://localhost:8000")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# HTTP server for serving HTML files (shared across all tests)
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


def get_http_server_port():
    """Get the current HTTP server port, starting it if needed."""
    if _http_server_port is None:
        start_http_server()
    return _http_server_port


def get_ui_url():
    """Get UI URL - use HTTP server if available, otherwise env or default."""
    default_ui = os.getenv("UI_URL", "")
    if default_ui and default_ui.startswith("http") and "localhost" not in default_ui:
        return default_ui
    
    # Use HTTP server for local files
    port = get_http_server_port()
    return f"http://localhost:{port}/test_search.html"


def get_review_url():
    """Get review URL - use HTTP server if available."""
    default_review = os.getenv("REVIEW_URL", "")
    if default_review and default_review.startswith("http") and "localhost" not in default_review:
        return default_review
    
    # Use HTTP server
    port = get_http_server_port()
    return f"http://localhost:{port}/review_similarities.html"


def setup_playwright_routing(context, api_base=None):
    """Set up Playwright route handler for API calls."""
    if api_base is None:
        api_base = API_BASE
    
    def handle_route(route):
        url = route.request.url
        request = route.request
        
        needs_routing = (
            ('/v1/' in url or '/similar' in url or '/search' in url or '/cards' in url)
            and not url.startswith(api_base)
            and ('localhost:876' in url or 'localhost:877' in url or 'localhost:878' in url)
        )
        
        if needs_routing:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                path = parsed.path
                query = parsed.query
                
                if path.startswith('/v1/'):
                    new_url = f"{api_base}{path}"
                elif path == '/similar' or path.startswith('/similar'):
                    new_url = f"{api_base}/v1/similar"
                elif path.startswith('/search'):
                    new_url = f"{api_base}/v1/search"
                elif path.startswith('/cards'):
                    new_url = f"{api_base}/v1/cards"
                else:
                    new_url = f"{api_base}{path}"
                
                if query:
                    new_url += f"?{query}"
                
                headers = dict(request.headers)
                if request.method == "POST" and "content-type" not in [h.lower() for h in headers.keys()]:
                    headers["Content-Type"] = "application/json"
                
                route.continue_(
                    url=new_url,
                    method=request.method,
                    headers=headers,
                    post_data=request.post_data
                )
            except:
                route.continue_()
        elif url.startswith(api_base):
            route.continue_()
        else:
            route.continue_()
    
    # Route API requests
    for port in range(8765, 8770):
        context.route(f"http://localhost:{port}/v1/**", handle_route)
    context.route("**/v1/similar**", handle_route)
    context.route("**/v1/search**", handle_route)
    context.route("**/v1/cards**", handle_route)
    
    return handle_route


def inject_api_base(page, api_base=None):
    """Inject API_BASE override into page."""
    if api_base is None:
        api_base = API_BASE
    
    page.add_init_script(f"""
        (function() {{
            const apiBase = '{api_base}';
            try {{
                Object.defineProperty(window.location, 'origin', {{
                    get: function() {{ return apiBase; }},
                    configurable: true
                }});
            }} catch(e) {{
                window.__TEST_API_BASE__ = apiBase;
            }}
        }})();
    """)


def wait_for_api(max_retries: int = 30, timeout: int = 2, verbose: bool = True) -> bool:
    """Wait for API to be ready."""
    if verbose:
        logger.info("Testing API readiness...")
    
    # Try /health first, then /ready
    for i in range(max_retries):
        try:
            resp = requests.get(f"{API_BASE}/health", timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok":
                    if verbose:
                        logger.info("✅ API is ready (checked /health)")
                    return True
        except Exception as e:
            if verbose and i == max_retries - 1:
                logger.debug(f"API /health check failed: {e}")
            pass
        time.sleep(1)

    # Fallback to /ready endpoint if /health fails or is not 'ok'
    for i in range(max_retries):
        try:
            resp = requests.get(f"{API_BASE}/ready", timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ready":
                    if verbose:
                        logger.info("✅ API is ready (checked /ready)")
                    return True
        except Exception as e:
            if verbose and i == max_retries - 1:
                logger.debug(f"API /ready check failed: {e}")
            pass
        if i < max_retries - 1:
            time.sleep(1)
    
    if verbose:
        logger.error(f"❌ API not ready after {max_retries}s")
    return False


def retry_with_backoff(
    func: Callable[[], Any],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Any:
    """Retry a function with exponential backoff."""
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return func()
        except exceptions as e:
            last_exception = e
            if attempt < max_retries - 1:
                logger.debug(f"Retry {attempt + 1}/{max_retries} after {delay}s: {e}")
                time.sleep(delay)
                delay *= backoff_factor
            else:
                logger.error(f"All {max_retries} retries failed: {e}")
    
    raise last_exception


def validate_similarity_response(data: dict[str, Any]) -> bool:
    """Validate a similarity search response."""
    required_fields = ["query", "results", "model_info"]
    return all(field in data for field in required_fields)


def validate_cards_response(data: dict[str, Any]) -> bool:
    """Validate a cards listing response."""
    required_fields = ["items", "total"]
    return all(field in data for field in required_fields)


def generate_test_queries() -> list[str]:
    """Generate test queries for various scenarios."""
    from .test_constants import TEST_CARDS, TEST_PREFIXES
    
    return [
        TEST_CARDS["common"],   # Common card
        TEST_CARDS["instant"],  # Common card
        TEST_CARDS["sorcery"],  # Common card
        *TEST_PREFIXES,         # Prefixes
        "damage",               # Text search
        "instant",              # Type search
        "",                     # Empty
        "zzzzzzzzzz",           # No results
    ]


def check_response_time(url: str, max_time: float = 1.0, **kwargs) -> tuple[bool, float]:
    """Check if a request completes within max_time seconds."""
    start = time.time()
    try:
        resp = requests.get(url, timeout=max_time * 2, **kwargs)
        elapsed = time.time() - start
        return resp.status_code == 200 and elapsed <= max_time, elapsed
    except Exception:
        elapsed = time.time() - start
        return False, elapsed


def wait_for_element_condition(
    page,
    locator,
    condition: str = "visible",
    timeout: int = 5000,
    retry_interval: float = 0.1,
) -> bool:
    """
    Wait for an element to meet a condition with retry logic.
    
    Args:
        page: Playwright page object
        locator: Element locator
        condition: Condition to wait for ("visible", "hidden", "enabled", "disabled")
        timeout: Maximum time to wait in milliseconds
        retry_interval: Time between retries in seconds
    
    Returns:
        True if condition met, False otherwise
    """
    from playwright.sync_api import expect
    
    try:
        if condition == "visible":
            expect(locator).to_be_visible(timeout=timeout)
        elif condition == "hidden":
            expect(locator).to_be_hidden(timeout=timeout)
        elif condition == "enabled":
            expect(locator).to_be_enabled(timeout=timeout)
        elif condition == "disabled":
            expect(locator).to_be_disabled(timeout=timeout)
        else:
            logger.warning(f"Unknown condition: {condition}")
            return False
        return True
    except Exception as e:
        logger.debug(f"Element condition check failed: {e}")
        return False


def wait_for_network_idle(page, timeout: int = 30000) -> bool:
    """Wait for network to be idle."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
        return True
    except Exception:
        return False


def safe_click(page, locator, timeout: int = 5000, retries: int = 3) -> bool:
    """
    Safely click an element with retry logic.
    
    Args:
        page: Playwright page object
        locator: Element locator
        timeout: Timeout for each attempt
        retries: Number of retry attempts
    
    Returns:
        True if click succeeded, False otherwise
    """
    for attempt in range(retries):
        try:
            # Wait for element to be visible and enabled
            expect(locator).to_be_visible(timeout=timeout)
            expect(locator).to_be_enabled(timeout=timeout)
            locator.click(timeout=timeout)
            return True
        except Exception as e:
            if attempt < retries - 1:
                logger.debug(f"Click attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(0.5)
            else:
                logger.error(f"Click failed after {retries} attempts: {e}")
                return False
    return False


def safe_type(page, locator, text: str, timeout: int = 5000, clear_first: bool = True) -> bool:
    """
    Safely type text into an element with retry logic.
    
    Args:
        page: Playwright page object
        locator: Element locator
        text: Text to type
        timeout: Timeout for each attempt
        clear_first: Whether to clear the field first
    
    Returns:
        True if typing succeeded, False otherwise
    """
    try:
        expect(locator).to_be_visible(timeout=timeout)
        expect(locator).to_be_enabled(timeout=timeout)
        if clear_first:
            locator.clear()
        locator.fill(text, timeout=timeout)
        return True
    except Exception as e:
        logger.error(f"Type failed: {e}")
        return False


def wait_for_similarities_loaded(page, timeout: int = 15000) -> bool:
    """
    Wait for similarities to be loaded on the review page.
    
    Args:
        page: Playwright page object
        timeout: Maximum time to wait in milliseconds
    
    Returns:
        True if similarities loaded, False otherwise
    """
    from playwright.sync_api import expect
    
    try:
        # Wait for loading to disappear
        loading = page.locator("#loadingContainer")
        expect(loading).to_be_hidden(timeout=timeout)
        
        # Wait for either similarities or empty state
        similarity_items = page.locator(".similarity-item")
        empty_state = page.locator("#emptyState")
        
        # Check if similarities appeared or empty state is shown
        try:
            expect(similarity_items.first).to_be_visible(timeout=2000)
            return True
        except:
            try:
                expect(empty_state).to_be_visible(timeout=2000)
                return True  # Empty state is also a valid result
            except:
                return False
    except Exception as e:
        logger.debug(f"Wait for similarities failed: {e}")
        return False
