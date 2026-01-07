#!/usr/bin/env python3
"""
Comprehensive Visual E2E Tests for All Pages using @arclabs561/ai-visual-test

Tests all UI pages with AI-powered visual validation:
- Landing page (/)
- Search page (/search.html)
- Review page (/review.html)

Uses ai-visual-test for:
- Layout validation
- Component presence
- Visual hierarchy
- Accessibility checks
- Responsive design
- Visual regression detection
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Import shared utilities (dotenv is loaded automatically by test_utils)
from test_utils import wait_for_api, logger, API_BASE, get_ui_url, start_http_server, setup_playwright_routing, inject_api_base, get_ui_url, start_http_server, setup_playwright_routing, inject_api_base
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
    logger.error("⚠️  Playwright not installed. Install with: uv add playwright")


def check_ai_visual_test_installed() -> bool:
    """Check if @arclabs561/ai-visual-test is installed."""
    # Check local node_modules first
    package_json = Path(__file__).parent / "package.json"
    if package_json.exists():
        node_modules = Path(__file__).parent / "node_modules" / "@arclabs561" / "ai-visual-test"
        if node_modules.exists():
            return True
    
    # Check via npx
    try:
        result = subprocess.run(
            ["npx", "--yes", "@arclabs561/ai-visual-test", "--help"],
            capture_output=True,
            text=True,
            timeout=TIMEOUTS["slow"],
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_vlm_api_key() -> tuple[str, str] | None:
    """Get VLM API key and provider."""
    key = os.getenv("GEMINI_API_KEY")
    if key:
        return "gemini", key
    
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return "openai", key
    
    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        return "anthropic", key
    
    return None


def test_visual_with_ai(
    screenshot_path: Path,
    prompt: str,
    threshold: float = 0.7,
    test_type: str = "layout",
) -> dict[str, Any]:
    """
    Test screenshot with AI visual test.
    
    Args:
        screenshot_path: Path to screenshot
        prompt: Prompt for AI evaluation
        threshold: Minimum score to pass (0-1)
        test_type: Type of test (layout, accessibility, regression, responsive)
    
    Returns:
        Dict with score, passed, issues, etc.
    """
    vlm_info = get_vlm_api_key()
    if not vlm_info:
        logger.warning("⚠️  No VLM API key found (GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY)")
        return {"score": 0, "passed": False, "error": "No API key"}
    
    provider, api_key = vlm_info
    
    test_dir = Path(__file__).parent
    # Use tempfile for automatic cleanup
    import tempfile
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.mjs', delete=False, dir=str(test_dir))
    node_script = Path(temp_file.name)
    temp_file.close()
    try:
        # Escape prompt for template string
        escaped_prompt = prompt.replace("`", "\\`").replace("$", "\\$").replace("\\", "\\\\")
        
        with open(node_script, "w") as f:
            f.write(f"""import {{ validateScreenshot, createConfig }} from '@arclabs561/ai-visual-test';

const config = createConfig({{
    provider: '{provider}',
    apiKey: '{api_key}'
}});

