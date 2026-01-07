/**
 * VLLM Judge
 * 
 * Core screenshot validation using Vision Language Models.
 * Supports multiple providers (Gemini, OpenAI, Claude, Groq).
 * 
 * GROQ INTEGRATION:
 * - Groq uses OpenAI-compatible API (routes to callOpenAIAPI)
 * - ~0.22s latency (10x faster than typical providers)
 * - Best for high-frequency decisions (10-60Hz temporal decisions)
 * 
 * NOTE: Groq should also be added to @arclabs561/llm-utils for text-only LLM calls.
 * This package handles VLLM (vision) calls; llm-utils handles text-only calls.
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { createConfig, getConfig } from './config.mjs';
import { getCached, setCached } from './cache.mjs';
import { FileError, ProviderError, TimeoutError } from './errors.mjs';
import { log, warn } from './logger.mjs';
import { retryWithBackoff, enhanceErrorMessage } from './retry.mjs';
import { recordCost } from './cost-tracker.mjs';
import { normalizeValidationResult } from './validation-result-normalizer.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * VLLM Judge Class
 * 
 * Handles screenshot validation using Vision Language Models.
 */
export class VLLMJudge {
  constructor(options = {}) {
    this.config = createConfig(options);
    this.provider = this.config.provider;
    this.apiKey = this.config.apiKey;
    this.providerConfig = this.config.providerConfig;
    this.enabled = this.config.enabled;
    this._cacheInitialized = false;
  }

  /**
   * Initialize cache (lazy initialization)
   */
  async _initCache() {
    if (this._cacheInitialized || !this.config.cache.enabled) return;
    
    if (this.config.cache.dir) {
      const { initCache } = await import('./cache.mjs');
      initCache(this.config.cache.dir);
    }
    this._cacheInitialized = true;
  }

  /**
   * Convert image to base64 for API
   */
  imageToBase64(imagePath) {
    if (!existsSync(imagePath)) {
      throw new FileError(`Screenshot not found: ${imagePath}`, imagePath);
    }
    try {
      const imageBuffer = readFileSync(imagePath);
      return imageBuffer.toString('base64');
    } catch (error) {
      throw new FileError(`Failed to read screenshot: ${error.message}`, imagePath, { originalError: error.message });
    }
  }

