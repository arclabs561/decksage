/**
 * Utils Sub-Module
 * 
 * Utility functions, helpers, and infrastructure.
 * 
 * Import from 'ai-visual-test/utils'
 */

// Cache
export {
  getCached,
  setCached,
  clearCache,
  getCacheStats,
  initCache,
  generateCacheKey
} from '../cache.mjs';

// Config
export {
  createConfig,
  getProvider,
  getConfig,
  setConfig
} from '../config.mjs';

// Environment
export { loadEnv } from '../load-env.mjs';

// Logger
export { enableDebug, disableDebug, isDebugEnabled, warn, log, error } from '../logger.mjs';

// Errors
export {
  AIBrowserTestError,
  ValidationError,
  CacheError,
  ConfigError,
  ProviderError,
  TimeoutError,
  FileError,
  StateMismatchError,
  isAIBrowserTestError,
  isErrorType
} from '../errors.mjs';

// Retry
export {
  retryWithBackoff,
  isRetryableError,
  calculateBackoff,
  enhanceErrorMessage
} from '../retry.mjs';

// Cost tracking
export {
  CostTracker,
  getCostTracker,
  recordCost,
  getCostStats
} from '../cost-tracker.mjs';

// Score tracking
export { ScoreTracker } from '../score-tracker.mjs';

// Batch optimization
export { BatchOptimizer } from '../batch-optimizer.mjs';
export { LatencyAwareBatchOptimizer } from '../latency-aware-batch-optimizer.mjs';

// Data extraction
export { extractStructuredData } from '../data-extractor.mjs';

// Feedback aggregation
export { aggregateFeedback, generateRecommendations } from '../feedback-aggregator.mjs';

// Context compression
export { compressContext, compressStateHistory } from '../context-compressor.mjs';

// Metrics
export {
  spearmanCorrelation,
  pearsonCorrelation,
  calculateRankAgreement
} from '../metrics.mjs';

// Type guards
export {
  isObject,
  isString,
  isNumber,
  isArray,
  isFunction,
  isPromise,
  isValidationResult,
  isValidationContext,
  isPersona,
  isTemporalNote,
  assertObject,
  assertString,
  assertNonEmptyString,
  assertNumber,
  assertArray,
  assertFunction,
  pick,
  getProperty
} from '../type-guards.mjs';

// Constants
export { 
  CACHE_CONSTANTS, 
  TEMPORAL_CONSTANTS, 
  API_CONSTANTS, 
  UNCERTAINTY_CONSTANTS, 
  BATCH_OPTIMIZER_CONSTANTS 
} from '../constants.mjs';

// Validation result normalization
export { normalizeValidationResult } from '../validation-result-normalizer.mjs';

// Error handlers
export { initErrorHandlers } from '../error-handler.mjs';

// Uncertainty reduction
export {
  estimateUncertainty,
  selfConsistencyCheck,
  combineUncertaintySources,
  enhanceWithUncertainty,
  shouldUseSelfConsistency
} from '../uncertainty-reducer.mjs';

// Dynamic few-shot
export {
  selectFewShotExamples,
  formatFewShotExamples
} from '../dynamic-few-shot.mjs';

// Dynamic prompts
export {
  generateDynamicPrompt,
  generatePromptVariations,
  generateInteractionPrompt,
  generateGameplayPrompt
} from '../dynamic-prompts.mjs';

// Rubrics
export {
  DEFAULT_RUBRIC,
  buildRubricPrompt,
  getRubricForTestType
} from '../rubrics.mjs';

// Model tier selection
export {
  selectModelTier,
  selectProvider,
  selectModelTierAndProvider
} from '../model-tier-selector.mjs';

// Smart validator
export {
  validateSmart,
  validateAccessibilitySmart,
  validateStateSmart,
  validateElementSmart,
  detectValidationMethod
} from '../smart-validator.mjs';

// Human validation
export {
  HumanValidationManager,
  getHumanValidationManager,
  initHumanValidation
} from '../human-validation-manager.mjs';

