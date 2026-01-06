#!/usr/bin/env python3
"""
Visual Regression Tests using @arclabs561/ai-visual-test

Tests visual consistency across pages and detects regressions.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Import shared utilities (dotenv is loaded automatically by test_utils)
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
    logger.error("⚠️  Playwright not installed. Install with: uv add playwright")


def check_ai_visual_test_installed() -> bool:
    """Check if @arclabs561/ai-visual-test is installed."""
    test_dir = Path(__file__).parent
    node_modules = test_dir / "node_modules" / "@arclabs561" / "ai-visual-test"
    if node_modules.exists():
        return True
    
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


def test_visual_regression(
    screenshot_path: Path,
    baseline_path: Path | None,
    prompt: str,
    threshold: float = 0.8,
) -> dict[str, Any]:
    """
    Test screenshot for visual regression.
    
    Args:
        screenshot_path: Path to current screenshot
        baseline_path: Path to baseline screenshot (optional)
        prompt: Prompt for AI evaluation
        threshold: Minimum score to pass (0-1)
    
    Returns:
        Dict with score, passed, issues, etc.
    """
    vlm_info = get_vlm_api_key()
    if not vlm_info:
        logger.warning("⚠️  No VLM API key found - skipping visual regression test")
        return {"score": 0, "passed": False, "error": "No API key"}
    
    provider, api_key = vlm_info
    
    test_dir = Path(__file__).parent
    # Use tempfile for automatic cleanup
    import tempfile
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.mjs', delete=False, dir=str(test_dir))
    node_script = Path(temp_file.name)
    temp_file.close()
    try:
        baseline_arg = f"'{baseline_path}'" if baseline_path and baseline_path.exists() else "null"
        
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
        {{
            testType: 'regression',
            baseline: {baseline_arg}
        }},
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


class VisualRegressionTester:
    """Visual regression tester for all UI pages."""
    
    def __init__(self):
        self.results = {
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "issues": [],
        }
        self.screenshots_dir = Path("/tmp/visual_regression")
        self.screenshots_dir.mkdir(exist_ok=True)
        self.baselines_dir = Path(__file__).parent / "tests" / "visual" / "baselines"
        self.baselines_dir.mkdir(parents=True, exist_ok=True)
        self.page = None
        self.browser = None
    
    def test_page(self, name: str, url: str, baseline_name: str, prompt: str):
        """Test a page for visual regression."""
        self.results["tests_run"] += 1
        try:
            self.page.goto(url)
            self.page.wait_for_load_state("networkidle")
            time.sleep(1)  # Let page settle
            
            screenshot_path = self.screenshots_dir / f"{baseline_name}_current.png"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            
            baseline_path = self.baselines_dir / f"{baseline_name}_baseline.png"
            
            result = test_visual_regression(
                screenshot_path,
                baseline_path if baseline_path.exists() else None,
                prompt,
                threshold=0.8,
            )
            
            if result.get("passed", False):
                self.results["tests_passed"] += 1
                logger.info(f"✅ {name} (score: {result['score']:.2f})")
                return True
            else:
                self.results["tests_failed"] += 1
                score = result.get("score", 0)
                issues = result.get("issues", [])
                logger.warning(f"⚠️  {name} failed (score: {score:.2f})")
                if issues:
                    for issue in issues[:3]:
                        logger.info(f"     - {issue}")
                self.results["issues"].append(f"{name}: {result.get('error', 'Low score')}")
                return False
        except Exception as e:
            self.results["tests_failed"] += 1
            self.results["issues"].append(f"{name}: {str(e)}")
            logger.error(f"❌ {name} (error: {e})")
            return False
    
    def run_all_tests(self):
        """Run all visual regression tests."""
        if not HAS_PLAYWRIGHT:
            logger.error("Playwright not available. Install with: uv add playwright")
            return False
        
        if not check_ai_visual_test_installed():
            logger.warning("⚠️  @arclabs561/ai-visual-test not installed")
            logger.info("  💡 Install with: npm install -g @arclabs561/ai-visual-test")
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
        logger.info("VISUAL REGRESSION TESTS")
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
                
                # Test landing page
                self.test_page(
                    "Landing page",
                    UI_URL,
                    "landing",
                    "Check for visual regressions: layout, colors, typography, spacing, component positions",
                )
                
                # Test search page
                self.test_page(
                    "Search page",
                    f"{UI_URL}/search.html",
                    "search",
                    "Check for visual regressions: search form, layout, styling consistency",
                )
                
                # Test review page
                self.test_page(
                    "Review page",
                    f"{UI_URL}/review.html",
                    "review",
                    "Check for visual regressions: form layout, controls, rating scale display",
                )
                
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
        logger.info(f"Screenshots saved to: {self.screenshots_dir}")
        
        if self.results["issues"]:
            logger.info("")
            logger.info("Issues:")
            for issue in self.results["issues"]:
                logger.info(f"  - {issue}")
        
        return self.results["tests_failed"] == 0


def main():
    """Main entry point."""
    tester = VisualRegressionTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

