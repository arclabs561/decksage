/**
 * Batch Validator
 * 
 * Enhanced BatchOptimizer with cost tracking and statistics
 * 
 * Provides:
 * - All BatchOptimizer functionality
 * - Cost tracking integration
 * - Performance statistics
 * - Success rate tracking
 */

import { BatchOptimizer } from '../batch-optimizer.mjs';
import { getCostTracker } from '../cost-tracker.mjs';

/**
 * Batch validator with cost tracking
 */
export class BatchValidator extends BatchOptimizer {
  constructor(options = {}) {
    super({
      maxConcurrency: options.maxConcurrency || 5,
      batchSize: options.batchSize || 3,
      cacheEnabled: options.cacheEnabled !== false,
      ...options
    });
    this.costTracker = getCostTracker();
    this.trackCosts = options.trackCosts !== false;
    this.trackStats = options.trackStats !== false;
    this.stats = {
      totalRequests: 0,
      totalDuration: 0,
      successfulRequests: 0,
      failedRequests: 0,
      minDuration: Infinity,
      maxDuration: 0
    };
  }

  /**
   * Validate multiple screenshots with cost tracking
   */
  async batchValidate(screenshots, prompt, context = {}) {
    const startTime = Date.now();
    
    const results = await super.batchValidate(screenshots, prompt, context);
    
    const duration = Date.now() - startTime;
    
    // Track costs
    if (this.trackCosts && this.costTracker) {
      const screenshotsArray = Array.isArray(screenshots) ? screenshots : [screenshots];
      results.forEach((result, index) => {
        if (result.estimatedCost) {
          try {
            this.costTracker.recordCost({
              provider: result.provider,
              cost: result.estimatedCost.total || 0,
              tokens: result.estimatedCost.tokens || 0,
              testType: context.testType || 'batch',
              screenshot: screenshotsArray[index]
            });
          } catch (error) {
            // Silently fail cost tracking to avoid breaking validation
            // Could log warning in production
          }
        }
      });
    }
    
    // Track stats
    if (this.trackStats) {
      this.stats.totalRequests += results.length;
      this.stats.totalDuration += duration;
      this.stats.minDuration = Math.min(this.stats.minDuration, duration);
      this.stats.maxDuration = Math.max(this.stats.maxDuration, duration);
      
      results.forEach(result => {
        if (result.error) {
          this.stats.failedRequests++;
        } else {
          this.stats.successfulRequests++;
        }
      });
    }
    
    return {
      results,
      stats: this.trackStats ? {
        total: screenshots.length,
        passed: results.filter(r => (r.score || 0) >= (context.passingScore || 7)).length,
        failed: results.filter(r => (r.score || 0) < (context.passingScore || 7)).length,
        duration,
        costStats: this.trackCosts && this.costTracker ? this.costTracker.getStats() : null,
        performance: this.trackStats ? {
          totalRequests: this.stats.totalRequests,
          avgDuration: this.stats.totalRequests > 0 ? this.stats.totalDuration / this.stats.totalRequests : 0,
          minDuration: this.stats.minDuration === Infinity ? 0 : this.stats.minDuration,
          maxDuration: this.stats.maxDuration,
          successRate: this.stats.totalRequests > 0 ? this.stats.successfulRequests / this.stats.totalRequests : 0
        } : null
      } : null
    };
  }

  /**
   * Get cost statistics
   */
  getCostStats() {
    if (!this.costTracker) {
      return null;
    }
    return this.costTracker.getStats();
  }

  /**
   * Get performance statistics
   */
  getPerformanceStats() {
    return {
      totalRequests: this.stats.totalRequests,
      avgDuration: this.stats.totalRequests > 0 ? this.stats.totalDuration / this.stats.totalRequests : 0,
      minDuration: this.stats.minDuration === Infinity ? 0 : this.stats.minDuration,
      maxDuration: this.stats.maxDuration,
      successRate: this.stats.totalRequests > 0 ? this.stats.successfulRequests / this.stats.totalRequests : 0
    };
  }

  /**
   * Reset statistics
   */
  resetStats() {
    this.stats = {
      totalRequests: 0,
      totalDuration: 0,
      successfulRequests: 0,
      failedRequests: 0,
      minDuration: Infinity,
      maxDuration: 0
    };
  }
}

