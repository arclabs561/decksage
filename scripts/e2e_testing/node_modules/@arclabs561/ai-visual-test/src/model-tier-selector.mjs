/**
 * Model Tier Selector
 * 
 * Automatically selects the best model tier based on context (frequency, criticality, cost).
 * Similar pattern to smart-validator.mjs which auto-selects validator types.
 * 
 * Design Philosophy:
 * - High-frequency decisions (10-60Hz) → use 'fast' tier
 * - Critical evaluations → use 'best' tier
 * - Cost-sensitive → use 'fast' tier
 * - Standard validations → use 'balanced' tier (default)
 * 
 * This prevents the common mistake of using expensive models for high-frequency decisions.
 */

import { log, warn } from './logger.mjs';

/**
 * Select model tier based on context
 * 
 * @param {Object} context - Validation context
 * @param {string|number} [context.frequency] - Decision frequency ('high'|'medium'|'low' or Hz number)
 * @param {string} [context.criticality] - Criticality level ('critical'|'high'|'medium'|'low')
 * @param {boolean} [context.costSensitive] - Cost-sensitive operation
 * @param {boolean} [context.qualityRequired] - High quality required
 * @param {string} [context.testType] - Test type (may indicate criticality)
 * @param {Object} [context.temporalNotes] - Temporal notes (for frequency detection)
 * @returns {string} Model tier ('fast'|'balanced'|'best')
 */
export function selectModelTier(context = {}) {
  const {
    frequency,
    criticality,
    costSensitive,
    qualityRequired,
    testType,
    temporalNotes
  } = context;

  // Detect frequency from temporal notes if available
  let detectedFrequency = frequency;
  if (!detectedFrequency && temporalNotes && Array.isArray(temporalNotes) && temporalNotes.length > 1) {
    const recentNotes = temporalNotes.slice(-10);
    if (recentNotes.length >= 2) {
      const timeSpan = recentNotes[recentNotes.length - 1].timestamp - recentNotes[0].timestamp;
      if (timeSpan > 0) {
        const notesPerSecond = recentNotes.length / (timeSpan / 1000);
        if (notesPerSecond > 10) {
          detectedFrequency = 'high';
        } else if (notesPerSecond > 1) {
          detectedFrequency = 'medium';
        } else {
          detectedFrequency = 'low';
        }
      }
    }
  }

  // Convert numeric frequency to category
  if (typeof detectedFrequency === 'number') {
    if (detectedFrequency >= 10) {
      detectedFrequency = 'high'; // 10-60Hz
    } else if (detectedFrequency >= 1) {
      detectedFrequency = 'medium'; // 1-10Hz
    } else {
      detectedFrequency = 'low'; // <1Hz
    }
  }

  // Tier 1: High-frequency decisions (10-60Hz) → fast
  // Rationale: Speed is critical, quality can be lower
  if (detectedFrequency === 'high' || detectedFrequency === 'ultra-high') {
    log('[ModelTierSelector] High-frequency detected, selecting fast tier');
    return 'fast';
  }

  // Tier 2: Critical evaluations → best
  // Rationale: Quality is critical, speed can be slower
  if (criticality === 'critical' || qualityRequired === true) {
    log('[ModelTierSelector] Critical evaluation detected, selecting best tier');
    return 'best';
  }

  // Check testType for critical indicators
  if (testType === 'expert-evaluation' || testType === 'medical' || testType === 'accessibility-critical') {
    log('[ModelTierSelector] Critical test type detected, selecting best tier');
    return 'best';
  }

  // Tier 3: Cost-sensitive → fast
  // Rationale: Minimize cost, acceptable quality
  if (costSensitive === true) {
    log('[ModelTierSelector] Cost-sensitive detected, selecting fast tier');
    return 'fast';
  }

  // Tier 4: Standard validations → balanced (default)
  // Rationale: Best balance of speed and quality
  log('[ModelTierSelector] Standard validation, selecting balanced tier (default)');
  return 'balanced';
}

