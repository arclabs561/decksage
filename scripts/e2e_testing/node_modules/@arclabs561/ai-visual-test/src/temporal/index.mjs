/**
 * Temporal Sub-Module
 * 
 * All temporal aggregation and decision-making functionality.
 * 
 * Import from 'ai-visual-test/temporal'
 */

// Core temporal aggregation
export {
  aggregateTemporalNotes,
  formatNotesForPrompt,
  calculateCoherenceExported as calculateCoherence
} from '../temporal.mjs';

// Temporal formatting
export {
  formatTemporalContext,
  formatTemporalForPrompt,
  formatSingleScaleForPrompt,
  formatMultiScaleForPrompt
} from '../temporal-prompt-formatter.mjs';

// Temporal decision management
export {
  TemporalDecisionManager,
  createTemporalDecisionManager
} from '../temporal-decision-manager.mjs';

// Temporal preprocessing
export {
  TemporalPreprocessingManager,
  AdaptiveTemporalProcessor,
  createTemporalPreprocessingManager,
  createAdaptiveTemporalProcessor
} from '../temporal-preprocessor.mjs';

// Temporal note pruning
export {
  pruneTemporalNotes,
  propagateNotes,
  selectTopWeightedNotes
} from '../temporal-note-pruner.mjs';

// Temporal decision functions
export {
  aggregateMultiScale,
  SequentialDecisionContext,
  humanPerceptionTime,
  calculateAttentionWeight
} from '../temporal-decision.mjs';

// Render change detection
export {
  detectRenderChanges,
  calculateOptimalFPS,
  detectVisualChanges,
  captureOnRenderChanges,
  captureAdaptiveTemporalScreenshots
} from '../render-change-detector.mjs';

// Adaptive temporal
export {
  aggregateTemporalNotesAdaptive,
  calculateOptimalWindowSize,
  detectActivityPattern
} from '../temporal-adaptive.mjs';

// Temporal batch optimization
export { TemporalBatchOptimizer } from '../temporal-batch-optimizer.mjs';

// Temporal context
export {
  createTemporalContext,
  mergeTemporalContext,
  extractTemporalContext
} from '../temporal-context.mjs';

// Temporal constants
export {
  TIME_SCALES,
  MULTI_SCALE_WINDOWS,
  READING_SPEEDS,
  ATTENTION_MULTIPLIERS,
  COMPLEXITY_MULTIPLIERS,
  CONFIDENCE_THRESHOLDS,
  TIME_BOUNDS,
  CONTENT_THRESHOLDS
} from '../temporal-constants.mjs';

// Temporal errors
export {
  TemporalError,
  PerceptionTimeError,
  SequentialContextError,
  MultiScaleError,
  TemporalBatchError
} from '../temporal-errors.mjs';

// Temporal screenshots (from multi-modal)
export { captureTemporalScreenshots } from '../multi-modal.mjs';