  /**
   * Judge screenshot using VLLM API
   * 
   * @param {string | string[]} imagePath - Single image path or array of image paths for comparison
   * @param {string} prompt - Evaluation prompt
   * @param {import('./index.mjs').ValidationContext} [context={}] - Validation context
   * @returns {Promise<import('./index.mjs').ValidationResult>} Validation result
   */
  async judgeScreenshot(imagePath, prompt, context = {}) {
    // Support both single image and multi-image (for pair comparison)
    const imagePaths = Array.isArray(imagePath) ? imagePath : [imagePath];
    const isMultiImage = imagePaths.length > 1;
    if (!this.enabled) {
      // Return normalized disabled result
      return normalizeValidationResult({
        enabled: false,
        provider: this.provider,
        message: `API validation disabled (set ${this.provider.toUpperCase()}_API_KEY or API_KEY)`,
        pricing: this.providerConfig.pricing,
        score: null,
        issues: [],
        reasoning: 'API validation is disabled',
        assessment: null
      }, 'judgeScreenshot-disabled');
    }

    // Initialize cache if needed
    await this._initCache();
    
    // Check cache first (if caching enabled)
    const useCache = context.useCache !== false && this.config.cache.enabled;
    if (useCache) {
      const cacheKey = isMultiImage ? imagePaths.join('|') : imagePath;
      const cached = getCached(cacheKey, prompt, context);
      if (cached) {
        if (this.config.debug.verbose) {
          log(`[VLLM] Cache hit for ${cacheKey}`);
        }
        return { ...cached, cached: true };
      }
    }

    const startTime = Date.now();
    const timeout = context.timeout || this.config.performance.timeout;
    const abortController = new AbortController();
    const timeoutId = setTimeout(() => abortController.abort(), timeout);
    
    let response;
    let data;
    let judgment = null;
    let error = null;
    let attempts = 0;

    try {
      // Convert all images to base64
      const base64Images = imagePaths.map(path => this.imageToBase64(path));
      const fullPrompt = await this.buildPrompt(prompt, context, isMultiImage);
      
      // Retry API calls with exponential backoff
      const maxRetries = context.maxRetries ?? 3;
      const apiResult = await retryWithBackoff(async () => {
        attempts++;
        let apiResponse;
        let apiData;
        let logprobs = null; // Declare once outside switch
        
        // Route to appropriate API based on provider
        switch (this.provider) {
          case 'gemini':
            apiResponse = await this.callGeminiAPI(base64Images, fullPrompt, abortController.signal, isMultiImage);
            clearTimeout(timeoutId);
            apiData = await apiResponse.json();
            
            if (apiData.error) {
              const statusCode = apiResponse.status;
              throw new ProviderError(
                `Gemini API error: ${apiData.error.message}`,
                'gemini',
                {
                  apiError: apiData.error,
                  statusCode,
                  retryable: statusCode === 429 || statusCode >= 500
                }
              );
            }
            
            // Extract logprobs if available (for uncertainty estimation)
            logprobs = apiData.candidates?.[0]?.content?.parts?.[0]?.logprobs || null;
            
            return {
              judgment: apiData.candidates?.[0]?.content?.parts?.[0]?.text || 'No response',
              data: apiData,
              logprobs
            };
            
          case 'openai':
            apiResponse = await this.callOpenAIAPI(base64Images, fullPrompt, abortController.signal, isMultiImage);
            clearTimeout(timeoutId);
            apiData = await apiResponse.json();
            
            if (apiData.error) {
              const statusCode = apiResponse.status;
              throw new ProviderError(
                `OpenAI API error: ${apiData.error.message}`,
                'openai',
                {
                  apiError: apiData.error,
                  statusCode,
                  retryable: statusCode === 429 || statusCode >= 500
                }
              );
            }
            
            // Extract logprobs if available (OpenAI provides logprobs when requested)
            logprobs = apiData.choices?.[0]?.logprobs || null;
            
            return {
              judgment: apiData.choices?.[0]?.message?.content || 'No response',
              data: apiData,
              logprobs
            };
            
          case 'claude':
            apiResponse = await this.callClaudeAPI(base64Images, fullPrompt, abortController.signal, isMultiImage);
            clearTimeout(timeoutId);
            apiData = await apiResponse.json();
            
            if (apiData.error) {
              const statusCode = apiResponse.status;
              throw new ProviderError(
                `Claude API error: ${apiData.error.message || 'Unknown error'}`,
                'claude',
                {
                  apiError: apiData.error,
                  statusCode,
                  retryable: statusCode === 429 || statusCode >= 500
                }
              );
            }
            
            // Claude doesn't provide logprobs in standard API
            logprobs = null;
            
            return {
              judgment: apiData.content?.[0]?.text || 'No response',
              data: apiData,
              logprobs
            };
            
          case 'groq':
            // Groq uses OpenAI-compatible API, so we can reuse callOpenAIAPI
            // Groq's endpoint is already set in providerConfig.apiUrl (https://api.groq.com/openai/v1)
            apiResponse = await this.callOpenAIAPI(base64Images, fullPrompt, abortController.signal, isMultiImage);
            clearTimeout(timeoutId);
            apiData = await apiResponse.json();
            
            if (apiData.error) {
              const statusCode = apiResponse.status;
              throw new ProviderError(
                `Groq API error: ${apiData.error.message || 'Unknown error'}`,
                'groq',
                {
                  apiError: apiData.error,
                  statusCode,
                  retryable: statusCode === 429 || statusCode >= 500
                }
              );
            }
            
            // Groq may provide logprobs (OpenAI-compatible, but check availability)
            logprobs = apiData.choices?.[0]?.logprobs || null;
            
            return {
              judgment: apiData.choices?.[0]?.message?.content || 'No response',
              data: apiData,
              logprobs
            };
            
          default:
            throw new ProviderError(`Unknown provider: ${this.provider}`, this.provider);
        }
      }, {
        maxRetries,
        baseDelay: 1000,
        maxDelay: 30000,
        onRetry: (err, attempt, delay) => {
          if (this.config.debug.verbose) {
            warn(`[VLLM] Retry ${attempt}/${maxRetries} for ${this.provider} API: ${err.message} (waiting ${delay}ms)`);
          }
        }
      });
      
      judgment = apiResult.judgment;
      data = apiResult.data;
      const logprobs = apiResult.logprobs || null;
      
      const responseTime = Date.now() - startTime;
      const semanticInfo = this.extractSemanticInfo(judgment);
      
      // Enhance with uncertainty reduction (if enabled)
      let uncertainty = null;
      let confidence = null;
      let selfConsistencyRecommended = false;
      let selfConsistencyN = 0;
      let selfConsistencyReason = '';
      
      if (context.enableUncertaintyReduction !== false) {
        try {
          const { enhanceWithUncertainty } = await import('./uncertainty-reducer.mjs');
          // Pass context and partial result for adaptive self-consistency decision
          const enhanced = enhanceWithUncertainty({
            judgment,
            logprobs,
            attempts,
            screenshotPath: imagePath,
            score: semanticInfo.score,
            issues: semanticInfo.issues || []
          }, {
            enableHallucinationCheck: context.enableHallucinationCheck !== false,
            adaptiveSelfConsistency: context.adaptiveSelfConsistency !== false
          }, context);
          uncertainty = enhanced.uncertainty;
          confidence = enhanced.confidence;
          // Extract self-consistency recommendation (for future use or logging)
          selfConsistencyRecommended = enhanced.selfConsistencyRecommended || false;
          selfConsistencyN = enhanced.selfConsistencyN || 0;
          selfConsistencyReason = enhanced.selfConsistencyReason || '';
        } catch (error) {
          // Silently fail - uncertainty reduction is optional
          if (this.config.debug.verbose) {
            warn(`[VLLM] Uncertainty reduction failed: ${error.message}`);
          }
        }
      }
      
      // Estimate cost (data might not be available if retry succeeded)
      const estimatedCost = data ? this.estimateCost(data, this.provider) : null;
      
      // Record cost for tracking
      if (estimatedCost && estimatedCost.totalCost) {
        try {
          recordCost({
            provider: this.provider,
            cost: estimatedCost.totalCost,
            inputTokens: estimatedCost.inputTokens || 0,
            outputTokens: estimatedCost.outputTokens || 0,
            testName: context.testType || context.step || 'unknown'
          });
        } catch {
          // Silently fail if cost tracking unavailable
        }
      }
      
      const validationResult = {
        enabled: true,
        provider: this.provider,
        judgment,
        score: semanticInfo.score,
        issues: semanticInfo.issues,
        assessment: semanticInfo.assessment,
        reasoning: semanticInfo.reasoning,
        pricing: this.providerConfig.pricing,
        estimatedCost,
        responseTime,
        timestamp: new Date().toISOString(),
        testName: context.testType || context.step || 'unknown',
        viewport: context.viewport || null,
        raw: data || null,
        semantic: semanticInfo,
        attempts: attempts || 1,
        logprobs, // Include logprobs for uncertainty estimation (if available)
        uncertainty, // Uncertainty estimate (0-1, higher = more uncertain)
        confidence, // Confidence estimate (0-1, higher = more confident)
        screenshotPath: imagePath, // Include for human validation
        // Self-consistency recommendation (based on uncertainty × payout analysis)
        selfConsistencyRecommended, // Whether self-consistency is recommended for this validation
        selfConsistencyN, // Recommended number of self-consistency calls (0 = not recommended)
        selfConsistencyReason // Reason for recommendation (for logging/debugging)
      };
      
      // Collect VLLM judgment for human validation (non-blocking)
      if (context.enableHumanValidation !== false) {
        try {
          const { getHumanValidationManager } = await import('./human-validation-manager.mjs');
          const manager = getHumanValidationManager();
          if (manager && manager.enabled) {
            // Non-blocking: Don't wait for human validation collection
            manager.collectVLLMJudgment(validationResult, imagePath, prompt, context)
              .catch(err => {
                // Silently fail - human validation is optional
                if (this.config.debug.verbose) {
                  warn('[VLLM] Human validation collection failed:', err.message);
                }
              });
          }
        } catch (err) {
          // Silently fail if human validation manager not available
        }
      }
      
      // Apply calibration if available (non-blocking check)
      if (context.applyCalibration !== false && validationResult.score !== null) {
        try {
          const { getHumanValidationManager } = await import('./human-validation-manager.mjs');
          const manager = getHumanValidationManager();
          if (manager && manager.enabled) {
            const calibratedScore = manager.applyCalibration(validationResult.score);
            if (calibratedScore !== validationResult.score) {
              validationResult.originalScore = validationResult.score;
              validationResult.score = calibratedScore;
              validationResult.calibrated = true;
            }
          }
        } catch (err) {
          // Silently fail if calibration not available
        }
      }
      
      // Cache result (use first image path for single image, or combined key for multi-image)
      if (useCache) {
        const cacheKey = isMultiImage ? imagePaths.join('|') : imagePath;
        setCached(cacheKey, prompt, context, validationResult);
      }
      
      // Normalize result structure before returning (ensures consistent structure)
      return normalizeValidationResult(validationResult, 'judgeScreenshot');
    } catch (err) {
      clearTimeout(timeoutId);
      error = err;
      
      // Handle timeout errors specifically
      if (error.name === 'AbortError' || error.message?.includes('timeout') || error.message?.includes('aborted')) {
        const enhancedMessage = enhanceErrorMessage(
          new TimeoutError(`VLLM API call timed out after ${timeout}ms`, timeout),
          attempts || 1,
          'judgeScreenshot'
        );
        throw new TimeoutError(enhancedMessage, timeout, {
          provider: this.provider,
          imagePath,
          attempts: attempts || 1
        });
      }
      
      // Re-throw ProviderError with enhanced context
      if (error instanceof ProviderError) {
        const enhancedMessage = enhanceErrorMessage(error, attempts || 1, 'judgeScreenshot');
        throw new ProviderError(enhancedMessage, this.provider, {
          ...error.details,
          imagePath,
          prompt: prompt.substring(0, 100),
          attempts: attempts || 1
        });
      }
      
      // Re-throw FileError and TimeoutError as-is (already have context)
      if (error instanceof FileError || error instanceof TimeoutError) {
        throw error;
      }
      
      // For other errors, enhance message and throw (consistent error handling)
      const enhancedMessage = enhanceErrorMessage(error, attempts || 1, 'judgeScreenshot');
      throw new ProviderError(
        `VLLM API call failed: ${enhancedMessage}`,
        this.provider,
        {
          imagePath,
          prompt: prompt.substring(0, 100),
          attempts: attempts || 1,
          originalError: error.message
        }
      );
    }
  }

