/**
 * Uncertainty Reduction for VLLM API Calls
 * 
 * Research-backed strategies to reduce uncertainty in VLLM judgments:
 * - Multiple API calls (self-consistency, ensemble)
 * - Logprob analysis (token-level confidence)
 * - Hallucination detection
 * - Confidence calibration
 * 
 * Research: Self-consistency improves accuracy by 5-15% (arXiv:2203.11171)
 * Research: Ensemble methods reduce uncertainty (arXiv:2305.10429)
 */

import { detectHallucination } from './hallucination-detector.mjs';
import { log, warn } from './logger.mjs';

/**
 * Estimate uncertainty from logprobs
 * 
 * @param {any} logprobs - Logprobs from API response
 * @returns {Object} Uncertainty estimate
 */
export function estimateUncertainty(logprobs) {
  if (!logprobs) {
    return { uncertainty: 0.5, confidence: 0.5, method: 'default' };
  }

  // OpenAI format: { tokens: [...], token_logprobs: [...] }
  if (Array.isArray(logprobs.token_logprobs)) {
    const valid = logprobs.token_logprobs.filter(p => p !== null);
    if (valid.length === 0) {
      return { uncertainty: 0.5, confidence: 0.5, method: 'no-logprobs' };
    }

    const avgLogprob = valid.reduce((a, b) => a + b, 0) / valid.length;
    const minLogprob = Math.min(...valid);
    const maxLogprob = Math.max(...valid);
    const variance = valid.reduce((sum, p) => sum + Math.pow(p - avgLogprob, 2), 0) / valid.length;

    // Convert logprob to probability: exp(logprob)
    const avgProb = Math.exp(avgLogprob);
    const minProb = Math.exp(minLogprob);

    // Uncertainty: inverse of confidence
    // Low logprob (more negative) = high uncertainty
    // Threshold: -2.0 ≈ 13% probability
    const uncertainty = avgLogprob < -2.0 
      ? Math.min(1.0, 1.0 - avgProb)
      : Math.max(0.0, 1.0 - avgProb);

    const confidence = 1.0 - uncertainty;

    return {
      uncertainty: Math.max(0, Math.min(1, uncertainty)),
      confidence: Math.max(0, Math.min(1, confidence)),
      method: 'logprobs',
      avgLogprob,
      avgProb,
      minProb,
      variance,
      tokenCount: valid.length
    };
  }

  // Gemini format: varies, may be nested
  if (typeof logprobs === 'object' && logprobs !== null) {
    // Try to extract any numeric logprob values
    const values = extractNumericValues(logprobs);
    if (values.length > 0) {
      const avg = values.reduce((a, b) => a + b, 0) / values.length;
      const uncertainty = avg < -2.0 ? Math.min(1.0, 1.0 - Math.exp(avg)) : Math.max(0.0, 1.0 - Math.exp(avg));
      return {
        uncertainty: Math.max(0, Math.min(1, uncertainty)),
        confidence: 1.0 - uncertainty,
        method: 'logprobs-gemini',
        avgLogprob: avg
      };
    }
  }

  return { uncertainty: 0.5, confidence: 0.5, method: 'unknown-format' };
}

/**
 * Extract numeric values from nested object
 */
function extractNumericValues(obj, maxDepth = 3, depth = 0) {
  if (depth > maxDepth) return [];
  
  const values = [];
  if (typeof obj === 'number') {
    values.push(obj);
  } else if (Array.isArray(obj)) {
    obj.forEach(item => values.push(...extractNumericValues(item, maxDepth, depth + 1)));
  } else if (typeof obj === 'object' && obj !== null) {
    Object.values(obj).forEach(val => values.push(...extractNumericValues(val, maxDepth, depth + 1)));
  }
  
  return values;
}

/**
 * Self-consistency check: Multiple API calls with same prompt
 * 
 * Research: Self-consistency improves accuracy by 5-15% (arXiv:2203.11171)
 * 
 * @param {Function} judgeFn - Function to call judge API
 * @param {number} [n=3] - Number of calls to make
 * @param {Object} [options={}] - Options
 * @returns {Promise<Object>} Aggregated result with consistency metrics
 */
