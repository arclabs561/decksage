/**
 * Validation Framework
 * 
 * Provides comprehensive validation of:
 * 1. Temporal perception accuracy (human time scales)
 * 2. VLLM judgment accuracy (against human ground truth)
 * 3. Gameplay temporal experience correctness
 * 4. Webpage evaluation correctness
 * 
 * This framework validates that our systems produce correct results,
 * not just that they work.
 */

import { humanPerceptionTime } from './temporal-decision.mjs';
import { TIME_SCALES } from './temporal-constants.mjs';
import { aggregateTemporalNotes, calculateCoherenceExported as calculateCoherence } from './temporal.mjs';
import {
  compareJudgments,
  collectHumanJudgment,
  loadHumanJudgment
} from '../evaluation/human-validation/human-validation.mjs';
import { getHumanValidationManager } from './human-validation-manager.mjs';
import { log, warn } from './logger.mjs';

/**
 * Validate temporal perception against research values
 * 
 * @param {Object} options - Validation options
 * @returns {Object} Validation results
 */
export function validateTemporalPerception(options = {}) {
  const results = {
    researchAlignment: {},
    consistency: {},
    recommendations: []
  };
  
  // Validate visual appeal time (50ms research base)
  const visualAppealTime = humanPerceptionTime('visual-appeal', {
    attentionLevel: 'focused',
    actionComplexity: 'simple'
  });
  
  results.researchAlignment.visualAppeal = {
    researchValue: 50, // Lindgaard research
    actualValue: visualAppealTime,
    aligned: visualAppealTime >= 50 && visualAppealTime <= 200,
    note: visualAppealTime >= 100 ? 'Enforces 100ms minimum (implementation constraint)' : 'Matches research (50ms)'
  };
  
  // Validate instant threshold (100ms research)
  results.researchAlignment.instantThreshold = {
    researchValue: 100, // NN/g research
    actualValue: TIME_SCALES.INSTANT,
    aligned: TIME_SCALES.INSTANT === 100,
    note: TIME_SCALES.INSTANT === 100 ? 'Matches research' : 'Does not match research'
  };
  
  // Validate reading time scales with content
  const shortReading = humanPerceptionTime('reading', { contentLength: 100 });
  const longReading = humanPerceptionTime('reading', { contentLength: 1000 });
  
  results.researchAlignment.readingTime = {
    scalesWithContent: longReading > shortReading,
    shortContent: shortReading,
    longContent: longReading,
    note: longReading > shortReading ? 'Reading time scales with content' : 'Reading time does not scale correctly'
  };
  
  // Generate recommendations
  if (!results.researchAlignment.visualAppeal.aligned) {
    results.recommendations.push('Visual appeal time does not align with research (50ms)');
  }
  if (!results.researchAlignment.instantThreshold.aligned) {
    results.recommendations.push('Instant threshold does not match research (100ms)');
  }
  if (!results.researchAlignment.readingTime.scalesWithContent) {
    results.recommendations.push('Reading time does not scale correctly with content length');
  }
  
  return results;
}

/**
 * Validate VLLM judgment accuracy against human ground truth
 * 
 * @param {Array} humanJudgments - Human judgment ground truth
 * @param {Array} vllmJudgments - VLLM judgments to validate
 * @param {Object} options - Validation options
 * @returns {Object} Validation results
 */
export function validateVLLMAccuracy(humanJudgments, vllmJudgments, options = {}) {
  const {
    minCorrelation = 0.7,
    maxMAE = 1.0,
    minKappa = 0.6
  } = options;
  
  try {
    const calibration = compareJudgments(humanJudgments, vllmJudgments);
    
    const results = {
      calibration,
      isValid: false,
      issues: [],
      recommendations: []
    };
    
    // Check correlation
    if (calibration.agreement.pearson < minCorrelation) {
      results.issues.push(`Low correlation (${calibration.agreement.pearson.toFixed(3)} < ${minCorrelation})`);
      results.isValid = false;
    }
    
    // Check MAE
    if (calibration.agreement.mae > maxMAE) {
      results.issues.push(`High MAE (${calibration.agreement.mae.toFixed(2)} > ${maxMAE})`);
      results.isValid = false;
    }
    
    // Check Kappa
    if (calibration.agreement.kappa < minKappa) {
      results.issues.push(`Low Kappa (${calibration.agreement.kappa.toFixed(3)} < ${minKappa})`);
      results.isValid = false;
    }
    
    // If all checks pass
    if (results.issues.length === 0) {
      results.isValid = true;
      results.recommendations.push('VLLM judgments align well with human ground truth');
    } else {
      results.recommendations.push(...calibration.recommendations);
    }
    
    return results;
  } catch (error) {
    return {
      error: error.message,
      isValid: false,
      issues: ['Failed to compare judgments'],
      recommendations: ['Ensure human and VLLM judgments are properly matched']
    };
  }
}

/**
 * Validate gameplay temporal experience
 * 
 * @param {Array} gameplayNotes - Temporal notes from gameplay
 * @param {Object} options - Validation options
 * @returns {Object} Validation results
 */
