/**
 * Retry Logic with Exponential Backoff
 * 
 * Provides retry mechanisms for API calls with exponential backoff,
 * configurable retry counts, and error classification.
 */

import { ProviderError, TimeoutError } from './errors.mjs';
import { log, warn } from './logger.mjs';

/**
 * Check if an error is retryable
 * 
 * @param {Error} error - Error to check
 * @returns {boolean} True if error is retryable
 */
export function isRetryableError(error) {
  // Network errors (timeouts, connection issues)
  if (error instanceof TimeoutError) return true;
  if (error.name === 'AbortError' || error.name === 'NetworkError') return true;
  if (error.message?.includes('timeout') || error.message?.includes('network')) return true;
  
  // Rate limiting (429)
  if (error instanceof ProviderError && error.details?.statusCode === 429) return true;
  if (error.message?.includes('rate limit') || error.message?.includes('429')) return true;
  
  // Server errors (5xx)
  if (error instanceof ProviderError) {
    const status = error.details?.statusCode;
    if (status >= 500 && status < 600) return true;
  }
  
  // Transient API errors
  if (error.message?.includes('temporarily unavailable') || 
      error.message?.includes('service unavailable') ||
      error.message?.includes('internal server error')) {
    return true;
  }
  
  // Not retryable: authentication errors, validation errors, etc.
  return false;
}

/**
 * Calculate exponential backoff delay
 * 
 * @param {number} attempt - Current attempt number (0-indexed)
 * @param {number} baseDelay - Base delay in milliseconds
 * @param {number} maxDelay - Maximum delay in milliseconds
 * @param {boolean} jitter - Add random jitter to prevent thundering herd
 * @returns {number} Delay in milliseconds
 */
export function calculateBackoff(attempt, baseDelay = 1000, maxDelay = 30000, jitter = true) {
  const exponentialDelay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay);
  
  if (jitter) {
    // Add ±25% random jitter
    const jitterAmount = exponentialDelay * 0.25;
    const jitterValue = (Math.random() * 2 - 1) * jitterAmount;
    return Math.max(0, exponentialDelay + jitterValue);
  }
  
  return exponentialDelay;
}

/**
 * Retry a function with exponential backoff
 * 
 * @template T
 * @param {() => Promise<T>} fn - Function to retry
 * @param {{
 *   maxRetries?: number;
 *   baseDelay?: number;
 *   maxDelay?: number;
 *   onRetry?: (error: Error, attempt: number, delay: number) => void;
 *   retryable?: (error: Error) => boolean;
 * }} [options={}] - Retry options
 * @returns {Promise<T>} Result of function
 * @throws {Error} Last error if all retries fail
 */
export async function retryWithBackoff(fn, options = {}) {
  const {
    maxRetries = 3,
    baseDelay = 1000,
    maxDelay = 30000,
    onRetry = null,
    retryable = isRetryableError
  } = options;
  
  let lastError;
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      
      // Don't retry if error is not retryable
      if (!retryable(error)) {
        throw error;
      }
      
      // Don't retry on last attempt
      if (attempt >= maxRetries) {
        break;
      }
      
      const delay = calculateBackoff(attempt, baseDelay, maxDelay);
      
      if (onRetry) {
        onRetry(error, attempt + 1, delay);
      } else {
        warn(`[Retry] Attempt ${attempt + 1}/${maxRetries} failed: ${error.message}. Retrying in ${delay}ms...`);
      }
      
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  
  // All retries exhausted
  throw lastError;
}

/**
 * Enhanced error message with retry context
 * 
 * @param {Error} error - Original error
 * @param {number} attempts - Number of attempts made
 * @param {string} operation - Operation that failed
 * @returns {string} Enhanced error message
 */
export function enhanceErrorMessage(error, attempts, operation) {
  const baseMessage = error.message || 'Unknown error';
  const context = [];
  
  context.push(`Operation: ${operation}`);
  context.push(`Attempts: ${attempts}`);
  
  if (error instanceof ProviderError) {
    context.push(`Provider: ${error.provider}`);
    if (error.details?.statusCode) {
      context.push(`HTTP Status: ${error.details.statusCode}`);
    }
  }
  
  if (error instanceof TimeoutError) {
    context.push(`Timeout: ${error.timeout}ms`);
  }
  
  return `${baseMessage} (${context.join(', ')})`;
}

