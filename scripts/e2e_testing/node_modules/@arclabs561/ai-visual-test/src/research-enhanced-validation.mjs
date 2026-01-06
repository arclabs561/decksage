/**
 * Research-Enhanced Validation
 * 
 * Enhanced validation functions that incorporate research findings from:
 * - arXiv:2406.07791 (position bias, quality gaps)
 * - arXiv:2407.01085 (length bias, AdapAlpaca)
 * - arXiv:2412.05579 (LLM-as-judge best practices)
 * 
 * These functions expose research-based features through a clean API.
 */

import { validateScreenshot } from './judge.mjs';
import { detectBias, detectPositionBias } from './bias-detector.mjs';
import { mitigateBias, mitigatePositionBias, applyBiasMitigation } from './bias-mitigation.mjs';
import { evaluateWithCounterBalance } from './position-counterbalance.mjs';
import { normalizeValidationResult } from './validation-result-normalizer.mjs';
import { log, warn } from './logger.mjs';

/**
 * Validate screenshot with research-enhanced bias detection and mitigation
 * 
 * Incorporates findings from arXiv:2406.07791, 2407.01085, 2412.05579:
 * - Quality gap analysis (equivocal case detection)
 * - Judge-level, candidate-level, task-level factor tracking
 * - Comprehensive bias detection and mitigation
 * - Position bias metrics (PC, PF)
 * 
 * @param {string} imagePath - Path to screenshot
 * @param {string} prompt - Evaluation prompt
 * @param {{
 *   enableBiasDetection?: boolean;
 *   enableBiasMitigation?: boolean;
 *   qualityGap?: number; // Quality gap (δ_q) between candidates (0-1, where 0.5 = tie)
 *   judgeModel?: string; // Judge model identifier
 *   taskMetadata?: { inputLength?: number; outputLength?: number; promptLength?: number };
 *   useCounterBalance?: boolean; // Use position counter-balancing
 *   [key: string]: any;
 * }} [options={}] - Enhanced validation options
 * @returns {Promise<import('./index.mjs').ValidationResult>} Enhanced validation result
 */
export async function validateWithResearchEnhancements(imagePath, prompt, options = {}) {
  const {
    enableBiasDetection = true,
    enableBiasMitigation = true,
    qualityGap = null,
    judgeModel = null,
    taskMetadata = {},
    useCounterBalance = false,
    ...validationOptions
  } = options;
  
  // Perform validation
  let result;
  if (useCounterBalance) {
    // Use counter-balancing for position bias mitigation
    result = await evaluateWithCounterBalance(
      validateScreenshot,
      imagePath,
      prompt,
      validationOptions,
      { enabled: true }
    );
  } else {
    result = await validateScreenshot(imagePath, prompt, validationOptions);
  }
  
  // Add research-based enhancements
  if (enableBiasDetection || enableBiasMitigation) {
    const reasoning = result.reasoning || result.assessment || '';
    
    // Detect biases
    const biasDetection = enableBiasDetection ? detectBias(reasoning, {
      checkVerbosity: true,
      checkLength: true,
      checkFormatting: true,
      checkAuthority: true
    }) : null;
    
    // Add position bias detection if we have multiple judgments
    let positionBias = null;
    if (enableBiasDetection && Array.isArray(result.judgments)) {
      positionBias = detectPositionBias(result.judgments, {
        qualityGap: qualityGap,
        judgeModel: judgeModel || validationOptions.provider || 'unknown',
        taskMetadata: taskMetadata
      });
    }
    
    // Apply mitigation if enabled
    if (enableBiasMitigation && biasDetection?.hasBias) {
      result = mitigateBias(result, biasDetection, {
        adjustScores: true,
        adjustIssues: false
      });
    }
    
    // Add research metadata
    result.researchEnhancements = {
      biasDetection: biasDetection,
      positionBias: positionBias,
      qualityGap: qualityGap ? {
        value: qualityGap,
        isEquivocal: Math.abs(qualityGap - 0.5) < 0.1,
        note: Math.abs(qualityGap - 0.5) < 0.1
          ? 'Equivocal case (δ_q ≈ 0.5) - maximum position bias risk per arXiv:2406.07791'
          : 'Quality gap analysis per research findings'
      } : null,
      factors: {
        judgeModel: judgeModel || validationOptions.provider || 'unknown',
        taskMetadata: taskMetadata
      },
      researchPapers: [
        'arXiv:2406.07791 - Position bias, quality gaps',
        'arXiv:2407.01085 - Length bias, AdapAlpaca',
        'arXiv:2412.05579 - LLM-as-judge best practices'
      ]
    };
  }
  
  // Normalize result structure before returning (ensures consistent structure)
  return normalizeValidationResult(result, 'validateWithResearchEnhancements');
}

