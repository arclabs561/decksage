/**
 * Configuration System
 *
 * Handles provider selection, API keys, and settings.
 * Designed to be flexible and extensible.
 */

import { ConfigError } from './errors.mjs';
import { loadEnv } from './load-env.mjs';
import { API_CONSTANTS } from './constants.mjs';

// Load .env file automatically on module load
loadEnv();

/**
 * Model tiers for each provider
 * Updated January 2025: Latest models - Gemini 2.5 Pro, GPT-5, Claude 4.5 Sonnet
 * 
 * GROQ INTEGRATION (2025):
 * - Groq added for high-frequency decisions (10-60Hz temporal decisions)
 * - ~0.22s latency (vs 1-3s for other providers)
 * - 185-276 tokens/sec throughput
 * - OpenAI-compatible API
 * - Cost-competitive, free tier available
 * - Best for: Fast tier decisions, high-Hz temporal decisions, real-time applications
 */
const MODEL_TIERS = {
  gemini: {
    fast: 'gemini-2.0-flash-exp',      // Fast, outperforms 1.5 Pro (2x speed)
    balanced: 'gemini-2.5-pro',        // Best balance (2025 leader, released June 2025)
    best: 'gemini-2.5-pro'              // Best quality (top vision-language model, 1M+ context)
  },
  openai: {
    fast: 'gpt-4o-mini',               // Fast, cheaper
    balanced: 'gpt-5',                 // Best balance (released August 2025, unified reasoning)
    best: 'gpt-5'                      // Best quality (state-of-the-art multimodal, August 2025)
  },
  claude: {
    fast: 'claude-3-5-haiku-20241022', // Fast, cheaper
    balanced: 'claude-sonnet-4-5',     // Best balance (released September 2025, enhanced vision)
    best: 'claude-sonnet-4-5'          // Best quality (latest flagship, September 2025)
  },
  groq: {
    // NOTE: Groq vision support requires different model
    // For vision: meta-llama/llama-4-scout-17b-16e-instruct (preview, supports vision)
    // For text-only: llama-3.3-70b-versatile is fastest (~0.22s latency)
    fast: 'meta-llama/llama-4-scout-17b-16e-instruct',   // Vision-capable, fastest Groq option
    balanced: 'meta-llama/llama-4-scout-17b-16e-instruct', // Vision-capable, balanced
    best: 'meta-llama/llama-4-scout-17b-16e-instruct'   // Vision-capable, best quality (preview)
    // WARNING: Groq vision models are preview-only. Text-only: use llama-3.3-70b-versatile
  }
};

/**
 * Default provider configurations
 * 
 * GROQ INTEGRATION:
 * - OpenAI-compatible API (easy migration)
 * - ~0.22s latency (10x faster than typical providers)
 * - Best for high-frequency decisions (10-60Hz temporal decisions)
 * - Free tier available for testing
 */
const PROVIDER_CONFIGS = {
  gemini: {
    name: 'gemini',
    apiUrl: 'https://generativelanguage.googleapis.com/v1beta',
    model: 'gemini-2.5-pro',            // Latest: Released June 2025, top vision-language model, 1M+ context
    freeTier: true,
    pricing: { input: 1.25, output: 5.00 }, // Updated pricing for 2.5 Pro
    priority: 1 // Higher priority = preferred
  },
  openai: {
    name: 'openai',
    apiUrl: 'https://api.openai.com/v1',
    model: 'gpt-5',                     // Latest: Released August 2025, state-of-the-art multimodal
    freeTier: false,
    pricing: { input: 5.00, output: 15.00 }, // Updated pricing for gpt-5
    priority: 2
  },
  claude: {
    name: 'claude',
    apiUrl: 'https://api.anthropic.com/v1',
    model: 'claude-sonnet-4-5',         // Latest: Released September 2025, enhanced vision capabilities
    freeTier: false,
    pricing: { input: 3.00, output: 15.00 }, // Updated pricing for 4.5
    priority: 3
  },
  groq: {
    name: 'groq',
    apiUrl: 'https://api.groq.com/openai/v1', // OpenAI-compatible endpoint
    model: 'meta-llama/llama-4-scout-17b-16e-instruct',   // Vision-capable (preview), ~0.22s latency
    freeTier: true,                      // Free tier available
    pricing: { input: 0.59, output: 0.79 }, // Actual 2025 pricing: $0.59/$0.79 per 1M tokens (real-time API)
    priority: 0,                         // Highest priority for high-frequency decisions
    latency: 220,                        // ~0.22s latency in ms (10x faster than typical)
    throughput: 200,                     // ~200 tokens/sec average
    visionSupported: true               // llama-4-scout-17b-16e-instruct supports vision (preview)
    // Text-only alternative: llama-3.3-70b-versatile (faster, no vision)
  }
};

/**
 * Create configuration from environment or options
 *
 * @param {import('./index.mjs').ConfigOptions} [options={}] - Configuration options
 * @returns {import('./index.mjs').Config} Configuration object
 */
