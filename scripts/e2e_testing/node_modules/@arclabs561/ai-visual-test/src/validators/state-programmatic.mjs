/**
 * Programmatic State Validator
 * 
 * Fast, deterministic state validation using direct state access and DOM inspection.
 * Use this when you have Playwright page access and direct state access (e.g., window.gameState).
 * 
 * For state extraction from screenshots (when you don't have direct state access), use StateValidator (VLLM-based).
 */

import { ValidationError } from '../errors.mjs';
import { assertString, assertObject, assertNumber } from '../type-guards.mjs';

/**
 * Validate state matches visual representation
 * 
 * @param {any} page - Playwright page object
 * @param {object} expectedState - Expected state object
 * @param {object} options - Validation options
 * @param {object} options.selectors - Map of state keys to CSS selectors (e.g., { ball: '#game-ball', paddle: '#game-paddle' })
 * @param {number} options.tolerance - Pixel tolerance for position comparison (default: 5)
 * @param {function} options.stateExtractor - Optional function to extract state from page (default: uses window.gameState)
 * @returns {Promise<{matches: boolean, discrepancies: string[], visualState: object, expectedState: object}>}
 * @throws {ValidationError} If page is not a valid Playwright Page object or inputs are invalid
 */
export async function validateStateProgrammatic(page, expectedState, options = {}) {
  // Validate inputs
  if (!page || typeof page.evaluate !== 'function') {
    throw new ValidationError('validateStateProgrammatic requires a Playwright Page object', {
      received: typeof page,
      hasEvaluate: typeof page?.evaluate === 'function'
    });
  }
  
  assertObject(expectedState, 'expectedState');
  
  const selectors = options.selectors || {};
  const tolerance = options.tolerance || 5;
  const stateExtractor = options.stateExtractor || ((page) => page.evaluate(() => window.gameState || null));
  
  if (typeof tolerance !== 'number' || tolerance < 0 || isNaN(tolerance)) {
    throw new ValidationError('tolerance must be a non-negative number', { received: tolerance });
  }
  
  // Extract state from page
  let gameState;
  if (typeof stateExtractor === 'function') {
    gameState = await stateExtractor(page);
  } else {
    gameState = await page.evaluate(() => window.gameState || null);
  }
  
  // Extract visual state from DOM
  const visualState = await page.evaluate(({ selectors }) => {
    const state = {};
    
    for (const [key, selector] of Object.entries(selectors)) {
      const element = document.querySelector(selector);
      if (element) {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        state[key] = {
          x: rect.x,
          y: rect.y,
          width: rect.width,
          height: rect.height,
          visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none'
        };
      } else {
        state[key] = null;
      }
    }
    
    return state;
  }, { selectors });
  
  // Compare gameState with expectedState
  const discrepancies = [];
  
  // If we have gameState, compare it with expectedState
  if (gameState && typeof gameState === 'object') {
    compareObjects(gameState, expectedState, '', discrepancies, tolerance);
  }
  
  // Compare visualState with expectedState (for position-based validation)
  if (Object.keys(selectors).length > 0) {
    for (const [key, expected] of Object.entries(expectedState)) {
      if (selectors[key]) {
        const actual = visualState[key];
        if (!actual) {
          discrepancies.push(`${key}: Element not found (selector: ${selectors[key]})`);
          continue;
        }
        
        if (!actual.visible) {
          discrepancies.push(`${key}: Element not visible (selector: ${selectors[key]})`);
          continue;
        }
        
        if (expected.x !== undefined && typeof expected.x === 'number') {
          const diff = Math.abs(actual.x - expected.x);
          if (diff > tolerance) {
            discrepancies.push(`${key}.x: Expected ${expected.x}, got ${actual.x} (diff: ${diff}px, tolerance: ${tolerance}px)`);
          }
        }
        
        if (expected.y !== undefined && typeof expected.y === 'number') {
          const diff = Math.abs(actual.y - expected.y);
          if (diff > tolerance) {
            discrepancies.push(`${key}.y: Expected ${expected.y}, got ${actual.y} (diff: ${diff}px, tolerance: ${tolerance}px)`);
          }
        }
      }
    }
  }
  
  return {
    matches: discrepancies.length === 0,
    discrepancies,
    visualState,
    expectedState,
    gameState
  };
}

/**
 * Validate element position matches expected position
 * 
 * @param {any} page - Playwright page object
 * @param {string} selector - CSS selector for element
 * @param {object} expectedPosition - Expected position {x, y} or {x, y, width, height}
 * @param {number} tolerance - Pixel tolerance (default: 5)
 * @returns {Promise<{matches: boolean, actual: object, expected: object, diff: object, error?: string}>}
 * @throws {ValidationError} If page is not a valid Playwright Page object or inputs are invalid
 */