/**
 * Validate multiple screenshots with position bias analysis
 * 
 * Based on arXiv:2406.07791 findings on position bias:
 * - Calculates Position Consistency (PC) and Preference Fairness (PF) metrics
 * - Detects equivocal cases (quality gap ≈ 0.5)
 * - Tracks judge-level and task-level factors
 * 
 * @param {string[]} imagePaths - Array of screenshot paths
 * @param {string} prompt - Evaluation prompt
 * @param {{
 *   calculateMetrics?: boolean; // Calculate PC/PF metrics
 *   qualityGap?: number;
 *   judgeModel?: string;
 *   taskMetadata?: { inputLength?: number; outputLength?: number; promptLength?: number };
 *   enableMitigation?: boolean;
 *   [key: string]: any;
 * }} [options={}] - Validation options
 * @returns {Promise<{
 *   judgments: import('./index.mjs').ValidationResult[];
 *   positionBias: import('./index.mjs').PositionBiasResult;
 *   qualityGap: { value: number; isEquivocal: boolean; note: string } | null;
 *   metrics?: { positionConsistency: number; preferenceFairness: object };
 * }>} Multi-judgment result with position bias analysis
 */
export async function validateMultipleWithPositionAnalysis(imagePaths, prompt, options = {}) {
  const {
    calculateMetrics = true,
    qualityGap = null,
    judgeModel = null,
    taskMetadata = {},
    enableMitigation = false,
    ...validationOptions
  } = options;
  
  // Validate all screenshots
  const judgments = await Promise.all(
    imagePaths.map(path => validateScreenshot(path, prompt, validationOptions))
  );
  
  // Extract scores for position bias detection
  const judgmentScores = judgments.map(j => ({ score: j.score }));
  
  // Detect position bias with research metrics
  const positionBias = detectPositionBias(judgmentScores, {
    calculateMetrics: calculateMetrics,
    qualityGap: qualityGap,
    judgeModel: judgeModel || validationOptions.provider || 'unknown',
    taskMetadata: taskMetadata
  });
  
  // Apply mitigation if enabled
  let mitigatedJudgments = judgments;
  if (enableMitigation && positionBias.detected) {
    mitigatedJudgments = mitigatePositionBias(judgments, {
      enabled: true
    });
  }
  
  // Calculate quality gap if not provided
  let calculatedQualityGap = qualityGap;
  if (calculatedQualityGap === null && judgments.length >= 2) {
    const scores = judgments.map(j => j.score).filter(s => s !== null);
    if (scores.length >= 2) {
      const scoreRange = Math.max(...scores) - Math.min(...scores);
      const maxPossibleRange = 10; // Assuming 0-10 scale
      calculatedQualityGap = 0.5 - Math.abs((scoreRange / maxPossibleRange) - 0.5);
    }
  }
  
  return {
    judgments: mitigatedJudgments,
    positionBias: positionBias,
    qualityGap: calculatedQualityGap !== null ? {
      value: calculatedQualityGap,
      isEquivocal: Math.abs(calculatedQualityGap - 0.5) < 0.1,
      note: Math.abs(calculatedQualityGap - 0.5) < 0.1
        ? 'Equivocal case (δ_q ≈ 0.5) - maximum position bias risk per arXiv:2406.07791'
        : 'Quality gap analysis per research findings'
    } : null,
    metrics: positionBias.metrics || undefined,
    researchMetadata: {
      papers: ['arXiv:2406.07791'],
      findings: [
        'Position bias varies by judge and task',
        'Quality gap strongly affects bias (parabolic relationship)',
        'Equivocal cases (δ_q ≈ 0.5) cause maximum confusion'
      ]
    }
  };
}

