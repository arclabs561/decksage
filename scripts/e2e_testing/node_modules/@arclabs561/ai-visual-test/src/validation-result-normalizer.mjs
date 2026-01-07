/**
 * Validation Result Normalizer
 * 
 * Ensures validation results have consistent structure.
 * Centralizes normalization logic to avoid duplication.
 */

import { warn } from './logger.mjs';

/**
 * Normalize validation result to ensure consistent structure
 * 
 * @param {Object} result - Validation result from validateScreenshot
 * @param {string} [source] - Source function name for logging
 * @returns {Object} Normalized validation result
 */
export function normalizeValidationResult(result, source = 'unknown') {
  if (!result) {
    warn(`[Normalizer] ${source}: result is null/undefined`);
    return {
      enabled: false,
      score: null,
      issues: [],
      reasoning: 'Result was null or undefined',
      assessment: null
    };
  }

  // Create a copy to avoid mutating the original
  const normalized = { ...result };

  // Ensure enabled field is always present (default to true if not specified)
  if (normalized.enabled === undefined) {
    // If enabled is not specified, infer from presence of other fields
    normalized.enabled = normalized.score !== null || normalized.judgment || normalized.provider !== undefined;
  }

  // Ensure score is always present (may be null)
  if (normalized.score === null || normalized.score === undefined) {
    if (normalized.score === undefined) {
      warn(`[Normalizer] ${source}: score is undefined, defaulting to null`);
    }
    normalized.score = null;
  }

  // Ensure issues is always an array
  if (!Array.isArray(normalized.issues)) {
    warn(`[Normalizer] ${source}: issues is not an array, defaulting to empty array`);
    normalized.issues = [];
  }

  // Ensure reasoning is always present
  if (!normalized.reasoning) {
    normalized.reasoning = normalized.judgment || normalized.message || 'No reasoning provided';
  }

  // Ensure assessment is present (may be null)
  if (normalized.assessment === undefined) {
    normalized.assessment = null;
  }

  return normalized;
}

