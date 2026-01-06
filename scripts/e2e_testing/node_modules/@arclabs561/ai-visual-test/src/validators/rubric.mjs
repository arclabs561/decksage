/**
 * Rubric System
 * 
 * Generic rubric-based validation with zero tolerance support
 * 
 * Provides:
 * - Rubric-based validation
 * - Zero tolerance violation enforcement
 * - Research-enhanced validation integration
 */

import { validateWithResearchEnhancements } from '../research-enhanced-validation.mjs';
import { PromptBuilder } from './prompt-builder.mjs';
import { ValidationError } from '../errors.mjs';
import { assertString, assertObject } from '../type-guards.mjs';

/**
 * Validate with rubric (generic, not project-specific)
 */
export async function validateWithRubric(screenshotPath, prompt, rubric, context = {}, options = {}) {
  // Input validation
  assertString(screenshotPath, 'screenshotPath');
  assertString(prompt, 'prompt');
  assertObject(rubric, 'rubric');
  
  if (!rubric.score || !rubric.score.criteria) {
    throw new ValidationError(
      'Rubric must have score.criteria property',
      { rubric: Object.keys(rubric) }
    );
  }
  
  const builder = new PromptBuilder({ rubric });
  const enhancedPrompt = builder.buildPrompt(prompt, {
    enforceZeroTolerance: options.enforceZeroTolerance !== false,
    ...options
  });
  
  try {
    const result = await validateWithResearchEnhancements(
      screenshotPath,
      enhancedPrompt,
      {
        ...context,
        rubric,
        testType: context.testType || 'rubric-validation'
      }
    );
  
    // Check for zero tolerance violations if rubric has them
    const hasZeroTolerance = rubric?.criteria?.some(c => c.zeroTolerance) || false;
    if (hasZeroTolerance && options.enforceZeroTolerance !== false) {
      // Ensure issues is an array before calling .some()
      const issues = Array.isArray(result.issues) ? result.issues : [];
      const hasZeroToleranceViolation = issues.some(issue => 
        typeof issue === 'string' && (
          issue.toLowerCase().includes('zero tolerance') ||
          issue.toLowerCase().includes('instant fail') ||
          rubric.criteria.some(c => c.zeroTolerance && issue.includes(c.id))
        )
      );
      
      if (hasZeroToleranceViolation) {
        return {
          ...result,
          score: 0,
          assessment: 'fail',
          zeroToleranceViolation: true
        };
      }
    }
    
    return result;
  } catch (error) {
    // Re-throw ValidationError as-is, wrap others
    if (error instanceof ValidationError) {
      throw error;
    }
    throw new ValidationError(
      `Rubric validation failed: ${error.message}`,
      { screenshotPath, rubricName: rubric.name, originalError: error.message }
    );
  }
}

