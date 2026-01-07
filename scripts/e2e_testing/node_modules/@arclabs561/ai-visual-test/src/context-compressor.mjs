/**
 * Context Compressor
 *
 * Compresses historical context to reduce token usage while maintaining accuracy.
 *
 * General-purpose utility - no domain-specific logic.
 */

/**
 * Compress context by aggregating notes and extracting key insights
 *
 * @param {import('./index.mjs').TemporalNote[]} notes - Array of temporal notes to compress
 * @param {{
 *   maxTokens?: number;
 *   maxNotes?: number;
 *   includeRecent?: boolean;
 *   includeKeyEvents?: boolean;
 *   aggregationStrategy?: 'temporal' | 'semantic' | 'importance';
 * }} [options={}] - Compression options
 * @returns {import('./index.mjs').TemporalNote[]} Compressed array of notes
 */
export function compressContext(notes, options = {}) {
  const {
    maxTokens = 500, // Target token count
    maxNotes = 10, // Maximum notes to include
    includeRecent = true, // Always include most recent notes
    includeKeyEvents = true, // Always include key events (bugs, state changes)
    aggregationStrategy = 'temporal' // 'temporal', 'semantic', 'importance'
  } = options;

  if (!notes || notes.length === 0) {
    return {
      compressed: [],
      summary: 'No notes available',
      tokenEstimate: 0,
      compressionRatio: 1.0
    };
  }

  // Sort notes by timestamp (most recent first)
  const sortedNotes = [...notes].sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));

  // Extract key events (bugs, state changes, critical observations)
  const keyEvents = sortedNotes.filter(note =>
    note.step?.includes('bug') ||
    note.step?.includes('error') ||
    note.step?.includes('critical') ||
    note.severity === 'CRITICAL' ||
    note.reflection?.score !== undefined
  );

  // Select notes based on strategy
  let selectedNotes = [];

  if (aggregationStrategy === 'temporal') {
    // Temporal: Include most recent + key events
    const recentNotes = includeRecent ? sortedNotes.slice(0, Math.floor(maxNotes * 0.7)) : [];
    const keyEventNotes = includeKeyEvents ? keyEvents.slice(0, Math.floor(maxNotes * 0.3)) : [];

    // Combine and deduplicate
    const combined = [...recentNotes, ...keyEventNotes];
    const seen = new Set();
    selectedNotes = combined.filter(note => {
      const id = note.step + (note.timestamp || 0);
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    }).slice(0, maxNotes);
  } else if (aggregationStrategy === 'semantic') {
    // Semantic: Group by similarity and select representatives
    selectedNotes = selectSemanticRepresentatives(sortedNotes, maxNotes, keyEvents);
  } else if (aggregationStrategy === 'importance') {
    // Importance: Score notes by importance and select top
    selectedNotes = selectByImportance(sortedNotes, maxNotes, keyEvents);
  }

  // Generate summary from selected notes
  const summary = generateSummary(selectedNotes, sortedNotes);

  // Estimate token count
  const tokenEstimate = estimateTokens(selectedNotes, summary);
  const originalTokenEstimate = estimateTokens(sortedNotes);
  const compressionRatio = originalTokenEstimate > 0 ? tokenEstimate / originalTokenEstimate : 1.0;

  return {
    compressed: selectedNotes,
    summary,
    tokenEstimate,
    compressionRatio,
    originalCount: notes.length,
    compressedCount: selectedNotes.length
  };
}

/**
 * Select semantic representatives (group similar notes, pick one from each group)
 */
function selectSemanticRepresentatives(notes, maxNotes, keyEvents) {
  // Simple semantic grouping by step type
  const groups = new Map();

  notes.forEach(note => {
    const groupKey = note.step?.split('_')[0] || 'other';
    if (!groups.has(groupKey)) {
      groups.set(groupKey, []);
    }
    groups.get(groupKey).push(note);
  });

  // Select most recent from each group
  const representatives = [];
  for (const [groupKey, groupNotes] of groups.entries()) {
    const sorted = groupNotes.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
    representatives.push(sorted[0]);
  }

  // Always include key events
  const combined = [...representatives, ...keyEvents];
  const seen = new Set();
  return combined.filter(note => {
    const id = note.step + (note.timestamp || 0);
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  }).slice(0, maxNotes);
}

/**
 * Select notes by importance score
 */
function selectByImportance(notes, maxNotes, keyEvents) {
  // Score notes by importance
  const scored = notes.map(note => {
    let score = 0;

    // Key events get high score
    if (keyEvents.includes(note)) score += 10;

    // Recent notes get higher score
    const age = Date.now() - (note.timestamp || 0);
    const ageScore = Math.max(0, 10 - (age / 1000)); // Decay over 10 seconds
    score += ageScore;

    // Critical severity gets high score
    if (note.severity === 'CRITICAL') score += 5;
    if (note.severity === 'HIGH') score += 3;

    // Reflections get higher score
    if (note.reflection) score += 2;

    // State changes get higher score
    if (note.gameState || note.state) score += 1;

    return { note, score };
  });

  // Sort by score and select top
  const topScored = scored.sort((a, b) => b.score - a.score).slice(0, maxNotes);
  return topScored.map(item => item.note);
}

/**
 * Generate summary from selected notes
 */