/**
 * Validate with length alignment (AdapAlpaca-inspired)
 * 
 * Based on arXiv:2407.01085 (AdapAlpaca):
 * - Decomposes preference into desirability (length-independent) and information mass (length-dependent)
 * - Aligns response lengths under equivalent intervals for fair comparison
 * - Reduces length bias in evaluations
 * 
 * Note: This is a simplified implementation. Full AdapAlpaca would require
 * length bucketing and alignment before comparison.
 * 
 * @param {string} imagePath - Path to screenshot
 * @param {string} prompt - Evaluation prompt
 * @param {{
 *   referenceLength?: number; // Reference response length for alignment
 *   lengthInterval?: number; // Length interval for bucketing
 *   enableLengthNormalization?: boolean;
 *   [key: string]: any;
 * }} [options={}] - Length alignment options
 * @returns {Promise<import('./index.mjs').ValidationResult>} Validation result with length alignment
 */
export async function validateWithLengthAlignment(imagePath, prompt, options = {}) {
  const {
    referenceLength = null,
    lengthInterval = 50, // Characters
    enableLengthNormalization = true,
    ...validationOptions
  } = options;
  
  // Perform validation
  const result = await validateScreenshot(imagePath, prompt, validationOptions);
  
  // Apply length-based bias detection and mitigation
  if (enableLengthNormalization && result.reasoning) {
    const reasoningLength = result.reasoning.length;
    
    // Detect verbosity/length bias
    const biasDetection = detectBias(result.reasoning, {
      checkVerbosity: true,
      checkLength: true
    });
    
    // Apply mitigation (simplified AdapAlpaca approach)
    if (biasDetection.hasBias) {
      const mitigated = mitigateBias(result, biasDetection, {
        adjustScores: true
      });
      
      // Add AdapAlpaca metadata
      mitigated.lengthAlignment = {
        originalLength: reasoningLength,
        referenceLength: referenceLength,
        lengthInterval: lengthInterval,
        normalized: true,
        note: 'AdapAlpaca-inspired length normalization (arXiv:2407.01085). Full implementation would align lengths under equivalent intervals before comparison.',
        researchPaper: 'arXiv:2407.01085 - Explaining Length Bias in LLM-Based Preference Evaluations'
      };
      
      // Normalize mitigated result before returning
      return normalizeValidationResult(mitigated, 'validateWithLengthAlignment');
    }
  }
  
  // Normalize result structure before returning
  return normalizeValidationResult(result, 'validateWithLengthAlignment');
}

/**
 * Validate with explicit rubrics (research-backed)
 * 
 * Based on arXiv:2412.05579 findings:
 * - Explicit rubrics improve reliability by 10-20%
 * - Reduce bias from superficial features
 * - Provide structured evaluation criteria
 * 
 * @param {string} imagePath - Path to screenshot
 * @param {string} prompt - Evaluation prompt
 * @param {{
 *   rubric?: string | object; // Explicit rubric to use
 *   useDefaultRubric?: boolean; // Use default research-backed rubric
 *   [key: string]: any;
 * }} [options={}] - Rubric options
 * @returns {Promise<import('./index.mjs').ValidationResult>} Validation result with explicit rubric
 */
export async function validateWithExplicitRubric(imagePath, prompt, options = {}) {
  const {
    rubric = null,
    useDefaultRubric = true,
    ...validationOptions
  } = options;
  
  // Import rubric builder
  const { buildRubricPrompt, DEFAULT_RUBRIC } = await import('./rubrics.mjs');
  
  // Build prompt with explicit rubric
  let enhancedPrompt = prompt;
  if (useDefaultRubric && !rubric) {
    enhancedPrompt = buildRubricPrompt(prompt, DEFAULT_RUBRIC);
  } else if (rubric) {
    enhancedPrompt = buildRubricPrompt(prompt, rubric);
  }
  
  // Perform validation
  const result = await validateScreenshot(imagePath, enhancedPrompt, validationOptions);
  
  // Add rubric metadata
  result.rubricEnhancement = {
    used: true,
    type: rubric ? 'custom' : 'default',
    researchPaper: 'arXiv:2412.05579 - LLMs-as-Judges Survey',
    finding: 'Explicit rubrics improve reliability by 10-20% and reduce bias from superficial features'
  };
  
  // Normalize result structure before returning
  return normalizeValidationResult(result, 'validateWithExplicitRubric');
}

