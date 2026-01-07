/**
 * Input Validation Utilities
 * 
 * Provides validation functions for common input types to prevent
 * security vulnerabilities and improve error messages.
 */

import { ValidationError } from './errors.mjs';
import { existsSync } from 'fs';
import { normalize, resolve } from 'path';

/**
 * Validate image file path
 * 
 * @param {string} imagePath - Path to image file
 * @returns {true} Always returns true if valid
 * @throws {ValidationError} If path is invalid, empty, or contains path traversal
 */
export function validateImagePath(imagePath) {
  if (typeof imagePath !== 'string') {
    throw new ValidationError('Image path must be a string', null, {
      received: typeof imagePath
    });
  }
  
  if (imagePath.length === 0) {
    throw new ValidationError('Image path cannot be empty');
  }
  
  // Check for path traversal attempts
  const normalized = normalize(imagePath);
  if (normalized.includes('..')) {
    throw new ValidationError('Invalid image path: path traversal detected', imagePath);
  }
  
  // Validate file extension
  const validExtensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp'];
  const hasValidExtension = validExtensions.some(ext => 
    imagePath.toLowerCase().endsWith(ext)
  );
  
  if (!hasValidExtension) {
    throw new ValidationError('Invalid image format. Supported: png, jpg, jpeg, gif, webp', imagePath);
  }
  
  // Check if file exists (optional - may not exist in all contexts)
  // This is a soft check - don't throw if file doesn't exist yet
  // The actual file operations will handle missing files
  
  return true;
}

/**
 * Validate prompt string
 * 
 * @param {string} prompt - Prompt text to validate
 * @param {number} [maxLength=10000] - Maximum allowed length
 * @returns {true} Always returns true if valid
 * @throws {ValidationError} If prompt is invalid, empty, or too long
 */
export function validatePrompt(prompt, maxLength = 10000) {
  if (typeof prompt !== 'string') {
    throw new ValidationError('Prompt must be a string', null, {
      received: typeof prompt
    });
  }
  
  if (prompt.length === 0) {
    throw new ValidationError('Prompt cannot be empty');
  }
  
  if (prompt.length > maxLength) {
    throw new ValidationError(`Prompt too long (max ${maxLength} characters)`, null, {
      length: prompt.length,
      maxLength
    });
  }
  
  return true;
}

/**
 * Validate context object
 * 
 * @param {unknown} context - Context object to validate (can be null/undefined)
 * @param {number} [maxSize=50000] - Maximum serialized size in bytes
 * @returns {true} Always returns true if valid
 * @throws {ValidationError} If context is invalid type, too large, or non-serializable
 */
export function validateContext(context, maxSize = 50000) {
  if (context === null || context === undefined) {
    return true; // Context is optional
  }
  
  if (typeof context !== 'object' || Array.isArray(context)) {
    throw new ValidationError('Context must be an object', null, {
      received: Array.isArray(context) ? 'array' : typeof context
    });
  }
  
  // Check size by stringifying
  try {
    const contextString = JSON.stringify(context);
    if (contextString.length > maxSize) {
      throw new ValidationError(`Context too large (max ${maxSize} bytes)`, null, {
        size: contextString.length,
        maxSize
      });
    }
  } catch (error) {
    if (error instanceof ValidationError) {
      throw error;
    }
    throw new ValidationError('Context contains non-serializable data', null, {
      originalError: error.message
    });
  }
  
  return true;
}

/**
 * Validate timeout value
 * 
 * @param {number} timeout - Timeout value in milliseconds
 * @param {number} [min=1000] - Minimum allowed timeout
 * @param {number} [max=300000] - Maximum allowed timeout
 * @returns {true} Always returns true if valid
 * @throws {ValidationError} If timeout is invalid, too short, or too long
 */
export function validateTimeout(timeout, min = 1000, max = 300000) {
  if (typeof timeout !== 'number') {
    throw new ValidationError('Timeout must be a number', null, {
      received: typeof timeout
    });
  }
  
  if (timeout < min) {
    throw new ValidationError(`Timeout too short (min ${min}ms)`, null, {
      timeout,
      min
    });
  }
  
  if (timeout > max) {
    throw new ValidationError(`Timeout too long (max ${max}ms)`, null, {
      timeout,
      max
    });
  }
  
  return true;
}

/**
 * Validate schema object for data extraction
 * 
 * @param {unknown} schema - Schema object to validate
 * @returns {true} Always returns true if valid
 * @throws {ValidationError} If schema is invalid or has invalid field types
 */
export function validateSchema(schema) {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) {
    throw new ValidationError('Schema must be a non-empty object', null, {
      received: Array.isArray(schema) ? 'array' : typeof schema
    });
  }
  
  const validTypes = ['string', 'number', 'boolean', 'object', 'array'];
  
  for (const [key, field] of Object.entries(schema)) {
    if (typeof field !== 'object' || Array.isArray(field)) {
      throw new ValidationError(`Schema field "${key}" must be an object`, null, {
        field
      });
    }
    
    if (!field.type || !validTypes.includes(field.type)) {
      throw new ValidationError(`Schema field "${key}" has invalid type`, null, {
        type: field.type,
        validTypes
      });
    }
  }
  
  return true;
}

/**
 * Validate file path (general purpose)
 * 
 * @param {string} filePath - File path to validate
 * @param {{
   *   mustExist?: boolean;
   *   allowedExtensions?: string[] | null;
   *   maxLength?: number;
   * }} [options={}] - Validation options
 * @returns {true} Always returns true if valid
 * @throws {ValidationError} If path is invalid, empty, too long, has path traversal, wrong extension, or doesn't exist (if required)
 */
export function validateFilePath(filePath, options = {}) {
  const {
    mustExist = false,
    allowedExtensions = null,
    maxLength = 4096
  } = options;
  
  if (typeof filePath !== 'string') {
    throw new ValidationError('File path must be a string', null, {
      received: typeof filePath
    });
  }
  
  if (filePath.length === 0) {
    throw new ValidationError('File path cannot be empty');
  }
  
  if (filePath.length > maxLength) {
    throw new ValidationError(`File path too long (max ${maxLength} characters)`, filePath);
  }
  
  // Check for path traversal
  const normalized = normalize(filePath);
  if (normalized.includes('..')) {
    throw new ValidationError('Invalid file path: path traversal detected', filePath);
  }
  
  // Check extension if specified
  if (allowedExtensions) {
    const ext = normalized.substring(normalized.lastIndexOf('.'));
    if (!allowedExtensions.includes(ext.toLowerCase())) {
      throw new ValidationError(`Invalid file extension. Allowed: ${allowedExtensions.join(', ')}`, filePath);
    }
  }
  
  // Check existence if required
  if (mustExist && !existsSync(filePath)) {
    throw new ValidationError('File does not exist', filePath);
  }
  
  return true;
}