try {{
    const result = await validateScreenshot(
        '{screenshot_path}',
        `{escaped_prompt}`,
        {{ testType: '{test_type}' }},
        config
    );
    console.log(JSON.stringify(result));
}} catch (error) {{
    console.log(JSON.stringify({{
        error: error.message,
        score: 0,
        issues: [],
        details: error.stack
    }}));
}}
""")
        
        # The package is an ES module, so we need to use .mjs extension and proper import
        # Run from test_dir where node_modules exists
        result = subprocess.run(
            ["node", str(node_script)],
            cwd=str(test_dir),
            capture_output=True,
            text=True,
            timeout=TIMEOUTS["extreme"],
            env={**os.environ, "NODE_PATH": str(test_dir / "node_modules")},
        )
        
        if result.returncode == 0:
            try:
                validation_result = json.loads(result.stdout)
                # Handle both 0-10 and 0-1 score formats
                raw_score = validation_result.get("score", 0)
                if isinstance(raw_score, (int, float)):
                    if raw_score > 1:
                        score = raw_score / 10.0  # Convert 0-10 to 0-1
                    else:
                        score = raw_score
                else:
                    score = 0
                passed = score >= threshold
                
                return {
                    "score": score,
                    "passed": passed,
                    "threshold": threshold,
                    "issues": validation_result.get("issues", []),
                    "details": validation_result.get("details", ""),
                }
            except json.JSONDecodeError:
                logger.warning(f"⚠️  Could not parse validation result: {result.stdout}")
                return {"score": 0, "passed": False, "error": "Parse error"}
        else:
            logger.warning(f"⚠️  Validation failed: {result.stderr}")
            return {"score": 0, "passed": False, "error": result.stderr}
    finally:
        if node_script.exists():
            node_script.unlink()


class AllPagesVisualTester:
    """Visual tester for all UI pages."""
    
    def __init__(self):
        self.results = {
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "visual_tests_run": 0,
            "visual_tests_passed": 0,
            "issues": [],
        }
        self.screenshots_dir = Path("/tmp/visual_tests")
        self.screenshots_dir.mkdir(exist_ok=True)
        self.page = None
        self.browser = None
    
    def test_feature(self, name: str, func):
        """Test a feature and track results."""
        self.results["tests_run"] += 1
        try:
            result = func()
            if result:
                self.results["tests_passed"] += 1
                logger.info(f"✅ {name}")
                return True
            else:
                self.results["tests_failed"] += 1
                self.results["issues"].append(name)
                logger.error(f"❌ {name}")
                return False
        except Exception as e:
            self.results["tests_failed"] += 1
            self.results["issues"].append(f"{name}: {str(e)}")
            logger.error(f"❌ {name} (error: {e})")
            return False
    
    def test_visual(self, name: str, screenshot_path: Path, prompt: str, threshold: float = 0.7, test_type: str = "layout"):
        """Test visual with AI and track results."""
        self.results["visual_tests_run"] += 1
        try:
            result = test_visual_with_ai(screenshot_path, prompt, threshold, test_type)
            if result.get("passed", False):
                self.results["visual_tests_passed"] += 1
                logger.info(f"  ✅ Visual test passed (score: {result['score']:.2f})")
                return True
            else:
                score = result.get("score", 0)
                issues = result.get("issues", [])
                logger.warning(f"  ⚠️  Visual test failed (score: {score:.2f})")
                if issues:
                    for issue in issues[:3]:
                        logger.info(f"     - {issue}")
                return False
        except Exception as e:
            logger.error(f"  ❌ Visual test error: {e}")
            return False
    
    def test_landing_page(self):
        """Test landing page (/) visual layout."""
        logger.info("Testing: Landing page visual layout...")
        try:
            self.page.goto(UI_URL)
            self.page.wait_for_load_state("networkidle")
            time.sleep(1)  # Let animations settle
            
            screenshot_path = self.screenshots_dir / "landing_page.png"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            
            prompt = """
            Evaluate this landing/search page:
            1. Is the search input clearly visible and prominent?
            2. Are there clear instructions or labels?
            3. Is the layout clean and organized?
            4. Are interactive elements (buttons, inputs) clearly visible?
            5. Is there good visual hierarchy (title, search, results)?
            6. Are colors and contrast appropriate for readability?
            7. Is the page responsive and well-structured?
            """
            
            return self.test_visual("Landing page layout", screenshot_path, prompt, threshold=0.7)
        except Exception as e:
            logger.error(f"  ❌ Landing page test failed: {e}")
            return False
    
    def test_search_page_loaded(self):
        """Test search page with loaded results."""
        logger.info("Testing: Search page with results...")
        try:
            self.page.goto(f"{UI_URL}/search.html")
            self.page.wait_for_load_state("networkidle")
            time.sleep(1)
            
            # Perform a search
            search_input = self.page.locator("#unifiedInput, #cardInput, input[type='text']").first
            if search_input.count() > 0:
                test_card = TEST_CARDS.get("common") if isinstance(TEST_CARDS, dict) else "Lightning Bolt"
                search_input.fill(test_card)
                search_input.press("Enter")
                
                # Wait for results
                time.sleep(3)
                self.page.wait_for_load_state("networkidle")
            
            screenshot_path = self.screenshots_dir / "search_page_loaded.png"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            
            prompt = """
            Evaluate this search results page:
            1. Are search results clearly displayed?
            2. Is each result item well-formatted and readable?
            3. Are similarity scores visible?
            4. Is metadata (if shown) organized and clear?
            5. Are there clear visual separations between results?
            6. Is the search input still visible/accessible?
            7. Are there any obvious layout issues or overlapping elements?
            8. Is the overall design consistent and professional?
            """
            
            return self.test_visual("Search page with results", screenshot_path, prompt, threshold=0.7)
        except Exception as e:
            logger.error(f"  ❌ Search page test failed: {e}")
            return False
    
    def test_review_page_initial(self):
        """Test review page initial state."""
        logger.info("Testing: Review page initial state...")
        try:
            self.page.goto(f"{UI_URL}/review.html")
            self.page.wait_for_load_state("networkidle")
            time.sleep(1)
            
            screenshot_path = self.screenshots_dir / "review_page_initial.png"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            
            prompt = """
            Evaluate this similarity review page:
            1. Is the page layout clean and organized?
            2. Are data source controls (API/File) clearly visible?
            3. Is the query input field prominent and accessible?
            4. Are bulk action buttons visible and well-positioned?
            5. Is there clear visual hierarchy?
            6. Are instructions or labels clear?
            7. Is the design consistent with the rest of the application?
            8. Are there any obvious layout issues?
            """
            
            return self.test_visual("Review page initial", screenshot_path, prompt, threshold=0.7)
        except Exception as e:
            logger.error(f"  ❌ Review page initial test failed: {e}")
            return False
    
    def test_review_page_loaded(self):
        """Test review page with loaded similarities."""
        logger.info("Testing: Review page with similarities...")
        try:
            self.page.goto(f"{UI_URL}/review.html")
            self.page.wait_for_load_state("networkidle")
            time.sleep(1)
            
            # Load similarities
            data_source = self.page.locator("#dataSource")
            if data_source.count() > 0:
                data_source.select_option("api")
                time.sleep(0.3)
            
            query_input = self.page.locator("#queryCard")
            if query_input.count() > 0:
                test_card = TEST_CARDS.get("common") if isinstance(TEST_CARDS, dict) else "Lightning Bolt"
                query_input.fill(test_card)
            
            top_k = self.page.locator("#topK")
            if top_k.count() > 0:
                top_k.fill("10")
            
            load_btn = self.page.locator("#loadBtn")
            if load_btn.count() > 0:
                load_btn.click()
                time.sleep(3)  # Wait for API call
                self.page.wait_for_load_state("networkidle")
            
            screenshot_path = self.screenshots_dir / "review_page_loaded.png"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            
            prompt = """
            Evaluate this review page with loaded similarities:
            1. Are similarity items clearly displayed in a list?
            2. Is each similarity item well-formatted with card names and scores?
            3. Are annotation controls (rating buttons 0-4) visible and accessible?
            4. Are substitute checkboxes clearly visible?
            5. Is metadata (if shown) organized and readable?
            6. Are statistics (total, annotated, pending) clearly displayed?
            7. Is the bulk actions bar visible and accessible?
            8. Is there good visual separation between items?
            9. Is the overall layout clean and professional?
            10. Are there any overlapping elements or layout issues?
            """
            
            return self.test_visual("Review page with similarities", screenshot_path, prompt, threshold=0.7)
        except Exception as e:
            logger.error(f"  ❌ Review page loaded test failed: {e}")
            return False
    
    def test_responsive_design(self):
        """Test responsive design across all pages."""
        logger.info("Testing: Responsive design...")
        try:
            viewports = [
                {"width": 375, "height": 667, "name": "mobile"},
                {"width": 768, "height": 1024, "name": "tablet"},
                {"width": 1920, "height": 1080, "name": "desktop"},
            ]
            
            passed = 0
            for viewport in viewports:
                self.page.set_viewport_size({"width": viewport["width"], "height": viewport["height"]})
                
                # Test landing page
                self.page.goto(UI_URL)
                self.page.wait_for_load_state("networkidle")
                time.sleep(1)
                
                screenshot_path = self.screenshots_dir / f"responsive_{viewport['name']}.png"
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                
                prompt = f"""
                Evaluate this page at {viewport['name']} size ({viewport['width']}x{viewport['height']}):
                1. Is there no horizontal scrolling?
                2. Are elements properly sized for this viewport?
                3. Is text readable without zooming?
                4. Are interactive elements (buttons, inputs) accessible and properly sized?
                5. Does the layout adapt well to this screen size?
                6. Are touch targets at least 44x44 pixels (for mobile)?
                7. Is the content well-organized for this screen size?
                """
                
                if self.test_visual(f"Responsive {viewport['name']}", screenshot_path, prompt, threshold=0.7, test_type="responsive"):
                    passed += 1
            
            logger.info(f"  Responsive tests: {passed}/{len(viewports)} passed")
            return passed == len(viewports)
        except Exception as e:
            logger.error(f"  ❌ Responsive design test failed: {e}")
            return False
    
    def test_accessibility_visual(self):
        """Test visual accessibility across pages."""
        logger.info("Testing: Visual accessibility...")
        try:
            # Test on landing page
            self.page.goto(UI_URL)
            self.page.wait_for_load_state("networkidle")
            time.sleep(1)
            
            screenshot_path = self.screenshots_dir / "accessibility_check.png"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            
            prompt = """
            Evaluate this interface for visual accessibility:
            1. Does text have sufficient contrast against background (WCAG AA)?
            2. Are interactive elements clearly visible and distinguishable?
            3. Are focus indicators visible when elements are focused?
            4. Are touch targets at least 44x44 pixels?
            5. Is there clear visual hierarchy?
            6. Are related elements grouped visually?
            7. Is color used appropriately (not as only indicator)?
            8. Are error states clearly indicated?
            """
            
            return self.test_visual("Accessibility", screenshot_path, prompt, threshold=0.7, test_type="accessibility")
        except Exception as e:
            logger.error(f"  ❌ Accessibility test failed: {e}")
            return False
    
    def run_all_tests(self):
        """Run all visual tests."""
        if not HAS_PLAYWRIGHT:
            logger.error("Playwright not available. Install with: uv add playwright")
            return False
        
        if not check_ai_visual_test_installed():
            logger.warning("⚠️  @arclabs561/ai-visual-test not installed")
            logger.info("  💡 Install with: npm install -g @arclabs561/ai-visual-test")
            logger.info("  💡 Or run: ./scripts/e2e_testing/setup_visual_tests.sh")
            return False
        
        if not get_vlm_api_key():
            logger.warning("⚠️  No VLM API key found")
            logger.info("  💡 Set GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY")
            return False
        
        # Wait for API
        if not wait_for_api(max_retries=30, timeout=TIMEOUTS["fast"]):
            logger.error("API not ready")
            return False
        
        logger.info("=" * 70)
        logger.info("ALL PAGES VISUAL E2E TESTS (AI-Powered)")
        logger.info("=" * 70)
        logger.info("")
        
        try:
            with sync_playwright() as p:
                self.browser = p.chromium.launch(headless=True)
                context = self.browser.new_context()
                
                # Set up API routing
                setup_playwright_routing(context)
                
                self.page = context.new_page()
                
                # Inject API_BASE override
                inject_api_base(self.page)
                self.page.set_viewport_size({"width": 1920, "height": 1080})
                
                # Run tests
                self.test_feature("Landing page visual", self.test_landing_page)
                self.test_feature("Search page with results", self.test_search_page_loaded)
                self.test_feature("Review page initial", self.test_review_page_initial)
                self.test_feature("Review page with similarities", self.test_review_page_loaded)
                self.test_feature("Responsive design", self.test_responsive_design)
                self.test_feature("Visual accessibility", self.test_accessibility_visual)
                
                self.browser.close()
        except Exception as e:
            logger.error(f"❌ Browser test failed: {e}")
            if self.browser:
                self.browser.close()
            return False
        
        # Summary
        logger.info("")
        logger.info("=" * 70)
        logger.info("TEST SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Tests run: {self.results['tests_run']}")
        logger.info(f"Tests passed: {self.results['tests_passed']}")
        logger.info(f"Tests failed: {self.results['tests_failed']}")
        logger.info("")
        logger.info(f"Visual tests run: {self.results['visual_tests_run']}")
        logger.info(f"Visual tests passed: {self.results['visual_tests_passed']}")
        logger.info("")
        logger.info(f"Screenshots saved to: {self.screenshots_dir}")
        
        if self.results["issues"]:
            logger.info("")
            logger.info("Issues:")
            for issue in self.results["issues"]:
                logger.info(f"  - {issue}")
        
        return self.results["tests_failed"] == 0


def main():
    """Main entry point."""
    tester = AllPagesVisualTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

