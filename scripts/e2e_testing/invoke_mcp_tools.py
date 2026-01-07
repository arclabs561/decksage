#!/usr/bin/env python3
"""
Example: How to Invoke MCP Browser Tools from Python Scripts

MCP (Model Context Protocol) tools can be invoked in several ways:
1. Directly from Cursor (using MCP server integration)
2. Via MCP Python SDK (for programmatic access)
3. Via HTTP/SSE/Stdio transport (for remote servers)

This script demonstrates the patterns and provides a wrapper for MCP browser tools.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Add test directory to path
test_dir = Path(__file__).parent
sys.path.insert(0, str(test_dir))

from test_utils import logger, API_BASE

UI_URL = os.getenv("UI_URL", "http://localhost:8000")


class MCPBrowserToolsWrapper:
    """
    Wrapper for MCP Browser Tools.
    
    Note: MCP tools are typically invoked through the MCP server protocol.
    In Cursor, these are available via the mcp_cursor-ide-browser server.
    
    For standalone scripts, we can:
    1. Use Playwright directly (recommended for automation)
    2. Use MCP Python SDK to connect to MCP server
    3. Use HTTP/SSE transport if MCP server is exposed
    """
    
    def __init__(self, use_playwright: bool = True):
        """
        Initialize MCP browser tools wrapper.
        
        Args:
            use_playwright: If True, use Playwright directly (recommended).
                           If False, attempt to use MCP protocol.
        """
        self.use_playwright = use_playwright
        self.browser = None
        self.page = None
        
        if use_playwright:
            try:
                from playwright.sync_api import sync_playwright
                self.playwright = sync_playwright
                self.has_playwright = True
            except ImportError:
                self.has_playwright = False
                logger.warning("⚠️  Playwright not available - MCP tools require Playwright or MCP server")
        else:
            # For MCP protocol access, we'd need MCP Python SDK
            # This is a placeholder for future MCP SDK integration
            self.has_playwright = False
            logger.info("💡 MCP SDK integration not yet implemented - using Playwright fallback")
    
    def navigate(self, url: str) -> dict[str, Any]:
        """
        Navigate to a URL (equivalent to browser_navigate).
        
        Args:
            url: URL to navigate to
            
        Returns:
            Dict with navigation result
        """
        if self.use_playwright and self.has_playwright:
            if not self.browser:
                p = self.playwright().start()
                self.browser = p.chromium.launch(headless=True)
                self.page = self.browser.new_page()
            
            self.page.goto(url)
            self.page.wait_for_load_state("networkidle")
            return {"success": True, "url": url}
        else:
            logger.error("❌ Playwright not available for navigation")
            return {"success": False, "error": "Playwright not available"}
    
    def snapshot(self) -> dict[str, Any]:
        """
        Get page snapshot (equivalent to browser_snapshot).
        
        Returns:
            Dict with page snapshot information
        """
        if self.page:
            try:
                # Get accessibility snapshot using Playwright (sync API)
                # Note: accessibility.snapshot() is available in sync API
                snapshot = self.page.accessibility.snapshot()
                return {"success": True, "snapshot": snapshot}
            except AttributeError:
                # Fallback for older Playwright versions or if method doesn't exist
                return {
                    "success": True,
                    "snapshot": {
                        "url": self.page.url,
                        "title": self.page.title(),
                        "note": "Accessibility snapshot not available (use Playwright >= 1.20)"
                    }
                }
            except Exception as e:
                # Fallback: get basic page info
                return {
                    "success": True,
                    "snapshot": {
                        "url": self.page.url,
                        "title": self.page.title(),
                        "note": f"Full accessibility snapshot not available: {str(e)}"
                    }
                }
        else:
            return {"success": False, "error": "Page not loaded"}
    
    def click(self, selector: str) -> dict[str, Any]:
        """
        Click an element (equivalent to browser_click).
        
        Args:
            selector: CSS selector or Playwright locator
            
        Returns:
            Dict with click result
        """
        if self.page:
            try:
                self.page.click(selector)
                return {"success": True, "selector": selector}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            return {"success": False, "error": "Page not loaded"}
    
    def type_text(self, selector: str, text: str) -> dict[str, Any]:
        """
        Type text into an element (equivalent to browser_type).
        
        Args:
            selector: CSS selector
            text: Text to type
            
        Returns:
            Dict with type result
        """
        if self.page:
            try:
                self.page.fill(selector, text)
                return {"success": True, "selector": selector, "text": text}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            return {"success": False, "error": "Page not loaded"}
    
    def take_screenshot(self, filename: str, full_page: bool = False) -> dict[str, Any]:
        """
        Take screenshot (equivalent to browser_take_screenshot).
        
        Args:
            filename: Output filename
            full_page: Whether to capture full page
            
        Returns:
            Dict with screenshot result
        """
        if self.page:
            try:
                self.page.screenshot(path=filename, full_page=full_page)
                return {"success": True, "filename": filename}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            return {"success": False, "error": "Page not loaded"}
    
    def close(self):
        """Close browser."""
        if self.browser:
            self.browser.close()
            self.browser = None
            self.page = None


def demonstrate_mcp_tools():
    """Demonstrate MCP browser tools usage."""
    logger.info("=" * 70)
    logger.info("MCP BROWSER TOOLS DEMONSTRATION")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Note: MCP tools in Cursor are invoked through the MCP server protocol.")
    logger.info("This wrapper uses Playwright to provide equivalent functionality.")
    logger.info("")
    
    tools = MCPBrowserToolsWrapper(use_playwright=True)
    
    if not tools.has_playwright:
        logger.error("❌ Playwright not available - install with: uv add playwright")
        return False
    
    try:
        # Navigate
        logger.info("1. Navigating to landing page...")
        result = tools.navigate(UI_URL)
        if result["success"]:
            logger.info(f"   ✅ Navigated to {result['url']}")
        else:
            logger.error(f"   ❌ Navigation failed: {result.get('error')}")
            return False
        
        # Snapshot
        logger.info("2. Getting page snapshot...")
        snapshot = tools.snapshot()
        if snapshot["success"]:
            logger.info("   ✅ Snapshot captured")
            # Log first few elements
            if "snapshot" in snapshot and snapshot["snapshot"]:
                first_elem = snapshot["snapshot"]
                logger.info(f"   Root element: {first_elem.get('role', 'unknown')}")
        else:
            logger.warning(f"   ⚠️  Snapshot failed: {snapshot.get('error')}")
        
        # Type text
        logger.info("3. Typing in search input...")
        type_result = tools.type_text("#unifiedInput, #cardInput", "Lightning Bolt")
        if type_result["success"]:
            logger.info(f"   ✅ Typed: {type_result['text']}")
        else:
            logger.warning(f"   ⚠️  Type failed: {type_result.get('error')}")
        
        # Screenshot
        logger.info("4. Taking screenshot...")
        screenshot_result = tools.take_screenshot("/tmp/mcp_demo.png", full_page=True)
        if screenshot_result["success"]:
            logger.info(f"   ✅ Screenshot saved: {screenshot_result['filename']}")
        else:
            logger.warning(f"   ⚠️  Screenshot failed: {screenshot_result.get('error')}")
        
        tools.close()
        logger.info("")
        logger.info("✅ MCP tools demonstration complete")
        return True
        
    except Exception as e:
        logger.error(f"❌ Demonstration failed: {e}")
        tools.close()
        return False


if __name__ == "__main__":
    success = demonstrate_mcp_tools()
    sys.exit(0 if success else 1)

