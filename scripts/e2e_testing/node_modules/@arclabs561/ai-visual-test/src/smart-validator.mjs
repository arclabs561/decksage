/**
 * Smart Validator Selector
 * 
 * Automatically selects the best validator type based on available context.
 * Guides users to the right tool for the job.
 * 
 * Design Philosophy:
 * - If you have page access and can measure it programmatically → use programmatic
 * - If you only have screenshots and need semantic evaluation → use VLLM
 * - If you need both accuracy and semantic understanding → use hybrid
 * 
 * This prevents the common mistake of using VLLM for measurable things.
 */

import { ValidationError } from './errors.mjs';
import {
  checkElementContrast,
  checkAllTextContrast,
  checkKeyboardNavigation
} from './validators/accessibility-programmatic.mjs';
import {
  validateStateProgrammatic as validateStateProg,
  validateElementPosition as validatePosProg
} from './validators/state-programmatic.mjs';
import {
  validateAccessibilityHybrid,
  validateStateHybrid
} from './validators/hybrid-validator.mjs';
import {
  AccessibilityValidator,
  StateValidator
} from './validators/index.mjs';
import { validateScreenshot } from './judge.mjs';
import { log, warn } from './logger.mjs';

/**
 * Smart accessibility validation
 * 
 * Automatically chooses the best validator based on available context:
 * - Has page access → uses programmatic (fast, deterministic)
 * - Only has screenshot → uses VLLM (semantic evaluation)
 * - Has both and needs semantic context → uses hybrid (best of both)
 * 
 * @param {Object} options - Validation options
 * @param {any} [options.page] - Playwright page object (if available)
 * @param {string} [options.screenshotPath] - Path to screenshot (if available)
 * @param {string} [options.selector] - CSS selector for element (if checking specific element)
 * @param {number} [options.minContrast] - Minimum contrast ratio (default: 4.5)
 * @param {boolean} [options.useHybrid] - Force hybrid validation (default: auto-detect)
 * @param {boolean} [options.needSemantic] - Need semantic evaluation (default: false)
 * @returns {Promise<Object>} Validation result
 */
export async function validateAccessibilitySmart(options = {}) {
  const {
    page = null,
    screenshotPath = null,
    selector = null,
    minContrast = 4.5,
    useHybrid = null, // null = auto-detect
    needSemantic = false
  } = options;

  // Validate inputs
  if (!page && !screenshotPath) {
    throw new ValidationError(
      'validateAccessibilitySmart: Either page or screenshotPath is required',
      { options }
    );
  }

  // Auto-detect: use hybrid if both available and semantic needed
  const shouldUseHybrid = useHybrid !== null 
    ? useHybrid 
    : (page && screenshotPath && needSemantic);

  // Decision tree:
  // 1. Has page access → use programmatic (fast, deterministic)
  // 2. Has both + need semantic → use hybrid (best of both)
  // 3. Only screenshot → use VLLM (semantic evaluation)

  if (page && !shouldUseHybrid) {
    // Use programmatic validator (fast, deterministic)
    log('[SmartValidator] Using programmatic accessibility validator (fast, deterministic)');
    
    if (selector) {
      // Check specific element
      return await checkElementContrast(page, selector, minContrast);
    } else {
      // Check all text elements
      const contrast = await checkAllTextContrast(page, minContrast);
      const keyboard = await checkKeyboardNavigation(page);
      
      return {
        contrast,
        keyboard,
        method: 'programmatic',
        speed: 'fast',
        cost: 'free'
      };
    }
  } else if (page && screenshotPath && shouldUseHybrid) {
    // Use hybrid validator (programmatic + VLLM)
    log('[SmartValidator] Using hybrid accessibility validator (programmatic + VLLM)');
    
    return await validateAccessibilityHybrid(
      page,
      screenshotPath,
      minContrast,
      { testType: 'accessibility-smart' }
    );
  } else if (screenshotPath) {
    // Use VLLM validator (semantic evaluation)
    log('[SmartValidator] Using VLLM accessibility validator (semantic evaluation)');
    warn('[SmartValidator] Consider using programmatic validator if you have page access (faster, more reliable)');
    
    const validator = new AccessibilityValidator({
      minContrast,
      standards: ['WCAG-AA']
    });
    
    return await validator.validateAccessibility(screenshotPath, {
      testType: 'accessibility-smart'
    });
  } else {
    throw new ValidationError(
      'validateAccessibilitySmart: Invalid combination of options',
      { page: !!page, screenshotPath: !!screenshotPath }
    );
  }
}

