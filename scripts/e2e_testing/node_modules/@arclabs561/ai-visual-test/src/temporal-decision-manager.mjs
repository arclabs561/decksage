/**
 * Temporal Decision Manager
 * 
 * Implements decision logic for WHEN to prompt based on temporal context.
 * 
 * Research: arXiv:2406.12125 - "Efficient Sequential Decision Making"
 * - Paper's core finding: Don't prompt on every state change, prompt when decision is needed
 * - Online model selection achieves 6x gains with 1.5% LLM calls
 * 
 * This module implements the decision logic (when to prompt) that was missing from
 * our temporal aggregation system. It complements temporal-decision.mjs which handles
 * HOW to aggregate temporal context, while this handles WHEN to use it.
 */

import { aggregateTemporalNotes } from './temporal.mjs';
import { aggregateMultiScale } from './temporal-decision.mjs';

/**
 * Temporal Decision Manager
 * 
 * Decides when context is sufficient to prompt, when to wait, and when to prompt immediately.
 */
export class TemporalDecisionManager {
  constructor(options = {}) {
    this.minNotesForPrompt = options.minNotesForPrompt || 3; // Minimum notes before prompting
    this.coherenceThreshold = options.coherenceThreshold || 0.5; // Minimum coherence to prompt
    this.urgencyThreshold = options.urgencyThreshold || 0.3; // Coherence drop triggers urgency
    this.maxWaitTime = options.maxWaitTime || 10000; // Max time to wait (10s)
    this.stateChangeThreshold = options.stateChangeThreshold || 0.2; // Significant state change
  }

  /**
   * Decide if we should prompt now or wait for more context
   * 
   * @param {Object} currentState - Current state
   * @param {Object} previousState - Previous state (if any)
   * @param {import('./index.mjs').TemporalNote[]} temporalNotes - Temporal notes so far
   * @param {Object} context - Additional context
   * @returns {{shouldPrompt: boolean, reason: string, urgency: 'low'|'medium'|'high'}}
   */
  shouldPrompt(currentState, previousState, temporalNotes, context = {}) {
    // 1. Check if we have minimum notes
    if (temporalNotes.length < this.minNotesForPrompt) {
      return {
        shouldPrompt: false,
        reason: `Insufficient notes (${temporalNotes.length} < ${this.minNotesForPrompt})`,
        urgency: 'low'
      };
    }

    // 2. Calculate temporal coherence
    const aggregated = aggregateTemporalNotes(temporalNotes);
    const coherence = aggregated.coherence || 0;

    // 3. Check for significant state change
    const stateChange = this.calculateStateChange(currentState, previousState);

    // 4. Check for user action
    const hasUserAction = this.hasRecentUserAction(temporalNotes, context);

    // 5. Check for decision point
    const isDecisionPoint = this.isDecisionPoint(currentState, context);

    // 6. Check for coherence drop (urgency signal)
    const coherenceDrop = this.detectCoherenceDrop(temporalNotes, aggregated);

    // Decision logic (from research: prompt when decision needed, not on every change)
    if (isDecisionPoint) {
      return {
        shouldPrompt: true,
        reason: 'Decision point reached',
        urgency: 'high'
      };
    }

    if (coherenceDrop) {
      return {
        shouldPrompt: true,
        reason: 'Coherence drop detected (quality issue)',
        urgency: 'high'
      };
    }

    if (hasUserAction && stateChange > this.stateChangeThreshold) {
      return {
        shouldPrompt: true,
        reason: 'User action with significant state change',
        urgency: 'medium'
      };
    }

    if (coherence >= this.coherenceThreshold && stateChange > this.stateChangeThreshold) {
      return {
        shouldPrompt: true,
        reason: 'Stable context with significant state change',
        urgency: 'medium'
      };
    }

    // Wait for more context
    return {
      shouldPrompt: false,
      reason: `Context not sufficient (coherence: ${coherence.toFixed(2)}, stateChange: ${stateChange.toFixed(2)})`,
      urgency: 'low'
    };
  }

