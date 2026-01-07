/**
 * Type Guards and Runtime Type Validation
 * 
 * Provides type-safe runtime checks and type narrowing utilities.
 * These functions enable better static analysis and runtime safety.
 */

import { ValidationError } from './errors.mjs';

/**
 * Type guard: Check if value is a non-null object
 * 
 * @template T
 * @param {unknown} value - Value to check
 * @returns {value is Record<string, T>} True if value is a non-null object
 */
export function isObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Type guard: Check if value is a string
 * 
 * @param {unknown} value - Value to check
 * @returns {value is string} True if value is a string
 */
export function isString(value) {
  return typeof value === 'string';
}

/**
 * Type guard: Check if value is a number
 * 
 * @param {unknown} value - Value to check
 * @returns {value is number} True if value is a number
 */
export function isNumber(value) {
  return typeof value === 'number' && !isNaN(value);
}

/**
 * Type guard: Check if value is a positive integer
 * 
 * @param {unknown} value - Value to check
 * @returns {value is number} True if value is a positive integer
 */
export function isPositiveInteger(value) {
  return isNumber(value) && Number.isInteger(value) && value > 0;
}

/**
 * Type guard: Check if value is a non-empty string
 * 
 * @param {unknown} value - Value to check
 * @returns {value is string} True if value is a non-empty string
 */
export function isNonEmptyString(value) {
  return isString(value) && value.length > 0;
}

/**
 * Type guard: Check if value is an array
 * 
 * @template T
 * @param {unknown} value - Value to check
 * @returns {value is T[]} True if value is an array
 */
export function isArray(value) {
  return Array.isArray(value);
}

/**
 * Type guard: Check if value is a function
 * 
 * @param {unknown} value - Value to check
 * @returns {value is Function} True if value is a function
 */
export function isFunction(value) {
  return typeof value === 'function';
}

/**
 * Type guard: Check if value is a Promise
 * 
 * @template T
 * @param {unknown} value - Value to check
 * @returns {value is Promise<T>} True if value is a Promise
 */
export function isPromise(value) {
  return value instanceof Promise || (isObject(value) && isFunction(value.then));
}

/**
 * Type guard: Check if value is a ValidationResult
 * 
 * @param {unknown} value - Value to check
 * @returns {value is import('./index.mjs').ValidationResult} True if value is a ValidationResult
 */
export function isValidationResult(value) {
  if (!isObject(value)) return false;
  return (
    typeof value.enabled === 'boolean' &&
    typeof value.provider === 'string' &&
    (value.score === null || isNumber(value.score)) &&
    isArray(value.issues)
  );
}

/**
 * Type guard: Check if value is a ValidationContext
 * 
 * @param {unknown} value - Value to check
 * @returns {value is import('./index.mjs').ValidationContext} True if value is a ValidationContext
 */
export function isValidationContext(value) {
  if (value === null || value === undefined) return true; // Optional
  if (!isObject(value)) return false;
  
  // Check optional properties
  if (value.viewport !== undefined) {
    if (!isObject(value.viewport) || 
        !isNumber(value.viewport.width) || 
        !isNumber(value.viewport.height)) {
      return false;
    }
  }
  
  if (value.timeout !== undefined && !isNumber(value.timeout)) {
    return false;
  }
  
  if (value.useCache !== undefined && typeof value.useCache !== 'boolean') {
    return false;
  }
  
  if (value.promptBuilder !== undefined && !isFunction(value.promptBuilder)) {
    return false;
  }
  
  return true;
}

/**
 * Type guard: Check if value is a Persona
 * 
 * @param {unknown} value - Value to check
 * @returns {value is import('./index.mjs').Persona} True if value is a Persona
 */
export function isPersona(value) {
  if (!isObject(value)) return false;
  return (
    isNonEmptyString(value.name) &&
    isNonEmptyString(value.perspective) &&
    isArray(value.focus)
  );
}

/**
 * Type guard: Check if value is a TemporalNote
 * 
 * @param {unknown} value - Value to check
 * @returns {value is import('./index.mjs').TemporalNote} True if value is a TemporalNote
 */
