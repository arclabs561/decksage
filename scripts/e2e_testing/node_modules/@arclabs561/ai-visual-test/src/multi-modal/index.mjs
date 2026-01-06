/**
 * Multi-Modal Sub-Module
 * 
 * Multi-modal validation features (screenshot + HTML + CSS + rendered code).
 * 
 * Import from 'ai-visual-test/multi-modal'
 */

// Core multi-modal functions
export {
  multiModalValidation,
  captureTemporalScreenshots,
  extractRenderedCode,
  multiPerspectiveEvaluation
} from '../multi-modal.mjs';

// Multi-modal fusion
export {
  buildStructuredFusionPrompt,
  calculateModalityWeights,
  compareFusionStrategies
} from '../multi-modal-fusion.mjs';

// Cross-modal consistency
export {
  checkCrossModalConsistency,
  validateExperienceConsistency
} from '../cross-modal-consistency.mjs';

// Prompt composition
export {
  composeSingleImagePrompt,
  composeComparisonPrompt,
  composeMultiModalPrompt
} from '../prompt-composer.mjs';

