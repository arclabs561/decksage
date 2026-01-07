/**
 * Environment Variable Loader
 * 
 * Loads environment variables from .env file if it exists.
 * Works in both local development and deployed environments.
 */

import { readFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { warn } from './logger.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// SECURITY: Whitelist allowed environment variable keys to prevent injection
// Only allow keys that are actually used by this application
const ALLOWED_ENV_KEYS = [
  'GEMINI_API_KEY',
  'OPENAI_API_KEY',
  'ANTHROPIC_API_KEY',
  'GROQ_API_KEY',  // Added for Groq integration (high-frequency decisions)
  'API_KEY',
  'VLLM_API_KEY',
  'VLM_PROVIDER',
  'VLM_MODEL',
  'VLM_MODEL_TIER',
  'RATE_LIMIT_MAX_REQUESTS',
  'REQUIRE_AUTH'
];

// Valid values for VLM_PROVIDER
// Groq added for high-frequency decisions (10-60Hz temporal decisions)
const VALID_PROVIDERS = ['gemini', 'openai', 'claude', 'groq'];

// Validation functions for environment variables
function validateRateLimitMaxRequests(value) {
  const num = parseInt(value, 10);
  if (isNaN(num) || num < 1 || num > 1000) {
    warn(`[LoadEnv] Invalid RATE_LIMIT_MAX_REQUESTS: ${value}. Must be between 1 and 1000. Using default.`);
    return null; // Will use default
  }
  return num;
}

function validateVLMProvider(value) {
  const normalized = value?.toLowerCase().trim();
  if (normalized && !VALID_PROVIDERS.includes(normalized)) {
    warn(`[LoadEnv] Invalid VLM_PROVIDER: ${value}. Must be one of: ${VALID_PROVIDERS.join(', ')}. Ignoring.`);
    return null; // Ignore invalid provider
  }
  return normalized;
}

function validateRequireAuth(value) {
  if (value === 'true' || value === '1' || value === 'yes') {
    return true;
  }
  if (value === 'false' || value === '0' || value === 'no' || value === '') {
    return false;
  }
  warn(`[LoadEnv] Invalid REQUIRE_AUTH: ${value}. Must be 'true' or 'false'. Using default.`);
  return null; // Will use default
}

/**
 * Load environment variables from .env file
 * 
 * @param {string | null} [basePath=null] - Base path to search for .env file (optional)
 * @returns {boolean} True if .env file was found and loaded
 */
export function loadEnv(basePath = null) {
  // Try multiple locations for .env file
  const possiblePaths = basePath 
    ? [
        join(basePath, '.env'),
        join(basePath, '..', '.env'),
        join(basePath, '../..', '.env')
      ]
    : [
        join(process.cwd(), '.env'),
        join(__dirname, '..', '.env'),
        join(__dirname, '../../..', '.env'),
        join(__dirname, '../../../..', '.env')
      ];

  for (const envPath of possiblePaths) {
    if (existsSync(envPath)) {
      try {
        const envContent = readFileSync(envPath, 'utf8');
        const lines = envContent.split('\n');
        
        for (const line of lines) {
          const trimmed = line.trim();
          
          // Skip comments and empty lines
          if (!trimmed || trimmed.startsWith('#')) {
            continue;
          }
          
          // Parse KEY=VALUE format
          const match = trimmed.match(/^([^=]+)=(.*)$/);
          if (match) {
            const key = match[1].trim();
            let value = match[2].trim();
            
            // SECURITY: Only allow whitelisted environment variable keys
            // Prevents malicious .env files from setting arbitrary variables
            if (!ALLOWED_ENV_KEYS.includes(key)) {
              warn(`[LoadEnv] Ignoring unknown environment variable key: ${key}`);
              continue;
            }
            
            // Remove quotes if present
            if ((value.startsWith('"') && value.endsWith('"')) ||
                (value.startsWith("'") && value.endsWith("'"))) {
              value = value.slice(1, -1);
            }
            
            // Validate and transform values based on key
            let validatedValue = value;
            if (key === 'RATE_LIMIT_MAX_REQUESTS') {
              const validated = validateRateLimitMaxRequests(value);
              if (validated === null) {
                continue; // Skip invalid value
              }
              validatedValue = String(validated);
            } else if (key === 'VLM_PROVIDER') {
              const validated = validateVLMProvider(value);
              if (validated === null) {
                continue; // Skip invalid value
              }
              validatedValue = validated;
            } else if (key === 'REQUIRE_AUTH') {
              const validated = validateRequireAuth(value);
              if (validated === null) {
                continue; // Skip invalid value
              }
              validatedValue = String(validated);
            }
            
            // Only set if not already set (env vars take precedence)
            if (!process.env[key]) {
              process.env[key] = validatedValue;
            }
          }
        }
        
        return true;
      } catch (err) {
        // Silently fail - .env is optional
        return false;
      }
    }
  }
  
  return false;
}