export function isTemporalNote(value) {
  if (!isObject(value)) return false;
  
  // All properties are optional, but if present must be correct type
  if (value.timestamp !== undefined && !isNumber(value.timestamp)) return false;
  if (value.elapsed !== undefined && !isNumber(value.elapsed)) return false;
  if (value.score !== undefined && value.score !== null && !isNumber(value.score)) return false;
  if (value.observation !== undefined && !isString(value.observation)) return false;
  if (value.step !== undefined && !isString(value.step)) return false;
  
  return true;
}

/**
 * Assert that value is a non-null object, throw if not
 * 
 * @template T
 * @param {unknown} value - Value to assert
 * @param {string} [name='value'] - Name for error message
 * @returns {asserts value is Record<string, T>}
 * @throws {ValidationError} If value is not an object
 */
export function assertObject(value, name = 'value') {
  if (!isObject(value)) {
    throw new ValidationError(`${name} must be an object`, null, {
      received: typeof value
    });
  }
}

/**
 * Assert that value is a string, throw if not
 * 
 * @param {unknown} value - Value to assert
 * @param {string} [name='value'] - Name for error message
 * @returns {asserts value is string}
 * @throws {ValidationError} If value is not a string
 */
export function assertString(value, name = 'value') {
  if (!isString(value)) {
    throw new ValidationError(`${name} must be a string`, null, {
      received: typeof value
    });
  }
}

/**
 * Assert that value is a non-empty string, throw if not
 * 
 * @param {unknown} value - Value to assert
 * @param {string} [name='value'] - Name for error message
 * @returns {asserts value is string}
 * @throws {ValidationError} If value is not a non-empty string
 */
export function assertNonEmptyString(value, name = 'value') {
  assertString(value, name);
  if (value.length === 0) {
    throw new ValidationError(`${name} cannot be empty`);
  }
}

/**
 * Assert that value is a number, throw if not
 * 
 * @param {unknown} value - Value to assert
 * @param {string} [name='value'] - Name for error message
 * @returns {asserts value is number}
 * @throws {ValidationError} If value is not a number
 */
export function assertNumber(value, name = 'value') {
  if (!isNumber(value)) {
    throw new ValidationError(`${name} must be a number`, null, {
      received: typeof value
    });
  }
}

/**
 * Assert that value is an array, throw if not
 * 
 * @template T
 * @param {unknown} value - Value to assert
 * @param {string} [name='value'] - Name for error message
 * @returns {asserts value is T[]}
 * @throws {ValidationError} If value is not an array
 */
export function assertArray(value, name = 'value') {
  if (!isArray(value)) {
    throw new ValidationError(`${name} must be an array`, null, {
      received: typeof value
    });
  }
}

/**
 * Assert that value is a function, throw if not
 * 
 * @param {unknown} value - Value to assert
 * @param {string} [name='value'] - Name for error message
 * @returns {asserts value is Function}
 * @throws {ValidationError} If value is not a function
 */
export function assertFunction(value, name = 'value') {
  if (!isFunction(value)) {
    throw new ValidationError(`${name} must be a function`, null, {
      received: typeof value
    });
  }
}

/**
 * Narrow type to specific keys of an object
 * 
 * @template T
 * @template K
 * @param {T} obj - Object to narrow
 * @param {K[]} keys - Keys to pick
 * @returns {Pick<T, K>} Object with only specified keys
 */
export function pick(obj, keys) {
  assertObject(obj, 'obj');
  assertArray(keys, 'keys');
  
  const result = {};
  for (const key of keys) {
    if (key in obj) {
      result[key] = obj[key];
    }
  }
  return result;
}

/**
 * Type-safe property access with default
 * 
 * @template T
 * @template D
 * @param {T} obj - Object to access
 * @param {string} key - Property key
 * @param {D} defaultValue - Default value if property doesn't exist
 * @returns {T[keyof T] | D} Property value or default
 */
export function getProperty(obj, key, defaultValue) {
  assertObject(obj, 'obj');
  assertString(key, 'key');
  return key in obj && obj[key] !== undefined ? obj[key] : defaultValue;
}

