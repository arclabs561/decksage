/**
 * Human Validation Manager
 * 
 * Cleverly integrates human validation into the evaluation pipeline:
 * - Non-blocking: Doesn't slow down evaluations
 * - Automatic: Collects VLLM judgments when enabled
 * - Smart sampling: Requests human validation for interesting cases
 * - Learning: Automatically calibrates based on collected data
 * - Seamless: Works with all existing systems (batching, temporal, personas)
 */

import { warn, log } from './logger.mjs';
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync } from 'fs';
import { join } from 'path';

// Lazy import to avoid circular dependencies
let humanValidationModule = null;
async function getHumanValidationModule() {
  if (!humanValidationModule) {
    humanValidationModule = await import('../evaluation/human-validation/human-validation.mjs');
  }
  return humanValidationModule;
}

/**
 * Human Validation Manager
 * 
 * Manages human validation collection and calibration
 */
export class HumanValidationManager {
  /**
   * @param {{
   *   enabled?: boolean;
   *   autoCollect?: boolean;
   *   smartSampling?: boolean;
   *   calibrationThreshold?: number;
   *   humanValidatorFn?: (vllmResult: any) => Promise<any> | null;
   * }} [options={}] - Manager options
   */
  constructor(options = {}) {
    const {
      enabled = false,
      autoCollect = true, // Automatically collect VLLM judgments
      smartSampling = true, // Only request human validation for interesting cases
      calibrationThreshold = 0.7, // Minimum correlation for good calibration
      humanValidatorFn = null // Optional function to request human validation
    } = options;
    
    this.enabled = enabled;
    this.autoCollect = autoCollect;
    this.smartSampling = smartSampling;
    this.calibrationThreshold = calibrationThreshold;
    this.humanValidatorFn = humanValidatorFn;
    
    // Track VLLM judgments for calibration
    this.vllmJudgments = [];
    this.pendingValidations = new Map(); // Track pending human validations
    
    // Calibration cache
    this.calibrationCache = null;
    this.calibrationCachePath = null; // Will be set after loading module
    // Load calibration cache asynchronously
    this._loadCalibrationCache().catch(() => {
      // Silently fail - will retry later
    });
  }
  
  /**
   * Load calibration cache
   */
  async _loadCalibrationCache() {
    try {
      const humanValidation = await getHumanValidationModule();
      const VALIDATION_DIR = humanValidation.VALIDATION_DIR;
      
      // Ensure validation directory exists
      if (!existsSync(VALIDATION_DIR)) {
        mkdirSync(VALIDATION_DIR, { recursive: true });
      }
      
      if (!this.calibrationCachePath) {
        this.calibrationCachePath = join(VALIDATION_DIR, 'calibration-cache.json');
      }
      
      if (existsSync(this.calibrationCachePath)) {
        try {
          this.calibrationCache = JSON.parse(readFileSync(this.calibrationCachePath, 'utf-8'));
        } catch (error) {
          warn('Failed to load calibration cache:', error.message);
          this.calibrationCache = null;
        }
      }
    } catch (error) {
      // Silently fail if module not available
      this.calibrationCache = null;
    }
  }
  
  /**
   * Save calibration cache
   */
  async _saveCalibrationCache() {
    const humanValidation = await getHumanValidationModule();
    const VALIDATION_DIR = humanValidation.VALIDATION_DIR;
    
    if (!this.calibrationCachePath) {
      this.calibrationCachePath = join(VALIDATION_DIR, 'calibration-cache.json');
    }
    
    if (!existsSync(VALIDATION_DIR)) {
      mkdirSync(VALIDATION_DIR, { recursive: true });
    }
    try {
      writeFileSync(this.calibrationCachePath, JSON.stringify(this.calibrationCache, null, 2));
    } catch (error) {
      warn('Failed to save calibration cache:', error.message);
    }
  }
  
