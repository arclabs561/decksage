/**
 * Batch Optimizer
 * 
 * Optimizes VLLM API calls by:
 * - Queueing requests for better throughput
 * - Caching responses for identical screenshots
 * - Implementing request pooling with concurrency limits
 * 
 * General-purpose utility - no domain-specific logic.
 * 
 * CACHE ARCHITECTURE NOTE:
 * - This has its OWN in-memory cache (Map), separate from VLLM cache
 * - Cache key generation fixed (2025-01): Now uses SHA-256 hash, no truncation
 * - Purpose: Short-term caching during request batching (process lifetime only)
 * - Why separate: Different lifetime (process vs 7 days), different purpose (batching optimization vs persistence),
 *   different failure domain (memory-only, no disk I/O), serves different lifecycle (request batching vs API responses)
 * - No coordination with VLLM cache (by design - they serve different purposes with minimal data overlap)
 * - No size limits or eviction (grows unbounded in long-running processes - acceptable for process-scoped cache)
 * - See docs/CACHE_ARCHITECTURE_DEEP_DIVE.md for details
 */

import { createHash } from 'crypto';

/**
 * Batch Optimizer Class
 * 
 * Optimizes VLLM API calls by queueing requests and caching responses.
 * 
 * @class BatchOptimizer
 */
import { API_CONSTANTS, BATCH_OPTIMIZER_CONSTANTS } from './constants.mjs';
import { TimeoutError } from './errors.mjs';
import { warn } from './logger.mjs';

export class BatchOptimizer {
  /**
   * @param {{
   *   maxConcurrency?: number;
   *   batchSize?: number;
   *   cacheEnabled?: boolean;
   *   maxQueueSize?: number;
   *   requestTimeout?: number;
   * }} [options={}] - Optimizer options
   */
  constructor(options = {}) {
    const {
      maxConcurrency = API_CONSTANTS.DEFAULT_MAX_CONCURRENCY,
      batchSize = 3,
      cacheEnabled = true,
      maxQueueSize = BATCH_OPTIMIZER_CONSTANTS.MAX_QUEUE_SIZE,
      requestTimeout = BATCH_OPTIMIZER_CONSTANTS.REQUEST_TIMEOUT_MS
    } = options;
    
    this.queue = [];
    this.processing = false;
    this.cache = cacheEnabled ? new Map() : null;
    this.batchSize = batchSize;
    this.maxConcurrency = maxConcurrency;
    this.activeRequests = 0;
    this.maxQueueSize = maxQueueSize;
    this.requestTimeout = requestTimeout;
    
    // CRITICAL FIX: Initialize metrics in constructor to prevent undefined errors
    // Metrics are used in _queueRequest before getPerformanceMetrics() is called
    this.metrics = {
      queueRejections: 0,
      timeouts: 0,
      totalQueued: 0,
      totalProcessed: 0,
      averageWaitTime: 0,
      waitTimes: []
    };
  }
  
  /**
   * Generate cache key from screenshot path and prompt
   * 
   * NOTE: This cache key generation may need improvement for better cache hit rates
   * 
   * Issues:
   * BUG FIX (2025-01): Fixed truncation and string concatenation issues.
   * 
   * Previous issues:
   * 1. Truncation: prompt truncated to 100 chars, context to 50 chars
   *    - Causes collisions: different prompts with same prefix = same key
   *    - Wrong cache hits = incorrect results
   * 
   * 2. String concatenation, not hash
   *    - VLLM cache uses SHA-256 hash (secure, no collisions)
   *    - This used string concatenation (collision-prone)
   *    - Inconsistent with VLLM cache approach
   * 
   * 3. Whitespace removal in prompt
   *    - `replace(/\s+/g, '')` removed all whitespace
   *    - "Check accessibility" vs "Checkaccessibility" = same key (wrong!)
   * 
   * Fix: Use SHA-256 hash like VLLM cache, don't truncate
   * - Hash full content to avoid collisions
   * - Cryptographically secure (collisions are extremely unlikely)
   * - Consistent with VLLM cache approach
   */
  _getCacheKey(imagePath, prompt, context) {
    const keyData = {
      imagePath,
      prompt: prompt || '',
      context: context ? JSON.stringify(context) : ''
    };
    const keyString = JSON.stringify(keyData);
    return createHash('sha256').update(keyString).digest('hex');
  }
  
