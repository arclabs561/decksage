/**
 * Temporal Aggregator
 * 
 * Aggregates opinions over time with coherence checking.
 * 
 * Research context:
 * - "Towards Dynamic Theory of Mind: Evaluating LLM Adaptation to Temporal Evolution of Human States"
 *   (arXiv:2505.17663) - DynToM benchmark, temporal progression of mental states
 *   * We use temporal aggregation concepts (loosely related)
 *   * We do NOT implement the DynToM benchmark or specific methods
 * - "The Other Mind: How Language Models Exhibit Human Temporal Cognition" (arXiv:2507.15851)
 *   * Paper discusses Weber-Fechner law and logarithmic compression
 *   * We use EXPONENTIAL decay (Math.pow), NOT logarithmic compression
 *   * We do NOT implement temporal reference points from the research
 * - Temporal aggregation and opinion propagation research
 * - Coherence analysis in temporal sequences
 * 
 * IMPORTANT: This implementation uses EXPONENTIAL decay (decayFactor^age), NOT the
 * logarithmic compression (Weber-Fechner law) described in arXiv:2507.15851. We cite
 * the papers for temporal awareness concepts, but do NOT implement their specific
 * findings (logarithmic compression, temporal reference points).
 */

/**
 * Aggregate notes temporally with coherence analysis
 * 
 * @param {import('./index.mjs').TemporalNote[]} notes - Array of temporal notes
 * @param {{
 *   windowSize?: number;
 *   decayFactor?: number;
 *   coherenceThreshold?: number;
 * }} [options={}] - Aggregation options
 * @returns {import('./index.mjs').AggregatedTemporalNotes} Aggregated temporal notes with windows and coherence
 */
import { TEMPORAL_CONSTANTS } from './constants.mjs';

export function aggregateTemporalNotes(notes, options = {}) {
  const {
    windowSize = TEMPORAL_CONSTANTS.DEFAULT_WINDOW_SIZE_MS,
    decayFactor = TEMPORAL_CONSTANTS.DEFAULT_DECAY_FACTOR,
    coherenceThreshold = TEMPORAL_CONSTANTS.DEFAULT_COHERENCE_THRESHOLD
  } = options;

  // Filter and sort notes by timestamp
  // Accept any note with a timestamp (not just gameplay_note_)
  const validNotes = notes
    .filter(n => n.timestamp || n.elapsed !== undefined)
    .sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
  
  // Use validNotes instead of gameplayNotes for broader compatibility
  const gameplayNotes = validNotes;

  if (gameplayNotes.length === 0) {
    return {
      windows: [],
      summary: 'No gameplay notes available',
      coherence: 1.0,
      conflicts: []
    };
  }

  // Group notes into temporal windows
  const windows = [];
  const startTime = gameplayNotes[0].timestamp || Date.now();
  
  // INVARIANT: Notes are sorted by timestamp (line 48), so elapsed is always >= 0
  // This ensures windowIndex is always >= 0 (Math.floor of non-negative number)
  // If notes were unsorted, negative elapsed would create negative window indices
  for (let i = 0; i < gameplayNotes.length; i++) {
    const note = gameplayNotes[i];
    const elapsed = note.elapsed || (note.timestamp - startTime);
    const windowIndex = Math.floor(elapsed / windowSize);
    
    if (!windows[windowIndex]) {
      windows[windowIndex] = {
        index: windowIndex,
        startTime: startTime + (windowIndex * windowSize),
        endTime: startTime + ((windowIndex + 1) * windowSize),
        notes: [],
        weightedScore: 0,
        totalWeight: 0
      };
    }
    
    // Calculate weight (exponential decay)
    const age = elapsed;
    const weight = Math.pow(decayFactor, age / windowSize);
    
    windows[windowIndex].notes.push({
      ...note,
      weight
    });
    
    // Extract score from gameState if available
    // NOTE: Score extraction order matters - gameState.score takes precedence over note.score
    // This is because gameState.score is more reliable (from actual game state)
    const score = note.gameState?.score || note.score || 0;
    
    // Accumulate weighted score and total weight for this window
    // INVARIANT: weightedScore must be divided by totalWeight to get average
    // Both are accumulated across all notes in the window
    // The weight uses exponential decay: Math.pow(decayFactor, age / windowSize)
    windows[windowIndex].weightedScore += score * weight;
    windows[windowIndex].totalWeight += weight;
  }

  // Calculate window summaries
  const windowSummaries = windows.map(window => {
    const avgScore = window.totalWeight > 0 
      ? window.weightedScore / window.totalWeight 
      : 0;
    
    const observations = window.notes.map(n => n.observation || n.assessment || '').join('; ');
    
    return {
      window: window.index,
      timeRange: `${Math.round((window.startTime - startTime) / 1000)}s-${Math.round((window.endTime - startTime) / 1000)}s`,
      noteCount: window.notes.length,
      avgScore: Math.round(avgScore),
      observations,
      weightedAvg: window.totalWeight > 0 ? window.weightedScore / window.totalWeight : 0
    };
  });

  // Coherence analysis: Check for logical progression
  const coherence = calculateCoherence(windowSummaries);
  const conflicts = detectConflicts(windowSummaries);

  // Generate summary
  const summary = generateSummary(windowSummaries, coherence, conflicts);

  // Handle timeSpan calculation safely
  const firstElapsed = gameplayNotes[0]?.elapsed ?? 0;
  const lastElapsed = gameplayNotes[gameplayNotes.length - 1]?.elapsed ?? 0;
  const timeSpan = lastElapsed - firstElapsed;
  
  return {
    windows: windowSummaries,
    summary,
    coherence,
    conflicts,
    totalNotes: gameplayNotes.length,
    timeSpan: Math.max(0, timeSpan)
  };
}