export function validateGameplayTemporal(gameplayNotes, options = {}) {
  const {
    minCoherenceForSmooth = 0.7,
    maxCoherenceForErratic = 0.5
  } = options;
  
  if (!gameplayNotes || gameplayNotes.length === 0) {
    return {
      isValid: false,
      issues: ['No gameplay notes provided'],
      recommendations: ['Provide gameplay notes for validation']
    };
  }
  
  const aggregated = aggregateTemporalNotes(gameplayNotes, options);
  
  const results = {
    aggregated,
    isValid: true,
    issues: [],
    recommendations: []
  };
  
  // Check coherence
  if (aggregated.coherence < minCoherenceForSmooth && aggregated.coherence > maxCoherenceForErratic) {
    results.issues.push(`Moderate coherence (${aggregated.coherence.toFixed(3)}) - neither smooth nor clearly erratic`);
    results.recommendations.push('Review gameplay notes for consistency issues');
  }
  
  // Check for conflicts
  if (aggregated.conflicts && aggregated.conflicts.length > 0) {
    results.issues.push(`Detected ${aggregated.conflicts.length} conflicts in gameplay notes`);
    results.recommendations.push('Review conflicting observations in gameplay notes');
  }
  
  // Check window count
  if (aggregated.windows.length < 2) {
    results.issues.push('Insufficient windows for temporal analysis (need at least 2)');
    results.recommendations.push('Collect more gameplay notes or use smaller window size');
  }
  
  return results;
}

/**
 * Validate webpage evaluation correctness
 * 
 * Validates that VLLM judgments about webpages align with human expectations.
 * 
 * @param {Array} evaluations - Array of evaluation results
 * @param {Object} groundTruth - Ground truth data (if available)
 * @param {Object} options - Validation options
 * @returns {Object} Validation results
 */
export function validateWebpageEvaluation(evaluations, groundTruth = null, options = {}) {
  const results = {
    evaluations,
    isValid: true,
    issues: [],
    recommendations: []
  };
  
  // If ground truth available, compare
  if (groundTruth) {
    const humanJudgments = groundTruth.humanJudgments || [];
    const vllmJudgments = evaluations.map(eval => ({
      id: eval.id || `eval-${Date.now()}`,
      vllmScore: eval.score,
      vllmIssues: eval.issues || [],
      vllmReasoning: eval.reasoning || '',
      provider: eval.provider || 'unknown',
      timestamp: eval.timestamp || new Date().toISOString()
    }));
    
    if (humanJudgments.length > 0 && vllmJudgments.length > 0) {
      const accuracy = validateVLLMAccuracy(humanJudgments, vllmJudgments, options);
      results.accuracy = accuracy;
      results.isValid = accuracy.isValid;
      results.issues.push(...accuracy.issues);
      results.recommendations.push(...accuracy.recommendations);
    }
  }
  
  // Validate evaluation structure
  for (const eval of evaluations) {
    if (eval.score === null || eval.score === undefined) {
      results.issues.push(`Evaluation ${eval.id || 'unknown'} has null/undefined score`);
      results.isValid = false;
    }
    if (eval.score !== null && (eval.score < 0 || eval.score > 10)) {
      results.issues.push(`Evaluation ${eval.id || 'unknown'} has invalid score: ${eval.score}`);
      results.isValid = false;
    }
    if (!Array.isArray(eval.issues)) {
      results.issues.push(`Evaluation ${eval.id || 'unknown'} has non-array issues`);
      results.isValid = false;
    }
  }
  
  return results;
}

/**
 * Comprehensive validation report
 * 
 * Validates all aspects: temporal perception, VLLM accuracy, gameplay, webpage evaluation
 * 
 * @param {Object} data - Validation data
 * @param {Object} options - Validation options
 * @returns {Object} Comprehensive validation report
 */
export function validateComprehensive(data, options = {}) {
  const report = {
    temporalPerception: null,
    vllmAccuracy: null,
    gameplayTemporal: null,
    webpageEvaluation: null,
    overall: {
      isValid: true,
      issues: [],
      recommendations: []
    }
  };
  
  // Validate temporal perception
  if (data.temporalPerception !== false) {
    report.temporalPerception = validateTemporalPerception(options);
    if (report.temporalPerception.recommendations.length > 0) {
      report.overall.issues.push('Temporal perception validation issues');
      report.overall.recommendations.push(...report.temporalPerception.recommendations);
    }
  }
  
  // Validate VLLM accuracy
  if (data.humanJudgments && data.vllmJudgments) {
    report.vllmAccuracy = validateVLLMAccuracy(data.humanJudgments, data.vllmJudgments, options);
    if (!report.vllmAccuracy.isValid) {
      report.overall.isValid = false;
      report.overall.issues.push('VLLM accuracy validation failed');
      report.overall.recommendations.push(...report.vllmAccuracy.recommendations);
    }
  }
  
  // Validate gameplay temporal
  if (data.gameplayNotes) {
    report.gameplayTemporal = validateGameplayTemporal(data.gameplayNotes, options);
    if (report.gameplayTemporal.issues.length > 0) {
      report.overall.issues.push('Gameplay temporal validation issues');
      report.overall.recommendations.push(...report.gameplayTemporal.recommendations);
    }
  }
  
  // Validate webpage evaluation
  if (data.evaluations) {
    report.webpageEvaluation = validateWebpageEvaluation(
      data.evaluations,
      data.groundTruth,
      options
    );
    if (!report.webpageEvaluation.isValid) {
      report.overall.isValid = false;
      report.overall.issues.push('Webpage evaluation validation failed');
      report.overall.recommendations.push(...report.webpageEvaluation.recommendations);
    }
  }
  
  return report;
}

