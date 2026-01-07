/**
 * Active Bias Mitigation
 * 
 * Uses bias detection to actively adjust scores and mitigate biases.
 * Research shows active mitigation is more effective than detection alone.
 * 
 * Based on research findings that counter-balancing and active score adjustment
 * can effectively eliminate position bias and other evaluation biases.
 * 
 * Research:
 * - Position bias: Systematic study (arXiv:2406.07791) - Position bias not random, varies by judge/task
 * - Counter-balancing: Effective elimination method (arXiv:2508.02020)
 * - Verbosity bias: Length alignment reduces bias (arXiv:2407.01085 - AdapAlpaca)
 */

import { detectBias, detectPositionBias } from './bias-detector.mjs';

/**
 * Apply bias mitigation to a judgment result
 * 
 * @param {import('./index.mjs').ValidationResult} result - Original judgment result
 * @param {import('./index.mjs').BiasDetectionResult} biasDetection - Bias detection results
 * @param {{
 *   adjustScores?: boolean;
 *   adjustIssues?: boolean;
 *   minAdjustment?: number;
 *   maxAdjustment?: number;
 * }} [options={}] - Mitigation options
 * @returns {import('./index.mjs').ValidationResult} Adjusted result
 */
export function mitigateBias(result, biasDetection, options = {}) {
  const {
    adjustScores = true,
    adjustIssues = false,
    minAdjustment = -2.0,
    maxAdjustment = 2.0
  } = options;
  
  if (!biasDetection || !biasDetection.hasBias) {
    return {
      ...result,
      biasMitigation: {
        applied: false,
        reason: 'No bias detected'
      }
    };
  }
  
  let adjustedScore = result.score;
  let adjustments = [];
  
  if (adjustScores && result.score !== null) {
    // Calculate adjustment based on detected biases
    let totalAdjustment = 0;
    
    for (const bias of biasDetection.biases) {
      let adjustment = 0;
      
      switch (bias.type) {
        case 'verbosity':
         // Verbosity bias: reduce score if reasoning is too verbose
         // Research: arXiv:2310.10076, arXiv:2407.01085
         // LLMs prefer longer answers more than humans. AdapAlpaca (arXiv:2407.01085)
         // proposes length alignment for fair comparison by decomposing preference into
         // desirability (length-independent) and information mass (length-dependent).
         //
         // IMPORTANT: This is a SIMPLIFIED mitigation. We do NOT implement AdapAlpaca's
         // full length alignment method or desirability/information mass decomposition.
         // Full implementation would:
         // - Align lengths of reference and test responses under equivalent length intervals
         // - Decompose preference into desirability (length-independent) and information mass
         // - Normalize response lengths before comparison
         //
         // Current implementation: Simple score reduction based on verbosity detection.
         // This is NOT the AdapAlpaca method, just a simplified approximation.
          adjustment = -0.5 * bias.score;
          adjustments.push({
            type: 'verbosity',
            adjustment: adjustment.toFixed(2),
            reason: 'Reduced score due to verbosity bias (research: arXiv:2310.10076, 2407.01085). Full AdapAlpaca would align lengths under equivalent intervals.',
            researchNote: 'AdapAlpaca decomposes win rate into desirability (length-independent) and information mass (length-dependent)'
          });
          break;
          
        case 'length':
          // Length bias: reduce score if length was a factor
          adjustment = -0.3 * bias.score;
          adjustments.push({
            type: 'length',
            adjustment: adjustment.toFixed(2),
            reason: 'Reduced score due to length bias'
          });
          break;
          
        case 'formatting':
          // Formatting bias: small reduction
          adjustment = -0.2 * bias.score;
          adjustments.push({
            type: 'formatting',
            adjustment: adjustment.toFixed(2),
            reason: 'Reduced score due to formatting bias'
          });
          break;
          
        case 'authority':
          // Authority bias: reduce if overly authoritative language
          adjustment = -0.4 * bias.score;
          adjustments.push({
            type: 'authority',
            adjustment: adjustment.toFixed(2),
            reason: 'Reduced score due to authority bias'
          });
          break;
      }
      
      totalAdjustment += adjustment;
    }
    
    // Clamp adjustment
    totalAdjustment = Math.max(minAdjustment, Math.min(maxAdjustment, totalAdjustment));
    
    // Apply adjustment
    adjustedScore = Math.max(0, Math.min(10, (result.score || 0) + totalAdjustment));
  }
  
  return {
    ...result,
    score: adjustedScore,
    originalScore: result.score,
    biasMitigation: {
      applied: true,
      adjustments,
      totalAdjustment: adjustedScore !== null && result.score !== null
        ? (adjustedScore - result.score).toFixed(2)
        : '0.00',
      detectedBiases: biasDetection.biases.map(b => b.type),
      severity: biasDetection.severity
    }
  };
}

/**
 * Mitigate position bias in array of judgments
 * 
 * @param {Array<import('./index.mjs').ValidationResult>} judgments - Array of judgment results
 * @param {{
 *   randomizeOrder?: boolean;
 *   adjustScores?: boolean;
 * }} [options={}] - Mitigation options
 * @returns {Array<import('./index.mjs').ValidationResult>} Adjusted judgments
 */
export function mitigatePositionBias(judgments, options = {}) {
  const {
    randomizeOrder = true,
    adjustScores = true
  } = options;
  
  // Detect position bias
  const positionBias = detectPositionBias(judgments);
  
  if (!positionBias.detected) {
    return judgments.map(j => ({
      ...j,
      biasMitigation: {
        applied: false,
        reason: 'No position bias detected'
      }
    }));
  }
  
  // If randomizing, shuffle order (would need to be done before evaluation)
  // For now, adjust scores
  if (adjustScores) {
    return judgments.map((judgment, index) => {
      if (judgment.score === null) return judgment;
      
      let adjustment = 0;
      
      // Reduce first position bias
      if (positionBias.firstBias && index === 0) {
        adjustment = -1.0;
      }
      
      // Reduce last position bias
      if (positionBias.lastBias && index === judgments.length - 1) {
        adjustment = -1.0;
      }
      
      const adjustedScore = Math.max(0, Math.min(10, (judgment.score || 0) + adjustment));
      
      return {
        ...judgment,
        score: adjustedScore,
        originalScore: judgment.score,
        biasMitigation: {
          applied: true,
          type: 'position',
          adjustment: adjustment.toFixed(2),
          reason: positionBias.firstBias && index === 0
            ? 'Reduced first position bias'
            : positionBias.lastBias && index === judgments.length - 1
            ? 'Reduced last position bias'
            : 'No adjustment needed'
        }
      };
    });
  }
  
  return judgments;
}

/**
 * Apply comprehensive bias mitigation to judgment
 * Combines all mitigation strategies
 * 
 * @param {import('./index.mjs').ValidationResult} result - Judgment result
 * @param {string} reasoning - Reasoning text for bias detection
 * @param {import('./index.mjs').BiasMitigationOptions} [options={}] - Mitigation options
 * @returns {import('./index.mjs').ValidationResult} Mitigated result
 */
export function applyBiasMitigation(result, reasoning, options = {}) {
  // Detect biases
  const biasDetection = detectBias(reasoning || result.reasoning || '', {
    checkVerbosity: true,
    checkLength: true,
    checkFormatting: true,
    checkAuthority: true
  });
  
  // Apply mitigation
  return mitigateBias(result, biasDetection, options);
}