export async function validateElementPosition(page, selector, expectedPosition, tolerance = 5) {
  // Validate inputs
  if (!page || typeof page.evaluate !== 'function') {
    throw new ValidationError('validateElementPosition requires a Playwright Page object', {
      received: typeof page,
      hasEvaluate: typeof page?.evaluate === 'function'
    });
  }
  
  assertString(selector, 'selector');
  assertObject(expectedPosition, 'expectedPosition');
  assertNumber(tolerance, 'tolerance');
  
  if (tolerance < 0 || isNaN(tolerance)) {
    throw new ValidationError('tolerance must be a non-negative number', { received: tolerance });
  }
  
  const actual = await page.evaluate((sel) => {
    const element = document.querySelector(sel);
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  }, selector);
  
  if (!actual) {
    return { matches: false, error: 'Element not found', selector, expected: expectedPosition };
  }
  
  const diff = {
    x: Math.abs(actual.x - (expectedPosition.x || 0)),
    y: Math.abs(actual.y - (expectedPosition.y || 0))
  };
  
  if (expectedPosition.width !== undefined) {
    diff.width = Math.abs(actual.width - expectedPosition.width);
  }
  if (expectedPosition.height !== undefined) {
    diff.height = Math.abs(actual.height - expectedPosition.height);
  }
  
  const matches = diff.x <= tolerance && diff.y <= tolerance &&
    (expectedPosition.width === undefined || (diff.width !== undefined && diff.width <= tolerance)) &&
    (expectedPosition.height === undefined || (diff.height !== undefined && diff.height <= tolerance));
  
  return {
    matches,
    actual,
    expected: expectedPosition,
    diff,
    tolerance
  };
}

/**
 * Recursive object comparison helper
 * 
 * @param {unknown} extracted - Extracted state
 * @param {unknown} expected - Expected state
 * @param {string} path - Current path in object tree
 * @param {string[]} discrepancies - Array to collect discrepancies
 * @param {number} tolerance - Pixel tolerance for numeric comparisons
 * @param {number} depth - Current recursion depth (prevents stack overflow)
 */
function compareObjects(extracted, expected, path, discrepancies, tolerance, depth = 0) {
  // Prevent stack overflow on deeply nested objects
  if (depth > 100) {
    discrepancies.push(`${path}: Maximum comparison depth (100) exceeded - possible circular reference or extremely deep nesting`);
    return;
  }
  
  if (typeof expected !== typeof extracted) {
    discrepancies.push(`${path}: Type mismatch (expected ${typeof expected}, got ${typeof extracted})`);
    return;
  }
  
  if (typeof expected === 'object' && expected !== null && extracted !== null) {
    if (Array.isArray(expected)) {
      if (!Array.isArray(extracted)) {
        discrepancies.push(`${path}: Expected array, got ${typeof extracted}`);
        return;
      }
      if (expected.length !== extracted.length) {
        discrepancies.push(`${path}: Array length mismatch (expected ${expected.length}, got ${extracted.length})`);
      }
      expected.forEach((item, i) => {
        compareObjects(extracted[i], item, `${path}[${i}]`, discrepancies, tolerance, depth + 1);
      });
    } else {
      const allKeys = new Set([...Object.keys(expected), ...Object.keys(extracted)]);
      allKeys.forEach(key => {
        const newPath = path ? `${path}.${key}` : key;
        if (!(key in expected)) {
          discrepancies.push(`${newPath}: Unexpected key in extracted state`);
        } else if (!(key in extracted)) {
          discrepancies.push(`${newPath}: Missing key in extracted state`);
        } else {
          compareObjects(extracted[key], expected[key], newPath, discrepancies, tolerance, depth + 1);
        }
      });
    }
  } else if (typeof expected === 'number' && typeof extracted === 'number') {
    // Handle NaN values
    if (isNaN(expected) || isNaN(extracted)) {
      if (!(isNaN(expected) && isNaN(extracted))) {
        discrepancies.push(`${path}: NaN value detected (expected ${expected}, got ${extracted})`);
      }
      return;
    }
    
    // Handle Infinity values
    if (!isFinite(expected) || !isFinite(extracted)) {
      if (expected !== extracted) {
        discrepancies.push(`${path}: Infinity value mismatch (expected ${expected}, got ${extracted})`);
      }
      return;
    }
    
    const diff = Math.abs(extracted - expected);
    if (diff > tolerance) {
      discrepancies.push(`${path}: Value differs by ${diff} (expected ${expected}, got ${extracted}, tolerance: ${tolerance})`);
    }
  } else if (extracted !== expected) {
    discrepancies.push(`${path}: Value mismatch (expected ${expected}, got ${extracted})`);
  }
}

