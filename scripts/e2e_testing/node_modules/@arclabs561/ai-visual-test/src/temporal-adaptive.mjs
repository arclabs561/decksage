/**
 * Adaptive Temporal Aggregation
 *
 * Implements adaptive window sizing based on note frequency and activity type.
 *
 * Research context:
 * - "Towards Dynamic Theory of Mind: Evaluating LLM Adaptation to Temporal Evolution of Human States"
 *   (arXiv:2505.17663) - DynToM benchmark, optimal window sizes vary by activity pattern
 *   * We use adaptive window sizing based on frequency (loosely related concept)
 *   * We do NOT implement the DynToM benchmark or its specific methods
 * - "The Other Mind: How Language Models Exhibit Human Temporal Cognition" (arXiv:2507.15851)
 *   * Paper discusses Weber-Fechner law: logarithmic compression of temporal perception
 *   * Paper discusses temporal reference points and hierarchical construction
 *   * We use LINEAR frequency-based adjustment, NOT logarithmic compression
 *   * We do NOT implement temporal reference points
 *
 * IMPORTANT: This implementation uses LINEAR frequency-based window adjustment, NOT the
 * logarithmic compression (Weber-Fechner law) described in arXiv:2507.15851. We cite
 * the papers for adaptive window concepts, but do NOT implement their specific findings.
 */

import { aggregateTemporalNotes } from './temporal.mjs';

/**
 * Calculate optimal window size based on note frequency
 *
 * @param {import('./index.mjs').TemporalNote[]} notes - Temporal notes
 * @param {{
 *   minWindow?: number;
 *   maxWindow?: number;
 *   defaultWindow?: number;
 * }} [options={}] - Options
 * @returns {number} Optimal window size in milliseconds
 */
export function calculateOptimalWindowSize(notes, options = {}) {
  const {
    minWindow = 5000,
    maxWindow = 30000,
    defaultWindow = 10000
  } = options;

  if (notes.length < 2) {
    return defaultWindow;
  }

  // Calculate note frequency (notes per second)
  const timeSpan = notes[notes.length - 1].timestamp - notes[0].timestamp;
  if (timeSpan <= 0) {
    return defaultWindow;
  }

  const frequency = notes.length / (timeSpan / 1000); // notes per second

  // Adaptive logic based on frequency
  // High frequency (>2 notes/sec): use smaller windows
  // Low frequency (<0.5 notes/sec): use larger windows
  // Medium frequency: use default window

  if (frequency > 2) {
    return Math.max(minWindow, defaultWindow * 0.5); // 5s for high frequency
  } else if (frequency < 0.5) {
    return Math.min(maxWindow, defaultWindow * 2); // 20s for low frequency
  } else {
    return defaultWindow; // 10s for medium frequency
  }
}

/**
 * Detect activity pattern from notes
 *
 * @param {import('./index.mjs').TemporalNote[]} notes - Temporal notes
 * @returns {'fastChange' | 'slowChange' | 'consistent' | 'erratic'} Activity pattern
 */
export function detectActivityPattern(notes) {
  if (notes.length < 3) {
    return 'consistent';
  }

  // Calculate change rate
  const timeSpan = notes[notes.length - 1].timestamp - notes[0].timestamp;
  const avgTimeBetween = timeSpan / (notes.length - 1);

  // Calculate score variance
  const scores = notes
    .map(n => n.gameState?.score || 0)
    .filter(s => typeof s === 'number');

  if (scores.length < 2) {
    return 'consistent';
  }

  const meanScore = scores.reduce((a, b) => a + b, 0) / scores.length;
  const variance = scores.reduce((sum, score) => sum + Math.pow(score - meanScore, 2), 0) / scores.length;

  // Detect direction changes
  let directionChanges = 0;
  for (let i = 1; i < scores.length; i++) {
    const prev = scores[i - 1];
    const curr = scores[i];
    if ((prev < curr && i > 1 && scores[i - 2] > prev) ||
        (prev > curr && i > 1 && scores[i - 2] < prev)) {
      directionChanges++;
    }
  }

  // Classify pattern
  if (avgTimeBetween < 1000 && variance > meanScore * 0.5) {
    return 'fastChange';
  } else if (avgTimeBetween > 2000 && variance < meanScore * 0.2) {
    return 'slowChange';
  } else if (directionChanges > scores.length * 0.3) {
    return 'erratic';
  } else {
    return 'consistent';
  }
}

/**
 * Aggregate temporal notes with adaptive window sizing
 *
 * @param {import('./index.mjs').TemporalNote[]} notes - Temporal notes
 * @param {{
 *   adaptive?: boolean;
 *   windowSize?: number;
 *   decayFactor?: number;
 *   coherenceThreshold?: number;
 * }} [options={}] - Aggregation options
 * @returns {import('./index.mjs').AggregatedTemporalNotes} Aggregated temporal notes
 */
export function aggregateTemporalNotesAdaptive(notes, options = {}) {
  const {
    adaptive = true,
    windowSize,
    decayFactor = 0.9,
    coherenceThreshold = 0.7
  } = options;

  let finalWindowSize = windowSize;

  if (adaptive && !windowSize) {
    // Calculate optimal window size based on note frequency
    finalWindowSize = calculateOptimalWindowSize(notes);

    // Adjust based on activity pattern
    const pattern = detectActivityPattern(notes);
    if (pattern === 'fastChange') {
      finalWindowSize = Math.min(finalWindowSize, 5000); // Prefer smaller for fast changes
    } else if (pattern === 'slowChange') {
      finalWindowSize = Math.max(finalWindowSize, 20000); // Prefer larger for slow changes
    }
  } else if (!finalWindowSize) {
    finalWindowSize = 10000; // Default
  }

  return aggregateTemporalNotes(notes, {
    windowSize: finalWindowSize,
    decayFactor,
    coherenceThreshold
  });
}