export async function selfConsistencyCheck(judgeFn, n = 3, options = {}) {
  const {
    minAgreement = 0.7, // Minimum agreement threshold
    maxCalls = 5 // Maximum calls before giving up
  } = options;

  const results = [];
  let attempts = 0;

  // Make multiple calls
  while (results.length < n && attempts < maxCalls) {
    attempts++;
    try {
      const result = await judgeFn();
      if (result && result.score !== null) {
        results.push(result);
      }
    } catch (error) {
      warn(`[Uncertainty] Self-consistency call ${attempts} failed: ${error.message}`);
    }
  }

  if (results.length === 0) {
    return {
      score: null,
      uncertainty: 1.0,
      confidence: 0.0,
      consistency: 0.0,
      method: 'self-consistency-failed'
    };
  }

  // Calculate consistency
  const scores = results.map(r => r.score).filter(s => s !== null);
  if (scores.length === 0) {
    return {
      score: null,
      uncertainty: 1.0,
      confidence: 0.0,
      consistency: 0.0,
      method: 'self-consistency-no-scores'
    };
  }

  // Mean score
  const meanScore = scores.reduce((a, b) => a + b, 0) / scores.length;

  // Standard deviation (measure of consistency)
  const variance = scores.reduce((sum, s) => sum + Math.pow(s - meanScore, 2), 0) / scores.length;
  const stdDev = Math.sqrt(variance);

  // Consistency: inverse of coefficient of variation
  // Lower stdDev relative to mean = higher consistency
  const consistency = meanScore > 0 
    ? Math.max(0, Math.min(1, 1.0 - (stdDev / meanScore)))
    : stdDev < 1.0 ? 1.0 - stdDev : 0.0;

  // Uncertainty: inverse of consistency
  const uncertainty = 1.0 - consistency;

  // Confidence: weighted by consistency and number of calls
  const confidence = consistency * Math.min(1.0, results.length / n);

  // VERIFIABLE: Calculate improvement metrics if baseline is provided
  // This allows verification of the "improves accuracy by 5-15%" claim
  let improvementMetrics = null;
  if (options.baselineScore !== undefined && options.baselineScore !== null) {
    const scoreImprovement = meanScore - options.baselineScore;
    // CRITICAL FIX: Handle baseline=0 case more robustly
    // MCP research: When baseline is 0, standard percentage formula breaks (division by zero)
    // Solution: Normalize against maximum scale (default 10, but configurable)
    // This ensures consistent behavior across different scales (0-10, 0-100, etc.)
    const maxScale = options.maxScale || 10; // Default to 0-10 scale, but allow override
    const improvementPercent = options.baselineScore > 0 
      ? (scoreImprovement / options.baselineScore) * 100 
      : (scoreImprovement / maxScale) * 100; // Normalize against scale maximum when baseline is 0
    
    improvementMetrics = {
      baselineScore: options.baselineScore,
      improvedScore: meanScore,
      improvement: scoreImprovement,
      improvementPercent,
      // Research claim: 5-15% improvement
      meetsResearchClaim: improvementPercent >= 5 && improvementPercent <= 15
    };
    
    // VERIFIABLE: Log improvement when it meets research claim threshold
    if (improvementPercent >= 5) {
      log(`[SelfConsistency] Accuracy improvement: ${improvementPercent.toFixed(1)}% (${options.baselineScore.toFixed(1)} → ${meanScore.toFixed(1)})`);
    }
  }

  return {
    score: Math.round(meanScore * 10) / 10, // Round to 1 decimal
    uncertainty: Math.max(0, Math.min(1, uncertainty)),
    confidence: Math.max(0, Math.min(1, confidence)),
    consistency: Math.max(0, Math.min(1, consistency)),
    method: 'self-consistency',
    calls: results.length,
    stdDev,
    scores,
    results,
    // VERIFIABLE: Export improvement metrics to verify research claim
    improvementMetrics
  };
}

/**
 * Ensemble uncertainty reduction
 * 
 * Combine multiple uncertainty sources:
 * - Logprob-based uncertainty
 * - Self-consistency uncertainty
 * - Hallucination detection
 * 
 * @param {Object} sources - Uncertainty sources
 * @returns {Object} Combined uncertainty estimate
 */