/**
 * Smart state validation
 * 
 * Automatically chooses the best validator based on available context:
 * - Has page access + direct state → uses programmatic (fast, deterministic)
 * - Has page access + screenshot + need semantic → uses hybrid (best of both)
 * - Only screenshot → uses VLLM (extracts state from screenshot)
 * 
 * @param {Object} options - Validation options
 * @param {any} [options.page] - Playwright page object (if available)
 * @param {string} [options.screenshotPath] - Path to screenshot (if available)
 * @param {Object} options.expectedState - Expected state object
 * @param {Object} [options.selectors] - Map of state keys to CSS selectors
 * @param {number} [options.tolerance] - Pixel tolerance (default: 5)
 * @param {boolean} [options.useHybrid] - Force hybrid validation (default: auto-detect)
 * @param {boolean} [options.needSemantic] - Need semantic evaluation (default: false)
 * @returns {Promise<Object>} Validation result
 */
export async function validateStateSmart(options = {}) {
  const {
    page = null,
    screenshotPath = null,
    expectedState,
    selectors = {},
    tolerance = 5,
    useHybrid = null, // null = auto-detect
    needSemantic = false
  } = options;

  // Validate inputs
  if (!expectedState || typeof expectedState !== 'object') {
    throw new ValidationError(
      'validateStateSmart: expectedState is required and must be an object',
      { received: typeof expectedState }
    );
  }

  if (!page && !screenshotPath) {
    throw new ValidationError(
      'validateStateSmart: Either page or screenshotPath is required',
      { options }
    );
  }

  // Check if we have direct state access (window.gameState, etc.)
  let hasDirectState = false;
  if (page) {
    try {
      const gameState = await page.evaluate(() => window.gameState || null);
      hasDirectState = gameState !== null;
    } catch (e) {
      // Ignore - no direct state access
    }
  }

  // Auto-detect: use hybrid if both available and semantic needed
  const shouldUseHybrid = useHybrid !== null 
    ? useHybrid 
    : (page && screenshotPath && needSemantic);

  // Decision tree:
  // 1. Has page access + direct state → use programmatic (fast, deterministic)
  // 2. Has page access + selectors → use programmatic (fast, deterministic)
  // 3. Has both + need semantic → use hybrid (best of both)
  // 4. Only screenshot → use VLLM (extracts state from screenshot)

  if (page && (hasDirectState || Object.keys(selectors).length > 0) && !shouldUseHybrid) {
    // Use programmatic validator (fast, deterministic)
    log('[SmartValidator] Using programmatic state validator (fast, deterministic)');
    
    return await validateStateProg(
      page,
      expectedState,
      { selectors, tolerance }
    );
  } else if (page && screenshotPath && shouldUseHybrid) {
    // Use hybrid validator (programmatic + VLLM)
    log('[SmartValidator] Using hybrid state validator (programmatic + VLLM)');
    
    return await validateStateHybrid(
      page,
      screenshotPath,
      expectedState,
      { selectors, tolerance, testType: 'state-smart' }
    );
  } else if (screenshotPath) {
    // Use VLLM validator (extracts state from screenshot)
    log('[SmartValidator] Using VLLM state validator (extracts state from screenshot)');
    warn('[SmartValidator] Consider using programmatic validator if you have page access (faster, more reliable)');
    
    const validator = new StateValidator({ tolerance });
    return await validator.validateState(
      screenshotPath,
      expectedState,
      { testType: 'state-smart' }
    );
  } else {
    throw new ValidationError(
      'validateStateSmart: Invalid combination of options',
      { page: !!page, screenshotPath: !!screenshotPath, hasDirectState, selectors: Object.keys(selectors).length }
    );
  }
}

/**
 * Smart element validation
 * 
 * Validates element visibility, position, contrast, etc. using the best available method.
 * 
 * @param {Object} options - Validation options
 * @param {any} options.page - Playwright page object
 * @param {string} options.selector - CSS selector for element
 * @param {Object} [options.checks] - What to check: { visible, position, contrast }
 * @param {Object} [options.expectedPosition] - Expected position {x, y, width, height}
 * @param {number} [options.minContrast] - Minimum contrast ratio
 * @param {number} [options.tolerance] - Pixel tolerance for position (default: 5)
 * @returns {Promise<Object>} Validation result
 */
