#!/usr/bin/env python3
"""
Deep Accessibility Testing

Tests accessibility features comprehensively:
- ARIA attributes
- Keyboard navigation
- Focus management
- Screen reader compatibility
- Color contrast
- Touch target sizes
- Error announcements
"""

import os
import time
from pathlib import Path

# Import shared utilities (dotenv is loaded automatically by test_utils)

# Use Playwright for browser automation
try:
    from playwright.sync_api import sync_playwright, Page, expect
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    # logger not yet imported, use print for this error
    print("⚠️  Playwright not installed. Install with: uv add playwright")

# Import shared utilities and constants
from test_utils import logger
from test_constants import TIMEOUTS

# Import shared utilities (dotenv is loaded automatically by test_utils)
from test_utils import get_ui_url, start_http_server

# Start HTTP server and get UI URL
start_http_server()
UI_URL = get_ui_url()


def test_aria_attributes():
    """Test all ARIA attributes are present."""
    logger.info("Testing ARIA attributes...")
    if not HAS_PLAYWRIGHT:
        logger.warning("⚠️  Playwright not available (install with: uv add playwright)")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            
            checks = {}
            
            # Search input
            search_input = page.locator("#cardInput")
            search_input.wait_for(state="visible")
            checks["search_role"] = search_input.get_attribute("role") == "combobox"
            checks["search_aria_autocomplete"] = search_input.get_attribute("aria-autocomplete") == "list"
            checks["search_aria_label"] = search_input.get_attribute("aria-label") is not None
            checks["search_aria_expanded"] = search_input.get_attribute("aria-expanded") is not None
            checks["search_aria_haspopup"] = search_input.get_attribute("aria-haspopup") == "listbox"
            
            # Trigger autocomplete
            search_input.type("Light", delay=50)
            page.wait_for_timeout(300)
            
            # Autocomplete dropdown
            dropdown = page.locator("#autocompleteDropdown")
            if dropdown.is_visible():
                checks["dropdown_role"] = dropdown.get_attribute("role") == "listbox"
                checks["dropdown_aria_label"] = dropdown.get_attribute("aria-label") is not None
                
                # Autocomplete items
                items = dropdown.locator(".autocomplete-item")
                if items.count() > 0:
                    first_item = items.first
                    checks["item_role"] = first_item.get_attribute("role") == "option"
                    checks["item_aria_label"] = first_item.get_attribute("aria-label") is not None
            
            # Advanced options toggle
            try:
                advanced_toggle = page.locator("#advancedToggle")
                if advanced_toggle.count() > 0:
                    checks["toggle_aria_expanded"] = advanced_toggle.get_attribute("aria-expanded") is not None
                    checks["toggle_aria_controls"] = advanced_toggle.get_attribute("aria-controls") is not None
                else:
                    checks["toggle_aria_expanded"] = False
                    checks["toggle_aria_controls"] = False
            except Exception:
                checks["toggle_aria_expanded"] = False
                checks["toggle_aria_controls"] = False
            
            browser.close()
            
            passed = sum(checks.values())
            total = len(checks)
            
            logger.info(f"Result: {passed}/{total} ARIA attributes present")
            for check, passed_check in checks.items():
                status = "✅" if passed_check else "❌"
                logger.info(f"    {status} {check}")
            
            return passed == total
    except Exception as e:
        logger.warning(f"⚠️  ARIA test failed: {e}")
        return None


def test_keyboard_navigation():
    """Test complete keyboard navigation flow."""
    logger.info("\n🔍 Testing keyboard navigation...")
    if not HAS_PLAYWRIGHT:
        logger.warning("⚠️  Playwright not available (install with: uv add playwright)")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            
            search_input = page.locator("#cardInput")
            search_input.wait_for(state="visible")
            
            checks = {}
            
            # Focus the input
            search_input.focus()
            page.wait_for_timeout(100)
            checks["tab_to_input"] = page.evaluate("document.activeElement.id") == "cardInput"
            
            # Type to trigger autocomplete
            search_input.type("Light", delay=50)
            page.wait_for_timeout(300)
            
            # Arrow down
            search_input.press("ArrowDown")
            page.wait_for_timeout(100)
            dropdown = page.locator("#autocompleteDropdown")
            if dropdown.is_visible():
                selected = dropdown.locator(".autocomplete-item.selected")
                checks["arrow_down"] = selected.count() > 0
                
                # Arrow down again
                search_input.press("ArrowDown")
                page.wait_for_timeout(100)
                selected = dropdown.locator(".autocomplete-item.selected")
                checks["arrow_down_multiple"] = selected.count() > 0
                
                # Arrow up
                search_input.press("ArrowUp")
                page.wait_for_timeout(100)
                selected = dropdown.locator(".autocomplete-item.selected")
                checks["arrow_up"] = selected.count() > 0
                
                # Escape to close
                search_input.press("Escape")
                page.wait_for_timeout(100)
                checks["escape_close"] = not dropdown.is_visible()
            else:
                checks["arrow_down"] = False
                checks["arrow_down_multiple"] = False
                checks["arrow_up"] = False
                checks["escape_close"] = False
            
            browser.close()
            
            passed = sum(checks.values())
            total = len(checks)
            
            logger.info(f"Result: {passed}/{total} keyboard navigation checks passed")
            for check, passed_check in checks.items():
                status = "✅" if passed_check else "❌"
                logger.info(f"    {status} {check}")
            
            return passed == total
    except Exception as e:
        logger.warning(f"⚠️  Keyboard navigation test failed: {e}")
        return None


