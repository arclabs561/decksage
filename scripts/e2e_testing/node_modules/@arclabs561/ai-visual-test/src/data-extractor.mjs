/**
 * Structured Data Extractor
 * 
 * Extracts structured data from VLLM responses using multiple strategies:
 * - JSON parsing (if response contains JSON)
 * - LLM extraction (if LLM is available)
 * - Regex fallback (simple patterns)
 * 
 * General-purpose utility - no domain-specific logic.
 */

import { createConfig } from './config.mjs';
import { loadEnv } from './load-env.mjs';
import { warn } from './logger.mjs';
// Load env before LLM utils
loadEnv();
// Use shared LLM utility library for text-only calls (optional dependency)
// Note: This module uses Claude Sonnet (advanced tier) for data extraction
// which requires higher quality than simple validation tasks
// Import is handled dynamically to make it optional

/**
 * Extract structured data from text using multiple strategies
 * 
 * @param {string} text - Text to extract data from
 * @param {Record<string, { type: string; [key: string]: unknown }>} schema - Schema definition for extraction
 * @param {{
 *   method?: 'json' | 'llm' | 'regex';
 *   provider?: string;
 *   apiKey?: string;
 *   fallback?: 'llm' | 'regex' | 'json' | 'auto';
 * }} [options={}] - Extraction options
 * @returns {Promise<unknown>} Extracted structured data matching schema, or null if extraction fails
 */
export async function extractStructuredData(text, schema, options = {}) {
  if (!text) return null;
  
  const {
    fallback = 'llm', // 'llm' | 'regex' | 'json'
    provider = null
  } = options;
  
  // Strategy 1: Try JSON parsing first (fastest)
  try {
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0]);
      // Validate against schema
      if (validateSchema(parsed, schema)) {
        return parsed;
      }
    }
  } catch (error) {
    // JSON parsing failed, try next strategy
  }
  
  // Strategy 2: Try LLM extraction (if available and requested)
  if (fallback === 'llm' || fallback === 'auto') {
    try {
      const config = createConfig({ provider });
      if (config.enabled) {
        const extracted = await extractWithLLM(text, schema, config);
        if (extracted) {
          return extracted;
        }
      }
    } catch (error) {
      warn(`[DataExtractor] LLM extraction failed: ${error.message}`);
    }
  }
  
  // Strategy 3: Try regex fallback
  if (fallback === 'regex' || fallback === 'auto') {
    try {
      const extracted = extractWithRegex(text, schema);
      if (extracted) {
        return extracted;
      }
    } catch (error) {
      warn(`[DataExtractor] Regex extraction failed: ${error.message}`);
    }
  }
  
  return null;
}

/**
 * Extract structured data using LLM
 */
async function extractWithLLM(text, schema, config) {
  const prompt = `Extract structured data from the following text. Return ONLY valid JSON matching this schema:

Schema:
${JSON.stringify(schema, null, 2)}

Text to extract from:
${text}

Return ONLY the JSON object, no other text.`;

  try {
    const response = await callLLMForExtraction(prompt, config);
    // Try to extract JSON from response
    let parsed;
    try {
      const llmUtils = await import('@arclabs561/llm-utils');
      parsed = llmUtils.extractJSON(response);
    } catch (error) {
      // Fallback: try to parse as JSON directly
      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        parsed = JSON.parse(jsonMatch[0]);
      } else {
        throw new Error('Could not extract JSON from response');
      }
    }
    if (parsed && validateSchema(parsed, schema)) {
      return parsed;
    }
  } catch (error) {
    warn(`[DataExtractor] LLM extraction error: ${error.message}`);
  }
  
  return null;
}

/**
 * Call LLM API (text-only, no vision)
 * Uses shared utility with advanced tier for better extraction quality
 */
async function callLLMForExtraction(prompt, config) {
  const apiKey = config.apiKey;
  const provider = config.provider || 'gemini';
  
  // Try to use optional llm-utils library if available
  try {
    const llmUtils = await import('@arclabs561/llm-utils');
    const callLLMUtil = llmUtils.callLLM;
    // Use advanced tier for data extraction (needs higher quality)
    return await callLLMUtil(prompt, provider, apiKey, {
      tier: 'advanced', // Data extraction benefits from better models
      temperature: 0.1,
      maxTokens: 1000,
    });
  } catch (error) {
    // Fallback: use local implementation or throw
    throw new Error(`LLM extraction requires @arclabs561/llm-utils package: ${error.message}`);
  }
}

/**
 * Escape special regex characters to prevent ReDoS
 */
function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Extract structured data using regex patterns
 */
function extractWithRegex(text, schema) {
  const result = {};
  
  for (const [key, field] of Object.entries(schema)) {
    const { type, required = false } = field;
    
    // Escape key to prevent ReDoS attacks
    const escapedKey = escapeRegex(key);
    
    // Try to find value in text
    let value = null;
    
    if (type === 'number') {
      // Look for number patterns
      const match = text.match(new RegExp(`${escapedKey}[\\s:=]+([0-9.]+)`, 'i'));
      if (match) {
        value = parseFloat(match[1]);
      }
    } else if (type === 'string') {
      // Look for string patterns
      const match = text.match(new RegExp(`${escapedKey}[\\s:=]+([^\\n,]+)`, 'i'));
      if (match) {
        value = match[1].trim();
      }
    } else if (type === 'boolean') {
      // Look for boolean patterns
      const match = text.match(new RegExp(`${escapedKey}[\\s:=]+(true|false|yes|no)`, 'i'));
      if (match) {
        value = match[1].toLowerCase() === 'true' || match[1].toLowerCase() === 'yes';
      }
    }
    
    if (value !== null) {
      result[key] = value;
    } else if (required) {
      // Required field not found
      return null;
    }
  }
  
  return Object.keys(result).length > 0 ? result : null;
}

/**
 * Validate extracted data against schema
 */
function validateSchema(data, schema) {
  if (!data || typeof data !== 'object') return false;
  
  for (const [key, field] of Object.entries(schema)) {
    const { type, required = false } = field;
    
    if (required && !(key in data)) {
      return false;
    }
    
    if (key in data) {
      const value = data[key];
      
      if (type === 'number' && typeof value !== 'number') {
        return false;
      } else if (type === 'string' && typeof value !== 'string') {
        return false;
      } else if (type === 'boolean' && typeof value !== 'boolean') {
        return false;
      }
    }
  }
  
  return true;
}