export function combineUncertaintySources(sources) {
  const {
    logprobs = null,
    selfConsistency = null,
    hallucination = null,
    retryCount = 1
  } = sources;

  const estimates = [];

  // 1. Logprob-based uncertainty
  if (logprobs) {
    const logprobEst = estimateUncertainty(logprobs);
    estimates.push({
      uncertainty: logprobEst.uncertainty,
      confidence: logprobEst.confidence,
      weight: 0.4,
      source: 'logprobs'
    });
  }

  // 2. Self-consistency uncertainty
  if (selfConsistency) {
    estimates.push({
      uncertainty: selfConsistency.uncertainty || (1.0 - selfConsistency.consistency),
      confidence: selfConsistency.confidence || selfConsistency.consistency,
      weight: 0.4,
      source: 'self-consistency'
    });
  }

  // 3. Hallucination detection
  if (hallucination) {
    estimates.push({
      uncertainty: 1.0 - hallucination.confidence,
      confidence: hallucination.confidence,
      weight: 0.2,
      source: 'hallucination'
    });
  }

  // 4. Retry count (more retries = higher uncertainty)
  if (retryCount > 1) {
    estimates.push({
      uncertainty: Math.min(0.3, (retryCount - 1) * 0.1),
      confidence: Math.max(0.7, 1.0 - (retryCount - 1) * 0.1),
      weight: 0.1,
      source: 'retries'
    });
  }

  // Weighted average
  if (estimates.length === 0) {
    return { uncertainty: 0.5, confidence: 0.5, method: 'default' };
  }

  const totalWeight = estimates.reduce((sum, e) => sum + e.weight, 0);
  const weightedUncertainty = estimates.reduce((sum, e) => sum + (e.uncertainty * e.weight), 0) / totalWeight;
  const weightedConfidence = estimates.reduce((sum, e) => sum + (e.confidence * e.weight), 0) / totalWeight;

  return {
    uncertainty: Math.max(0, Math.min(1, weightedUncertainty)),
    confidence: Math.max(0, Math.min(1, weightedConfidence)),
    method: 'ensemble',
    sources: estimates.map(e => e.source),
    breakdown: estimates
  };
}

/**
 * Determine if self-consistency should be used based on context (uncertainty × payout analysis)
 * 
 * Based on research: Self-consistency provides highest ROI for:
 * - Critical/high-stakes scenarios (expert, medical, accessibility)
 * - Edge cases (extreme scores)
 * - High uncertainty scenarios
 * - High-impact issues (blocks-use, degrades-experience)
 * 
 * @param {Object} context - Validation context
 * @param {Object} partialResult - Partial validation result (score, issues, uncertainty)
 * @returns {Object} { shouldUse: boolean, n: number, reason: string }
 */
export function shouldUseSelfConsistency(context = {}, partialResult = {}) {
  const { testType, importance, impact } = context;
  const { score, uncertainty, issues } = partialResult;
  
  // Use constants for thresholds (imported at top level to avoid async)
  // These values are documented in src/constants.mjs and docs/misc/UNCERTAINTY_TIER_LOGIC.md
  const LOW_SCORE_THRESHOLD = 3;  // Bottom 30% of 0-10 scale
  const HIGH_SCORE_THRESHOLD = 9;  // Top 10% of 0-10 scale
  const HIGH_UNCERTAINTY_THRESHOLD = 0.3;  // 30% uncertainty
  const OVER_DETECTION_ISSUE_COUNT = 5;  // 5+ issues might indicate hallucination
  const TIER1_N = 5;  // Tier 1: Critical scenarios (expert, medical, blocking issues)
  const EDGE_CASE_N = 3;  // Tier 2: Edge cases

  // Tier 1: Critical scenarios (always use, N=5)
  if (testType === 'expert-evaluation' || testType === 'medical') {
    return {
      shouldUse: true,
      n: TIER1_N,
      reason: `Critical test type: ${testType}`
    };
  }

  // Tier 1: Critical issues (blocks-use with critical importance)
  if (importance === 'critical' && impact === 'blocks-use') {
    return {
      shouldUse: true,
      n: TIER1_N,
      reason: 'Critical issue that blocks use'
    };
  }

  // Tier 2: Edge cases (extreme scores)
  // NOTE: Thresholds (3, 9) represent bottom 30% and top 10% of 0-10 scale
  // These are where models are most likely to be incorrect
  if (score !== null && (score <= LOW_SCORE_THRESHOLD || score >= HIGH_SCORE_THRESHOLD)) {
    return {
      shouldUse: true,
      n: EDGE_CASE_N,
      reason: `Edge case score: ${score}`
    };
  }

  // Tier 2: High uncertainty
  // NOTE: 0.3 threshold based on research showing uncertainty > 0.3 indicates low confidence
  if (uncertainty !== null && uncertainty > HIGH_UNCERTAINTY_THRESHOLD) {
    return {
      shouldUse: true,
      n: EDGE_CASE_N,
      reason: `High uncertainty: ${uncertainty.toFixed(2)}`
    };
  }

  // Tier 2: Many issues (over-detection risk)
  // NOTE: 5+ issues might indicate hallucination/over-detection
  if (Array.isArray(issues) && issues.length >= OVER_DETECTION_ISSUE_COUNT) {
    return {
      shouldUse: true,
      n: EDGE_CASE_N,
      reason: `Many issues detected: ${issues.length} (over-detection risk)`
    };
  }

  // Tier 2: High-impact degradation
  if (importance === 'high' && impact === 'degrades-experience') {
    return {
      shouldUse: true,
      n: 3,
      reason: 'High-impact issue that degrades experience'
    };
  }

  // Tier 3: Standard scenarios (no self-consistency)
  return {
    shouldUse: false,
    n: 0,
    reason: 'Standard validation (logprobs + hallucination sufficient)'
  };
}