  /**
   * Check if result should trigger human validation (smart sampling)
   */
  _shouldRequestHumanValidation(vllmResult) {
    if (!this.smartSampling) return true; // Request all if not using smart sampling
    
    // Request human validation for:
    // 1. Edge cases (very high or very low scores)
    const score = vllmResult.score;
    if (score !== null && (score <= 3 || score >= 9)) {
      return true;
    }
    
    // 2. High uncertainty (if available)
    if (vllmResult.uncertainty && vllmResult.uncertainty > 0.3) {
      return true;
    }
    
    // 3. Many issues detected (might be over-detection)
    if (vllmResult.issues && vllmResult.issues.length >= 5) {
      return true;
    }
    
    // 4. No issues but low score (might be under-detection)
    if (vllmResult.issues && vllmResult.issues.length === 0 && score !== null && score < 6) {
      return true;
    }
    
    // 5. Random sampling (10% of cases)
    if (Math.random() < 0.1) {
      return true;
    }
    
    return false;
  }
  
  /**
   * Collect VLLM judgment (non-blocking)
   * 
   * @param {import('./index.mjs').ValidationResult} vllmResult - VLLM validation result
   * @param {string} imagePath - Screenshot path
   * @param {string} prompt - Evaluation prompt
   * @param {import('./index.mjs').ValidationContext} context - Validation context
   */
  async collectVLLMJudgment(vllmResult, imagePath, prompt, context = {}) {
    if (!this.enabled || !this.autoCollect) return;
    
    // Generate unique ID
    const id = context.validationId || `vllm-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    // Store VLLM judgment with temporal and experience context
    const vllmJudgment = {
      id,
      screenshot: imagePath,
      prompt,
      vllmScore: vllmResult.score,
      vllmIssues: vllmResult.issues || [],
      vllmReasoning: vllmResult.reasoning || vllmResult.assessment || '',
      provider: vllmResult.provider || 'unknown',
      timestamp: new Date().toISOString(),
      // NEW: Store temporal and experience context for late interaction
      temporalNotes: context.temporalNotes || null,
      aggregatedNotes: context.aggregatedNotes || null,
      experienceTrace: context.experienceTrace || null,
      context: {
        testType: context.testType,
        viewport: context.viewport,
        persona: context.persona?.name,
        stage: context.stage,
        step: context.step,
        interaction: context.interaction,
        sessionId: context.sessionId,
        experienceTrace: context.experienceTrace?.sessionId || null
      }
    };
    
    this.vllmJudgments.push(vllmJudgment);
    
    // Request human validation if smart sampling says so
    if (this._shouldRequestHumanValidation(vllmResult) && this.humanValidatorFn) {
      // Non-blocking: Don't wait for human validation
      this._requestHumanValidation(vllmJudgment).catch(error => {
        warn('Failed to request human validation:', error.message);
      });
    }
    
    // Auto-save periodically (every 10 judgments) - non-blocking
    if (this.vllmJudgments.length % 10 === 0) {
      // Don't await - save in background to avoid blocking
      this._saveVLLMJudgments().catch(error => {
        warn('Failed to auto-save VLLM judgments:', error.message);
      });
    }
  }
  
  /**
   * Request human validation (non-blocking)
   * 
   * If humanValidatorFn is provided, uses it. Otherwise, queues the judgment
   * for later review via the real-human-feedback tool.
   */
  async _requestHumanValidation(vllmJudgment) {
    if (this.humanValidatorFn) {
      // Use provided validator function
      try {
        // Call human validator function (can be async, can return null)
        const humanResult = await Promise.resolve(this.humanValidatorFn(vllmJudgment));
        
        if (humanResult) {
          // Store human judgment
          const humanJudgment = {
            id: vllmJudgment.id,
            screenshot: vllmJudgment.screenshot,
            prompt: vllmJudgment.prompt,
            humanScore: humanResult.score,
            humanIssues: humanResult.issues || [],
            humanReasoning: humanResult.reasoning || '',
            timestamp: new Date().toISOString(),
            evaluatorId: humanResult.evaluatorId
          };
          
          const humanValidation = await getHumanValidationModule();
          humanValidation.collectHumanJudgment(humanJudgment);
          
          // Update calibration cache
          this._updateCalibrationCache(vllmJudgment, humanJudgment);
        }
      } catch (error) {
        // Silently fail - human validation is optional
        warn('Human validation request failed:', error.message);
      }
    } else {
      // No validator function - queue for later review
      // The judgment is already saved to disk, so it will be available
      // when the user runs: node evaluation/human-validation/real-human-feedback.mjs
      log(`[Human Validation] Queued judgment ${vllmJudgment.id} for human review`);
      log(`[Human Validation] Run 'node evaluation/human-validation/real-human-feedback.mjs' to review`);
    }
  }
  
  /**
   * Update calibration cache with new human judgment
   */
  async _updateCalibrationCache(vllmJudgment, humanJudgment) {
    if (!this.calibrationCache) {
      this.calibrationCache = {
        judgments: [],
        lastCalibration: null,
        stats: {
          total: 0,
          agreements: 0,
          disagreements: 0
        }
      };
    }
    
    this.calibrationCache.judgments.push({
      vllm: vllmJudgment,
      human: humanJudgment,
      timestamp: new Date().toISOString()
    });
    
    // Update stats
    this.calibrationCache.stats.total++;
    const scoreDiff = Math.abs(vllmJudgment.vllmScore - humanJudgment.humanScore);
    if (scoreDiff <= 1) {
      this.calibrationCache.stats.agreements++;
    } else {
      this.calibrationCache.stats.disagreements++;
    }
    
    // Recalibrate if we have enough data (every 20 judgments)
    if (this.calibrationCache.judgments.length % 20 === 0) {
      await this._recalibrate();
    } else {
      await this._saveCalibrationCache();
    }
  }
  
  /**
   * Recalibrate based on collected judgments
   */
  async _recalibrate() {
    if (!this.calibrationCache || this.calibrationCache.judgments.length < 10) {
      return; // Need at least 10 judgments
    }
    
    try {
      const humanValidation = await getHumanValidationModule();
      const humanJudgments = this.calibrationCache.judgments.map(j => j.human);
      const vllmJudgments = this.calibrationCache.judgments.map(j => j.vllm);
      
      const calibration = humanValidation.compareJudgments(humanJudgments, vllmJudgments);
      
      this.calibrationCache.lastCalibration = {
        ...calibration,
        timestamp: new Date().toISOString(),
        sampleSize: this.calibrationCache.judgments.length
      };
      
      // Save calibration results
      const humanValidationModule = await getHumanValidationModule();
      humanValidationModule.saveCalibrationResults(calibration);
      
      // Log calibration status
      const correlation = calibration.agreement.pearson;
      if (correlation >= this.calibrationThreshold) {
        log(`[Human Validation] Good calibration: r=${correlation.toFixed(3)}, κ=${calibration.agreement.kappa.toFixed(3)}`);
      } else {
        warn(`[Human Validation] Poor calibration: r=${correlation.toFixed(3)}, κ=${calibration.agreement.kappa.toFixed(3)}`);
        warn(`[Human Validation] Recommendations: ${calibration.recommendations.join('; ')}`);
      }
      
      await this._saveCalibrationCache();
    } catch (error) {
      warn('Failed to recalibrate:', error.message);
    }
  }
  
  /**
   * Get calibration status
   */
  getCalibrationStatus() {
    if (!this.calibrationCache || !this.calibrationCache.lastCalibration) {
      return {
        calibrated: false,
        message: 'No calibration data available'
      };
    }
    
    const cal = this.calibrationCache.lastCalibration;
    const correlation = cal.agreement.pearson;
    
    return {
      calibrated: true,
      correlation,
      kappa: cal.agreement.kappa,
      mae: cal.agreement.mae,
      isGood: correlation >= this.calibrationThreshold,
      sampleSize: cal.sampleSize,
      recommendations: cal.recommendations,
      lastCalibration: cal.timestamp
    };
  }
  
  /**
   * Apply calibration adjustments to VLLM score
   * 
   * @param {number} vllmScore - Original VLLM score
   * @returns {number} Calibrated score
   */
  applyCalibration(vllmScore) {
    if (!this.calibrationCache || !this.calibrationCache.lastCalibration) {
      return vllmScore; // No calibration available
    }
    
    const bias = this.calibrationCache.lastCalibration.bias.scoreBias;
    
    // Apply bias correction (simple linear adjustment)
    // More sophisticated calibration could use logistic regression
    const calibrated = vllmScore - bias;
    
    // Clamp to valid range
    return Math.max(0, Math.min(10, calibrated));
  }
  
  /**
   * Save VLLM judgments to disk
   */
  async _saveVLLMJudgments() {
    const humanValidation = await getHumanValidationModule();
    const VALIDATION_DIR = humanValidation.VALIDATION_DIR;
    
    if (!existsSync(VALIDATION_DIR)) {
      mkdirSync(VALIDATION_DIR, { recursive: true });
    }
    
    const path = join(VALIDATION_DIR, `vllm-judgments-${Date.now()}.json`);
    try {
      writeFileSync(path, JSON.stringify({
        timestamp: new Date().toISOString(),
        judgments: this.vllmJudgments
      }, null, 2));
      
      // Clear in-memory cache after saving (keep last 100)
      if (this.vllmJudgments.length > 100) {
        this.vllmJudgments = this.vllmJudgments.slice(-100);
      }
    } catch (error) {
      warn('Failed to save VLLM judgments:', error.message);
    }
  }
  
  /**
   * Load existing VLLM judgments
   */
  loadVLLMJudgments() {
    // Load from disk if needed
    // This is called when manager is initialized
    return this.vllmJudgments;
  }
  
  /**
   * Manually trigger calibration
   */
  async calibrate() {
    const humanValidation = await getHumanValidationModule();
    const VALIDATION_DIR = humanValidation.VALIDATION_DIR;
    
    // Load all human judgments
    const humanJudgments = [];
    
    if (existsSync(VALIDATION_DIR)) {
      const files = readdirSync(VALIDATION_DIR);
      for (const file of files) {
        if (file.startsWith('human-') && file.endsWith('.json')) {
          try {
            const id = file.replace('human-', '').replace('.json', '');
            const judgment = humanValidation.loadHumanJudgment(id);
            if (judgment) {
              humanJudgments.push(judgment);
            }
          } catch (error) {
            // Skip invalid files
          }
        }
      }
    }
    
    // Match with VLLM judgments
    const vllmJudgments = this.vllmJudgments.filter(v => 
      humanJudgments.some(h => h.id === v.id)
    );
    const matchedHumanJudgments = humanJudgments.filter(h =>
      vllmJudgments.some(v => v.id === h.id)
    );
    
    if (matchedHumanJudgments.length === 0 || vllmJudgments.length === 0) {
      return {
        success: false,
        message: 'No matched judgments found for calibration'
      };
    }
    
    const calibration = humanValidation.compareJudgments(matchedHumanJudgments, vllmJudgments);
    humanValidation.saveCalibrationResults(calibration);
    
    this.calibrationCache = {
      ...this.calibrationCache,
      lastCalibration: {
        ...calibration,
        timestamp: new Date().toISOString(),
        sampleSize: matchedHumanJudgments.length
      }
    };
    await this._saveCalibrationCache();
    
    return {
      success: true,
      calibration,
      sampleSize: matchedHumanJudgments.length
    };
  }
}

/**
 * Global human validation manager instance
 */
let globalHumanValidationManager = null;

/**
 * Get or create global human validation manager
 * 
 * @param {Object} options - Manager options
 * @returns {HumanValidationManager} Manager instance
 */
export function getHumanValidationManager(options = {}) {
  if (!globalHumanValidationManager) {
    globalHumanValidationManager = new HumanValidationManager(options);
  }
  return globalHumanValidationManager;
}

/**
 * Initialize human validation (call this to enable)
 * 
 * @param {Object} options - Manager options
 * @returns {HumanValidationManager} Manager instance
 */
export function initHumanValidation(options = {}) {
  globalHumanValidationManager = new HumanValidationManager({
    enabled: true,
    ...options
  });
  return globalHumanValidationManager;
}

