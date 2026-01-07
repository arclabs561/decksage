/**
 * State Validator
 *
 * Generic state validation for any structured state (game state, UI state, form state, etc.)
 *
 * Provides:
 * - Configurable state extraction
 * - Deep comparison with tolerance
 * - Extensible via plugins
 */

import { validateScreenshot } from '../judge.mjs';
import { ValidationError, StateMismatchError } from '../errors.mjs';
import { assertString, assertObject } from '../type-guards.mjs';

/**
 * Generic state validator for any structured state validation
 * Works with game state, UI state, form state, etc.
 */
export class StateValidator {
  constructor(options = {}) {
    // Validate tolerance
    if (options.tolerance !== undefined) {
      if (typeof options.tolerance !== 'number' || options.tolerance < 0 || isNaN(options.tolerance)) {
        throw new ValidationError(
          'tolerance must be a non-negative number',
          { received: options.tolerance }
        );
      }
      this.tolerance = options.tolerance;
    } else {
      this.tolerance = 5; // pixels for position-based validation
    }

    this.validateScreenshot = options.validateScreenshot || validateScreenshot;
    this.stateExtractor = options.stateExtractor || this.defaultStateExtractor.bind(this);
    this.stateComparator = options.stateComparator || this.defaultStateComparator.bind(this);
  }

  /**
   * Static method for quick validation without instantiation
   *
   * @param {string} screenshotPath - Path to screenshot
   * @param {object} expectedState - Expected state object
   * @param {object} options - Validation options (tolerance, testType, etc.)
   * @returns {Promise<object>} Validation result with extracted state and comparison
   */
  static async validate(screenshotPath, expectedState, options = {}) {
    const validator = new StateValidator(options);
    return validator.validateState(screenshotPath, expectedState, options);
  }

  /**
   * Validate state matches visual representation
   *
   * @param {string | string[]} screenshotPath - Path to screenshot(s) - supports multi-image for comparison
   * @param {object} expectedState - Expected state object
   * @param {object} options - Validation options
   * @param {function} options.promptBuilder - Custom prompt builder function
   * @param {object} options.context - Additional context for validation
   * @returns {Promise<object>} Validation result with extracted state and comparison
   */
  async validateState(screenshotPath, expectedState, options = {}) {
    // Input validation - support both single and array
    const isArray = Array.isArray(screenshotPath);
    if (!isArray) {
      assertString(screenshotPath, 'screenshotPath');
    } else {
      screenshotPath.forEach((path, i) => {
        assertString(path, `screenshotPath[${i}]`);
      });
    }
    assertObject(expectedState, 'expectedState');

    if (!expectedState || typeof expectedState !== 'object') {
      throw new ValidationError(
        'expectedState must be a non-null object',
        { received: typeof expectedState, value: expectedState }
      );
    }

    const prompt = options.promptBuilder
      ? options.promptBuilder(expectedState, { tolerance: this.tolerance, ...options })
      : this.buildStatePrompt(expectedState, options);

    try {
      // Pass through all validateScreenshot options (useCache, timeout, provider, viewport, etc.)
      const screenshotOptions = {
        testType: options.testType || 'state-validation',
        expectedState,
        ...options.context,
        // Explicitly pass through common options
        useCache: options.useCache !== undefined ? options.useCache : options.context?.useCache,
        timeout: options.timeout || options.context?.timeout,
        provider: options.provider || options.context?.provider,
        viewport: options.viewport || options.context?.viewport
      };

      // Support multi-image (array of screenshots) for comparison
      const result = await this.validateScreenshot(screenshotPath, prompt, screenshotOptions);

      // Extract state from result
      const extractedState = this.stateExtractor(result, expectedState);

      // Compare with expected
      const validation = this.stateComparator(extractedState, expectedState, {
        tolerance: this.tolerance,
        ...options
      });

      const matches = validation.discrepancies.length === 0;

      // Throw StateMismatchError if validation fails and throwOnMismatch is enabled
      if (!matches && options.throwOnMismatch !== false) {
        throw new StateMismatchError(
          validation.discrepancies,
          extractedState,
          expectedState
        );
      }

      return {
        ...result,
        extractedState,
        expectedState,
        validation,
        matches
      };
    } catch (error) {
      // Re-throw ValidationError as-is, wrap others
      if (error instanceof ValidationError) {
        throw error;
      }
      throw new ValidationError(
        `State validation failed: ${error.message}`,
        { screenshotPath, expectedState, originalError: error.message }
      );
    }
  }

  /**
   * Build generic state validation prompt
   */
  buildStatePrompt(expectedState, options = {}) {
    const stateDescription = options.stateDescription || 'current state';
    const extractionTasks = options.extractionTasks || [
      'Extract current state from screenshot',
      'Compare with expected state',
      'Report discrepancies'
    ];

    return `Extract ${stateDescription} from screenshot with precision:

EXPECTED STATE:
${JSON.stringify(expectedState, null, 2)}

EXTRACTION TASKS:
${extractionTasks.map((task, i) => `${i + 1}. ${task}`).join('\n')}

VALIDATION:
- Compare extracted state to expected state
- Report discrepancies with differences
${this.tolerance ? `- Tolerance: ${this.tolerance}px for positions` : ''}

Return structured data with extracted state and validation results.`;
  }

  /**
   * Default state extractor - tries to extract from structured data or parse from text
   */
  defaultStateExtractor(result, expectedState) {
    // Try structured data first
    if (result.structuredData) {
      // Validate that structuredData is an object
      if (typeof result.structuredData === 'object' && result.structuredData !== null) {
        return result.structuredData;
      }
    }

    // Try to parse from reasoning/assessment
    const text = result.reasoning || result.assessment || '';
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[0]);
        // Validate parsed result is an object
        if (typeof parsed === 'object' && parsed !== null) {
          return parsed;
        }
      } catch (e) {
        // Fall through - extraction failed
      }
    }

    // Return null to indicate extraction failed
    // Note: null might be a valid state value, but this is the best we can do
    // without a sentinel value. Callers should check if extraction succeeded.
    return null;
  }

  /**
   * Default state comparator - deep comparison with tolerance for numeric values
   */
  defaultStateComparator(extracted, expected, options = {}) {
    if (!extracted || !expected) {
      return {
        matches: false,
        discrepancies: ['Missing state data']
      };
    }

    const discrepancies = [];
    const tolerance = options.tolerance || this.tolerance;

    // Recursive comparison
    this.compareObjects(extracted, expected, '', discrepancies, tolerance);

    return {
      matches: discrepancies.length === 0,
      discrepancies
    };
  }

  /**
   * Recursive object comparison helper
   * @param {number} depth - Current recursion depth (prevents stack overflow)
   */
  compareObjects(extracted, expected, path, discrepancies, tolerance, depth = 0) {
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
          this.compareObjects(extracted[i], item, `${path}[${i}]`, discrepancies, tolerance, depth + 1);
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
            this.compareObjects(extracted[key], expected[key], newPath, discrepancies, tolerance, depth + 1);
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
}

