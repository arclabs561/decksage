/**
 * Simple logger utility
 * 
 * Provides conditional logging that respects debug mode.
 * In production, warnings are silent unless explicitly enabled.
 */

let DEBUG_ENABLED = false;

/**
 * Enable debug logging
 */
export function enableDebug() {
  DEBUG_ENABLED = true;
}

/**
 * Disable debug logging
 */
export function disableDebug() {
  DEBUG_ENABLED = false;
}

/**
 * Check if debug is enabled
 */
export function isDebugEnabled() {
  return DEBUG_ENABLED;
}

/**
 * Log a warning (only if debug enabled)
 */
export function warn(...args) {
  if (DEBUG_ENABLED) {
    console.warn(...args);
  }
}

/**
 * Log info (only if debug enabled)
 */
export function log(...args) {
  if (DEBUG_ENABLED) {
    console.log(...args);
  }
}

/**
 * Log error (always logged)
 */
export function error(...args) {
  console.error(...args);
}