export async function validateElementSmart(options = {}) {
  const {
    page,
    selector,
    checks = { visible: true, position: false, contrast: false },
    expectedPosition = null,
    minContrast = 4.5,
    tolerance = 5
  } = options;

  if (!page || typeof page.evaluate !== 'function') {
    throw new ValidationError(
      'validateElementSmart: page is required and must be a Playwright Page object',
      { received: typeof page }
    );
  }

  if (!selector || typeof selector !== 'string') {
    throw new ValidationError(
      'validateElementSmart: selector is required and must be a string',
      { received: typeof selector }
    );
  }

  const results = {};

  // Always use programmatic (we have page access)
  if (checks.visible) {
    const visible = await page.locator(selector).isVisible();
    results.visible = visible;
    if (!visible) {
      results.errors = results.errors || [];
      results.errors.push(`Element ${selector} is not visible`);
    }
  }

  if (checks.position && expectedPosition) {
    const position = await validatePosProg(
      page,
      selector,
      expectedPosition,
      tolerance
    );
    results.position = position;
    if (!position.matches) {
      results.errors = results.errors || [];
      results.errors.push(`Element ${selector} position mismatch: ${position.diff}`);
    }
  }

  if (checks.contrast) {
    const contrast = await checkElementContrast(page, selector, minContrast);
    results.contrast = contrast;
    if (!contrast.passes) {
      results.errors = results.errors || [];
      results.errors.push(`Element ${selector} contrast ${contrast.ratio}:1 < ${minContrast}:1`);
    }
  }

  results.passes = !results.errors || results.errors.length === 0;
  results.method = 'programmatic';
  results.speed = 'fast';
  results.cost = 'free';

  return results;
}

/**
 * Smart validation with automatic tool selection
 * 
 * This is the main entry point that automatically selects the best validator
 * based on what you're trying to validate and what context you have.
 * 
 * @param {Object} options - Validation options
 * @param {string} options.type - Type of validation: 'accessibility', 'state', 'element', 'visual'
 * @param {any} [options.page] - Playwright page object (if available)
 * @param {string} [options.screenshotPath] - Path to screenshot (if available)
 * @param {Object} [options.expectedState] - Expected state (for state validation)
 * @param {string} [options.selector] - CSS selector (for element validation)
 * @param {Object} [options.checks] - What to check (for element validation)
 * @param {string} [options.prompt] - Evaluation prompt (for visual validation)
 * @param {Object} [options.context] - Additional context
 * @returns {Promise<Object>} Validation result
 */
export async function validateSmart(options = {}) {
  const { type, ...rest } = options;

  if (!type) {
    throw new ValidationError(
      'validateSmart: type is required (accessibility, state, element, or visual)',
      { received: type }
    );
  }

  switch (type) {
    case 'accessibility':
      return await validateAccessibilitySmart(rest);
    
    case 'state':
      return await validateStateSmart(rest);
    
    case 'element':
      return await validateElementSmart(rest);
    
    case 'visual':
      // For visual validation, always use VLLM (semantic evaluation)
      if (!rest.screenshotPath) {
        throw new ValidationError(
          'validateSmart: screenshotPath is required for visual validation',
          { type }
        );
      }
      if (!rest.prompt) {
        throw new ValidationError(
          'validateSmart: prompt is required for visual validation',
          { type }
        );
      }
      log('[SmartValidator] Using VLLM for visual validation (semantic evaluation)');
      return await validateScreenshot(
        rest.screenshotPath,
        rest.prompt,
        { testType: 'visual-smart', ...rest.context }
      );
    
    default:
      throw new ValidationError(
        `validateSmart: Unknown type "${type}" (must be: accessibility, state, element, or visual)`,
        { received: type }
      );
  }
}

/**
 * Helper to detect if validation can be done programmatically
 * 
 * @param {Object} options - Validation options
 * @param {any} [options.page] - Playwright page object
 * @param {string} [options.screenshotPath] - Path to screenshot
 * @param {string} [options.type] - Type of validation
 * @returns {Object} Detection result with recommendations
 */
export function detectValidationMethod(options = {}) {
  const { page, screenshotPath, type } = options;

  const hasPage = page && typeof page.evaluate === 'function';
  const hasScreenshot = !!screenshotPath;

  const recommendations = [];

  if (type === 'accessibility' || type === 'state') {
    if (hasPage) {
      recommendations.push({
        method: 'programmatic',
        reason: 'Has page access - use programmatic validator (fast, deterministic, free)',
        speed: 'fast',
        cost: 'free',
        reliability: 'high'
      });
    }

    if (hasPage && hasScreenshot) {
      recommendations.push({
        method: 'hybrid',
        reason: 'Has both page and screenshot - use hybrid validator (programmatic ground truth + VLLM semantic)',
        speed: 'medium',
        cost: 'api',
        reliability: 'high'
      });
    }

    if (hasScreenshot && !hasPage) {
      recommendations.push({
        method: 'vllm',
        reason: 'Only has screenshot - use VLLM validator (semantic evaluation)',
        speed: 'slow',
        cost: 'api',
        reliability: 'medium'
      });
    }
  } else if (type === 'visual') {
    recommendations.push({
      method: 'vllm',
      reason: 'Visual validation requires semantic evaluation - use VLLM',
      speed: 'slow',
      cost: 'api',
      reliability: 'medium'
    });
  }

  return {
    hasPage,
    hasScreenshot,
    recommendations,
    recommended: recommendations[0] || null
  };
}