  /**
   * Calculate state change magnitude
   */
  calculateStateChange(currentState, previousState) {
    if (!previousState) return 1.0; // First state = maximum change

    // Simple state change calculation (can be enhanced)
    let change = 0.0;
    let comparisons = 0;

    // Compare scores if available
    if (currentState.score !== undefined && previousState.score !== undefined) {
      const scoreChange = Math.abs(currentState.score - previousState.score) / 10; // Normalize to 0-1
      change += scoreChange;
      comparisons++;
    }

    // Compare issues if available
    if (currentState.issues && previousState.issues) {
      const currentIssues = new Set(currentState.issues);
      const previousIssues = new Set(previousState.issues);
      const added = [...currentIssues].filter(i => !previousIssues.has(i)).length;
      const removed = [...previousIssues].filter(i => !currentIssues.has(i)).length;
      const issueChange = (added + removed) / Math.max(currentIssues.size + previousIssues.size, 1);
      change += issueChange;
      comparisons++;
    }

    // Compare game state if available
    if (currentState.gameState && previousState.gameState) {
      const gameStateChange = this.calculateGameStateChange(currentState.gameState, previousState.gameState);
      change += gameStateChange;
      comparisons++;
    }

    return comparisons > 0 ? change / comparisons : 0.0;
  }

  /**
   * Calculate game state change
   */
  calculateGameStateChange(current, previous) {
    // Simple comparison (can be enhanced)
    const currentKeys = Object.keys(current || {});
    const previousKeys = Object.keys(previous || {});
    
    const added = currentKeys.filter(k => !previousKeys.includes(k)).length;
    const removed = previousKeys.filter(k => !currentKeys.includes(k)).length;
    const changed = currentKeys.filter(k => 
      previousKeys.includes(k) && 
      JSON.stringify(current[k]) !== JSON.stringify(previous[k])
    ).length;

    const totalKeys = new Set([...currentKeys, ...previousKeys]).size;
    return totalKeys > 0 ? (added + removed + changed) / totalKeys : 0.0;
  }

  /**
   * Check for recent user action
   */
  hasRecentUserAction(temporalNotes, context) {
    if (context.recentAction) return true;

    // Check last few notes for interactions
    const recentNotes = temporalNotes.slice(-3);
    return recentNotes.some(note => 
      note.step?.includes('interaction') ||
      note.step?.includes('click') ||
      note.step?.includes('action') ||
      note.observation?.includes('user') ||
      note.observation?.includes('clicked')
    );
  }

  /**
   * Check if this is a decision point
   */
  isDecisionPoint(currentState, context) {
    // Decision points based on context
    if (context.stage === 'decision' || context.stage === 'evaluation') return true;
    if (context.testType === 'critical' || context.critical) return true;
    if (context.goal && context.goalCompleted) return true;
    
    return false;
  }

  /**
   * Detect coherence drop (quality issue signal)
   */
  detectCoherenceDrop(temporalNotes, currentAggregated) {
    if (temporalNotes.length < 4) return false; // Need history to detect drop

    // Get previous coherence (from notes without last one)
    const previousNotes = temporalNotes.slice(0, -1);
    const previousAggregated = aggregateTemporalNotes(previousNotes);
    const previousCoherence = previousAggregated.coherence || 1.0;
    const currentCoherence = currentAggregated.coherence || 1.0;

    // Drop detected if coherence decreased significantly
    const drop = previousCoherence - currentCoherence;
    return drop > this.urgencyThreshold;
  }

  /**
   * Calculate prompt urgency
   */
  calculatePromptUrgency(temporalContext, decision) {
    if (decision.urgency === 'high') return 1.0;
    if (decision.urgency === 'medium') return 0.6;
    
    // Low urgency, but check if we should wait
    const coherence = temporalContext.coherence || 0;
    const timeSinceLastPrompt = temporalContext.timeSinceLastPrompt || 0;
    
    // Increase urgency if coherence is good and it's been a while
    if (coherence > 0.7 && timeSinceLastPrompt > 5000) {
      return 0.4; // Medium-low
    }
    
    return 0.2; // Low
  }

  /**
   * Select optimal timing for requests
   */
  selectOptimalTiming(requests, temporalContext) {
    const decisions = requests.map(req => ({
      request: req,
      decision: this.shouldPrompt(
        req.currentState,
        req.previousState,
        req.temporalNotes || [],
        req.context || {}
      )
    }));

    // Separate by urgency
    const urgent = decisions.filter(d => d.decision.urgency === 'high');
    const medium = decisions.filter(d => d.decision.urgency === 'medium');
    const low = decisions.filter(d => d.decision.urgency === 'low');

    // Urgent: prompt immediately
    // Medium: batch if context stable, otherwise prompt
    // Low: wait or batch

    const stable = temporalContext.coherence > 0.7;
    const shouldBatch = stable && medium.length + low.length > 1;

    return {
      promptNow: urgent.map(d => d.request),
      batch: shouldBatch ? [...medium, ...low].map(d => d.request) : medium.map(d => d.request),
      wait: shouldBatch ? [] : low.map(d => d.request),
      decisions
    };
  }
}

/**
 * Create a temporal decision manager with default options
 */
export function createTemporalDecisionManager(options = {}) {
  return new TemporalDecisionManager(options);
}