/**
 * Select provider based on requirements
 * 
 * @param {Object} requirements - Provider requirements
 * @param {string} [requirements.speed] - Speed requirement ('ultra-fast'|'fast'|'normal'|'slow')
 * @param {string} [requirements.quality] - Quality requirement ('best'|'good'|'acceptable')
 * @param {boolean} [requirements.costSensitive] - Cost-sensitive
 * @param {number} [requirements.contextSize] - Context size in tokens
 * @param {boolean} [requirements.vision] - Vision required (default: true for VLLM)
 * @param {Object} [requirements.env] - Environment variables (for API key detection)
 * @returns {string} Provider name ('gemini'|'openai'|'claude'|'groq')
 */
export function selectProvider(requirements = {}) {
  const {
    speed = 'normal',
    quality = 'good',
    costSensitive = false,
    contextSize = 0,
    vision = true, // Default true for VLLM
    env = {}
  } = requirements;

  // Ultra-fast, text-only → Groq (if no vision needed)
  if (speed === 'ultra-fast' && !vision) {
    if (env.GROQ_API_KEY) {
      log('[ModelTierSelector] Ultra-fast text-only, selecting Groq');
      return 'groq';
    }
  }

  // Large context → Gemini (1M+ tokens)
  if (contextSize > 200000) {
    if (env.GEMINI_API_KEY) {
      log('[ModelTierSelector] Large context detected, selecting Gemini');
      return 'gemini';
    }
  }

  // Best quality → Gemini 2.5 Pro or GPT-5
  if (quality === 'best') {
    if (env.GEMINI_API_KEY) {
      log('[ModelTierSelector] Best quality required, selecting Gemini');
      return 'gemini';
    }
    if (env.OPENAI_API_KEY) {
      log('[ModelTierSelector] Best quality required, selecting OpenAI');
      return 'openai';
    }
  }

  // Fast + good quality → Gemini Flash
  if (speed === 'fast' && quality === 'good') {
    if (env.GEMINI_API_KEY) {
      log('[ModelTierSelector] Fast + good quality, selecting Gemini');
      return 'gemini';
    }
  }

  // Cost-sensitive → Gemini (free tier, lower cost)
  if (costSensitive) {
    if (env.GEMINI_API_KEY) {
      log('[ModelTierSelector] Cost-sensitive, selecting Gemini');
      return 'gemini';
    }
    if (env.GROQ_API_KEY && !vision) {
      log('[ModelTierSelector] Cost-sensitive text-only, selecting Groq');
      return 'groq';
    }
  }

  // Default → Auto-detect from available API keys
  // Priority: Groq (if vision supported) > Gemini > OpenAI > Claude
  if (vision && env.GROQ_API_KEY) {
    log('[ModelTierSelector] Default, selecting Groq (vision supported)');
    return 'groq';
  }
  if (env.GEMINI_API_KEY) {
    log('[ModelTierSelector] Default, selecting Gemini');
    return 'gemini';
  }
  if (env.OPENAI_API_KEY) {
    log('[ModelTierSelector] Default, selecting OpenAI');
    return 'openai';
  }
  if (env.ANTHROPIC_API_KEY) {
    log('[ModelTierSelector] Default, selecting Claude');
    return 'claude';
  }

  // Fallback
  warn('[ModelTierSelector] No API keys found, defaulting to gemini');
  return 'gemini';
}

/**
 * Select model tier and provider based on context
 * 
 * Combines tier and provider selection for convenience.
 * 
 * @param {Object} context - Validation context
 * @param {Object} [context.requirements] - Provider requirements
 * @returns {{tier: string, provider: string, reason: string}}
 */
export function selectModelTierAndProvider(context = {}) {
  const { requirements = {}, ...tierContext } = context;
  
  const tier = selectModelTier(tierContext);
  const provider = selectProvider({
    ...requirements,
    env: process.env
  });
  
  return {
    tier,
    provider,
    reason: `Selected ${provider} ${tier} tier based on context`
  };
}

