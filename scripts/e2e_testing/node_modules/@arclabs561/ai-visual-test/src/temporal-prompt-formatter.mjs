/**
 * Temporal Prompt Formatter
 *
 * Formats temporal notes (single-scale and multi-scale) for optimal VLM understanding.
 * Provides different formatting strategies for different temporal aggregation types.
 */

import { formatNotesForPrompt } from './temporal.mjs';

/**
 * Format temporal notes for prompt inclusion
 *
 * Handles both single-scale (AggregatedTemporalNotes) and multi-scale (MultiScaleAggregation)
 * temporal notes, formatting them optimally for VLM understanding.
 *
 * @param {import('./index.mjs').AggregatedTemporalNotes | import('./index.mjs').MultiScaleAggregation | Array} temporalNotes - Temporal notes (aggregated, multi-scale, or raw array)
 * @param {Object} options - Formatting options
 * @param {boolean} [options.includeMultiScale=true] - Include multi-scale insights if available
 * @param {boolean} [options.naturalLanguage=true] - Use natural language formatting
 * @returns {string} Formatted temporal context for prompt
 */
export function formatTemporalForPrompt(temporalNotes, options = {}) {
  const {
    includeMultiScale = true,
    naturalLanguage = true
  } = options;

  if (!temporalNotes) {
    return '';
  }

  // Handle raw array - should be aggregated first (caller's responsibility)
  if (Array.isArray(temporalNotes)) {
    return ''; // Don't format raw arrays here
  }

  // Handle multi-scale aggregation
  if (temporalNotes.scales && !temporalNotes.windows) {
    return formatMultiScaleForPrompt(temporalNotes, { naturalLanguage });
  }

  // Handle single-scale aggregation
  if (temporalNotes.windows) {
    return formatSingleScaleForPrompt(temporalNotes, { naturalLanguage });
  }

  return '';
}

/**
 * Format single-scale aggregated notes for prompt
 */
function formatSingleScaleForPrompt(aggregated, options = {}) {
  const { naturalLanguage = true } = options;

  if (naturalLanguage) {
    // Natural language format
    const parts = [];

    parts.push('TEMPORAL CONTEXT:');
    parts.push(aggregated.summary || 'Previous observations over time.');

    if (aggregated.windows && aggregated.windows.length > 0) {
      parts.push('\nTime Windows:');
      aggregated.windows.slice(-5).forEach((window, i) => {
        const timeRange = window.timeRange || `window ${window.window || i + 1}`;
        const score = window.avgScore !== null && window.avgScore !== undefined
          ? `${window.avgScore.toFixed(1)}/10`
          : 'N/A';
        parts.push(`  ${timeRange}: Score ${score}, ${window.noteCount || 0} observations`);
        if (window.observations) {
          parts.push(`    Notes: ${window.observations.substring(0, 150)}${window.observations.length > 150 ? '...' : ''}`);
        }
      });
    }

    if (aggregated.coherence !== null && aggregated.coherence !== undefined) {
      const coherenceDesc = aggregated.coherence > 0.7 ? 'high' : aggregated.coherence > 0.4 ? 'moderate' : 'low';
      parts.push(`\nTemporal Coherence: ${(aggregated.coherence * 100).toFixed(0)}% (${coherenceDesc})`);
    }

    if (aggregated.conflicts && aggregated.conflicts.length > 0) {
      parts.push(`\nCoherence Issues: ${aggregated.conflicts.length} potential conflicts detected`);
    }

    parts.push('\nWhen evaluating, consider how the current state relates to these temporal patterns and trends.');

    return parts.join('\n');
  } else {
    // Structured format (original)
    return formatNotesForPrompt(aggregated);
  }
}

/**
 * Format multi-scale aggregation for prompt
 */
