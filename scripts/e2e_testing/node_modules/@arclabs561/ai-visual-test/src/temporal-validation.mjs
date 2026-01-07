/**
 * Temporal Validation
 * Input validation for temporal decision-making components
 */

import { MultiScaleError, PerceptionTimeError, SequentialContextError } from './temporal-errors.mjs';
import { warn } from './logger.mjs';

/**
 * Validate temporal notes
 */
export function validateNotes(notes) {
  if (!Array.isArray(notes)) {
    throw new MultiScaleError('Notes must be an array', { received: typeof notes });
  }
  
  const validNotes = [];
  const invalidNotes = [];
  
  for (let i = 0; i < notes.length; i++) {
    const note = notes[i];
    
    if (!note || typeof note !== 'object') {
      invalidNotes.push({ index: i, reason: 'Not an object' });
      continue;
    }
    
    if (!note.timestamp && note.elapsed === undefined) {
      invalidNotes.push({ index: i, reason: 'Missing timestamp or elapsed' });
      continue;
    }
    
    if (note.timestamp && typeof note.timestamp !== 'number') {
      invalidNotes.push({ index: i, reason: 'Invalid timestamp type' });
      continue;
    }
    
    if (note.elapsed !== undefined && typeof note.elapsed !== 'number') {
      invalidNotes.push({ index: i, reason: 'Invalid elapsed type' });
      continue;
    }
    
    validNotes.push(note);
  }
  
  if (invalidNotes.length > 0) {
    warn(`[Temporal] ${invalidNotes.length} invalid notes filtered out:`, invalidNotes);
  }
  
  return validNotes;
}

/**
 * Validate and sort notes
 * Convenience function that validates and sorts in one step
 */
export function validateAndSortNotes(notes) {
  const validNotes = validateNotes(notes);
  return validNotes.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
}

/**
 * Validate time scales
 */
export function validateTimeScales(timeScales) {
  if (typeof timeScales !== 'object' || timeScales === null) {
    throw new MultiScaleError('Time scales must be an object', { received: typeof timeScales });
  }
  
  for (const [name, value] of Object.entries(timeScales)) {
    if (typeof value !== 'number' || value <= 0) {
      throw new MultiScaleError(`Invalid time scale ${name}: ${value}`, { 
        scaleName: name, 
        value,
        type: typeof value
      });
    }
  }
  
  return true;
}

/**
 * Validate action for human perception time
 */
export function validateAction(action) {
  const validActions = ['page-load', 'reading', 'interaction', 'evaluation', 'scanning', 'visual-appeal'];
  
  if (typeof action !== 'string') {
    throw new PerceptionTimeError('Action must be a string', { received: typeof action });
  }
  
  if (!validActions.includes(action)) {
    throw new PerceptionTimeError(`Invalid action: ${action}`, { 
      action,
      validActions 
    });
  }
  
  return true;
}

/**
 * Validate context for human perception time
 */
export function validatePerceptionContext(context) {
  if (context === null || typeof context !== 'object') {
    throw new PerceptionTimeError('Context must be an object', { received: typeof context });
  }
  
  if (context.attentionLevel && !['focused', 'normal', 'distracted'].includes(context.attentionLevel)) {
    throw new PerceptionTimeError(`Invalid attentionLevel: ${context.attentionLevel}`, {
      attentionLevel: context.attentionLevel,
      validLevels: ['focused', 'normal', 'distracted']
    });
  }
  
  if (context.actionComplexity && !['simple', 'normal', 'complex'].includes(context.actionComplexity)) {
    throw new PerceptionTimeError(`Invalid actionComplexity: ${context.actionComplexity}`, {
      actionComplexity: context.actionComplexity,
      validComplexities: ['simple', 'normal', 'complex']
    });
  }
  
  if (context.contentLength !== undefined && (typeof context.contentLength !== 'number' || context.contentLength < 0)) {
    throw new PerceptionTimeError('contentLength must be a non-negative number', {
      contentLength: context.contentLength
    });
  }
  
  return true;
}

/**
 * Validate sequential decision context options
 */
export function validateSequentialContextOptions(options) {
  // Allow empty object or undefined (defaults will be used)
  if (options === null || options === undefined) {
    return true;
  }
  
  // Allow empty object {} (defaults will be used)
  if (typeof options !== 'object') {
    throw new SequentialContextError('Options must be an object', { received: typeof options });
  }
  
  // Only validate if maxHistory is explicitly provided
  if (options.maxHistory !== undefined && options.maxHistory !== null) {
    if (typeof options.maxHistory !== 'number' || options.maxHistory < 1) {
      throw new SequentialContextError('maxHistory must be a positive number', {
        maxHistory: options.maxHistory
      });
    }
  }
  
  return true;
}

