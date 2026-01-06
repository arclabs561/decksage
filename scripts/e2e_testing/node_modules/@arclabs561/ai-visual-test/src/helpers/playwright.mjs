/**
 * Playwright Helper Utilities
 * 
 * Provides utilities for working with Playwright, including graceful
 * handling when Playwright is not installed.
 */

/**
 * Get Playwright chromium browser, with graceful fallback
 * @returns {Promise<{chromium: any, available: boolean}>}
 */
export async function getPlaywrightChromium() {
  try {
    const playwright = await import('playwright');
    return {
      chromium: playwright.chromium,
      available: true
    };
  } catch (error) {
    if (error.code === 'ERR_MODULE_NOT_FOUND' || error.message.includes('Cannot find module')) {
      return {
        chromium: null,
        available: false,
        error: 'Playwright not installed. Install with: npm install --save-dev @playwright/test'
      };
    }
    throw error;
  }
}

/**
 * Check if Playwright is available
 * @returns {Promise<boolean>}
 */
export async function isPlaywrightAvailable() {
  const { available } = await getPlaywrightChromium();
  return available;
}

/**
 * Create a mock page object for testing when Playwright is not available
 * @returns {object} Mock page object
 */
export function createMockPage() {
  return {
    goto: async () => {},
    screenshot: async () => ({ path: 'mock-screenshot.png' }),
    waitForLoadState: async () => {},
    waitForTimeout: async () => {},
    evaluate: async () => ({}),
    close: async () => {}
  };
}

/**
 * Get Playwright page with fallback to mock
 * @param {object} options - Options for browser/page creation
 * @returns {Promise<{page: any, browser: any, isMock: boolean}>}
 */
export async function getPlaywrightPage(options = {}) {
  const { chromium, available } = await getPlaywrightChromium();
  
  if (!available) {
    return {
      page: createMockPage(),
      browser: null,
      isMock: true
    };
  }
  
  const browser = await chromium.launch(options.browserOptions || {});
  const page = await browser.newPage();
  
  return {
    page,
    browser,
    isMock: false
  };
}

