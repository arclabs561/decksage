/**
 * Configuration for Natural Language Specs
 * 
 * Makes spec parsing, execution, and error analysis configurable per project/test.
 * Follows the library's config pattern (like createConfig in config.mjs).
 */

import { getConfig } from './config.mjs';
import { log } from './logger.mjs';

/**
 * Default spec configuration
 */
const DEFAULT_SPEC_CONFIG = {
  // Context extraction
  useLLM: true,
  fallback: 'regex',
  provider: null, // Auto-detect from config
  
  // Spec validation
  validateBeforeExecute: true,
  strictValidation: false, // If true, throw on validation errors
  
  // Error analysis
  enableErrorAnalysis: true,
  errorAnalysisOptions: {
    saveReport: true,
    outputPath: null
  },
  
  // Template system
  templateDir: null, // Custom template directory
  autoLoadTemplates: true,
  
  // Execution
  timeout: 30000,
  retryOnFailure: false,
  maxRetries: 3
};

/**
 * Create spec configuration
 * 
 * Merges with global config and environment variables.
 * 
 * @param {Object} [options={}] - Configuration options
 * @returns {Object} Spec configuration
 */
export function createSpecConfig(options = {}) {
  const globalConfig = getConfig();
  
  // Merge with defaults
  const config = {
    ...DEFAULT_SPEC_CONFIG,
    ...options
  };
  
  // Auto-detect provider from global config if not specified
  if (!config.provider && globalConfig.provider) {
    config.provider = globalConfig.provider;
  }
  
  // Respect environment variables
  if (process.env.SPEC_USE_LLM !== undefined) {
    config.useLLM = process.env.SPEC_USE_LLM === 'true';
  }
  if (process.env.SPEC_VALIDATE_BEFORE_EXECUTE !== undefined) {
    config.validateBeforeExecute = process.env.SPEC_VALIDATE_BEFORE_EXECUTE === 'true';
  }
  if (process.env.SPEC_STRICT_VALIDATION !== undefined) {
    config.strictValidation = process.env.SPEC_STRICT_VALIDATION === 'true';
  }
  if (process.env.SPEC_TEMPLATE_DIR) {
    config.templateDir = process.env.SPEC_TEMPLATE_DIR;
  }
  
  return config;
}

/**
 * Get current spec configuration (singleton)
 */
let specConfigInstance = null;

export function getSpecConfig() {
  if (!specConfigInstance) {
    specConfigInstance = createSpecConfig();
  }
  return specConfigInstance;
}

/**
 * Set spec configuration (useful for testing)
 */
export function setSpecConfig(config) {
  specConfigInstance = config;
  log('[SpecConfig] Configuration updated');
}

/**
 * Reset spec configuration to defaults
 */
export function resetSpecConfig() {
  specConfigInstance = null;
}