/**
 * Comprehensive research-enhanced validation
 * 
 * Combines all research enhancements:
 * - Explicit rubrics (arXiv:2412.05579)
 * - Bias detection and mitigation (arXiv:2406.07791, 2407.01085)
 * - Quality gap analysis (arXiv:2406.07791)
 * - Length alignment (arXiv:2407.01085)
 * - Position bias metrics (arXiv:2406.07791)
 * 
 * @param {string} imagePath - Path to screenshot
 * @param {string} prompt - Evaluation prompt
 * @param {{
 *   enableRubrics?: boolean;
 *   enableBiasDetection?: boolean;
 *   enableBiasMitigation?: boolean;
 *   enableLengthAlignment?: boolean;
 *   qualityGap?: number;
 *   judgeModel?: string;
 *   taskMetadata?: { inputLength?: number; outputLength?: number; promptLength?: number };
 *   [key: string]: any;
 * }} [options={}] - Comprehensive options
 * @returns {Promise<import('./index.mjs').ValidationResult>} Comprehensive validation result
 */
export async function validateWithAllResearchEnhancements(imagePath, prompt, options = {}) {
  const {
    enableRubrics = true,
    enableBiasDetection = true,
    enableBiasMitigation = true,
    enableLengthAlignment = true,
    qualityGap = null,
    judgeModel = null,
    taskMetadata = {},
    ...validationOptions
  } = options;
  
  // Step 1: Apply explicit rubric if enabled
  let currentPrompt = prompt;
  if (enableRubrics) {
    const { buildRubricPrompt, DEFAULT_RUBRIC } = await import('./rubrics.mjs');
    currentPrompt = buildRubricPrompt(currentPrompt, DEFAULT_RUBRIC);
  }
  
  // Step 2: Perform validation with length alignment if enabled
  let result;
  if (enableLengthAlignment) {
    result = await validateWithLengthAlignment(imagePath, currentPrompt, {
      ...validationOptions,
      enableLengthNormalization: true
    });
  } else {
    result = await validateScreenshot(imagePath, currentPrompt, validationOptions);
  }
  
  // Step 3: Apply bias detection and mitigation
  if (enableBiasDetection || enableBiasMitigation) {
    const reasoning = result.reasoning || result.assessment || '';
    const biasDetection = enableBiasDetection ? detectBias(reasoning, {
      checkVerbosity: true,
      checkLength: true,
      checkFormatting: true,
      checkAuthority: true
    }) : null;
    
    if (enableBiasMitigation && biasDetection?.hasBias) {
      result = mitigateBias(result, biasDetection, {
        adjustScores: true
      });
    }
    
    // Add comprehensive research metadata
    result.comprehensiveResearchEnhancements = {
      rubrics: enableRubrics ? {
        used: true,
        paper: 'arXiv:2412.05579',
        finding: 'Explicit rubrics improve reliability by 10-20%'
      } : null,
      biasDetection: biasDetection,
      lengthAlignment: enableLengthAlignment ? {
        applied: true,
        paper: 'arXiv:2407.01085',
        method: 'AdapAlpaca-inspired'
      } : null,
      qualityGap: qualityGap ? {
        value: qualityGap,
        isEquivocal: Math.abs(qualityGap - 0.5) < 0.1,
        paper: 'arXiv:2406.07791'
      } : null,
      factors: {
        judgeModel: judgeModel || validationOptions.provider || 'unknown',
        taskMetadata: taskMetadata
      },
      researchPapers: [
        'arXiv:2406.07791 - Position bias, quality gaps',
        'arXiv:2407.01085 - Length bias, AdapAlpaca',
        'arXiv:2412.05579 - LLM-as-judge best practices'
      ]
    };
  }
  
  // Normalize result structure before returning (ensures consistent structure)
  return normalizeValidationResult(result, 'validateWithAllResearchEnhancements');
}