/**
 * Enhance validation result with uncertainty reduction
 * 
 * @param {Object} partialResult - Partial validation result (judgment, logprobs, attempts, screenshotPath)
 * @param {Object} [options={}] - Options
 * @param {Object} [context={}] - Validation context (for adaptive self-consistency)
 * @returns {Object} Uncertainty and confidence estimates
 */
export function enhanceWithUncertainty(partialResult, options = {}, context = {}) {
  const {
    enableSelfConsistency = false,
    enableHallucinationCheck = true,
    adaptiveSelfConsistency = true // New: adaptive strategy based on context
  } = options;

  // Extract uncertainty sources
  const logprobs = partialResult.logprobs || null;
  const attempts = partialResult.attempts || 1;
  const judgment = partialResult.judgment || null;
  const score = partialResult.score || null;
  const issues = partialResult.issues || [];
  const uncertainty = partialResult.uncertainty || null;

  // Determine if self-consistency should be used (adaptive strategy)
  let shouldUseSelfConsistencyValue = enableSelfConsistency;
  let selfConsistencyN = 3;
  let selfConsistencyReason = '';

  if (adaptiveSelfConsistency && !enableSelfConsistency) {
    // Check if context suggests self-consistency is warranted
    const selfConsistencyDecision = shouldUseSelfConsistency(context, {
      score,
      uncertainty,
      issues
    });
    shouldUseSelfConsistencyValue = selfConsistencyDecision.shouldUse;
    selfConsistencyN = selfConsistencyDecision.n;
    selfConsistencyReason = selfConsistencyDecision.reason;
  } else if (enableSelfConsistency) {
    selfConsistencyReason = 'Explicitly enabled';
  }

  // Estimate uncertainty from logprobs
  const logprobUncertainty = logprobs ? estimateUncertainty(logprobs) : null;

  // Check for hallucination
  let hallucinationResult = null;
  if (enableHallucinationCheck && judgment) {
    try {
      hallucinationResult = detectHallucination(
        judgment,
        partialResult.screenshotPath || null,
        { logprobs }
      );
    } catch (error) {
      // Silently fail
    }
  }

  // Combine uncertainty sources
  const combined = combineUncertaintySources({
    logprobs: logprobUncertainty,
    hallucination: hallucinationResult,
    retryCount: attempts
  });

  // Return uncertainty metrics with self-consistency recommendation
  return {
    uncertainty: combined.uncertainty,
    confidence: combined.confidence,
    uncertaintyMethod: combined.method,
    uncertaintyBreakdown: combined.breakdown || null,
    hallucination: hallucinationResult,
    // Self-consistency recommendation (caller should use this if needed)
    selfConsistencyRecommended: shouldUseSelfConsistencyValue,
    selfConsistencyN,
    selfConsistencyReason
  };
}

