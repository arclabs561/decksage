/**
 * Temporal Note Pruner
 * 
 * Prunes irrelevant or low-weight notes to keep prompt context manageable.
 * 
 * Research context:
 * - Temporal aggregation research shows older notes should decay
 * - Attention-based weighting shows some notes are more relevant than others
 * - Context compression research shows pruning improves efficiency
 * 
 * This implements note pruning based on:
 * - Recency (exponential decay)
 * - Relevance (salience, action, novelty)
 * - Weight thresholds
 */

// Import calculateAttentionWeight directly (now exported from temporal-decision.mjs)
import { calculateAttentionWeight } from './temporal-decision.mjs';

/**
 * Prune temporal notes based on relevance and weight
 * 
 * @param {import('./index.mjs').TemporalNote[]} notes - Temporal notes
 * @param {Object} options - Pruning options
 * @param {number} [options.maxNotes=10] - Maximum notes to keep
 * @param {number} [options.minWeight=0.1] - Minimum weight threshold
 * @param {number} [options.currentTime] - Current time (default: Date.now())
 * @param {number} [options.windowSize=10000] - Window size for weight calculation
 * @returns {import('./index.mjs').TemporalNote[]} Pruned notes
 */
export function pruneTemporalNotes(notes, options = {}) {
  const {
    maxNotes = 10,
    minWeight = 0.1,
    currentTime = Date.now(),
    windowSize = 10000
  } = options;

  if (notes.length === 0) return [];

  const startTime = notes[0].timestamp || currentTime;

  // Calculate weights for all notes
  const weightedNotes = notes.map(note => {
    const elapsed = note.elapsed || (note.timestamp - startTime);
    const weight = calculateAttentionWeight(note, {
      elapsed,
      windowSize,
      scaleName: 'medium'
    });

    return {
      note,
      weight,
      relevance: calculateRelevance(note, currentTime, startTime)
    };
  });

  // Filter by minimum weight
  const aboveThreshold = weightedNotes.filter(w => w.weight >= minWeight);

  // Sort by weight (descending)
  const sorted = aboveThreshold.sort((a, b) => b.weight - a.weight);

  // Take top N
  const pruned = sorted.slice(0, maxNotes).map(w => w.note);

  return pruned;
}

/**
 * Calculate relevance score for a note
 */
function calculateRelevance(note, currentTime, startTime) {
  let relevance = 1.0;

  // Recency (exponential decay)
  const age = currentTime - (note.timestamp || startTime);
  const recency = Math.pow(0.9, age / 10000); // Decay over 10s
  relevance *= recency;

  // Salience (importance)
  const score = note.score || note.gameState?.score || 5;
  if (score >= 8 || score <= 2) {
    relevance *= 1.5; // High/low scores are more relevant
  }

  // Issues increase relevance
  if (note.issues && note.issues.length > 0) {
    relevance *= 1.2;
  }

  // User actions increase relevance
  if (note.step?.includes('interaction') || note.step?.includes('click')) {
    relevance *= 1.3;
  }

  // Context changes increase relevance
  if (note.observation?.includes('change') || note.observation?.includes('new')) {
    relevance *= 1.2;
  }

  return relevance;
}

/**
 * Propagate notes forward with decay
 * 
 * @param {import('./index.mjs').TemporalNote[]} notes - Temporal notes
 * @param {Object} options - Propagation options
 * @param {number} [options.currentTime] - Current time
 * @param {number} [options.relevanceThreshold=0.2] - Minimum relevance to keep
 * @returns {import('./index.mjs').TemporalNote[]} Propagated notes with updated weights
 */
export function propagateNotes(notes, options = {}) {
  const {
    currentTime = Date.now(),
    relevanceThreshold = 0.2
  } = options;

  if (notes.length === 0) return [];

  const startTime = notes[0].timestamp || currentTime;

  return notes
    .map(note => {
      const relevance = calculateRelevance(note, currentTime, startTime);
      const weight = Math.pow(0.9, (currentTime - (note.timestamp || startTime)) / 10000);

      return {
        ...note,
        weight,
        relevance,
        propagated: true
      };
    })
    .filter(note => note.relevance >= relevanceThreshold)
    .sort((a, b) => b.relevance - a.relevance);
}

/**
 * Select top-weighted notes for prompt inclusion
 * 
 * @param {import('./index.mjs').TemporalNote[]} notes - Temporal notes
 * @param {Object} options - Selection options
 * @param {number} [options.topN=5] - Number of top notes to select
 * @returns {import('./index.mjs').TemporalNote[]} Top-weighted notes
 */
export function selectTopWeightedNotes(notes, options = {}) {
  const { topN = 5 } = options;

  if (notes.length === 0) return [];

  const currentTime = Date.now();
  const startTime = notes[0].timestamp || currentTime;

  const weighted = notes.map(note => {
    const elapsed = note.elapsed || (note.timestamp - startTime);
    const weight = calculateAttentionWeight(note, {
      elapsed,
      windowSize: 10000,
      scaleName: 'medium'
    });

    return { note, weight };
  });

  return weighted
    .sort((a, b) => b.weight - a.weight)
    .slice(0, topN)
    .map(w => w.note);
}

