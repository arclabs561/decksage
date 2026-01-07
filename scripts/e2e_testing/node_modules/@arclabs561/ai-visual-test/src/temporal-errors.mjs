/**
 * Temporal Error Types
 * Custom error classes for temporal decision-making components
 */

/**
 * Base error class for temporal components
 */
export class TemporalError extends Error {
  constructor(message, code, context = {}) {
    super(message);
    this.name = 'TemporalError';
    this.code = code;
    this.context = context;
    Error.captureStackTrace(this, this.constructor);
  }
}

/**
 * Error for human perception time calculations
 */
export class PerceptionTimeError extends TemporalError {
  constructor(message, context = {}) {
    super(message, 'PERCEPTION_TIME_ERROR', context);
    this.name = 'PerceptionTimeError';
  }
}

/**
 * Error for sequential decision context
 */
export class SequentialContextError extends TemporalError {
  constructor(message, context = {}) {
    super(message, 'SEQUENTIAL_CONTEXT_ERROR', context);
    this.name = 'SequentialContextError';
  }
}

/**
 * Error for multi-scale aggregation
 */
export class MultiScaleError extends TemporalError {
  constructor(message, context = {}) {
    super(message, 'MULTI_SCALE_ERROR', context);
    this.name = 'MultiScaleError';
  }
}

/**
 * Error for temporal batch optimization
 */
export class TemporalBatchError extends TemporalError {
  constructor(message, context = {}) {
    super(message, 'TEMPORAL_BATCH_ERROR', context);
    this.name = 'TemporalBatchError';
  }
}

