/**
 * Cost Tracking Utilities
 * 
 * Tracks API costs over time, provides cost estimates, and helps optimize spending.
 */

import { getCached, setCached } from './cache.mjs';

/**
 * Cost Tracker Class
 * 
 * Tracks costs across multiple validations and provides cost analysis.
 */
export class CostTracker {
  constructor(options = {}) {
    this.storageKey = options.storageKey || 'ai-visual-test-costs';
    this.maxHistory = options.maxHistory || 1000;
    this.costs = this.loadCosts();
  }

  /**
   * Load costs from cache/storage
   */
  loadCosts() {
    try {
      const cached = getCached(this.storageKey, 'cost-tracker', {});
      return cached || { history: [], totals: {}, byProvider: {} };
    } catch {
      return { history: [], totals: {}, byProvider: {} };
    }
  }

  /**
   * Save costs to cache/storage
   */
  saveCosts() {
    try {
      setCached(this.storageKey, 'cost-tracker', this.costs, {});
    } catch {
      // Silently fail if cache unavailable
    }
  }

  /**
   * Record a cost
   * 
   * @param {{
   *   provider: string;
   *   cost: number;
   *   inputTokens?: number;
   *   outputTokens?: number;
   *   timestamp?: number;
   *   testName?: string;
   * }} costData - Cost data to record
   */
  recordCost(costData) {
    const {
      provider,
      cost,
      inputTokens = 0,
      outputTokens = 0,
      timestamp = Date.now(),
      testName = 'unknown'
    } = costData;

    if (cost === null || cost === undefined) return; // Skip null costs

    const entry = {
      provider,
      cost,
      inputTokens,
      outputTokens,
      timestamp,
      testName,
      date: new Date(timestamp).toISOString().split('T')[0] // YYYY-MM-DD
    };

    // Add to history
    this.costs.history.push(entry);

    // Trim history if too long
    if (this.costs.history.length > this.maxHistory) {
      this.costs.history = this.costs.history.slice(-this.maxHistory);
    }

    // Update totals
    this.costs.totals.total = (this.costs.totals.total || 0) + cost;
    this.costs.totals.count = (this.costs.totals.count || 0) + 1;

    // Update by provider
    if (!this.costs.byProvider[provider]) {
      this.costs.byProvider[provider] = { total: 0, count: 0, inputTokens: 0, outputTokens: 0 };
    }
    this.costs.byProvider[provider].total += cost;
    this.costs.byProvider[provider].count += 1;
    this.costs.byProvider[provider].inputTokens += inputTokens;
    this.costs.byProvider[provider].outputTokens += outputTokens;

    // Update by date
    if (!this.costs.byDate) {
      this.costs.byDate = {};
    }
    if (!this.costs.byDate[entry.date]) {
      this.costs.byDate[entry.date] = { total: 0, count: 0 };
    }
    this.costs.byDate[entry.date].total += cost;
    this.costs.byDate[entry.date].count += 1;

    this.saveCosts();
  }

  /**
   * Get cost statistics
   * 
   * @returns {{
   *   total: number;
   *   count: number;
   *   average: number;
   *   byProvider: Record<string, { total: number; count: number; average: number }>;
   *   byDate: Record<string, { total: number; count: number }>;
   *   recent: Array<{ provider: string; cost: number; timestamp: number }>;
   * }} Cost statistics
   */
  getStats() {
    const stats = {
      total: this.costs.totals.total || 0,
      count: this.costs.totals.count || 0,
      average: 0,
      byProvider: {},
      byDate: this.costs.byDate || {},
      recent: this.costs.history.slice(-10).map(e => ({
        provider: e.provider,
        cost: e.cost,
        timestamp: e.timestamp,
        testName: e.testName
      }))
    };

    if (stats.count > 0) {
      stats.average = stats.total / stats.count;
    }

    // Calculate averages by provider
    for (const [provider, data] of Object.entries(this.costs.byProvider)) {
      stats.byProvider[provider] = {
        total: data.total,
        count: data.count,
        average: data.count > 0 ? data.total / data.count : 0,
        inputTokens: data.inputTokens,
        outputTokens: data.outputTokens
      };
    }

    return stats;
  }

  /**
   * Get cost projection
   * 
   * @param {number} [days=30] - Number of days to project
   * @returns {{ projected: number; dailyAverage: number; trend: 'increasing' | 'decreasing' | 'stable' }} Projection
   */
  getProjection(days = 30) {
    const stats = this.getStats();
    const dailyAverage = stats.byDate ? 
      Object.values(stats.byDate).reduce((sum, day) => sum + day.total, 0) / 
      Math.max(Object.keys(stats.byDate).length, 1) : 0;
    
    const projected = dailyAverage * days;

    // Simple trend detection (last 7 days vs previous 7 days)
    const dates = Object.keys(stats.byDate || {}).sort().slice(-14);
    let trend = 'stable';
    if (dates.length >= 14) {
      const recent = dates.slice(-7).reduce((sum, d) => sum + (stats.byDate[d]?.total || 0), 0);
      const previous = dates.slice(0, 7).reduce((sum, d) => sum + (stats.byDate[d]?.total || 0), 0);
      if (recent > previous * 1.1) trend = 'increasing';
      else if (recent < previous * 0.9) trend = 'decreasing';
    }

    return { projected, dailyAverage, trend };
  }

  /**
   * Check if cost exceeds threshold
   * 
   * @param {number} threshold - Cost threshold
   * @returns {{ exceeded: boolean; current: number; remaining: number }} Threshold check
   */
  checkThreshold(threshold) {
    const current = this.getStats().total;
    return {
      exceeded: current >= threshold,
      current,
      remaining: Math.max(0, threshold - current)
    };
  }

  /**
   * Reset cost tracking
   */
  reset() {
    this.costs = { history: [], totals: {}, byProvider: {}, byDate: {} };
    this.saveCosts();
  }

  /**
   * Export cost data
   * 
   * @returns {object} Cost data for export
   */
  export() {
    return {
      ...this.costs,
      stats: this.getStats(),
      projection: this.getProjection(30)
    };
  }
}

/**
 * Global cost tracker instance
 */
let globalCostTracker = null;

/**
 * Get or create global cost tracker
 * 
 * @param {object} [options] - Cost tracker options
 * @returns {CostTracker} Cost tracker instance
 */
export function getCostTracker(options = {}) {
  if (!globalCostTracker) {
    globalCostTracker = new CostTracker(options);
  }
  return globalCostTracker;
}

/**
 * Record cost (convenience function)
 * 
 * @param {object} costData - Cost data
 */
export function recordCost(costData) {
  const tracker = getCostTracker();
  tracker.recordCost(costData);
}

/**
 * Get cost statistics (convenience function)
 * 
 * @returns {object} Cost statistics
 */
export function getCostStats() {
  return getCostTracker().getStats();
}