/**
 * Calculate coherence score (0-1)
 * 
 * Coherence measures how consistent temporal notes are over time. Higher coherence
 * indicates stable, predictable patterns. Lower coherence indicates erratic behavior.
 * 
 * BUG FIX (2025-01): The adjustedVarianceCoherence calculation was incomplete.
 * It was: `const adjustedVarianceCoherence = Math.max;` which is just a function reference.
 * This would cause incorrect coherence scores for erratic behavior. The fix completes
 * the calculation with proper penalty for direction changes.
 * 
 * @param {Array} windows - Temporal window summaries with avgScore
 * @returns {number} Coherence score 0-1 (1 = perfectly consistent, 0 = erratic)
 */
function calculateCoherence(windows) {
  if (windows.length < 2) return 1.0;

  // Check for consistent trends (score progression)
  const scores = windows.map(w => w.avgScore).filter(s => !isNaN(s) && isFinite(s));
  
  // If no valid scores, return default
  if (scores.length < 2) return 1.0;
  
  const trends = [];
  
  for (let i = 1; i < scores.length; i++) {
    const change = scores[i] - scores[i - 1];
    trends.push(change >= 0 ? 1 : -1); // Direction only
  }

  // Metric 1: Direction consistency
  // Count how often the direction of change flips (up→down or down→up)
  // More flips = more erratic behavior
  let directionChanges = 0;
  for (let i = 1; i < trends.length; i++) {
    if (trends[i] !== trends[i - 1]) {
      directionChanges++;
    }
  }
  const directionConsistency = Math.max(0, Math.min(1, 1.0 - (directionChanges / Math.max(1, trends.length))));

  // Metric 2: Score variance
  // Use stricter normalization that properly penalizes erratic behavior
  // 
  // IMPORTANT: We changed from meanScore² to score range because:
  // - meanScore² was too lenient (e.g., mean=5 → maxVariance=25, but scores 0-10 have range=10)
  // - Score range better captures actual variance in the data
  // - For scores 0-10, max reasonable variance is ~25 (when scores vary uniformly from 0 to 10)
  // - For scores 0-100, max reasonable variance is ~2500
  const meanScore = scores.reduce((a, b) => a + b, 0) / scores.length;
  const variance = scores.reduce((sum, score) => sum + Math.pow(score - meanScore, 2), 0) / scores.length;
  
  const scoreRange = Math.max(...scores) - Math.min(...scores);
  const maxVariance = Math.max(
    Math.pow(scoreRange / 2, 2), // Variance for uniform distribution over range
    Math.pow(meanScore * 0.5, 2), // Fallback: 50% of mean as standard deviation
    10 // Minimum to avoid division by tiny numbers
  );
  
  // Variance coherence: penalize high variance more aggressively
  const varianceCoherence = Math.max(0, Math.min(1, 1.0 - (variance / maxVariance)));
  
  // Add stronger penalty for frequent direction changes (erratic behavior)
  // Direction changes are a strong signal of erratic behavior
  // 
  // NOTE: This calculation must be complete! The bug was:
  //   const adjustedVarianceCoherence = Math.max; // WRONG - just function reference
  // The fix is:
  //   const adjustedVarianceCoherence = Math.max(0, Math.min(1, varianceCoherence * (1.0 - directionChangePenalty * 0.7)));
  // 
  // The 0.7 multiplier means direction changes reduce variance coherence by up to 70%
  // This was increased from 0.5 to be more aggressive at detecting erratic behavior
  const directionChangePenalty = directionChanges / Math.max(1, trends.length);
  const adjustedVarianceCoherence = Math.max(0, Math.min(1, varianceCoherence * (1.0 - directionChangePenalty * 0.7)));

  // Metric 3: Observation consistency
  let observationConsistency = 1.0;
  if (windows.length > 1) {
    const observations = windows.map(w => (w.observations || '').toLowerCase());
    const keywords = observations.map(obs => {
      const words = obs.split(/\s+/).filter(w => w.length > 3);
      return new Set(words);
    });
    
    let overlapSum = 0;
    for (let i = 1; i < keywords.length; i++) {
      const prev = keywords[i - 1];
      const curr = keywords[i];
      if (prev && curr && prev.size > 0 && curr.size > 0) {
      const intersection = new Set([...prev].filter(x => curr.has(x)));
      const union = new Set([...prev, ...curr]);
      const overlap = union.size > 0 ? intersection.size / union.size : 0;
      overlapSum += overlap;
      }
    }
    observationConsistency = Math.max(0, Math.min(1, overlapSum / Math.max(1, keywords.length - 1)));
  }

  // Metric 3: Stability
  // Stability directly penalizes erratic behavior by measuring direction change frequency
  // Stability = 1 - (directionChanges / maxPossibleChanges)
  // For n windows, max possible direction changes is n-2 (can't change at first or last)
  const maxPossibleChanges = Math.max(1, trends.length);
  const stability = Math.max(0, Math.min(1, 1.0 - (directionChanges / maxPossibleChanges)));
  
  // Metric 4: Observation consistency (recalculated)
  // Check if observations use similar keywords across windows
  // Less reliable than score-based metrics (keyword matching is approximate)
  observationConsistency = 1.0;
  if (windows.length > 1) {
    const observations = windows.map(w => (w.observations || '').toLowerCase());
    const keywords = observations.map(obs => {
      const words = obs.split(/\s+/).filter(w => w.length > 3);
      return new Set(words);
    });
    
    let overlapSum = 0;
    for (let i = 1; i < keywords.length; i++) {
      const prev = keywords[i - 1];
      const curr = keywords[i];
      if (prev && curr && prev.size > 0 && curr.size > 0) {
      const intersection = new Set([...prev].filter(x => curr.has(x)));
      const union = new Set([...prev, ...curr]);
      const overlap = union.size > 0 ? intersection.size / union.size : 0;
      overlapSum += overlap;
      }
    }
    observationConsistency = Math.max(0, Math.min(1, overlapSum / Math.max(1, keywords.length - 1)));
  }
  
  // Final coherence: Weighted combination of all metrics
  // 
  // Weight rationale (2025-01):
  // - Direction (0.35): Strongest signal of erratic behavior, most reliable
  // - Stability (0.25): Directly measures direction change frequency
  // - Variance (0.25): Captures score spread, adjusted for direction changes
  // - Observation (0.15): Least reliable (keyword-based), lowest weight
  // 
  // These weights were chosen to heavily penalize erratic behavior while still
  // considering all aspects of temporal consistency. Don't change without:
  // - Testing with known erratic vs. stable patterns
  // - Validating against human-annotated coherence scores
  // - Measuring impact on conflict detection
  const coherence = (
    directionConsistency * 0.35 +
    stability * 0.25 +
    adjustedVarianceCoherence * 0.25 +
    observationConsistency * 0.15
  );
  
  // Clamp to [0, 1] and handle NaN/Infinity
  const clamped = Math.max(0, Math.min(1, isNaN(coherence) || !isFinite(coherence) ? 0.5 : coherence));
  return clamped;
}

