/**
 * Hybrid Validator
 * 
 * Combines programmatic validation with VLLM evaluation.
 * Programmatic data provides ground truth, VLLM provides semantic reasoning.
 * 
 * This follows the PROVE framework pattern: programmatic verification + LLM evaluation.
 */

import { validateScreenshot } from '../judge.mjs';
import { ValidationError } from '../errors.mjs';
import { assertString, assertObject } from '../type-guards.mjs';
import {
  checkAllTextContrast,
  checkKeyboardNavigation
} from './accessibility-programmatic.mjs';
import {
  validateStateProgrammatic
} from './state-programmatic.mjs';

// Allow dependency injection for testing
let injectedValidateScreenshot = null;

/**
 * Inject validateScreenshot function for testing
 * @internal
 * @param {Function} fn - Mock validateScreenshot function
 */
export function _injectValidateScreenshot(fn) {
  injectedValidateScreenshot = fn;
}

/**
 * Reset injected function
 * @internal
 */
export function _resetValidateScreenshot() {
  injectedValidateScreenshot = null;
}

function getValidateScreenshot() {
  return injectedValidateScreenshot || validateScreenshot;
}

/**
 * Hybrid accessibility validation
 * 
 * Combines programmatic contrast/keyboard checks with VLLM semantic evaluation.
 * Programmatic data provides ground truth, VLLM evaluates context and criticality.
 * 
 * @param {any} page - Playwright page object
 * @param {string} screenshotPath - Path to screenshot
 * @param {number} minContrast - Minimum contrast ratio (default: 4.5)
 * @param {object} options - Validation options
 * @returns {Promise<import('../index.mjs').ValidationResult & {programmaticData: object}>}
 * @throws {ValidationError} If inputs are invalid
 */
export async function validateAccessibilityHybrid(
  page,
  screenshotPath,
  minContrast = 4.5,
  options = {}
) {
  // Validate inputs
  if (!page || typeof page.evaluate !== 'function') {
    throw new ValidationError('validateAccessibilityHybrid requires a Playwright Page object', {
      received: typeof page,
      hasEvaluate: typeof page?.evaluate === 'function'
    });
  }
  
  assertString(screenshotPath, 'screenshotPath');
  
  if (typeof minContrast !== 'number' || minContrast < 1 || minContrast > 21) {
    throw new ValidationError('minContrast must be a number between 1 and 21', {
      received: minContrast
    });
  }
  
  // Extract programmatic data
  const programmaticData = {
    contrast: await checkAllTextContrast(page, minContrast),
    keyboard: await checkKeyboardNavigation(page)
  };
  
  // Build prompt with programmatic context
  const prompt = `
ACCESSIBILITY EVALUATION

PROGRAMMATIC DATA (GROUND TRUTH):
- Contrast: ${programmaticData.contrast.passing}/${programmaticData.contrast.total} elements pass (required: ${minContrast}:1)
- Violations: ${programmaticData.contrast.failing} elements fail
${programmaticData.contrast.violations.length > 0 ? `
  Top violations:
${programmaticData.contrast.violations.slice(0, 5).map(v => `  - ${v.element}: ${v.ratio}:1 (required: ${v.required}:1)`).join('\n')}
` : ''}
- Keyboard: ${programmaticData.keyboard.focusableElements} focusable elements
${programmaticData.keyboard.violations.length > 0 ? `
  Violations:
${programmaticData.keyboard.violations.map(v => `  - ${v.element}: ${v.issue}`).join('\n')}
` : ''}

EVALUATION TASK:
Use this programmatic data as ground truth (no hallucinations about measurements).
Evaluate semantic aspects:
1. Is contrast adequate for readability in context? (ratio alone doesn't tell you if it's readable)
2. Are contrast violations critical or minor? (some violations might be acceptable in context)
3. Is keyboard navigation intuitive? (semantic evaluation beyond just focusable elements)
4. Does overall accessibility support user goals? (holistic evaluation)
5. Are there accessibility issues that programmatic checks don't capture? (visual, semantic, contextual)

Provide actionable recommendations based on both programmatic and semantic analysis.
`;
  
  // VLLM evaluation with programmatic grounding
  const result = await getValidateScreenshot()(screenshotPath, prompt, {
    testType: options.testType || 'accessibility-hybrid',
    minContrast,
    ...options,
    programmaticData
  });
  
  return {
    ...result,
    programmaticData
  };
}