function formatMultiScaleForPrompt(multiScale, options = {}) {
  const { naturalLanguage = true } = options;

  if (!multiScale.scales || Object.keys(multiScale.scales).length === 0) {
    return '';
  }

  const parts = [];

  if (naturalLanguage) {
    parts.push('TEMPORAL CONTEXT (Multi-Scale Analysis):');
    parts.push('The experience has been analyzed across multiple time scales:');
    parts.push('');

    // Order scales by time (shortest to longest)
    const scaleOrder = ['immediate', 'short', 'medium', 'long'];
    const orderedScales = scaleOrder
      .filter(scale => multiScale.scales[scale])
      .map(scale => [scale, multiScale.scales[scale]]);

    orderedScales.forEach(([scaleName, scaleData]) => {
      const scaleDescriptions = {
        immediate: 'Instant perception (0.1s) - visual feedback, animations',
        short: 'Quick interaction (1s) - button responses, immediate feedback',
        medium: 'Short task (5s) - form filling, quick actions',
        long: 'Longer session (30s) - overall experience, engagement'
      };

      parts.push(`${scaleName.toUpperCase()} Scale (${scaleDescriptions[scaleName] || scaleName}):`);

      if (scaleData.windows && scaleData.windows.length > 0) {
        const recentWindows = scaleData.windows.slice(-3); // Last 3 windows
        recentWindows.forEach((window, i) => {
          const timeRange = window.timeRange || `window ${window.window || i + 1}`;
          const score = window.avgScore !== null && window.avgScore !== undefined
            ? `${window.avgScore.toFixed(1)}/10`
            : 'N/A';
          parts.push(`  ${timeRange}: Score ${score}`);
        });

        if (scaleData.coherence !== null && scaleData.coherence !== undefined) {
          const coherenceDesc = scaleData.coherence > 0.7 ? 'high' : scaleData.coherence > 0.4 ? 'moderate' : 'low';
          parts.push(`  Coherence: ${(scaleData.coherence * 100).toFixed(0)}% (${coherenceDesc})`);
        }
      } else {
        parts.push(`  No windows in this scale`);
      }
      parts.push('');
    });

    // Overall summary
    if (multiScale.summary) {
      parts.push(`Overall: ${multiScale.summary}`);
    }

    parts.push('\nWhen evaluating, consider patterns at different time scales:');
    parts.push('- Immediate: Visual feedback and animation quality');
    parts.push('- Short: Interaction responsiveness and quick feedback');
    parts.push('- Medium: Task completion flow and user journey');
    parts.push('- Long: Overall experience quality and engagement');

    return parts.join('\n');
  } else {
    // Structured format
    parts.push('TEMPORAL CONTEXT (Multi-Scale):');
    parts.push(multiScale.summary || 'Multi-scale temporal analysis');
    parts.push('');

    Object.entries(multiScale.scales).forEach(([scaleName, scaleData]) => {
      parts.push(`${scaleName.toUpperCase()} Scale:`);
      parts.push(`  Windows: ${scaleData.windows?.length || 0}`);
      parts.push(`  Coherence: ${scaleData.coherence ? (scaleData.coherence * 100).toFixed(0) : 'N/A'}%`);
      if (scaleData.windows && scaleData.windows.length > 0) {
        scaleData.windows.slice(-3).forEach(window => {
          const timeRange = window.timeRange || `window ${window.window}`;
          const score = window.avgScore !== null && window.avgScore !== undefined
            ? `${window.avgScore.toFixed(1)}/10`
            : 'N/A';
          parts.push(`  ${timeRange}: ${score}`);
        });
      }
      parts.push('');
    });

    return parts.join('\n');
  }
}

/**
 * Format temporal notes with optimal strategy
 *
 * Chooses the best formatting based on the type of temporal notes provided.
 *
 * @param {any} temporalNotes - Temporal notes (any format)
 * @param {Object} options - Formatting options
 * @returns {string} Formatted temporal context
 */
export function formatTemporalContext(temporalNotes, options = {}) {
  if (!temporalNotes) {
    return '';
  }

  // Raw array - return empty (should be aggregated first)
  if (Array.isArray(temporalNotes)) {
    return '';
  }

  // Multi-scale - use multi-scale formatter
  if (temporalNotes.scales && !temporalNotes.windows) {
    return formatMultiScaleForPrompt(temporalNotes, options);
  }

  // Single-scale - use single-scale formatter
  if (temporalNotes.windows) {
    return formatSingleScaleForPrompt(temporalNotes, options);
  }

  return '';
}

export { formatSingleScaleForPrompt, formatMultiScaleForPrompt };