  /**
   * Build prompt for screenshot validation
   * 
   * Uses unified prompt composition system for research-backed consistency.
   * Research: Explicit rubrics improve reliability by 10-20% (arXiv:2412.05579)
   * 
   * Supports variable goals: if context.goal is provided, it will be used to generate
   * the base prompt before composition. This allows seamless integration of variable
   * goals throughout the system.
   * 
   * @param {string} prompt - Base prompt (or ignored if context.goal is provided)
   * @param {import('./index.mjs').ValidationContext} context - Validation context
   * @param {boolean} [isMultiImage=false] - Whether this is a multi-image comparison
   * @returns {string} Full prompt with context
   */
  async buildPrompt(prompt, context = {}, isMultiImage = false) {
    // If custom prompt builder provided, use it
    if (context.promptBuilder && typeof context.promptBuilder === 'function') {
      return context.promptBuilder(prompt, context);
    }
    
    // Use unified prompt composition system (which handles variable goals)
    // Pass goal in context - composeSingleImagePrompt/composeComparisonPrompt will handle it
    try {
      if (isMultiImage) {
        return await composeComparisonPrompt(prompt, context, {
          includeRubric: context.includeRubric !== false // Default true (research-backed)
        });
      } else {
        return await composeSingleImagePrompt(prompt, context, {
          includeRubric: context.includeRubric !== false, // Default true (research-backed)
          temporalNotes: context.temporalNotes || null
        });
      }
    } catch (error) {
      // Fallback to basic prompt building if composition fails
      if (this.config.debug.verbose) {
        warn(`[VLLM] Prompt composition failed, using fallback: ${error.message}`);
      }
      
      // Basic fallback (original implementation)
      let fullPrompt = prompt;
      const contextParts = [];
      if (context.testType) {
        contextParts.push(`Test Type: ${context.testType}`);
      }
      if (context.viewport) {
        contextParts.push(`Viewport: ${context.viewport.width}x${context.viewport.height}`);
      }
      if (context.gameState) {
        contextParts.push(`Game State: ${JSON.stringify(context.gameState)}`);
      }
      if (contextParts.length > 0) {
        fullPrompt = `${prompt}\n\nContext:\n${contextParts.join('\n')}`;
      }
      if (isMultiImage) {
        fullPrompt = `${fullPrompt}\n\nYou are comparing two screenshots side-by-side. Return JSON with:
{
  "winner": "A" | "B" | "tie",
  "confidence": 0.0-1.0,
  "reasoning": "explanation",
  "differences": ["difference1", "difference2"],
  "scores": {"A": 0-10, "B": 0-10}
}`;
      }
      return fullPrompt;
    }
  }