/**
 * Hybrid state validation
 * 
 * Combines programmatic state extraction with VLLM semantic evaluation.
 * Programmatic data provides ground truth, VLLM evaluates visual consistency and context.
 * 
 * @param {any} page - Playwright page object
 * @param {string} screenshotPath - Path to screenshot
 * @param {object} expectedState - Expected state object
 * @param {object} options - Validation options
 * @param {object} options.selectors - Map of state keys to CSS selectors
 * @param {number} options.tolerance - Pixel tolerance (default: 5)
 * @returns {Promise<import('../index.mjs').ValidationResult & {programmaticData: object}>}
 * @throws {ValidationError} If inputs are invalid
 */
export async function validateStateHybrid(
  page,
  screenshotPath,
  expectedState,
  options = {}
) {
  // Validate inputs
  if (!page || typeof page.evaluate !== 'function') {
    throw new ValidationError('validateStateHybrid requires a Playwright Page object', {
      received: typeof page,
      hasEvaluate: typeof page?.evaluate === 'function'
    });
  }
  
  assertString(screenshotPath, 'screenshotPath');
  assertObject(expectedState, 'expectedState');
  
  const selectors = options.selectors || {};
  const tolerance = options.tolerance || 5;
  
  // Extract programmatic state
  // Note: validateStateProgrammatic will extract gameState internally if available
  // We also extract it separately for the prompt
  const gameState = await page.evaluate(() => window.gameState || null);
  
  // validateStateProgrammatic doesn't throw by default, it returns matches: false
  const visualState = await validateStateProgrammatic(
    page,
    expectedState,
    { selectors, tolerance }
  );
  
  // visualState already includes gameState if extracted, but we want it in programmaticData too
  
  const programmaticData = {
    gameState,
    visualState: visualState.visualState,
    discrepancies: visualState.discrepancies,
    matches: visualState.matches
  };
  
  // Build prompt with programmatic context
  const prompt = `
STATE CONSISTENCY EVALUATION

PROGRAMMATIC DATA (GROUND TRUTH):
${gameState ? `Game State: ${JSON.stringify(gameState, null, 2)}` : 'Game State: Not available'}
Visual State: ${JSON.stringify(visualState.visualState, null, 2)}
Expected State: ${JSON.stringify(expectedState, null, 2)}
${visualState.discrepancies.length > 0 ? `
Discrepancies: ${visualState.discrepancies.join(', ')}
` : 'No discrepancies found (programmatic check passed)'}

EVALUATION TASK:
Use this programmatic data as ground truth (no hallucinations about positions/state).
Evaluate semantic aspects:
1. Does visual representation match programmatic state? (semantic check beyond exact positions)
2. Is game state consistent with gameplay? (context-aware evaluation)
3. Are there visual bugs that state data doesn't capture? (holistic evaluation)
4. Is the state transition smooth and coherent? (temporal/contextual evaluation)
5. Are discrepancies critical or acceptable? (context-aware criticality assessment)

Provide actionable recommendations based on both programmatic and semantic analysis.
`;
  
  // VLLM evaluation with programmatic grounding
  const result = await getValidateScreenshot()(screenshotPath, prompt, {
    testType: options.testType || 'state-hybrid',
    expectedState,
    ...options,
    programmaticData
  });
  
  return {
    ...result,
    programmaticData
  };
}

/**
 * Generic hybrid validator helper
 * 
 * Combines any programmatic data with VLLM evaluation.
 * 
 * @param {string} screenshotPath - Path to screenshot
 * @param {string} prompt - Base evaluation prompt
 * @param {object} programmaticData - Programmatic validation data
 * @param {object} options - Validation options
 * @returns {Promise<import('../index.mjs').ValidationResult & {programmaticData: object}>}
 */
export async function validateWithProgrammaticContext(
  screenshotPath,
  prompt,
  programmaticData,
  options = {}
) {
  assertString(screenshotPath, 'screenshotPath');
  assertString(prompt, 'prompt');
  assertObject(programmaticData, 'programmaticData');
  
  // Build enhanced prompt with programmatic context
  const enhancedPrompt = `
${prompt}

PROGRAMMATIC DATA (GROUND TRUTH):
${JSON.stringify(programmaticData, null, 2)}

EVALUATION INSTRUCTIONS:
- Use programmatic data as ground truth (no hallucinations about measurements)
- Evaluate semantic aspects: context, criticality, usability, consistency
- Report any discrepancies between programmatic data and visual appearance
- Provide actionable recommendations based on both programmatic and semantic analysis
`;
  
  const result = await getValidateScreenshot()(screenshotPath, enhancedPrompt, {
    ...options,
    programmaticData
  });
  
  return {
    ...result,
    programmaticData
  };
}