export function createConfig(options = {}) {
  const {
    provider = null,
    apiKey = null,
    env = process.env,
    cacheDir = null,
    cacheEnabled = true,
    maxConcurrency = API_CONSTANTS.DEFAULT_MAX_CONCURRENCY,
    timeout = API_CONSTANTS.DEFAULT_TIMEOUT_MS,
    verbose = false,
    modelTier = null, // 'fast', 'balanced', 'best', or null for default
    model = null      // Explicit model override
  } = options;

  // Auto-detect provider if not specified
  let selectedProvider = provider;
  if (!selectedProvider) {
    selectedProvider = detectProvider(env);
  }

  // Get API key - respect explicit null/undefined (don't check env if null/undefined is explicitly passed)
  // Check if apiKey was explicitly provided in options (vs defaulting to null)
  const apiKeyExplicitlyProvided = 'apiKey' in options;
  let selectedApiKey;
  if (apiKeyExplicitlyProvided && (apiKey === null || apiKey === undefined)) {
    // Explicitly null/undefined - don't check env, use null
    selectedApiKey = null;
  } else {
    // apiKey not provided or has a value - use it if provided, otherwise check env
    selectedApiKey = apiKey || getApiKey(selectedProvider, env);
  }

  // Get provider config
  let providerConfig = { ...PROVIDER_CONFIGS[selectedProvider] || PROVIDER_CONFIGS.gemini };

  // Override model if specified
  if (model) {
    providerConfig.model = model;
  } else if (modelTier && MODEL_TIERS[selectedProvider] && MODEL_TIERS[selectedProvider][modelTier]) {
    // Use tier-based model selection
    providerConfig.model = MODEL_TIERS[selectedProvider][modelTier];
  } else if (env.VLM_MODEL_TIER && MODEL_TIERS[selectedProvider] && MODEL_TIERS[selectedProvider][env.VLM_MODEL_TIER]) {
    // Check environment variable for model tier
    providerConfig.model = MODEL_TIERS[selectedProvider][env.VLM_MODEL_TIER];
  } else if (env.VLM_MODEL) {
    // Explicit model override from environment
    providerConfig.model = env.VLM_MODEL;
  }

  return {
    provider: selectedProvider,
    apiKey: selectedApiKey,
    providerConfig,
    enabled: !!selectedApiKey,
    cache: {
      enabled: cacheEnabled,
      dir: cacheDir
    },
    performance: {
      maxConcurrency,
      timeout
    },
    debug: {
      verbose
    }
  };
}

/**
 * Detect provider from environment variables
 */
function detectProvider(env) {
  // Priority: explicit VLM_PROVIDER > auto-detect from API keys > default to gemini
  const explicitProvider = env.VLM_PROVIDER?.trim().toLowerCase();
  if (explicitProvider && PROVIDER_CONFIGS[explicitProvider]) {
    return explicitProvider;
  }

  // Auto-detect: prefer cheaper/faster providers first
  // Groq has priority 0 (highest) for high-frequency decisions
  const availableProviders = Object.values(PROVIDER_CONFIGS)
    .filter(config => {
      // Check provider-specific key
      const providerKey = env[`${config.name.toUpperCase()}_API_KEY`];
      if (providerKey) {
        return true;
      }
      // Special case: Anthropic uses ANTHROPIC_API_KEY
      if (config.name === 'claude' && env.ANTHROPIC_API_KEY) {
        return true;
      }
      // Fallback to generic API_KEY
      return !!env.API_KEY;
    })
    .sort((a, b) => a.priority - b.priority); // Lower priority number = higher priority

  return availableProviders.length > 0
    ? availableProviders[0].name
    : 'gemini'; // Default to gemini (cheapest)
}

/**
 * Get API key for provider
 */
function getApiKey(provider, env) {
  // Check provider-specific key first
  const providerKey = env[`${provider.toUpperCase()}_API_KEY`];
  if (providerKey) {
    return providerKey;
  }

  // Special case: Anthropic uses ANTHROPIC_API_KEY (not CLAUDE_API_KEY)
  if (provider === 'claude' && env.ANTHROPIC_API_KEY) {
    return env.ANTHROPIC_API_KEY;
  }

  // Special case: Groq uses GROQ_API_KEY
  if (provider === 'groq' && env.GROQ_API_KEY) {
    return env.GROQ_API_KEY;
  }

  // Fallback to generic API_KEY
  return env.API_KEY || null;
}

/**
 * Get current configuration (singleton)
 *
 * @returns {import('./index.mjs').Config} Current configuration
 */
let configInstance = null;

export function getConfig() {
  if (!configInstance) {
    configInstance = createConfig();
  }
  return configInstance;
}

/**
 * Set configuration (useful for testing)
 *
 * @param {import('./index.mjs').Config} config - Configuration to set
 * @returns {void}
 */
export function setConfig(config) {
  configInstance = config;
}

/**
 * Get provider configuration
 *
 * @param {string | null} [providerName=null] - Provider name, or null to use default
 * @returns {import('./index.mjs').Config['providerConfig']} Provider configuration
 */
export function getProvider(providerName = null) {
  const config = getConfig();
  const provider = providerName || config.provider;
  return PROVIDER_CONFIGS[provider] || PROVIDER_CONFIGS.gemini;
}