function generateSummary(selectedNotes, allNotes) {
  if (selectedNotes.length === 0) {
    return 'No notes available';
  }

  const parts = [];

  // Count by type
  const typeCounts = {};
  selectedNotes.forEach(note => {
    const type = note.step?.split('_')[0] || 'other';
    typeCounts[type] = (typeCounts[type] || 0) + 1;
  });

  parts.push(`Summary: ${selectedNotes.length} key observations from ${allNotes.length} total notes.`);

  // Key statistics
  const bugs = selectedNotes.filter(n => n.step?.includes('bug')).length;
  const reflections = selectedNotes.filter(n => n.reflection).length;
  const critical = selectedNotes.filter(n => n.severity === 'CRITICAL').length;

  if (bugs > 0) parts.push(`${bugs} bug detection(s)`);
  if (reflections > 0) parts.push(`${reflections} reflection(s)`);
  if (critical > 0) parts.push(`${critical} critical issue(s)`);

  // Time span
  if (selectedNotes.length > 1) {
    const first = selectedNotes[selectedNotes.length - 1].timestamp || 0;
    const last = selectedNotes[0].timestamp || 0;
    const span = Math.round((last - first) / 1000);
    if (span > 0) parts.push(`Time span: ${span}s`);
  }

  return parts.join(', ');
}

/**
 * Estimate token count for notes
 */
function estimateTokens(notes, summary = '') {
  // Rough estimate: 1 token ≈ 4 characters
  const noteText = notes.map(n =>
    `${n.step || ''} ${n.observation || ''} ${JSON.stringify(n.gameState || n.state || {})}`
  ).join(' ');
  const totalText = noteText + ' ' + summary;
  return Math.ceil(totalText.length / 4);
}

/**
 * Compress state history by keeping important transitions
 *
 * @param {Array<Record<string, unknown>>} stateHistory - Array of state objects
 * @param {{
 *   maxLength?: number;
 *   preserveImportant?: boolean;
 * }} [options={}] - Compression options
 * @returns {Array<Record<string, unknown>>} Compressed state history
 */
export function compressStateHistory(stateHistory, options = {}) {
  const {
    maxStates = 3, // Maximum states to include
    includeFirst = true, // Always include first state
    includeLast = true, // Always include last state
    includeKeyTransitions = true // Include states with significant changes
  } = options;

  if (!stateHistory || stateHistory.length === 0) {
    return {
      compressed: [],
      summary: 'No state history',
      tokenEstimate: 0
    };
  }

  const states = Array.isArray(stateHistory) ? stateHistory : [stateHistory];

  // Select key states
  let selectedStates = [];

  if (includeFirst && states.length > 0) {
    selectedStates.push(states[0]);
  }

  if (includeLast && states.length > 1 && states[states.length - 1] !== states[0]) {
    selectedStates.push(states[states.length - 1]);
  }

  // Find key transitions (significant changes)
  if (includeKeyTransitions && states.length > 2) {
    const transitions = findKeyTransitions(states);
    selectedStates.push(...transitions);
  }

  // Deduplicate and limit
  const seen = new Set();
  const unique = selectedStates.filter(state => {
    const id = JSON.stringify(state);
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  }).slice(0, maxStates);

  // Generate summary
  const summary = generateStateSummary(unique, states);

  // Estimate tokens
  const tokenEstimate = estimateStateTokens(unique, summary);
  const originalTokenEstimate = estimateStateTokens(states);
  const compressionRatio = originalTokenEstimate > 0 ? tokenEstimate / originalTokenEstimate : 1.0;

  return {
    compressed: unique,
    summary,
    tokenEstimate,
    compressionRatio,
    originalCount: states.length,
    compressedCount: unique.length,
    originalTokenEstimate
  };
}

/**
 * Find key transitions (states with significant changes)
 */
function findKeyTransitions(states) {
  const transitions = [];

  for (let i = 1; i < states.length; i++) {
    const prev = states[i - 1];
    const curr = states[i];

    // Check for significant changes (general-purpose, not game-specific)
    const hasSignificantChange = Object.keys(curr).some(key => {
      const prevVal = prev[key];
      const currVal = curr[key];

      // Numeric changes
      if (typeof prevVal === 'number' && typeof currVal === 'number') {
        return Math.abs(currVal - prevVal) > 10; // Threshold for significant change
      }

      // String/boolean changes
      return prevVal !== currVal;
    });

    if (hasSignificantChange) {
      transitions.push(curr);
    }
  }

  return transitions;
}

/**
 * Generate summary for state history
 */
function generateStateSummary(selectedStates, allStates) {
  if (selectedStates.length === 0) {
    return 'No state history';
  }

  const parts = [];
  parts.push(`${selectedStates.length} key states from ${allStates.length} total`);

  if (selectedStates.length > 1) {
    const first = selectedStates[0];
    const last = selectedStates[selectedStates.length - 1];

    // Check for any changes (general-purpose)
    const hasChanges = Object.keys(last).some(key => first[key] !== last[key]);

    if (hasChanges) parts.push('state changes detected');
  }

  return parts.join(', ');
}

/**
 * Estimate tokens for state history
 */
function estimateStateTokens(states, summary = '') {
  const stateText = states.map(s => JSON.stringify(s)).join(' ');
  const totalText = stateText + ' ' + summary;
  return Math.ceil(totalText.length / 4);
}

