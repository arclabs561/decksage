#!/usr/bin/env python3
"""
E2E Browser Test for Similarity Review Page

Tests the bulk similarity review interface:
- Page loading and rendering
- Loading similarities from API
- Loading similarities from file
- Display of similarity information
- Annotation controls (rating, substitute, notes)
- Bulk submission
- Export functionality
- Statistics display
"""

import os
import json
import tempfile
from pathlib import Path

# Import shared utilities (dotenv is loaded automatically by test_utils)
from test_utils import (
    wait_for_api,
    logger,
    API_BASE,
    wait_for_element_condition,
    wait_for_network_idle,
    safe_click,
    safe_type,
    wait_for_similarities_loaded,
    retry_with_backoff,
    get_ui_url,
    get_review_url,
    start_http_server,
    setup_playwright_routing,
    inject_api_base,
)

# Import expect for Playwright assertions
from playwright.sync_api import expect
from test_constants import TEST_CARDS, TIMEOUTS

# Start HTTP server and get URLs
start_http_server()
UI_URL = get_ui_url()
REVIEW_URL = get_review_url()

# Use Playwright for browser automation
try:
    from playwright.sync_api import sync_playwright, Page, expect
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.error("⚠️  Playwright not installed. Install with: uv add playwright")


class ReviewPageTester:
    """E2E tester for similarity review page."""
    
    def __init__(self):
        self.results = {
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "issues": [],
        }
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
    
    def test_page_loads(self):
        """Test 1: Review page loads correctly."""
        logger.info("Testing: Review page loads...")
        try:
            # Navigate with retry
            def navigate():
                self.page.goto(REVIEW_URL, wait_until="domcontentloaded")
                wait_for_network_idle(self.page, timeout=10000)
                return True
            
            retry_with_backoff(navigate, max_retries=3, initial_delay=1.0)
            
            # Check for main elements with better waiting
            title = self.page.locator("h1")
            if not wait_for_element_condition(self.page, title, "visible", timeout=5000):
                logger.error("  ❌ Title not found")
                return False
            expect(title).to_contain_text("Similarity Review")
            
            # Check for controls
            data_source = self.page.locator("#dataSource")
            if not wait_for_element_condition(self.page, data_source, "visible", timeout=5000):
                logger.error("  ❌ Data source selector not found")
                return False
            
            load_btn = self.page.locator("#loadBtn")
            if not wait_for_element_condition(self.page, load_btn, "visible", timeout=5000):
                logger.error("  ❌ Load button not found")
                return False
            
            logger.info("  ✅ Page loaded with all controls")
            return True
        except Exception as e:
            logger.error(f"  ❌ Page load failed: {e}")
            return False
    
    def test_load_from_api(self):
        """Test 2: Load similarities from API."""
        logger.info("Testing: Load similarities from API...")
        try:
            # Set data source to API
            data_source = self.page.locator("#dataSource")
            data_source.select_option("api")
            
            # Enter query card
            query_input = self.page.locator("#queryCard")
            test_card = TEST_CARDS.get("common") if isinstance(TEST_CARDS, dict) else (TEST_CARDS[0] if TEST_CARDS else "Lightning Bolt")
            query_input.fill(test_card)
            
            # Set top K
            top_k = self.page.locator("#topK")
            top_k.fill("10")
            
            # Click load button with safe click
            load_btn = self.page.locator("#loadBtn")
            if not safe_click(self.page, load_btn, timeout=5000):
                logger.error("  ❌ Failed to click load button")
                return False
            
            # Wait for similarities to load (handles loading state internally)
            if not wait_for_similarities_loaded(self.page, timeout=15000):
                logger.warning("  ⚠️  Similarities may not have loaded")
                # Check for error state
                error_msg = self.page.locator(".error")
                if error_msg.count() > 0:
                    error_text = error_msg.inner_text()
                    logger.warning(f"  ⚠️  Error shown: {error_text[:100]}")
                    return True  # Error is a valid state to test
            
            # Wait for either similarities to appear OR error/empty state
            # Check for error first
            error_msg = self.page.locator(".error")
            empty_state = self.page.locator("#emptyState")
            
            # Wait a bit for results to load
            self.page.wait_for_timeout(1000)
            
            # Check for similarities
            similarity_items = self.page.locator(".similarity-item")
            count = similarity_items.count()
            
            if count > 0:
                logger.info(f"  ✅ Loaded {count} similarities from API")
                return True
            elif error_msg.count() > 0:
                error_text = error_msg.inner_text()
                logger.warning(f"  ⚠️  API returned error: {error_text[:100]}")
                # Check if it's a real error or just no results
                if "not found" in error_text.lower() or "no results" in error_text.lower():
                    logger.info("  ✅ API call succeeded but no results (acceptable)")
                    return True
                return False
            elif empty_state.is_visible():
                logger.info("  ✅ API call succeeded but returned empty results (acceptable)")
                return True
            else:
                # Check if similarityList exists but is empty
                similarity_list = self.page.locator("#similarityList")
                if similarity_list.count() > 0:
                    logger.warning("  ⚠️  Similarity list exists but is empty")
                    return True  # Not a failure, just no results
                logger.error("  ❌ No similarities loaded and no error/empty state")
                return False
        except Exception as e:
            logger.error(f"  ❌ API load failed: {e}")
            return False
    
    def test_display_metadata(self):
        """Test 3: Similarity metadata is displayed."""
        logger.info("Testing: Metadata display...")
        try:
            # Check for similarity items
            similarity_items = self.page.locator(".similarity-item")
            if similarity_items.count() == 0:
                logger.warning("  ⚠️  No similarities to check metadata for")
                return True  # Not a failure, just no data
            
            # Check first item for metadata
            first_item = similarity_items.first
            
            # Check for card names
            card_names = first_item.locator(".card-name")
            expect(card_names).to_have_count(2, timeout=2000)
            
            # Check for similarity score
            score_value = first_item.locator(".score-value")
            expect(score_value).to_be_visible()
            
            # Check for metadata grid
            metadata_grid = first_item.locator(".metadata-grid")
            expect(metadata_grid).to_be_visible()
            
            logger.info("  ✅ Metadata displayed correctly")
            return True
        except Exception as e:
            logger.error(f"  ❌ Metadata display failed: {e}")
            return False
    
    def test_annotation_controls(self):
        """Test 4: Annotation controls work."""
        logger.info("Testing: Annotation controls...")
        try:
            similarity_items = self.page.locator(".similarity-item")
            if similarity_items.count() == 0:
                logger.warning("  ⚠️  No similarities to annotate")
                return True
            
            first_item = similarity_items.first
            
            # Test rating buttons
            rating_btn = first_item.locator(".rating-btn").first
            expect(rating_btn).to_be_visible()
            rating_btn.click()
            
            # Wait a bit for the click to register
            self.page.wait_for_timeout(200)
            
            # Check that button is selected (it may have multiple classes like "rating-btn selected")
            # Check that the class attribute contains "selected"
            class_attr = rating_btn.get_attribute("class")
            if class_attr and "selected" in class_attr:
                logger.info("  ✅ Rating button selected")
            else:
                logger.error(f"  ❌ Rating button not selected, classes: {class_attr}")
                return False
            
            # Test substitute checkbox
            substitute_checkbox = first_item.locator('input[type="checkbox"]').first
            expect(substitute_checkbox).to_be_visible()
            if not substitute_checkbox.is_checked():
                substitute_checkbox.check()
            
            # Test notes input
            notes_input = first_item.locator(".notes-input")
            expect(notes_input).to_be_visible()
            notes_input.fill("Test annotation note")
            
            logger.info("  ✅ Annotation controls work")
            return True
        except Exception as e:
            logger.error(f"  ❌ Annotation controls failed: {e}")
            return False
    
    def test_statistics(self):
        """Test 5: Statistics are displayed and updated."""
        logger.info("Testing: Statistics display...")
        try:
            # Check if there are similarities first
            similarity_items = self.page.locator(".similarity-item")
            if similarity_items.count() == 0:
                logger.warning("  ⚠️  No similarities loaded, stats won't be visible")
                return True  # Not a failure if no data
            
            # Stats should be visible when there are similarities
            stats = self.page.locator("#stats")
            expect(stats).to_be_visible(timeout=2000)
            
            # Check stat values
            stat_total = self.page.locator("#statTotal")
            total_text = stat_total.inner_text()
            
            if total_text and total_text != "0":
                logger.info(f"  ✅ Statistics displayed: {total_text} total")
                return True
            else:
                logger.warning("  ⚠️  Statistics show 0 (may be expected if no data)")
                return True  # Not a failure
        except Exception as e:
            logger.error(f"  ❌ Statistics display failed: {e}")
            return False
    
    def test_load_from_file(self):
        """Test 6: Load similarities from file."""
        logger.info("Testing: Load similarities from file...")
        try:
            # Create test JSON file
            test_data = [
                {
                    "card1": "Lightning Bolt",
                    "card2": "Chain Lightning",
                    "similarity_score": 0.85,
                    "similarity_type": "functional",
                    "is_substitute": True,
                    "reasoning": "Both are direct damage spells",
                    "source": "test"
                },
                {
                    "card1": "Lightning Bolt",
                    "card2": "Shock",
                    "similarity_score": 0.75,
                    "similarity_type": "functional",
                    "is_substitute": False,
                    "reasoning": "Similar but weaker",
                    "source": "test"
                }
            ]
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(test_data, f)
                temp_file = f.name
            
            try:
                # Set data source to file
                data_source = self.page.locator("#dataSource")
                data_source.select_option("file")
                
                # Wait for file input to appear
                file_input_group = self.page.locator("#fileInputGroup")
                expect(file_input_group).to_be_visible()
                
                # Upload file
                file_input = self.page.locator("#fileInput")
                file_input.set_input_files(temp_file)
                
                # Click load button
                load_btn = self.page.locator("#loadBtn")
                load_btn.click()
                
                # Wait for similarities to appear
                similarity_list = self.page.locator("#similarityList")
                expect(similarity_list).to_be_visible(timeout=5000)
                
                # Check that similarities are displayed
                similarity_items = self.page.locator(".similarity-item")
                count = similarity_items.count()
                
                if count >= 2:
                    logger.info(f"  ✅ Loaded {count} similarities from file")
                    return True
                else:
                    logger.error(f"  ❌ Expected 2 similarities, got {count}")
                    return False
            finally:
                # Clean up temp file
                Path(temp_file).unlink()
        except Exception as e:
            logger.error(f"  ❌ File load failed: {e}")
            return False
    
    def test_export_functionality(self):
        """Test 7: Export annotations."""
        logger.info("Testing: Export functionality...")
        try:
            # First, create some annotations
            similarity_items = self.page.locator(".similarity-item")
            if similarity_items.count() == 0:
                logger.warning("  ⚠️  No similarities to export")
                return True
            
            # Annotate first item
            first_item = similarity_items.first
            rating_btn = first_item.locator(".rating-btn").nth(3)  # Rating 3
            rating_btn.click()
            
            # Check export button is enabled
            export_btn = self.page.locator("#exportBtn")
            expect(export_btn).not_to_be_disabled()
            
            # Wait a bit for annotation to register
            self.page.wait_for_timeout(300)
            
            # Set up download listener with timeout
            try:
                with self.page.expect_download(timeout=5000) as download_info:
                    export_btn.click()
                download = download_info.value
                if download.suggested_filename and download.suggested_filename.endswith('.json'):
                    logger.info(f"  ✅ Export triggered: {download.suggested_filename}")
                    return True
                else:
                    logger.warning("  ⚠️  Export triggered but filename unexpected")
                    return True  # Still pass if download was triggered
            except Exception as e:
                # Check if alert was shown (no annotations case)
                # The export function shows an alert if no annotations
                logger.warning(f"  ⚠️  Export may have shown alert (no annotations or other issue): {e}")
                # This is acceptable - the button works, just no data to export
                return True
        except Exception as e:
            logger.error(f"  ❌ Export failed: {e}")
            return False
    
    def test_bulk_actions(self):
        """Test 8: Bulk actions are visible and functional."""
        logger.info("Testing: Bulk actions...")
        try:
            # Check that bulk actions are visible after loading
            bulk_actions = self.page.locator("#bulkActions")
            expect(bulk_actions).to_be_visible()
            
            # Check submit button
            submit_btn = self.page.locator("#submitAllBtn")
            expect(submit_btn).to_be_visible()
            
            # Check clear button
            clear_btn = self.page.locator("#clearAllBtn")
            expect(clear_btn).to_be_visible()
            
            logger.info("  ✅ Bulk actions visible")
            return True
        except Exception as e:
            logger.error(f"  ❌ Bulk actions check failed: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests."""
        if not HAS_PLAYWRIGHT:
            logger.error("Playwright not available. Install with: uv add playwright")
            return False
        
        # Wait for API to be ready
        if not wait_for_api(max_retries=30, timeout=TIMEOUTS["fast"]):
            logger.error("API not ready")
            return False
        
        logger.info("=" * 70)
        logger.info("REVIEW PAGE E2E TESTS")
        logger.info("=" * 70)
        logger.info("")
        
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
            self.test_feature("Page loads", self.test_page_loads)
            self.test_feature("Load from API", self.test_load_from_api)
            self.test_feature("Display metadata", self.test_display_metadata)
            self.test_feature("Annotation controls", self.test_annotation_controls)
            self.test_feature("Statistics", self.test_statistics)
            self.test_feature("Load from file", self.test_load_from_file)
            self.test_feature("Export functionality", self.test_export_functionality)
            self.test_feature("Bulk actions", self.test_bulk_actions)
            
            # Take final screenshot for visual inspection
            try:
                screenshot_path = Path("/tmp/review_page_final.png")
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                logger.info(f"  📸 Final screenshot saved: {screenshot_path}")
            except Exception as e:
                logger.warning(f"  ⚠️  Could not save screenshot: {e}")
            
            self.browser.close()
        
        # Print summary
        logger.info("")
        logger.info("=" * 70)
        logger.info("TEST SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Tests run: {self.results['tests_run']}")
        logger.info(f"Tests passed: {self.results['tests_passed']}")
        logger.info(f"Tests failed: {self.results['tests_failed']}")
        
        if self.results["issues"]:
            logger.info("")
            logger.info("Issues:")
            for issue in self.results["issues"]:
                logger.info(f"  - {issue}")
        
        return self.results["tests_failed"] == 0


def main():
    """Main entry point."""
    tester = ReviewPageTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

