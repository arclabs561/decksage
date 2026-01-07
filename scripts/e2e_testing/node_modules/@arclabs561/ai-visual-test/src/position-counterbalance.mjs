/**
 * Position Counter-Balancing for Single Evaluations
 *
 * Research: Position bias is severe and systematic (arXiv:2406.07791).
 * Counter-balancing (running evaluations twice with reversed order) effectively
 * eliminates bias (arXiv:2508.02020).
 *
 * Note: arXiv:2406.07791 is the systematic study showing position bias is not random
 * and varies significantly across judges and tasks. arXiv:2508.02020 demonstrates
 * that counter-balancing effectively eliminates this bias.
 *
 * This module provides systematic counter-balancing for single screenshot
 * evaluations when position might matter (e.g., when comparing against baseline,
 * or when context order matters).
 */

import { normalizeValidationResult } from './validation-result-normalizer.mjs';

/**
 * Run evaluation with counter-balancing to eliminate position bias
 *
 * @param {Function} evaluateFn - Function that performs evaluation: (imagePath, prompt, context) => Promise<Result>
 * @param {string} imagePath - Path to screenshot
 * @param {string} prompt - Evaluation prompt
 * @param {import('./index.mjs').ValidationContext} context - Validation context
 * @param {{
 *   enabled?: boolean;
 *   baselinePath?: string | null;
 *   contextOrder?: 'original' | 'reversed';
 * }} [options={}] - Counter-balancing options
 * @returns {Promise<import('./index.mjs').ValidationResult>} Counter-balanced result
 */
export async function evaluateWithCounterBalance(evaluateFn, imagePath, prompt, context = {}, options = {}) {
  const {
    enabled = true,
    baselinePath = null,
    contextOrder = 'original'
  } = options;

  if (!enabled) {
    // Just run once without counter-balancing
    return await evaluateFn(imagePath, prompt, context);
  }

  // If no baseline and no context order dependency, no need for counter-balancing
  if (!baselinePath && !context.contextOrder) {
    return await evaluateFn(imagePath, prompt, context);
  }

  // Run evaluation twice: once with original order, once with reversed
  const originalContext = { ...context, contextOrder: 'original' };
  const reversedContext = { ...context, contextOrder: 'reversed' };

  // If baseline exists, swap order in second evaluation
  let firstResult, secondResult;

  if (baselinePath) {
    // First: image vs baseline
    firstResult = await evaluateFn(imagePath, prompt, {
      ...originalContext,
      baseline: baselinePath,
      comparisonOrder: 'image-first'
    });

    // Second: baseline vs image (reversed)
    secondResult = await evaluateFn(baselinePath, prompt, {
      ...reversedContext,
      baseline: imagePath,
      comparisonOrder: 'baseline-first'
    });
  } else {
    // Just reverse context order
    firstResult = await evaluateFn(imagePath, prompt, originalContext);
    secondResult = await evaluateFn(imagePath, prompt, reversedContext);
  }

  // Average scores and combine results
  const avgScore = firstResult.score !== null && secondResult.score !== null
    ? (firstResult.score + secondResult.score) / 2
    : firstResult.score ?? secondResult.score;

  // Combine issues (deduplicate)
  const allIssues = [
    ...(firstResult.issues || []),
    ...(secondResult.issues || [])
  ];
  const uniqueIssues = [...new Set(allIssues)];

  // Combine reasoning
  const combinedReasoning = `Counter-balanced evaluation:
Original: ${firstResult.reasoning || 'N/A'}
Reversed: ${secondResult.reasoning || 'N/A'}
Average score: ${avgScore?.toFixed(2) || 'N/A'}`;

  const counterBalancedResult = {
    ...firstResult,
    score: avgScore,
    issues: uniqueIssues,
    reasoning: combinedReasoning,
    counterBalanced: true,
    originalScore: firstResult.score,
    reversedScore: secondResult.score,
    scoreDifference: firstResult.score !== null && secondResult.score !== null
      ? Math.abs(firstResult.score - secondResult.score)
      : null,
    metadata: {
      ...firstResult.metadata,
      counterBalancing: {
        enabled: true,
        originalResult: firstResult,
        reversedResult: secondResult,
        positionBiasDetected: firstResult.score !== null && secondResult.score !== null
          ? Math.abs(firstResult.score - secondResult.score) > 1.0
          : false
      }
    }
  };

  // Normalize result structure before returning (ensures consistent structure)
  return normalizeValidationResult(counterBalancedResult, 'evaluateWithCounterBalance');
}

/**
 * Check if counter-balancing is needed for this evaluation
 *
 * @param {import('./index.mjs').ValidationContext} context - Validation context
 * @returns {boolean} Whether counter-balancing should be applied
 */
export function shouldUseCounterBalance(context) {
  // Counter-balance if:
  // 1. Baseline is provided (position matters in comparison)
  // 2. Context order is explicitly set
  // 3. Multiple images are being compared
  return !!(
    context.baseline ||
    context.contextOrder ||
    (Array.isArray(context.images) && context.images.length > 1)
  );
}