/**
 * Detect conflicting opinions
 */
function detectConflicts(windows) {
  const conflicts = [];
  
  const observations = windows.map(w => (w.observations || '').toLowerCase());
  
  const positiveWords = ['good', 'great', 'excellent', 'smooth', 'responsive', 'clear'];
  const negativeWords = ['bad', 'poor', 'slow', 'laggy', 'unclear', 'confusing'];
  
  for (let i = 0; i < observations.length; i++) {
    const obs = observations[i] || '';
    const hasPositive = positiveWords.some(w => obs.includes(w));
    const hasNegative = negativeWords.some(w => obs.includes(w));
    
    if (hasPositive && hasNegative) {
      conflicts.push({
        window: windows[i].window,
        type: 'mixed_sentiment',
        observation: windows[i].observations
      });
    }
  }
  
  // Check for score inconsistencies
  for (let i = 1; i < windows.length; i++) {
    if (windows[i] && windows[i - 1] && 
        windows[i].avgScore !== undefined && windows[i - 1].avgScore !== undefined &&
        windows[i].avgScore < windows[i - 1].avgScore) {
      conflicts.push({
        window: windows[i].window,
        type: 'score_decrease',
        previousScore: windows[i - 1].avgScore,
        currentScore: windows[i].avgScore
      });
    }
  }
  
  return conflicts;
}

