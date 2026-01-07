/**
 * Global Error Handler
 * 
 * Handles unhandled promise rejections and uncaught exceptions.
 * Prevents silent failures and improves debugging.
 */

import { error } from './logger.mjs';

/**
 * Initialize global error handlers
 * 
 * **Opt-in**: This function is exported but not automatically called.
 * Users must explicitly call `initErrorHandlers()` if they want global
 * error handling for unhandled rejections and uncaught exceptions.
 * 
 * Should be called early in application startup.
 * Only call once per process.
 * 
 * @example
 * ```javascript
 * import { initErrorHandlers } from 'ai-visual-test';
 * initErrorHandlers(); // Opt-in to global error handling
 * ```
 */
export function initErrorHandlers() {
  // Handle unhandled promise rejections
  process.on('unhandledRejection', (reason, promise) => {
    error('[Unhandled Rejection]', {
      reason: reason instanceof Error ? {
        message: reason.message,
        stack: reason.stack,
        name: reason.name
      } : reason,
      promise: promise?.toString?.() || 'Unknown promise'
    });
    
    // In production, you might want to:
    // - Log to monitoring service (Sentry, DataDog, etc.)
    // - Send alerts
    // - Gracefully shutdown
  });
  
  // Handle uncaught exceptions
  process.on('uncaughtException', (err) => {
    error('[Uncaught Exception]', {
      message: err.message,
      stack: err.stack,
      name: err.name
    });
    
    // NOTE: Libraries should not call process.exit()
    // Let the application decide how to handle uncaught exceptions.
    // Users can add their own process.exit(1) if needed, or use a process manager
    // that handles restarts automatically.
  });
  
  // Handle warnings
  process.on('warning', (warning) => {
    error('[Process Warning]', {
      name: warning.name,
      message: warning.message,
      stack: warning.stack
    });
  });
}

