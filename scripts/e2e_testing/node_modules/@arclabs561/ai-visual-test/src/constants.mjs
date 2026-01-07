/**
 * Shared Constants
 * 
 * Centralized constants for magic numbers used throughout the codebase.
 * All values are documented with their purpose and rationale.
 */

/**
 * Cache Configuration
 */
export const CACHE_CONSTANTS = {
  /** Maximum age of cache entries in milliseconds (7 days) */
  MAX_CACHE_AGE_MS: 7 * 24 * 60 * 60 * 1000,
  
  /** Maximum number of cache entries before LRU eviction */
  MAX_CACHE_SIZE: 1000,
  
  /** Maximum cache file size in bytes (100MB) */
  MAX_CACHE_SIZE_BYTES: 100 * 1024 * 1024
};

/**
 * Temporal Aggregation Configuration
 */
export const TEMPORAL_CONSTANTS = {
  /** Default window size for temporal aggregation in milliseconds (10 seconds) */
  DEFAULT_WINDOW_SIZE_MS: 10000,
  
  /** Default exponential decay factor for older notes (0.9 = 10% decay per window) */
  DEFAULT_DECAY_FACTOR: 0.9,
  
  /** Default coherence threshold for temporal consistency checks (0.7 = 70% coherence required) */
  DEFAULT_COHERENCE_THRESHOLD: 0.7
};

/**
 * API Configuration
 */
export const API_CONSTANTS = {
  /** Default timeout for API calls in milliseconds (30 seconds) */
  DEFAULT_TIMEOUT_MS: 30000,
  
  /** Default maximum concurrency for API calls */
  DEFAULT_MAX_CONCURRENCY: 5
};

/**
 * Batch Optimizer Configuration
 */
export const BATCH_OPTIMIZER_CONSTANTS = {
  /** Maximum queue size before rejecting new requests (prevents memory leaks) */
  MAX_QUEUE_SIZE: 1000,
  
  /** Request timeout in milliseconds (30 seconds) */
  REQUEST_TIMEOUT_MS: 30000
};

/**
 * Uncertainty Reduction Configuration
 */
export const UNCERTAINTY_CONSTANTS = {
  /** Low score threshold for edge case detection (bottom 30% of 0-10 scale) */
  LOW_SCORE_THRESHOLD: 3,
  
  /** High score threshold for edge case detection (top 10% of 0-10 scale) */
  HIGH_SCORE_THRESHOLD: 9,
  
  /** High uncertainty threshold for triggering self-consistency (0.3 = 30% uncertainty) */
  HIGH_UNCERTAINTY_THRESHOLD: 0.3,
  
  /** Issue count threshold for over-detection risk (5+ issues might indicate hallucination) */
  OVER_DETECTION_ISSUE_COUNT: 5,
  
  /** Self-consistency N for Tier 1 scenarios (expert, medical, blocking issues) */
  TIER1_SELF_CONSISTENCY_N: 5,
  
  /** Self-consistency N for edge cases (Tier 2) */
  EDGE_CASE_SELF_CONSISTENCY_N: 3
};