/**
 * Generate human-readable summary
 */
function generateSummary(windows, coherence, conflicts) {
  const parts = [];
  
  parts.push(`Aggregated ${windows.length} temporal windows from gameplay notes.`);
  
  if (windows.length > 0) {
    const firstWindow = windows[0];
    const lastWindow = windows[windows.length - 1];
    const firstScore = firstWindow?.avgScore ?? 0;
    const lastScore = lastWindow?.avgScore ?? 0;
    parts.push(`Score progression: ${firstScore} → ${lastScore} (${lastScore - firstScore > 0 ? '+' : ''}${lastScore - firstScore}).`);
  }
  
  parts.push(`Temporal coherence: ${(coherence * 100).toFixed(0)}% ${coherence > 0.7 ? '(high)' : coherence > 0.4 ? '(moderate)' : '(low)'}.`);
  
  if (conflicts.length > 0) {
    parts.push(`Detected ${conflicts.length} potential conflict${conflicts.length > 1 ? 's' : ''}: ${conflicts.map(c => c.type).join(', ')}.`);
  }
  
  return parts.join(' ');
}

/**
 * Format aggregated temporal notes for prompt inclusion
 * 
 * @param {import('./index.mjs').AggregatedTemporalNotes} aggregated - Aggregated temporal notes
 * @returns {string} Formatted string for prompt inclusion
 */
export function formatNotesForPrompt(aggregated) {
  const parts = [];
  
  parts.push('TEMPORAL AGGREGATION ANALYSIS:');
  parts.push(aggregated.summary);
  parts.push('');
  
  if (aggregated.windows.length > 0) {
    parts.push('Temporal Windows:');
    aggregated.windows.forEach(window => {
      parts.push(`  [${window.timeRange}] Score: ${window.avgScore}, Notes: ${window.noteCount}`);
      if (window.observations) {
        parts.push(`    Observations: ${window.observations.substring(0, 100)}${window.observations.length > 100 ? '...' : ''}`);
      }
    });
    parts.push('');
  }
  
  if (aggregated.conflicts.length > 0) {
    parts.push('Coherence Issues:');
    aggregated.conflicts.forEach(conflict => {
      parts.push(`  - ${conflict.type}: ${JSON.stringify(conflict)}`);
    });
    parts.push('');
  }
  
  parts.push(`Overall Coherence: ${(aggregated.coherence * 100).toFixed(0)}%`);
  
  return parts.join('\n');
}

/**
 * Calculate coherence score for temporal windows
 * 
 * @param {import('./index.mjs').TemporalWindow[]} windows - Array of temporal windows
 * @returns {number} Coherence score (0-1)
 */
export function calculateCoherenceExported(windows) {
  return calculateCoherence(windows);
}

