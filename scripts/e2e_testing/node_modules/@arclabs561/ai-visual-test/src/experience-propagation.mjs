/**
 * Experience Propagation Tracker
 * 
 * Tracks and logs how experience (screenshots, HTML/CSS, state) propagates through the system.
 * Provides visibility into propagation paths and validates that context is preserved.
 */

import { log, warn } from './logger.mjs';

/**
 * Track experience propagation through the system
 */
export class ExperiencePropagationTracker {
  constructor(options = {}) {
    this.enabled = options.enabled !== false; // Default enabled
    this.logLevel = options.logLevel || 'info'; // 'debug', 'info', 'warn'
    this.propagationPath = [];
  }

  /**
   * Track HTML/CSS propagation at a stage
   * 
   * @param {string} stage - Stage name (e.g., 'capture', 'notes', 'trace', 'aggregation', 'context', 'evaluation')
   * @param {Object} context - Context object
   * @param {Object} [context.renderedCode] - Rendered code (HTML/CSS)
   * @param {string} [context.screenshot] - Screenshot path
   * @param {Object} [context.state] - State object
   * @param {string} [description] - Optional description
   */
  track(stage, context, description = '') {
    if (!this.enabled) return;

    const hasRenderedCode = !!context?.renderedCode;
    const hasHTML = !!context?.renderedCode?.html;
    const hasCSS = !!context?.renderedCode?.criticalCSS;
    const hasDOM = !!context?.renderedCode?.domStructure;
    const htmlLength = context?.renderedCode?.html?.length || 0;
    const hasScreenshot = !!context?.screenshot;
    const hasState = !!context?.state || !!context?.pageState || !!context?.gameState;

    const propagation = {
      stage,
      timestamp: Date.now(),
      hasRenderedCode,
      hasHTML,
      hasCSS,
      hasDOM,
      htmlLength,
      hasScreenshot,
      hasState,
      description
    };

    this.propagationPath.push(propagation);

    // Log based on log level
    if (this.logLevel === 'debug' || this.logLevel === 'info') {
      log(`[Experience Propagation] ${stage}:`, {
        renderedCode: hasRenderedCode ? '✓' : '✗',
        html: hasHTML ? `✓ (${htmlLength} chars)` : '✗',
        css: hasCSS ? '✓' : '✗',
        dom: hasDOM ? '✓' : '✗',
        screenshot: hasScreenshot ? '✓' : '✗',
        state: hasState ? '✓' : '✗',
        description
      });
    }

    // Warn if context is lost
    if (this.propagationPath.length > 1) {
      const previous = this.propagationPath[this.propagationPath.length - 2];
      if (previous.hasRenderedCode && !hasRenderedCode) {
        warn(`[Experience Propagation] WARNING: RenderedCode lost at stage '${stage}'`);
      }
      if (previous.hasHTML && !hasHTML) {
        warn(`[Experience Propagation] WARNING: HTML lost at stage '${stage}'`);
      }
      if (previous.hasCSS && !hasCSS) {
        warn(`[Experience Propagation] WARNING: CSS lost at stage '${stage}'`);
      }
    }

    return propagation;
  }

  /**
   * Get propagation path summary
   */
  getSummary() {
    return {
      path: this.propagationPath,
      stages: this.propagationPath.map(p => p.stage),
      hasRenderedCodeAtAllStages: this.propagationPath.every(p => p.hasRenderedCode),
      hasHTMLAtAllStages: this.propagationPath.every(p => p.hasHTML),
      hasCSSAtAllStages: this.propagationPath.every(p => p.hasCSS),
      htmlLengthProgression: this.propagationPath.map(p => p.htmlLength)
    };
  }

  /**
   * Reset propagation tracking
   */
  reset() {
    this.propagationPath = [];
  }
}

// Global tracker instance
let globalTracker = null;

/**
 * Get or create global propagation tracker
 */
export function getPropagationTracker(options = {}) {
  if (!globalTracker) {
    globalTracker = new ExperiencePropagationTracker(options);
  }
  return globalTracker;
}

/**
 * Track experience propagation (convenience function)
 */
export function trackPropagation(stage, context, description = '') {
  const tracker = getPropagationTracker();
  return tracker.track(stage, context, description);
}

