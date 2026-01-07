/**
 * Ensemble Sub-Module
 * 
 * Ensemble judging, bias detection, and counter-balancing.
 * 
 * Import from 'ai-visual-test/ensemble'
 */

// Ensemble judging
export {
  EnsembleJudge,
  createEnsembleJudge
} from '../ensemble-judge.mjs';

// Bias detection
export {
  detectBias,
  detectPositionBias
} from '../bias-detector.mjs';

// Bias mitigation
export {
  applyBiasMitigation,
  mitigateBias,
  mitigatePositionBias
} from '../bias-mitigation.mjs';

// Position counter-balance
export {
  evaluateWithCounterBalance,
  shouldUseCounterBalance
} from '../position-counterbalance.mjs';

// Pair comparison
export {
  comparePair,
  rankBatch
} from '../pair-comparison.mjs';

// Hallucination detection
export {
  detectHallucination
} from '../hallucination-detector.mjs';

// Research-enhanced validation
export {
  validateWithResearchEnhancements,
  validateMultipleWithPositionAnalysis,
  validateWithLengthAlignment,
  validateWithExplicitRubric,
  validateWithAllResearchEnhancements
} from '../research-enhanced-validation.mjs';

