/**
 * Latency-Aware Batch Optimizer
 *
 * Adaptive batching that considers latency requirements for fast reactive games.
 *
 * Key features:
 * - Bypasses batching for critical requests (<100ms requirement)
 * - Adaptive batch sizing based on latency requirements
 * - Deadline-based scheduling
 * - Priority queue for fast games
 */

import { BatchOptimizer } from './batch-optimizer.mjs';

/**
 * Latency-Aware Batch Optimizer
 *
 * Extends BatchOptimizer with latency awareness for fast reactive games.
 */
export class LatencyAwareBatchOptimizer extends BatchOptimizer {
  /**
   * @param {{
   *   maxConcurrency?: number;
   *   batchSize?: number;
   *   cacheEnabled?: boolean;
   *   defaultMaxLatency?: number;
   *   adaptiveBatchSize?: boolean;
   * }} [options={}] - Optimizer options
   */
  constructor(options = {}) {
    super(options);
    this.defaultMaxLatency = options.defaultMaxLatency || 1000; // Default 1 second
    this.adaptiveBatchSize = options.adaptiveBatchSize !== false;
    this.criticalRequests = new Set(); // Track critical requests
  }

  /**
   * Add request with latency requirement
   *
   * @param {string} imagePath - Screenshot path
   * @param {string} prompt - Validation prompt
   * @param {import('./index.mjs').ValidationContext} [context={}] - Validation context
   * @param {number} [maxLatency=null] - Maximum acceptable latency in ms (null = use default)
   * @returns {Promise<import('./index.mjs').ValidationResult>} Validation result
   */
  async addRequest(imagePath, prompt, context = {}, maxLatency = null) {
    const latencyRequirement = maxLatency || context.maxLatency || this.defaultMaxLatency;
    const isCritical = latencyRequirement < 200; // Critical if <200ms

    if (isCritical) {
      this.criticalRequests.add(imagePath);
    }

    // If latency requirement is very tight, bypass batching
    if (latencyRequirement < 100) {
      // Process immediately, no batching
      return this._processRequest(imagePath, prompt, {
        ...context,
        maxLatency: latencyRequirement,
        critical: true
      });
    }

    // For slightly less critical requests, use adaptive batch size
    if (this.adaptiveBatchSize && latencyRequirement < 200) {
      // Use smaller batch size for fast games
      const originalBatchSize = this.batchSize;
      this.batchSize = 1; // Process one at a time for very fast games

      try {
        return await this._queueRequest(imagePath, prompt, {
          ...context,
          maxLatency: latencyRequirement,
          critical: isCritical
        });
      } finally {
        this.batchSize = originalBatchSize;
      }
    }

    // For normal requests, use standard batching
    return this._queueRequest(imagePath, prompt, {
      ...context,
      maxLatency: latencyRequirement
    });
  }

  /**
   * Process queue with latency awareness
   */
  async _processQueue() {
    if (this.processing || this.queue.length === 0 || this.activeRequests >= this.maxConcurrency) {
      return;
    }

    this.processing = true;

    try {
      // Sort queue by latency requirement (critical first)
      const sortedQueue = [...this.queue].sort((a, b) => {
        const latencyA = a.context?.maxLatency || this.defaultMaxLatency;
        const latencyB = b.context?.maxLatency || this.defaultMaxLatency;

        // Critical requests (low latency) come first
        if (latencyA < latencyB) return -1;
        if (latencyA > latencyB) return 1;

        // If same latency, process in order
        return 0;
      });

      while (sortedQueue.length > 0 && this.activeRequests < this.maxConcurrency) {
        // Calculate adaptive batch size based on latency requirements
        const batchSize = this.adaptiveBatchSize
          ? this._calculateAdaptiveBatchSize(sortedQueue)
          : this.batchSize;

        const batch = sortedQueue.splice(0, batchSize);

        // Remove from original queue
        batch.forEach(item => {
          const index = this.queue.findIndex(q => q.imagePath === item.imagePath);
          if (index >= 0) this.queue.splice(index, 1);
        });

        // Process batch
        const promises = batch.map(async ({ imagePath, prompt, context, validateFn, resolve, reject }) => {
          try {
            // Check cache
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
          } finally {
            // Remove from critical requests if processed
            this.criticalRequests.delete(imagePath);
          }
        });

        await Promise.allSettled(promises);
      }
    } finally {
      this.processing = false;
    }
  }

  /**
   * Calculate adaptive batch size based on latency requirements
   */
  _calculateAdaptiveBatchSize(queue) {
    if (queue.length === 0) return this.batchSize;

    // Get latency requirement of first request
    const firstLatency = queue[0].context?.maxLatency || this.defaultMaxLatency;

    // Very fast games (<100ms) - no batching
    if (firstLatency < 100) return 1;

    // Fast games (<200ms) - small batches
    if (firstLatency < 200) return 2;

    // Normal games - standard batch size
    return this.batchSize;
  }

  /**
   * Get latency-aware statistics
   */
  getLatencyStats() {
    return {
      ...this.getCacheStats(),
      criticalRequests: this.criticalRequests.size,
      queueLatencyRequirements: this.queue.map(q => ({
        imagePath: q.imagePath,
        maxLatency: q.context?.maxLatency || this.defaultMaxLatency,
        critical: (q.context?.maxLatency || this.defaultMaxLatency) < 200
      }))
    };
  }
}




