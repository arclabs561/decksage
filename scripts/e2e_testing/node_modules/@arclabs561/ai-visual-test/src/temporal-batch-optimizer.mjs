/**
 * Temporal Batch Optimizer
 * 
 * Adaptive batching that considers temporal dependencies and human perception.
 * 
 * Research context (loosely related):
 * - Efficient Sequential Decision Making (arXiv:2406.12125)
 *   * Paper focuses on online model selection (NOT implemented here)
 *   * We use temporal dependency concepts inspired by sequential decision aspects
 *   * We do NOT implement the paper's core online model selection algorithm
 * - Serving LLM Reasoning Efficiently (arXiv:2505.13326)
 *   * Paper discusses "short and right" thinking management (NOT implemented here)
 *   * We do adaptive batching with temporal awareness (loosely related concept)
 *   * We do NOT implement the paper's specific adaptive batching strategy
 * - Human Time Perception (NN/g, PMC)
 *   * 0.1s threshold for direct manipulation (used in time scales)
 *   * Attention affects temporal perception (used in weighting)
 * 
 * IMPORTANT: This implements temporal-aware batching with dependencies, but does NOT
 * implement the core algorithms from the cited papers. The citations are for loosely
 * related concepts, not direct implementations.
 */

import { BatchOptimizer } from './batch-optimizer.mjs';

/**
 * Temporal Batch Optimizer
 * Extends BatchOptimizer with temporal awareness
 */
export class TemporalBatchOptimizer extends BatchOptimizer {
  constructor(options = {}) {
    super(options);
    this.temporalDependencies = new Map(); // Track dependencies
    this.sequentialContext = options.sequentialContext || null;
    this.adaptiveBatching = options.adaptiveBatching !== false;
  }
  
  /**
   * Add request with temporal dependencies
   */
  async addTemporalRequest(imagePath, prompt, context, dependencies = []) {
    // Track dependencies
    this.temporalDependencies.set(imagePath, {
      dependencies,
      timestamp: Date.now(),
      priority: this.calculatePriority(dependencies, context)
    });
    
    return this._queueRequest(imagePath, prompt, context);
  }
  
  /**
   * Calculate priority based on temporal dependencies
   */
  calculatePriority(dependencies, context) {
    // Higher priority for:
    // - No dependencies (can run in parallel)
    // - Earlier timestamps (sequential order)
    // - Critical evaluations (high importance)
    
    let priority = 0;
    
    // No dependencies = can run immediately
    if (dependencies.length === 0) {
      priority += 100;
    } else {
      // Dependencies reduce priority (must wait)
      priority -= dependencies.length * 10;
    }
    
    // Earlier timestamps get higher priority (decay over time)
    if (context.timestamp) {
      const age = Date.now() - context.timestamp;
      // Earlier requests (older timestamp = larger age) should have higher priority
      // But we want to decay this over time, so very old requests get lower priority
      // For requests within reasonable time window, earlier = higher priority
      if (age < 60000) { // Within 1 minute
        priority += Math.max(0, 30 - age / 1000); // Earlier = higher, but decays
      }
    }
    
    // Critical evaluations get higher priority
    if (context.critical || context.testType === 'critical') {
      priority += 50;
    }
    
    return priority;
  }
  
  /**
   * Process queue with temporal awareness
   */
  async _processQueue() {
    if (this.processing || this.queue.length === 0) {
      return;
    }
    
    this.processing = true;
    
    try {
      // Sort by priority and dependencies
      const sortedQueue = this.sortByTemporalDependencies([...this.queue]);
      
      // Process in batches, respecting dependencies
      while (sortedQueue.length > 0 && this.activeRequests < this.maxConcurrency) {
        const batch = this.selectTemporalBatch(sortedQueue);
        
        // Remove from queue
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
            
            // Add sequential context if available
            if (this.sequentialContext) {
              context = {
                ...context,
                sequentialContext: this.sequentialContext.getContext()
              };
            }
            
            const result = await this._processRequest(imagePath, prompt, context, validateFn);
            
            // Update sequential context
            if (this.sequentialContext && result.score !== null) {
              this.sequentialContext.addDecision({
                score: result.score,
                issues: result.issues || [],
                assessment: result.assessment,
                reasoning: result.reasoning
              });
            }
            
            resolve(result);
          } catch (error) {
            reject(error);
          }
        });
        
        await Promise.allSettled(promises);
      }
    } finally {
      this.processing = false;
    }
  }
  
  /**
   * Sort queue by temporal dependencies
   */
  sortByTemporalDependencies(queue) {
    return queue.sort((a, b) => {
      const depsA = this.temporalDependencies.get(a.imagePath);
      const depsB = this.temporalDependencies.get(b.imagePath);
      
      // No dependencies come first
      if (!depsA && depsB) return -1;
      if (depsA && !depsB) return 1;
      if (!depsA && !depsB) return 0;
      
      // Compare priorities
      return depsB.priority - depsA.priority;
    });
  }
  
  /**
   * Select batch considering temporal dependencies
   */
  selectTemporalBatch(sortedQueue) {
    if (!this.adaptiveBatching) {
      // Fixed batch size
      return sortedQueue.splice(0, this.batchSize);
    }
    
    // Adaptive batch selection
    const batch = [];
    const processed = new Set();
    
    for (const item of sortedQueue) {
      if (batch.length >= this.batchSize) break;
      if (processed.has(item.imagePath)) continue;
      
      const deps = this.temporalDependencies.get(item.imagePath);
      
      // Check if dependencies are satisfied
      if (!deps || deps.dependencies.every(dep => processed.has(dep))) {
        batch.push(item);
        processed.add(item.imagePath);
      }
    }
    
    return batch;
  }
  
  /**
   * Get temporal statistics
   */
  getTemporalStats() {
    return {
      ...this.getCacheStats(),
      dependencies: this.temporalDependencies.size,
      sequentialContext: this.sequentialContext
        ? {
            historyLength: this.sequentialContext.history.length,
            patterns: this.sequentialContext.identifyPatterns()
          }
        : null
    };
  }
}

