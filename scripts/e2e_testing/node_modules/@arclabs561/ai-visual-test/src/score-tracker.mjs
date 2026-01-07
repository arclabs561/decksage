/**
 * Score Tracker
 * 
 * Tracks test scores over time for regression detection and improvement tracking.
 * Stores baselines in JSON files for comparison.
 * 
 * General-purpose utility - no domain-specific logic.
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { warn } from './logger.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * Score Tracker Class
 * 
 * Tracks test scores over time for regression detection and improvement tracking.
 * 
 * @class ScoreTracker
 */
export class ScoreTracker {
  /**
   * @param {{
   *   baselineDir?: string;
   *   autoSave?: boolean;
   * }} [options={}] - Tracker options
   */
  constructor(options = {}) {
    const {
      baselineDir = join(process.cwd(), 'test-results', 'baselines'),
      autoSave = true
    } = options;
    
    this.baselineDir = baselineDir;
    this.autoSave = autoSave;
    this.baselineFile = join(baselineDir, 'scores.json');
    
    // Ensure baseline directory exists
    if (!existsSync(baselineDir)) {
      mkdirSync(baselineDir, { recursive: true });
    }
  }
  
  /**
   * Load baseline scores
   */
  _loadBaselines() {
    if (!existsSync(this.baselineFile)) {
      return {};
    }
    
    try {
      const content = readFileSync(this.baselineFile, 'utf8');
      if (!content || content.trim().length === 0) {
        return {};
      }
      return JSON.parse(content);
    } catch (error) {
      // SECURITY: Don't expose file paths or internal details in error
      warn(`[ScoreTracker] Failed to load baselines: ${error instanceof SyntaxError ? 'Invalid JSON format' : 'File read error'}`);
      return {};
    }
  }
  
  /**
   * Save baseline scores
   */
  _saveBaselines(baselines) {
    if (!this.autoSave) return;
    
    try {
      writeFileSync(this.baselineFile, JSON.stringify(baselines, null, 2), 'utf8');
    } catch (error) {
      warn(`[ScoreTracker] Failed to save baselines: ${error.message}`);
    }
  }
  
  /**
   * Record a test score
   * 
   * @param {string} testName - Name of the test
   * @param {number} score - Test score (0-10)
   * @param {Record<string, unknown>} [metadata={}] - Additional metadata
   * @returns {{ score: number; timestamp: string; metadata: Record<string, unknown> }} Recorded entry
   */
  record(testName, score, metadata = {}) {
    const baselines = this._loadBaselines();
    const now = new Date().toISOString();
    
    if (!baselines[testName]) {
      baselines[testName] = {
        history: [],
        current: null,
        baseline: null,
        firstRecorded: now,
        lastUpdated: now
      };
    }
    
    const entry = {
      score,
      timestamp: now,
      metadata
    };
    
    baselines[testName].history.push(entry);
    baselines[testName].current = score;
    baselines[testName].lastUpdated = now;
    
    // Set baseline if not set (first score becomes baseline)
    if (baselines[testName].baseline === null) {
      baselines[testName].baseline = score;
      baselines[testName].baselineSetAt = now;
    }
    
    // Keep only last 100 entries per test
    if (baselines[testName].history.length > 100) {
      baselines[testName].history = baselines[testName].history.slice(-100);
    }
    
    this._saveBaselines(baselines);
    return entry;
  }
  
  /**
   * Get baseline for a test
   * 
   * @param {string} testName - Name of the test
   * @returns {number | null} Baseline score or null if not set
   */
  getBaseline(testName) {
    const baselines = this._loadBaselines();
    return baselines[testName]?.baseline ?? null;
  }
  
  /**
   * Get current score for a test
   * 
   * @param {string} testName - Name of the test
   * @returns {number | null} Current score or null if not recorded
   */
  getCurrent(testName) {
    const baselines = this._loadBaselines();
    return baselines[testName]?.current ?? null;
  }
  
  /**
   * Compare current score with baseline
   * 
   * @param {string} testName - Name of the test
   * @param {number} currentScore - Current score to compare
   * @returns {{ hasBaseline: boolean; baseline: number | null; current: number; improved: boolean; delta: number; percentage: number } | null} Comparison result or null if no baseline
   */
  compare(testName, currentScore) {
    const baselines = this._loadBaselines();
    const testData = baselines[testName];
    
    if (!testData || testData.baseline === null) {
      return {
        hasBaseline: false,
        baseline: null,
        current: currentScore,
        delta: null,
        regression: false,
        improvement: false,
        trend: 'unknown'
      };
    }
    
    const baseline = testData.baseline;
    const delta = currentScore - baseline;
    const regression = delta < -1; // Score dropped by more than 1 point
    const improvement = delta > 1; // Score improved by more than 1 point
    
    // Calculate trend from recent history
    const recentScores = testData.history.slice(-10).map(e => e.score);
    const trend = recentScores.length >= 3 
      ? (recentScores[recentScores.length - 1] > recentScores[0] ? 'improving' : 
         recentScores[recentScores.length - 1] < recentScores[0] ? 'declining' : 'stable')
      : 'unknown';
    
    return {
      hasBaseline: true,
      baseline,
      current: currentScore,
      delta,
      regression,
      improvement,
      trend,
      history: testData.history.slice(-10) // Last 10 scores
    };
  }
  
  /**
   * Update baseline (e.g., after fixing issues)
   * 
   * @param {string} testName - Name of the test
   * @param {number | null} [newBaseline=null] - New baseline score, or null to use current score
   * @returns {boolean} True if baseline was updated
   */
  updateBaseline(testName, newBaseline = null) {
    const baselines = this._loadBaselines();
    if (!baselines[testName]) {
      return false;
    }
    
    if (newBaseline === null) {
      // Use current score as new baseline
      newBaseline = baselines[testName].current;
    }
    
    baselines[testName].baseline = newBaseline;
    baselines[testName].baselineSetAt = new Date().toISOString();
    this._saveBaselines(baselines);
    return true;
  }
  
  /**
   * Get all baselines
   */
  getAll() {
    return this._loadBaselines();
  }
  
  /**
   * Get baseline stats
   * 
   * @returns {import('./index.mjs').ScoreTracker['getStats']} Statistics object
   */
  getStats() {
    const baselines = this._loadBaselines();
    const stats = {
      totalTests: Object.keys(baselines).length,
      testsWithBaselines: 0,
      testsWithRegressions: 0,
      testsWithImprovements: 0,
      averageScore: 0,
      averageBaseline: 0
    };
    
    let totalScore = 0;
    let totalBaseline = 0;
    let count = 0;
    
    for (const [testName, testData] of Object.entries(baselines)) {
      if (testData.baseline !== null) {
        stats.testsWithBaselines++;
        totalBaseline += testData.baseline;
        
        if (testData.current !== null) {
          totalScore += testData.current;
          count++;
          
          const comparison = this.compare(testName, testData.current);
          if (comparison.regression) {
            stats.testsWithRegressions++;
          }
          if (comparison.improvement) {
            stats.testsWithImprovements++;
          }
        }
      }
    }
    
    if (count > 0) {
      stats.averageScore = totalScore / count;
      stats.averageBaseline = totalBaseline / stats.testsWithBaselines;
    }
    
    return stats;
  }
}

