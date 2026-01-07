/**
 * Custom Error Classes for ai-visual-test
 * 
 * Provides standardized error handling across the package.
 * Based on Playwright's error handling patterns and industry best practices.
 * 
 * All errors extend AIBrowserTestError for consistent error handling and serialization.
 */

/**
 * Base error class for all ai-visual-test errors
 * 
 * @class AIBrowserTestError
 * @extends {Error}
 */
export class AIBrowserTestError extends Error {
  /**
   * @param {string} message - Error message
   * @param {string} code - Error code
   * @param {Record<string, unknown>} [details={}] - Additional error details
   */
  constructor(message, code, details = {}) {
    super(message);
    this.name = this.constructor.name;
    this.code = code;
    this.details = details;
    
    // Maintains proper stack trace for where error was thrown (V8 only)
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, this.constructor);
    }
  }

  /**
   * Convert error to JSON for serialization
   * 
   * @returns {import('./index.mjs').AIBrowserTestError['toJSON']} JSON representation
   */
  toJSON() {
    return {
      name: this.name,
      code: this.code,
      message: this.message,
      details: this.details,
      stack: this.stack
    };
  }
}

/**
 * Validation error - thrown when validation fails
 * 
 * @class ValidationError
 * @extends {AIBrowserTestError}
 */
export class ValidationError extends AIBrowserTestError {
  /**
   * @param {string} message - Error message
   * @param {Record<string, unknown>} [details={}] - Additional error details
   */
  constructor(message, details = {}) {
    super(message, 'VALIDATION_ERROR', details);
  }
}

/**
 * Cache error - thrown when cache operations fail
 */
export class CacheError extends AIBrowserTestError {
  constructor(message, details = {}) {
    super(message, 'CACHE_ERROR', details);
  }
}

/**
 * Config error - thrown when configuration is invalid
 */
export class ConfigError extends AIBrowserTestError {
  constructor(message, details = {}) {
    super(message, 'CONFIG_ERROR', details);
  }
}

/**
 * Provider error - thrown when VLLM provider operations fail
 */
export class ProviderError extends AIBrowserTestError {
  constructor(message, provider, details = {}) {
    super(message, 'PROVIDER_ERROR', { provider, ...details });
    this.provider = provider;
  }
}

/**
 * Timeout error - thrown when operations timeout
 */
export class TimeoutError extends AIBrowserTestError {
  constructor(message, timeout, details = {}) {
    super(message, 'TIMEOUT_ERROR', { timeout, ...details });
    this.timeout = timeout;
  }
}

/**
 * File error - thrown when file operations fail
 */
export class FileError extends AIBrowserTestError {
  constructor(message, filePath, details = {}) {
    super(message, 'FILE_ERROR', { filePath, ...details });
    this.filePath = filePath;
  }
}

/**
 * State mismatch error - thrown when state validation fails
 * 
 * @class StateMismatchError
 * @extends {ValidationError}
 */
export class StateMismatchError extends ValidationError {
  /**
   * @param {string[]} discrepancies - List of discrepancies found
   * @param {unknown} extracted - Extracted state
   * @param {unknown} expected - Expected state
   * @param {string} [message] - Custom error message
   */
  constructor(discrepancies, extracted, expected, message) {
    const defaultMessage = `State mismatch: ${discrepancies.length} discrepancy(ies) found`;
    super(
      message || defaultMessage,
      {
        discrepancies,
        extracted,
        expected,
        discrepancyCount: discrepancies.length
      }
    );
    this.discrepancies = discrepancies;
    this.extracted = extracted;
    this.expected = expected;
  }
}

/**
 * Check if error is an instance of AIBrowserTestError
 * 
 * @param {unknown} error - Error to check
 * @returns {error is AIBrowserTestError} True if error is an AIBrowserTestError
 */
export function isAIBrowserTestError(error) {
  return error instanceof AIBrowserTestError;
}

/**
 * Check if error is a specific error type
 * 
 * @template {new (...args: any[]) => AIBrowserTestError} T
 * @param {unknown} error - Error to check
 * @param {T} errorClass - Error class constructor
 * @returns {error is InstanceType<T>} True if error is instance of errorClass
 */
export function isErrorType(error, errorClass) {
  return error instanceof errorClass;
}