  /**
   * Extract semantic information from judgment text
   */
  extractSemanticInfo(judgment) {
    // Handle case where judgment is already an object
    if (typeof judgment === 'object' && judgment !== null && !Array.isArray(judgment)) {
      // Normalize issues: handle both array of strings and array of objects
      let issues = judgment.issues || [];
      if (issues.length > 0 && typeof issues[0] === 'string') {
        // Convert string array to object array for consistency
        issues = issues.map(desc => ({
          description: desc,
          importance: 'medium',
          annoyance: 'medium',
          impact: 'minor-inconvenience'
        }));
      }
      
      // Normalize recommendations: handle both array of strings and array of objects
      let recommendations = judgment.recommendations || [];
      if (recommendations.length > 0 && typeof recommendations[0] === 'string') {
        recommendations = recommendations.map(suggestion => ({
          priority: 'medium',
          suggestion,
          expectedImpact: 'improved user experience'
        }));
      }
      
      return {
        score: judgment.score || null,
        issues: issues,
        assessment: judgment.assessment || null,
        reasoning: judgment.reasoning || null,
        strengths: judgment.strengths || [],
        recommendations: recommendations,
        evidence: judgment.evidence || null,
        brutalistViolations: judgment.brutalistViolations || [],
        zeroToleranceViolations: judgment.zeroToleranceViolations || []
      };
    }

    // Handle case where judgment is a string
    const judgmentText = typeof judgment === 'string' ? judgment : String(judgment || '');
    
    try {
      const jsonMatch = judgmentText.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        // Normalize issues and recommendations
        let issues = parsed.issues || [];
        if (issues.length > 0 && typeof issues[0] === 'string') {
          issues = issues.map(desc => ({
            description: desc,
            importance: 'medium',
            annoyance: 'medium',
            impact: 'minor-inconvenience'
          }));
        }
        
        let recommendations = parsed.recommendations || [];
        if (recommendations.length > 0 && typeof recommendations[0] === 'string') {
          recommendations = recommendations.map(suggestion => ({
            priority: 'medium',
            suggestion,
            expectedImpact: 'improved user experience'
          }));
        }
        
        return {
          score: parsed.score || null,
          issues: issues,
          assessment: parsed.assessment || null,
          reasoning: parsed.reasoning || null,
          strengths: parsed.strengths || [],
          recommendations: recommendations,
          evidence: parsed.evidence || null,
          brutalistViolations: parsed.brutalistViolations || [],
          zeroToleranceViolations: parsed.zeroToleranceViolations || []
        };
      }
    } catch (e) {
      // Fall through to regex extraction
    }

