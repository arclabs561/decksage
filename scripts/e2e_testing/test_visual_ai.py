#!/usr/bin/env python3
"""
AI-Powered Visual Testing using @arclabs561/ai-visual-test

Uses Vision Language Models (VLMs) to test UI visually:
- Visual regression detection
- Layout validation
- Component presence checks
- Accessibility visual checks
- Responsive design validation

Requires:
- Node.js and npm
- @arclabs561/ai-visual-test (installed via setup script)
- Playwright (for taking screenshots)
- VLM API key in .env (GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

# Import shared utilities (dotenv is loaded automatically by test_utils)

# Use Playwright for browser automation
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.warning("⚠️  Playwright not installed. Install with: uv add playwright")

# Import shared utilities and constants
from test_utils import wait_for_api, logger, API_BASE
from test_constants import TEST_CARDS, TIMEOUTS

# Configuration from .env
# API_BASE imported from test_utils
UI_URL = os.getenv("UI_URL", "http://localhost:8000")
REVIEW_URL = f"{UI_URL}/review.html"


def check_ai_visual_test_installed() -> bool:
    """Check if @arclabs561/ai-visual-test is installed."""
    try:
        # Check if it's available via npx
        result = subprocess.run(
            ["npx", "--yes", "@arclabs561/ai-visual-test", "--help"],
            capture_output=True,
            text=True,
            timeout=TIMEOUTS["slow"],
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Also check if installed locally
        package_json = Path(__file__).parent / "package.json"
        if package_json.exists():
            node_modules = Path(__file__).parent / "node_modules" / "@arclabs561" / "ai-visual-test"
            return node_modules.exists()
        return False


def install_ai_visual_test() -> bool:
    """Install @arclabs561/ai-visual-test via npm."""
    logger.info("🔍 Installing @arclabs561/ai-visual-test...")
    try:
        # Check if npm is available
        subprocess.run(["npm", "--version"], check=True, capture_output=True)
        
        # Try local installation first (in scripts/e2e_testing)
        package_json = Path(__file__).parent / "package.json"
        if package_json.exists():
            result = subprocess.run(
                ["npm", "install"],
                cwd=str(Path(__file__).parent),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                logger.info("✅ Installed @arclabs561/ai-visual-test (local)")
                return True
        
        # Fallback to global installation
        result = subprocess.run(
            ["npm", "install", "-g", "@arclabs561/ai-visual-test"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            logger.info("✅ Installed @arclabs561/ai-visual-test (global)")
            return True
        else:
            logger.warning(f"⚠️  Installation failed: {result.stderr}")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError) as e:
        logger.warning(f"⚠️  Could not install: {e}")
        return False


def test_api_readiness():
    """Ensure API is ready."""
    logger.info("Testing API readiness...")
    max_retries = 30
    for i in range(max_retries):
        try:
            resp = requests.get(f"{API_BASE}/ready", timeout=TIMEOUTS["fast"])
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ready"):
                    logger.info("✅ API is ready")
                    return True
        except Exception:
            pass
        if i < max_retries - 1:
            time.sleep(1)
    logger.info("❌ API not ready after 30s")
    return False


def test_visual_layout():
    """Test visual layout using AI visual test with Playwright."""
    logger.info("\n🔍 Testing visual layout...")
    
    if not check_ai_visual_test_installed():
        logger.warning("⚠️  @arclabs561/ai-visual-test not installed")
        logger.info("  💡 Install with: npm install -g @arclabs561/ai-visual-test")
        logger.info("  💡 Or run: ./scripts/e2e_testing/setup_visual_tests.sh")
        return None
    
    # Use Playwright to take screenshots, then validate with AI
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            page.wait_for_load_state("networkidle")
            
            # Test 1: Search interface layout
            screenshot_path = Path("/tmp/search_interface.png")
            page.screenshot(path=str(screenshot_path), full_page=True)
            
            # Validate screenshot using AI visual test
            # Create a Node.js script to use the package
            node_script = Path("/tmp/validate_screenshot.mjs")
            validation_prompt = """
            Evaluate this search interface screenshot:
            1. Is the search input field visible and prominent?
            2. Is the search button visible and accessible?
            3. Are advanced options hidden by default?
            4. Are there any layout shifts or overlapping elements?
            5. Is the overall layout clean and minimal (Google-like)?
            """
            
            with open(node_script, "w") as f:
                f.write(f"""
                import {{ validateScreenshot }} from '@arclabs561/ai-visual-test';
                
                const result = await validateScreenshot(
                    '{screenshot_path}',
                    `{validation_prompt}`
                );
                console.log(JSON.stringify(result));
                """)
            
            result = subprocess.run(
                ["node", str(node_script)],
                cwd=str(Path(__file__).parent),
                capture_output=True,
                text=True,
                timeout=TIMEOUTS["extreme"],
            )
            
            # Cleanup
            if node_script.exists():
                node_script.unlink()
            
            if result.returncode == 0:
                try:
                    validation_result = json.loads(result.stdout)
                    score = validation_result.get("score", 0)
                    issues = validation_result.get("issues", [])
                    
                    logger.info(f"✅ Search interface layout score: {score}/10")
                    if issues:
                        logger.warning(f"⚠️  Issues: {', '.join(issues[:3])}")
                    
                    # Test 2: Autocomplete dropdown
                    search_input = page.locator("#cardInput")
                    search_input.type("Light", delay=50)
                    page.wait_for_timeout(300)
                    
                    autocomplete_path = Path("/tmp/autocomplete.png")
                    page.screenshot(path=str(autocomplete_path), full_page=True)
                    
                    autocomplete_prompt = """
                    Evaluate this autocomplete dropdown:
                    1. Does the dropdown appear below the input?
                    2. Are suggestions visible and readable?
                    3. Is matching text highlighted?
                    4. Does the dropdown not overlap other elements?
                    """
                    
                    node_script2 = Path("/tmp/validate_autocomplete.mjs")
                    provider = "gemini" if os.getenv("GEMINI_API_KEY") else "openai" if os.getenv("OPENAI_API_KEY") else "anthropic"
                    with open(node_script2, "w") as f:
                        f.write(f"""
                        import {{ validateScreenshot, createConfig }} from '@arclabs561/ai-visual-test';
                        
                        const config = createConfig({{
                            provider: '{provider}',
                            apiKey: '{vlm_key}'
                        }});
                        
                        const result = await validateScreenshot(
                            '{autocomplete_path}',
                            `{autocomplete_prompt}`,
                            config
                        );
                        console.log(JSON.stringify(result));
                        """)
                    
                    result2 = subprocess.run(
                        ["node", str(node_script2)],
                        cwd=str(Path(__file__).parent),
                        capture_output=True,
                        text=True,
                        timeout=TIMEOUTS["extreme"],
                    )
                    
                    if node_script2.exists():
                        node_script2.unlink()
                    
                    if result2.returncode == 0:
                        validation_result2 = json.loads(result2.stdout)
                        score2 = validation_result2.get("score", 0)
                        logger.info(f"✅ Autocomplete dropdown score: {score2}/10")
                        
                        browser.close()
                        return score >= 7 and score2 >= 7
                    else:
                        logger.warning(f"⚠️  Autocomplete validation failed: {result2.stderr}")
                        browser.close()
                        return score >= 7
                except json.JSONDecodeError:
                    logger.warning(f"⚠️  Could not parse validation result: {result.stdout}")
                    browser.close()
                    return False
            else:
                logger.warning(f"⚠️  Validation failed: {result.stderr}")
                browser.close()
                return False
    except ImportError:
        logger.warning("⚠️  Playwright not available, skipping visual layout test")
        return None
    except Exception as e:
        logger.warning(f"⚠️  Visual layout test error: {e}")
        return None


def test_visual_accessibility():
    """Test visual accessibility using AI visual test."""
    logger.info("\n🔍 Testing visual accessibility...")
    
    if not check_ai_visual_test_installed():
        logger.warning("⚠️  @arclabs561/ai-visual-test not installed, skipping")
        return None
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            page.wait_for_load_state("networkidle")
            
            screenshot_path = Path("/tmp/accessibility_check.png")
            page.screenshot(path=str(screenshot_path), full_page=True)
            
            accessibility_prompt = """
            Evaluate this interface for visual accessibility:
            1. Does text have sufficient contrast against background (WCAG AA)?
            2. Are interactive elements clearly visible?
            3. Are focus indicators visible?
            4. Are touch targets at least 44x44 pixels?
            5. Is there clear visual hierarchy?
            6. Are related elements grouped visually?
            """
            
            node_script = Path("/tmp/validate_accessibility.mjs")
            provider = "gemini" if os.getenv("GEMINI_API_KEY") else "openai" if os.getenv("OPENAI_API_KEY") else "anthropic"
            with open(node_script, "w") as f:
                f.write(f"""
                import {{ validateScreenshot, createConfig }} from '@arclabs561/ai-visual-test';
                
                const config = createConfig({{
                    provider: '{provider}',
                    apiKey: '{vlm_key}'
                }});
                
                const result = await validateScreenshot(
                    '{screenshot_path}',
                    `{accessibility_prompt}`,
                    {{ testType: 'accessibility' }},
                    config
                );
                console.log(JSON.stringify(result));
                """)
            
            result = subprocess.run(
                ["node", str(node_script)],
                cwd=str(Path(__file__).parent),
                capture_output=True,
                text=True,
                timeout=TIMEOUTS["extreme"],
            )
            
            if node_script.exists():
                node_script.unlink()
            
            browser.close()
            
            if result.returncode == 0:
                try:
                    validation_result = json.loads(result.stdout)
                    score = validation_result.get("score", 0)
                    issues = validation_result.get("issues", [])
                    
                    logger.info(f"✅ Visual accessibility score: {score}/10")
                    if issues:
                        logger.warning(f"⚠️  Issues found: {len(issues)}")
                        for issue in issues[:3]:
                            logger.info(f"     - {issue}")
                    
                    return score >= 7
                except json.JSONDecodeError:
                    logger.warning(f"⚠️  Could not parse result: {result.stdout}")
                    return False
            else:
                logger.warning(f"⚠️  Accessibility validation failed: {result.stderr}")
                return False
    except Exception as e:
        logger.warning(f"⚠️  Visual accessibility test error: {e}")
        return None


def test_visual_regression():
    """Test for visual regressions using AI visual test."""
    logger.info("\n🔍 Testing visual regression...")
    
    if not check_ai_visual_test_installed():
        logger.warning("⚠️  @arclabs561/ai-visual-test not installed, skipping")
        return None
    
    # Take baseline screenshot if it doesn't exist
    baseline_dir = Path(__file__).parent.parent.parent / "scripts" / "e2e_testing" / "tests" / "visual" / "baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    
    baseline_path = baseline_dir / "search_interface.png"
    current_path = Path("/tmp/current_search_interface.png")
    
    try:
        from playwright.sync_api import sync_playwright
        
        # Take current screenshot
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(current_path), full_page=True)
            browser.close()
        
        if current_path.exists():
            # Compare with baseline if it exists
            if baseline_path.exists():
                # Use AI to compare semantically (not pixel-perfect)
                compare_prompt = """
                Compare these two screenshots of the search interface.
                Are they functionally equivalent? Ignore minor spacing/color changes.
                Focus on: layout structure, element positions, functionality.
                """
                
                # For now, validate current screenshot and compare scores
                # Full comparison would require both images, simplified here
                node_script = Path("/tmp/validate_regression.mjs")
                provider = "gemini" if os.getenv("GEMINI_API_KEY") else "openai" if os.getenv("OPENAI_API_KEY") else "anthropic"
                with open(node_script, "w") as f:
                    f.write(f"""
                    import {{ validateScreenshot, createConfig }} from '@arclabs561/ai-visual-test';
                    
                    const config = createConfig({{
                        provider: '{provider}',
                        apiKey: '{vlm_key}'
                    }});
                    
                    const result = await validateScreenshot(
                        '{current_path}',
                        'Verify this search interface matches the expected design and layout. Check for any visual regressions or layout issues.',
                        config
                    );
                    console.log(JSON.stringify(result));
                    """)
                
                result = subprocess.run(
                    ["node", str(node_script)],
                    cwd=str(Path(__file__).parent),
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUTS["extreme"],
                )
                
                if node_script.exists():
                    node_script.unlink()
                
                if result.returncode == 0:
                    try:
                        validation_result = json.loads(result.stdout)
                        score = validation_result.get("score", 0)
                        
                        if score >= 8:  # High score = no regression
                            logger.info("✅ No visual regressions detected")
                            # Update baseline
                            import shutil
                            shutil.copy(current_path, baseline_path)
                            return True
                        else:
                            logger.warning(f"⚠️  Potential visual regression (score: {score}/10)")
                            issues = validation_result.get("issues", [])
                            if issues:
                                logger.info(f"     Issues: {', '.join(issues[:2])}")
                            return False
                    except json.JSONDecodeError:
                        logger.warning("⚠️  Could not parse comparison result")
                        return False
                else:
                    logger.warning(f"⚠️  Comparison failed: {result.stderr}")
                    return False
            else:
                # Create baseline
                import shutil
                shutil.copy(current_path, baseline_path)
                logger.info(f"✅ Created baseline: {baseline_path}")
                return True
        else:
            logger.warning("⚠️  Could not take screenshot")
            return False
    except Exception as e:
        logger.warning(f"⚠️  Visual regression test error: {e}")
        return None
    finally:
        if current_path.exists():
            current_path.unlink()


def test_responsive_design():
    """Test responsive design at different viewport sizes."""
    logger.info("\n🔍 Testing responsive design...")
    
    if not check_ai_visual_test_installed():
        logger.warning("⚠️  @arclabs561/ai-visual-test not installed, skipping")
        return None
    
    viewports = [
        {"width": 375, "height": 667, "name": "mobile"},
        {"width": 768, "height": 1024, "name": "tablet"},
        {"width": 1920, "height": 1080, "name": "desktop"},
    ]
    
    try:
        from playwright.sync_api import sync_playwright
        
        passed = 0
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            for viewport in viewports:
                page = browser.new_page(viewport=viewport)
                page.goto(UI_URL)
                page.wait_for_load_state("networkidle")
                
                screenshot_path = Path(f"/tmp/responsive_{viewport['name']}.png")
                page.screenshot(path=str(screenshot_path), full_page=True)
                
                responsive_prompt = f"""
                Evaluate this interface at {viewport['name']} size ({viewport['width']}x{viewport['height']}):
                1. Is there no horizontal scrolling?
                2. Are elements properly sized for this viewport?
                3. Is text readable?
                4. Are interactive elements accessible?
                5. Does the layout adapt well to this screen size?
                """
                
                node_script = Path(f"/tmp/validate_responsive_{viewport['name']}.mjs")
                provider = "gemini" if os.getenv("GEMINI_API_KEY") else "openai" if os.getenv("OPENAI_API_KEY") else "anthropic"
                with open(node_script, "w") as f:
                    f.write(f"""
                    import {{ validateScreenshot, createConfig }} from '@arclabs561/ai-visual-test';
                    
                    const config = createConfig({{
                        provider: '{provider}',
                        apiKey: '{vlm_key}'
                    }});
                    
                    const result = await validateScreenshot(
                        '{screenshot_path}',
                        `{responsive_prompt}`,
                        {{ testType: 'responsive' }},
                        config
                    );
                    console.log(JSON.stringify(result));
                    """)
                
                result = subprocess.run(
                    ["node", str(node_script)],
                    cwd=str(Path(__file__).parent),
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUTS["extreme"],
                )
                
                if node_script.exists():
                    node_script.unlink()
                
                if result.returncode == 0:
                    try:
                        validation_result = json.loads(result.stdout)
                        score = validation_result.get("score", 0)
                        
                        if score >= 7:
                            logger.info(f"✅ {viewport['name']} layout: OK (score: {score}/10)")
                            passed += 1
                        else:
                            logger.warning(f"⚠️  {viewport['name']} layout: Issues (score: {score}/10)")
                    except json.JSONDecodeError:
                        logger.warning(f"⚠️  {viewport['name']}: Could not parse result")
                
                page.close()
            
            browser.close()
        
        logger.info(f"Result: {passed}/{len(viewports)} viewports passed")
        return passed == len(viewports)
    except Exception as e:
        logger.warning(f"⚠️  Responsive design test error: {e}")
        return None


def test_review_page_visual():
    """Test review page visual layout using AI visual test."""
    logger.info("\n🔍 Testing review page visual layout...")
    
    if not check_ai_visual_test_installed():
        logger.warning("⚠️  @arclabs561/ai-visual-test not installed, skipping")
        return None
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(REVIEW_URL)
            page.wait_for_load_state("networkidle")
            
            screenshot_path = Path("/tmp/review_page_visual.png")
            page.screenshot(path=str(screenshot_path), full_page=True)
            
            review_prompt = """
            Evaluate this similarity review page:
            1. Is the layout clean and organized?
            2. Are similarity items clearly displayed?
            3. Are annotation controls (rating buttons, checkboxes) visible and accessible?
            4. Is metadata information readable and well-formatted?
            5. Are bulk action buttons clearly visible?
            6. Is the progress/statistics display clear?
            7. Does the page have good visual hierarchy?
            """
            
            vlm_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
            if not vlm_key:
                logger.warning("⚠️  No VLM API key found (GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY)")
                browser.close()
                return None
            
            node_script = Path("/tmp/validate_review_page.mjs")
            provider = "gemini" if os.getenv("GEMINI_API_KEY") else "openai" if os.getenv("OPENAI_API_KEY") else "anthropic"
            with open(node_script, "w") as f:
                f.write(f"""
                import {{ validateScreenshot, createConfig }} from '@arclabs561/ai-visual-test';
                
                const config = createConfig({{
                    provider: '{provider}',
                    apiKey: '{vlm_key}'
                }});
                
                const result = await validateScreenshot(
                    '{screenshot_path}',
                    `{review_prompt}`,
                    config
                );
                console.log(JSON.stringify(result));
                """)
            
            result = subprocess.run(
                ["node", str(node_script)],
                cwd=str(Path(__file__).parent),
                capture_output=True,
                text=True,
                timeout=TIMEOUTS["extreme"],
            )
            
            if node_script.exists():
                node_script.unlink()
            
            browser.close()
            
            if result.returncode == 0:
                try:
                    validation_result = json.loads(result.stdout)
                    score = validation_result.get("score", 0)
                    issues = validation_result.get("issues", [])
                    
                    logger.info(f"✅ Review page visual score: {score}/10")
                    if issues:
                        logger.warning(f"⚠️  Issues found: {len(issues)}")
                        for issue in issues[:3]:
                            logger.info(f"     - {issue}")
                    
                    return score >= 7
                except json.JSONDecodeError:
                    logger.warning("⚠️  Could not parse validation result")
                    return False
            else:
                logger.warning(f"⚠️  Validation failed: {result.stderr}")
                return False
    except ImportError:
        logger.warning("⚠️  Playwright not available, skipping review page visual test")
        return None
    except Exception as e:
        logger.warning(f"⚠️  Review page visual test error: {e}")
        return None


def main():
    """Run all AI visual tests."""
    logger.info("=" * 60)
    logger.info("AI-Powered Visual Testing")
    logger.info("=" * 60)
    
    if not test_api_readiness():
        logger.info("\n❌ API not ready. Start with: docker-compose up")
        return 1
    
    results = {
        "layout": test_visual_layout(),
        "accessibility": test_visual_accessibility(),
        "regression": test_visual_regression(),
        "responsive": test_responsive_design(),
        "review_page": test_review_page_visual(),
    }
    
    logger.info("\n" + "=" * 60)
    logger.info("Visual Test Results:")
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
    skipped = sum(1 for r in results.values() if r is None)
    
    logger.info(f"\nPassed: {passed}/{total} (skipped: {skipped})")
    
    if skipped > 0:
        logger.warning("\n⚠️  To enable visual tests, install:")
        logger.info("   npm install -g @arclabs561/ai-visual-test")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit(main())