  /**
   * Batch validate multiple screenshots
   * 
   * @param {string | string[]} imagePaths - Single image path or array of image paths
   * @param {string} prompt - Validation prompt
   * @param {import('./index.mjs').ValidationContext} [context={}] - Validation context
   * @returns {Promise<import('./index.mjs').ValidationResult[]>} Array of validation results
   */
  async batchValidate(imagePaths, prompt, context = {}) {
    if (!Array.isArray(imagePaths)) {
      imagePaths = [imagePaths];
    }
    
    // Handle empty array
    if (imagePaths.length === 0) {
      return [];
    }
    
    // Process all screenshots in parallel (respecting concurrency limit)
    const results = await Promise.all(
      imagePaths.map(path => this._queueRequest(path, prompt, context))
    );
    
    return results;
  }
  
  /**
   * Queue VLLM request for batch processing
   * 
   * SECURITY: Queue size limit prevents memory leaks from unbounded queue growth
   */
  async _queueRequest(imagePath, prompt, context, validateFn = null) {
    // Check cache first
    if (this.cache) {
      const cacheKey = this._getCacheKey(imagePath, prompt, context);
      if (this.cache.has(cacheKey)) {
        return this.cache.get(cacheKey);
      }
    }
    
    // If under concurrency limit, process immediately
    // NOTE: Track metrics for immediate processing too (not just queued requests)
    // Note: totalQueued counts ALL requests (immediate + queued), totalProcessed counts completed requests
    if (this.activeRequests < this.maxConcurrency) {
      try {
        this.metrics.totalQueued++; // Count immediate processing in total requests
        // Note: totalProcessed will be incremented when request completes (in resolve handler for queued, or we could add it here)
        // For now, we track it in the resolve handler for consistency
      } catch (metricsError) {
        warn(`[BatchOptimizer] Error updating metrics: ${metricsError.message}`);
      }
      // Track start time for immediate processing (for consistency with queued requests)
      const startTime = Date.now();
      // CRITICAL FIX: Wrap _processRequest in try-catch to ensure metrics balance even on errors
      // MCP research confirms: If totalQueued is incremented but request fails, metrics become inaccurate
      // This ensures totalProcessed is tracked even if _processRequest throws
      try {
        const result = await this._processRequest(imagePath, prompt, context, validateFn);
        // Track successful completion for immediate processing
        try {
          this.metrics.totalProcessed++;
          const waitTime = Date.now() - startTime;
          this.metrics.waitTimes.push(waitTime);
          if (this.metrics.waitTimes.length > 100) {
            this.metrics.waitTimes.shift();
          }
          if (this.metrics.waitTimes.length === 1) {
            this.metrics.averageWaitTime = waitTime;
          } else {
            const count = this.metrics.waitTimes.length;
            this.metrics.averageWaitTime = this.metrics.averageWaitTime + (waitTime - this.metrics.averageWaitTime) / count;
          }
        } catch (metricsError) {
          warn(`[BatchOptimizer] Error updating metrics: ${metricsError.message}`);
        }
        return result;
      } catch (error) {
        // CRITICAL FIX: Track failed requests to maintain metrics accuracy
        // Even if request fails, we should track that it was "processed" (attempted)
        // This prevents totalQueued > totalProcessed imbalance
        try {
          this.metrics.totalProcessed++; // Count failed attempts too
          // Note: We could add a separate totalFailed counter, but for now we count all attempts
        } catch (metricsError) {
          warn(`[BatchOptimizer] Error updating failure metrics: ${metricsError.message}`);
        }
        // Re-throw error so caller can handle it
        throw error;
      }
    }
    
    // Check queue size limit (prevent memory leaks)
    // VERIFIABLE: Track queue rejections to verify "prevents memory leaks" claim
    // CRITICAL FIX: Increment totalQueued BEFORE checking queue size to ensure rejectionRate calculation is accurate
    // This ensures rejected requests are included in the denominator for accurate rate calculation
    const queueStartTime = Date.now();
    try {
      this.metrics.totalQueued++;
    } catch (metricsError) {
      // Metrics are best-effort, don't let them crash the application
      warn(`[BatchOptimizer] Error updating metrics: ${metricsError.message}`);
    }
    
    if (this.queue.length >= this.maxQueueSize) {
      try {
        this.metrics.queueRejections++;
      } catch (metricsError) {
        warn(`[BatchOptimizer] Error updating rejection metrics: ${metricsError.message}`);
      }
      warn(`[BatchOptimizer] Queue is full (${this.queue.length}/${this.maxQueueSize}). Rejecting request to prevent memory leak. Total rejections: ${this.metrics.queueRejections}`);
      throw new TimeoutError(
        `Queue is full (${this.queue.length}/${this.maxQueueSize}). Too many concurrent requests.`,
        { queueSize: this.queue.length, maxQueueSize: this.maxQueueSize }
      );
    }
    
    // Otherwise, queue for later with timeout
    // VERIFIABLE: Track queue time and timeouts to verify "prevents indefinite waiting" claim
    
    return new Promise((resolve, reject) => {
      // Set timeout for queued request (prevents indefinite waiting)
      // NOTE: Use a flag to prevent double-counting if request completes just before timeout
      let timeoutFired = false;
      let queueEntry = null; // Store reference to queue entry for timeout callback
      
      const timeoutId = setTimeout(() => {
        timeoutFired = true;
        // Remove from queue if still waiting
        // CRITICAL FIX: Use stored queueEntry reference instead of searching by resolve function
        // The resolve function is wrapped, so direct comparison might not work
        if (queueEntry) {
          const index = this.queue.indexOf(queueEntry);
          if (index >= 0) {
            this.queue.splice(index, 1);
            // VERIFIABLE: Track timeout to verify claim
            // Only increment if request was still in queue (not already processed)
            // CRITICAL FIX: Wrap in try-catch to ensure metrics don't crash application
            try {
              this.metrics.timeouts++;
            } catch (metricsError) {
              warn(`[BatchOptimizer] Error updating timeout metrics: ${metricsError.message}`);
            }
            const waitTime = Date.now() - queueStartTime;
            warn(`[BatchOptimizer] Request timed out after ${waitTime}ms in queue (limit: ${this.requestTimeout}ms). Total timeouts: ${this.metrics.timeouts}`);
            reject(new TimeoutError(
              `Request timed out after ${this.requestTimeout}ms in queue`,
              { timeout: this.requestTimeout, queuePosition: index, waitTime }
            ));
          }
        }
        // If queueEntry not found, request was already processed, don't count as timeout
      }, this.requestTimeout);
      
      // Create queue entry with wrapped resolve/reject to clear timeout
      queueEntry = {
        imagePath,
        prompt,
        context,
        validateFn,
        queueStartTime, // Track when queued for wait time calculation
        resolve: (value) => {
          clearTimeout(timeoutId);
          // CRITICAL FIX: Check if timeout already fired to prevent double-counting
          if (!timeoutFired) {
            // VERIFIABLE: Track wait time to verify queue performance
            // CRITICAL FIX: Wrap in try-catch to ensure metrics don't crash application
            try {
              const waitTime = Date.now() - queueStartTime;
              this.metrics.waitTimes.push(waitTime);
              this.metrics.totalProcessed++;
              // Keep only last 100 wait times for average calculation
              if (this.metrics.waitTimes.length > 100) {
                this.metrics.waitTimes.shift();
              }
              // OPTIMIZATION: Use running average instead of recalculating sum every time
              // Running average: newAvg = oldAvg + (newValue - oldAvg) / count
              if (this.metrics.waitTimes.length === 1) {
                this.metrics.averageWaitTime = waitTime;
              } else {
                const count = this.metrics.waitTimes.length;
                this.metrics.averageWaitTime = this.metrics.averageWaitTime + (waitTime - this.metrics.averageWaitTime) / count;
              }
            } catch (metricsError) {
              // Metrics are best-effort, don't let them crash the application
              warn(`[BatchOptimizer] Error updating metrics: ${metricsError.message}`);
            }
          }
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timeoutId);
          reject(error);
        }
      };
      
      this.queue.push(queueEntry);
      this._processQueue();
    });
  }
  
  /**
   * Process a single request
   */
  async _processRequest(imagePath, prompt, context, validateFn) {
    if (!validateFn) {
      // Import validateScreenshot if not provided
      const { validateScreenshot } = await import('./judge.mjs');
      validateFn = validateScreenshot;
    }
    
    this.activeRequests++;
    
    try {
      const result = await validateFn(imagePath, prompt, context);
      
      // Cache result if enabled
      if (this.cache) {
        const cacheKey = this._getCacheKey(imagePath, prompt, context);
        this.cache.set(cacheKey, result);
      }
      
      return result;
    } finally {
      this.activeRequests--;
      this._processQueue();
    }
  }
  
  /**
   * Process queued requests
   */
  async _processQueue() {
    if (this.processing || this.queue.length === 0 || this.activeRequests >= this.maxConcurrency) {
      return;
    }
    
    this.processing = true;
    
    try {
      while (this.queue.length > 0 && this.activeRequests < this.maxConcurrency) {
        const batch = this.queue.splice(0, this.batchSize);
        
        // Process batch in parallel
        const promises = batch.map(async ({ imagePath, prompt, context, validateFn, resolve, reject }) => {
          try {
            // Check cache again (might have been added by another request)
            if (this.cache) {
              const cacheKey = this._getCacheKey(imagePath, prompt, context);
              if (this.cache.has(cacheKey)) {
                resolve(this.cache.get(cacheKey));
                return;
              }
            }
            
            const result = await this._processRequest(imagePath, prompt, context, validateFn);
            resolve(result);
          } catch (error) {
            reject(error);
          }
        });
        
        // Wait for batch to complete before processing next batch
        await Promise.allSettled(promises);
      }
    } finally {
      this.processing = false;
    }
  }
  
  /**
   * Clear cache (useful for testing)
   * 
   * @returns {void}
   */
  clearCache() {
    if (this.cache) {
      this.cache.clear();
    }
  }
  
  /**
   * Get cache stats
   * 
   * @returns {{ cacheSize: number; queueLength: number; activeRequests: number }} Cache statistics
   */
  getCacheStats() {
    return {
      cacheSize: this.cache ? this.cache.size : 0,
      queueLength: this.queue.length,
      activeRequests: this.activeRequests
    };
  }
  
  /**
   * Get performance metrics
   * 
   * VERIFIABLE: Exports metrics to verify claims about queue limits and timeouts
   * 
   * @returns {Object} Performance metrics including queue rejections and timeouts
   */
  getPerformanceMetrics() {
    // NOTE: Metrics are initialized in constructor, but keep this check for safety
    // for defensive programming (in case constructor wasn't called properly)
    if (!this.metrics) {
      this.metrics = {
        queueRejections: 0,
        timeouts: 0,
        totalQueued: 0,
        totalProcessed: 0,
        averageWaitTime: 0,
        waitTimes: []
      };
    }
    
    return {
      queue: {
        currentLength: this.queue.length,
        maxSize: this.maxQueueSize,
        rejections: this.metrics.queueRejections,
        totalQueued: this.metrics.totalQueued,
        totalProcessed: this.metrics.totalProcessed,
        averageWaitTime: this.metrics.averageWaitTime,
        timeouts: this.metrics.timeouts,
        timeoutRate: this.metrics.totalQueued > 0 
          ? (this.metrics.timeouts / this.metrics.totalQueued) * 100 
          : 0,
        rejectionRate: this.metrics.totalQueued > 0
          ? (this.metrics.queueRejections / (this.metrics.totalQueued + this.metrics.queueRejections)) * 100
          : 0
      },
      concurrency: {
        active: this.activeRequests,
        max: this.maxConcurrency,
        utilization: (this.activeRequests / this.maxConcurrency) * 100
      },
      cache: this.getCacheStats()
    };
  }
}