    // Fallback: extract basic info from text
    // Try to extract score from the full judgment text (including reasoning)
    const extractedScore = this.extractScore(judgmentText);
    
    return {
      score: extractedScore,
      issues: this.extractIssues(judgmentText),
      assessment: this.extractAssessment(judgmentText),
      reasoning: judgmentText.substring(0, 500)
    };
  }

  /**
   * Extract score from judgment text
   */
  extractScore(judgment) {
    if (!judgment || typeof judgment !== 'string') return null;
    
    const patterns = [
      // JSON format: "score": 7
      /"score"\s*:\s*(\d+)/i,
      // Text format: Score: 7 or Score 7
      /score[:\s]*(\d+)/i,
      // Fraction format: score: 7/10 or 7/10
      /score[:\s]*(\d+)\s*\/\s*10/i,
      /(\d+)\s*\/\s*10/i,
      // Rating format: Rating: 7, Rated 7
      /rating[:\s]*(\d+)/i,
      /rated[:\s]*(\d+)/i,
      // Verdict format: Verdict: PASS (7/10) or Verdict: FAIL (3/10)
      /verdict[:\s]*(?:pass|fail)[:\s]*\((\d+)\s*\/\s*10\)/i,
      // Markdown format: **Score**: 7 or ## Score: 7
      /\*\*score\*\*[:\s]*(\d+)/i,
      /##\s*score[:\s]*(\d+)/i,
      // Structured text: "Overall Score: 7 out of 10"
      /overall\s*score[:\s]*(\d+)\s*(?:out\s*of|\/)\s*10/i,
      // Standalone number at start (common when API returns just "10" or "9" as reasoning)
      // Match: "10", "10.", "10 ", "10\n", etc.
      /^\s*(\d{1,2})(?:\s|\.|$)/,
      // Number followed by common words (e.g., "10 out of 10", "9/10")
      /^(\d{1,2})\s*(?:out\s*of|\/)\s*10/i,
      // "Rate from 1-10" response patterns
      /rate[:\s]*(\d{1,2})\s*(?:out\s*of|\/)?\s*10/i,
      // Very simple: just a number 0-10 at the start (for cases like "10" with nothing else)
      /^(\d{1,2})$/
    ];
    
    for (const pattern of patterns) {
      const match = judgment.match(pattern);
      if (match) {
        const score = parseInt(match[1]);
        if (score >= 0 && score <= 10) {
          return score;
        }
      }
    }
    
    // Try to infer from verdict language
    const lower = judgment.toLowerCase();
    if (lower.includes('excellent') || lower.includes('outstanding')) {
      return 9;
    }
    if (lower.includes('very good') || lower.includes('great')) {
      return 8;
    }
    if (lower.includes('good') || lower.includes('satisfactory')) {
      return 7;
    }
    if (lower.includes('fair') || lower.includes('adequate')) {
      return 6;
    }
    if (lower.includes('poor') || lower.includes('needs improvement')) {
      return 4;
    }
    if (lower.includes('fail') && !lower.includes('pass')) {
      return 3;
    }
    
    return null;
  }

  /**
   * Extract issues from judgment text
   */
  extractIssues(judgment) {
    try {
      const jsonMatch = judgment.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        return parsed.issues || [];
      }
    } catch (e) {
      // Fall through to regex
    }

    const issues = [];
    const lines = judgment.split('\n');
    for (const line of lines) {
      if (line.match(/[-*]\s*(.+)/i) || line.match(/\d+\.\s*(.+)/i)) {
        issues.push(line.replace(/[-*]\s*|\d+\.\s*/i, '').trim());
      }
    }
    
    return issues;
  }

  /**
   * Extract assessment from judgment text
   */
  extractAssessment(judgment) {
    try {
      const jsonMatch = judgment.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        return parsed.assessment || null;
      }
    } catch (e) {
      // Fall through to regex
    }

    const lower = judgment.toLowerCase();
    if (lower.includes('pass') && !lower.includes('fail')) {
      return 'pass';
    }
    if (lower.includes('fail')) {
      return 'fail';
    }
    
    return null;
  }

  /**
   * Call Google Gemini API
   * 
   * @param {string | string[]} base64Images - Single image or array of images (base64)
   * @param {string} prompt - Evaluation prompt
   * @param {AbortSignal} signal - Abort signal for timeout
   * @param {boolean} [isMultiImage=false] - Whether this is a multi-image request
   * @returns {Promise<Response>} API response
   */
  async callGeminiAPI(base64Images, prompt, signal, isMultiImage = false) {
    const images = Array.isArray(base64Images) ? base64Images : [base64Images];
    
    // Build parts array: text prompt + all images
    const parts = [{ text: prompt }];
    for (const base64Image of images) {
      parts.push({
        inline_data: {
          mime_type: 'image/png',
          data: base64Image
        }
      });
    }
    
    // SECURITY: Use header for API key, not URL parameter
    // API keys in URLs are exposed in logs, browser history, referrer headers
    return fetch(
      `${this.providerConfig.apiUrl}/models/${this.providerConfig.model}:generateContent`,
      {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'x-goog-api-key': this.apiKey  // Use header instead of URL parameter
        },
        signal,
        body: JSON.stringify({
          contents: [{ parts }],
          generationConfig: {
            temperature: 0.1,
            maxOutputTokens: 2000,
            topP: 0.95,
            topK: 40
          }
        })
      }
    );
  }

  /**
   * Call OpenAI API
   * 
   * @param {string | string[]} base64Images - Single image or array of images (base64)
   * @param {string} prompt - Evaluation prompt
   * @param {AbortSignal} signal - Abort signal for timeout
   * @param {boolean} [isMultiImage=false] - Whether this is a multi-image request
   * @returns {Promise<Response>} API response
   */
  async callOpenAIAPI(base64Images, prompt, signal, isMultiImage = false) {
    const images = Array.isArray(base64Images) ? base64Images : [base64Images];
    
    // Build content array: text prompt + all images
    const content = [{ type: 'text', text: prompt }];
    for (const base64Image of images) {
      content.push({
        type: 'image_url',
        image_url: { url: `data:image/png;base64,${base64Image}` }
      });
    }
    
    return fetch(`${this.providerConfig.apiUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`
      },
      signal,
      body: JSON.stringify({
        model: this.providerConfig.model,
        messages: [{
          role: 'user',
          content
        }],
        // Some OpenAI models have limited parameter support
        // Models that only support default temperature (1): gpt-4o-mini, gpt-5
        // Models that support custom temperature: gpt-4o, gpt-4-turbo, etc.
        // Only include temperature if model supports custom values (omit for models that require default)
        ...(this.providerConfig.model.includes('mini') || this.providerConfig.model.includes('gpt-5')
          ? {} // Use default temperature (1) - don't specify for models that require it
          : { temperature: 0.1, top_p: 0.95 } // Custom values for models that support them
        ),
        // Use max_completion_tokens for newer models (gpt-4o, gpt-5), max_tokens for older models
        ...(this.providerConfig.model.startsWith('gpt-4o') || this.providerConfig.model.startsWith('gpt-5')
          ? { max_completion_tokens: 2000 }
          : { max_tokens: 2000 })
        // Note: logprobs removed - not all OpenAI models support it (e.g., vision models)
        // If needed, can be conditionally added based on model support
      })
    });
  }

  /**
   * Call Anthropic Claude API
   * 
   * @param {string | string[]} base64Images - Single image or array of images (base64)
   * @param {string} prompt - Evaluation prompt
   * @param {AbortSignal} signal - Abort signal for timeout
   * @param {boolean} [isMultiImage=false] - Whether this is a multi-image request
   * @returns {Promise<Response>} API response
   */
  async callClaudeAPI(base64Images, prompt, signal, isMultiImage = false) {
    const images = Array.isArray(base64Images) ? base64Images : [base64Images];
    
    // Build content array: text prompt + all images
    const content = [{ type: 'text', text: prompt }];
    for (const base64Image of images) {
      content.push({
        type: 'image',
        source: {
          type: 'base64',
          media_type: 'image/png',
          data: base64Image
        }
      });
    }
    
    return fetch(`${this.providerConfig.apiUrl}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': this.apiKey,
        'anthropic-version': '2023-06-01'
      },
      signal,
      body: JSON.stringify({
        model: this.providerConfig.model,
        max_tokens: 2000, // Increased for pair comparison
        messages: [{
          role: 'user',
          content
        }]
      })
    });
  }

  /**
   * Estimate cost based on token usage
   */
  estimateCost(data, provider) {
    if (!this.providerConfig.pricing || this.providerConfig.pricing.input === 0) {
      return null; // Free or self-hosted
    }
    
    let inputTokens = 0;
    let outputTokens = 0;
    
    switch (provider) {
      case 'gemini':
        inputTokens = data.usageMetadata?.promptTokenCount || 0;
        outputTokens = data.usageMetadata?.candidatesTokenCount || 0;
        break;
      case 'openai':
        inputTokens = data.usage?.prompt_tokens || 0;
        outputTokens = data.usage?.completion_tokens || 0;
        break;
      case 'claude':
        inputTokens = data.usage?.input_tokens || 0;
        outputTokens = data.usage?.output_tokens || 0;
        break;
      case 'groq':
        // Groq uses OpenAI-compatible API format
        inputTokens = data.usage?.prompt_tokens || 0;
        outputTokens = data.usage?.completion_tokens || 0;
        break;
    }
    
    const inputCost = (inputTokens / 1_000_000) * this.providerConfig.pricing.input;
    const outputCost = (outputTokens / 1_000_000) * this.providerConfig.pricing.output;
    const totalCost = inputCost + outputCost;
    
    return {
      inputTokens,
      outputTokens,
      inputCost: inputCost.toFixed(6),
      outputCost: outputCost.toFixed(6),
      totalCost: totalCost.toFixed(6),
      currency: 'USD'
    };
  }
}

/**
 * Validate screenshot (convenience function)
 * 
 * Creates a judge instance and validates a screenshot.
 */
export async function validateScreenshot(imagePath, prompt, context = {}) {
  const judge = new VLLMJudge(context);
  return judge.judgeScreenshot(imagePath, prompt, context);
}