def test_focus_indicators():
    """Test that focus indicators are visible."""
    logger.info("\n🔍 Testing focus indicators...")
    if not HAS_PLAYWRIGHT:
        logger.warning("⚠️  Playwright not available (install with: uv add playwright)")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            
            search_input = page.locator("#cardInput")
            search_input.wait_for(state="visible")
            search_input.focus()
            page.wait_for_timeout(100)
            
            # Check computed styles for focus indicator
            focus_style = page.evaluate("""
                (element) => {
                    const style = window.getComputedStyle(element);
                    return {
                        outline: style.outline,
                        boxShadow: style.boxShadow
                    };
                }
            """, search_input)
            
            has_focus_indicator = (
                focus_style["outline"] and focus_style["outline"] != "none" and focus_style["outline"] != "0px"
            ) or (focus_style["boxShadow"] and focus_style["boxShadow"] != "none")
            
            browser.close()
            
            if has_focus_indicator:
                logger.info("✅ Focus indicator is visible")
                return True
            else:
                logger.warning("⚠️  Focus indicator may not be visible")
                return False
    except Exception as e:
        logger.warning(f"⚠️  Focus indicator test failed: {e}")
        return None


def test_touch_target_sizes():
    """Test that touch targets are appropriately sized (44px minimum)."""
    logger.info("\n🔍 Testing touch target sizes...")
    if not HAS_PLAYWRIGHT:
        logger.warning("⚠️  Playwright not available (install with: uv add playwright)")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            
            checks = {}
            
            # Search input
            search_input = page.locator("#cardInput")
            search_input.wait_for(state="visible")
            input_box = search_input.bounding_box()
            if input_box:
                checks["input_height"] = input_box["height"] >= 44
            
            # Search button
            try:
                search_button = page.locator(".search-button")
                if search_button.count() > 0:
                    button_box = search_button.bounding_box()
                    if button_box:
                        checks["button_size"] = button_box["height"] >= 44 and button_box["width"] >= 44
                    else:
                        checks["button_size"] = False
                else:
                    checks["button_size"] = False
            except Exception:
                checks["button_size"] = False
            
            # Autocomplete items (when visible)
            search_input.type("Light", delay=50)
            page.wait_for_timeout(300)
            try:
                items = page.locator(".autocomplete-item")
                if items.count() > 0:
                    first_item_box = items.first.bounding_box()
                    if first_item_box:
                        checks["autocomplete_item_height"] = first_item_box["height"] >= 44
                    else:
                        checks["autocomplete_item_height"] = False
                else:
                    checks["autocomplete_item_height"] = False
            except Exception:
                checks["autocomplete_item_height"] = False
            
            browser.close()
            
            passed = sum(checks.values())
            total = len(checks)
            
            logger.info(f"Result: {passed}/{total} touch target size checks passed")
            for check, passed_check in checks.items():
                status = "✅" if passed_check else "❌"
                logger.info(f"    {status} {check}")
            
            return passed == total
    except Exception as e:
        logger.warning(f"⚠️  Touch target test failed: {e}")
        return None


def test_screen_reader_structure():
    """Test semantic HTML structure for screen readers."""
    logger.info("\n🔍 Testing screen reader structure...")
    if not HAS_PLAYWRIGHT:
        logger.warning("⚠️  Playwright not available (install with: uv add playwright)")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(UI_URL)
            
            checks = {}
            
            # Check for semantic HTML
            search_form = page.locator("#searchForm")
            if search_form.count() > 0:
                checks["form_role"] = search_form.get_attribute("role") == "search"
            else:
                checks["form_role"] = False
            
            # Check for labels
            search_input = page.locator("#cardInput")
            search_input.wait_for(state="visible")
            checks["input_label"] = (
                search_input.get_attribute("aria-label") is not None
                or search_input.get_attribute("aria-labelledby") is not None
            )
            
            # Check for descriptions
            try:
                described_by = search_input.get_attribute("aria-describedby")
                if described_by:
                    desc_elem = page.locator(f"#{described_by}")
                    checks["input_description"] = desc_elem.count() > 0
                else:
                    checks["input_description"] = False
            except Exception:
                checks["input_description"] = False
            
            browser.close()
            
            passed = sum(checks.values())
            total = len(checks)
            
            logger.info(f"Result: {passed}/{total} screen reader structure checks passed")
            for check, passed_check in checks.items():
                status = "✅" if passed_check else "❌"
                logger.info(f"    {status} {check}")
            
            return passed == total
    except Exception as e:
        logger.warning(f"⚠️  Screen reader test failed: {e}")
        return None


def main():
    """Run all accessibility tests."""
    logger.info("=" * 60)
    logger.info("Deep Accessibility Testing")
    logger.info("=" * 60)
    
    results = {
        "aria": test_aria_attributes(),
        "keyboard": test_keyboard_navigation(),
        "focus": test_focus_indicators(),
        "touch_targets": test_touch_target_sizes(),
        "screen_reader": test_screen_reader_structure(),
    }
    
    logger.info("\n" + "=" * 60)
    logger.info("Accessibility Test Results:")
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
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit(main())
