/**
 * Temporal Context Utilities
 * Standardized context creation and merging for temporal components
 */

/**
 * Create standardized temporal context
 */
export function createTemporalContext(options = {}) {
  return {
    sequentialContext: options.sequentialContext || null,
    viewport: options.viewport || null,
    testType: options.testType || null,
    enableBiasMitigation: options.enableBiasMitigation !== false,
    attentionLevel: options.attentionLevel || 'normal',
    actionComplexity: options.actionComplexity || 'normal',
    persona: options.persona || null,
    contentLength: options.contentLength || 0,
    ...options
  };
}

/**
 * Merge temporal contexts
 */
export function mergeTemporalContext(base, additional) {
  return {
    ...base,
    ...additional,
    sequentialContext: additional.sequentialContext || base.sequentialContext,
    // Preserve base values if additional doesn't override
    attentionLevel: additional.attentionLevel || base.attentionLevel || 'normal',
    actionComplexity: additional.actionComplexity || base.actionComplexity || 'normal'
  };
}

/**
 * Extract temporal context from options
 */
export function extractTemporalContext(options) {
  return {
    sequentialContext: options.sequentialContext,
    attentionLevel: options.attentionLevel,
    actionComplexity: options.actionComplexity,
    persona: options.persona,
    contentLength: options.contentLength
  };
}

