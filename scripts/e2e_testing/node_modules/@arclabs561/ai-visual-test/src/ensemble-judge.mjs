/**
 * Ensemble Judging
 * 
 * Implements multiple LLM judges with consensus voting.
 * Research shows ensemble judging improves accuracy and reduces bias.
 * 
 * Supports:
 * - Multiple judges (different providers or prompts)
 * - Weighted voting
 * - Consensus calculation
 * - Disagreement analysis
 */

import { VLLMJudge } from './judge.mjs';
import { detectBias, detectPositionBias } from './bias-detector.mjs';

/**
 * Ensemble Judge Class
 * 
 * Manages multiple judges and aggregates their results.
 * 
 * @class EnsembleJudge
 */
export class EnsembleJudge {
  /**
   * @param {import('./index.mjs').EnsembleJudgeOptions} [options={}] - Ensemble configuration
   */
  constructor(options = {}) {
    const {
      judges = [],
      votingMethod = 'weighted_average', // 'weighted_average', 'majority', 'consensus', 'optimal'
      weights = null, // Array of weights for each judge
      judgeAccuracies = null, // Array of accuracy scores (0-1) for optimal weighting
      minAgreement = 0.7, // Minimum agreement for consensus
      enableBiasDetection = true
    } = options;
    
    this.judges = judges.length > 0 ? judges : [new VLLMJudge()];
    this.votingMethod = votingMethod;
    this.judgeAccuracies = judgeAccuracies; // For optimal weighting (arXiv:2510.01499)
    this.weights = weights || this.judges.map(() => 1.0);
    this.minAgreement = minAgreement;
    this.enableBiasDetection = enableBiasDetection;
    
    // Calculate weights based on method
    if (votingMethod === 'optimal' && this.judgeAccuracies) {
      this.weights = this.calculateOptimalWeights(this.judgeAccuracies);
    }
    
    // Normalize weights
    const weightSum = this.weights.reduce((a, b) => a + b, 0);
    this.normalizedWeights = this.weights.map(w => w / weightSum);
  }
  
  /**
   * Calculate optimal weights using inverse generalized sigmoid function
   * Research: arXiv:2510.01499 - ω_i = σ_K^{-1}(x_i) where σ_K(x) = e^x/(K-1+e^x)
   * 
   * CORRECTED: Uses generalized sigmoid σ_K(x) for N models, not standard logistic σ(x)
   * For K=2 models, this reduces to standard logistic. For K>2, the formula differs.
   * 
   * @param {number[]} accuracies - Array of accuracy scores (0-1) for each judge
   * @returns {number[]} Optimal weights
   */
  calculateOptimalWeights(accuracies) {
    const K = accuracies.length; // Number of models
    
    // Edge case: single judge gets weight 1.0
    if (K === 1) {
      return [1.0];
    }
    
    // Handle edge cases: p=0 → -∞, p=1 → +∞, so clamp to [0.001, 0.999]
    const clamped = accuracies.map(a => Math.max(0.001, Math.min(0.999, a)));
    
    // CORRECT formula: σ_K^{-1}(x) = ln(x(K-1) / (1-x))
    // This is the inverse of σ_K(x) = e^x/(K-1+e^x)
    const inverseSigmoid = clamped.map(p => {
      if (p <= 0 || p >= 1) return 0; // Safety check
      const numerator = p * (K - 1);
      const denominator = 1 - p;
      if (denominator <= 0 || numerator <= 0) return 0; // Safety check (handles K=1 case)
      const ratio = numerator / denominator;
      if (ratio <= 0) return 0; // Safety check for ln(0) or ln(negative)
      return Math.log(ratio);
    });
    
    // Normalize to positive weights (shift by min to make all positive, preserve ratios)
    const min = Math.min(...inverseSigmoid);
    const shifted = inverseSigmoid.map(w => {
      const shiftedValue = w - min + 1;
      // Ensure positive weight (clamp to minimum 0.001 to avoid zero weights)
      return Math.max(0.001, shiftedValue);
    });
    
    return shifted;
  }
  
  /**
   * Evaluate screenshot with ensemble of judges
   * 
   * @param {string} imagePath - Path to screenshot file
   * @param {string} prompt - Evaluation prompt
   * @param {import('./index.mjs').ValidationContext} [context={}] - Validation context
   * @returns {Promise<import('./index.mjs').EnsembleResult>} Ensemble evaluation result
   */
  async evaluate(imagePath, prompt, context = {}) {
    // Run all judges in parallel
    const judgments = await Promise.all(
      this.judges.map((judge, index) => 
        judge.judgeScreenshot(imagePath, prompt, {
          ...context,
          judgeIndex: index,
          judgeCount: this.judges.length
        }).catch(error => ({
          error: error.message,
          judgeIndex: index,
          score: null
        }))
      )
    );
    
    // Extract scores and results
    const results = judgments.map((judgment, index) => ({
      judgeIndex: index,
      score: judgment.score,
      assessment: judgment.assessment,
      issues: judgment.issues || [],
      reasoning: judgment.reasoning,
      provider: judgment.provider,
      error: judgment.error,
      raw: judgment
    }));
    
    // Aggregate results
    const aggregated = this.aggregateResults(results);
    
    // Detect biases if enabled
    if (this.enableBiasDetection) {
      aggregated.biasDetection = {
        individual: results.map(r => detectBias(r.reasoning || '')),
        position: detectPositionBias(results)
      };
    }
    
    // Calculate agreement
    aggregated.agreement = this.calculateAgreement(results);
    aggregated.disagreement = this.analyzeDisagreement(results);
    
    return {
      ...aggregated,
      individualJudgments: results,
      judgeCount: this.judges.length,
      votingMethod: this.votingMethod
    };
  }
  
  /**
   * Aggregate results based on voting method
   */
  aggregateResults(results) {
    const validResults = results.filter(r => r.score !== null && !r.error);
    
    if (validResults.length === 0) {
      return {
        score: null,
        assessment: 'error',
        issues: ['All judges failed'],
        reasoning: 'All judges encountered errors',
        confidence: 0
      };
    }
    
    switch (this.votingMethod) {
      case 'weighted_average':
      case 'optimal':
        return this.weightedAverage(validResults);
      case 'majority':
        return this.majorityVote(validResults);
      case 'consensus':
        return this.consensusVote(validResults);
      default:
        return this.weightedAverage(validResults);
    }
  }
  
  /**
   * Weighted average voting
   */
  weightedAverage(results) {
    const scores = results.map((r, i) => ({
      score: r.score,
      weight: this.normalizedWeights[r.judgeIndex] || 1.0 / results.length
    }));
    
    const weightedSum = scores.reduce((sum, s) => sum + (s.score * s.weight), 0);
    const totalWeight = scores.reduce((sum, s) => sum + s.weight, 0);
    const avgScore = totalWeight > 0 ? weightedSum / totalWeight : null;
    
    // Aggregate issues (union)
    const allIssues = new Set();
    results.forEach(r => {
      if (r.issues) r.issues.forEach(issue => allIssues.add(issue));
    });
    
    // Aggregate reasoning
    const reasoning = results
      .map((r, i) => `Judge ${i + 1} (${r.provider}): ${r.reasoning || 'No reasoning'}`)
      .join('\n\n');
    
    // Determine assessment
    const assessment = avgScore >= 7 ? 'pass' : avgScore >= 5 ? 'needs-improvement' : 'fail';
    
    return {
      score: Math.round(avgScore * 10) / 10, // Round to 1 decimal
      assessment,
      issues: Array.from(allIssues),
      reasoning: `Ensemble judgment (weighted average):\n${reasoning}`,
      confidence: this.calculateConfidence(results, avgScore)
    };
  }
  
  /**
   * Majority vote
   */
  majorityVote(results) {
    const assessments = results.map(r => r.assessment || (r.score >= 7 ? 'pass' : r.score >= 5 ? 'needs-improvement' : 'fail'));
    const assessmentCounts = {};
    assessments.forEach(a => {
      assessmentCounts[a] = (assessmentCounts[a] || 0) + 1;
    });
    
    const majorityAssessment = Object.entries(assessmentCounts)
      .sort((a, b) => b[1] - a[1])[0][0];
    
    // Average score of majority
    const majorityResults = results.filter((r, i) => assessments[i] === majorityAssessment);
    const avgScore = majorityResults.reduce((sum, r) => sum + r.score, 0) / majorityResults.length;
    
    return {
      score: Math.round(avgScore * 10) / 10,
      assessment: majorityAssessment,
      issues: Array.from(new Set(majorityResults.flatMap(r => r.issues || []))),
      reasoning: `Majority vote: ${majorityAssessment} (${assessmentCounts[majorityAssessment]}/${results.length} judges)`,
      confidence: assessmentCounts[majorityAssessment] / results.length
    };
  }
  
  /**
   * Consensus vote (requires high agreement)
   */
  consensusVote(results) {
    const agreement = this.calculateAgreement(results);
    
    if (agreement.score < this.minAgreement) {
      // No consensus - return weighted average with low confidence
      const avg = this.weightedAverage(results);
      return {
        ...avg,
        assessment: 'no-consensus',
        confidence: agreement.score,
        reasoning: `No consensus reached (agreement: ${(agreement.score * 100).toFixed(0)}%). ${avg.reasoning}`
      };
    }
    
    // Consensus reached - return weighted average
    return this.weightedAverage(results);
  }
  
  /**
   * Calculate agreement between judges
   */
  calculateAgreement(results) {
    if (results.length < 2) {
      return { score: 1.0, type: 'single_judge' };
    }
    
    const scores = results.map(r => r.score).filter(s => s !== null);
    if (scores.length < 2) {
      return { score: 0, type: 'insufficient_scores' };
    }
    
    // Calculate variance
    const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
    const variance = scores.reduce((sum, score) => sum + Math.pow(score - mean, 2), 0) / scores.length;
    const stdDev = Math.sqrt(variance);
    
    // Agreement is inverse of normalized standard deviation
    // Max std dev for 0-10 scale is ~5, so normalize
    const normalizedStdDev = stdDev / 5;
    const agreement = Math.max(0, 1 - normalizedStdDev);
    
    // Check assessment agreement
    const assessments = results.map(r => r.assessment || (r.score >= 7 ? 'pass' : 'fail'));
    const uniqueAssessments = new Set(assessments);
    const assessmentAgreement = uniqueAssessments.size === 1 ? 1.0 : 0.5;
    
    return {
      score: (agreement + assessmentAgreement) / 2,
      scoreAgreement: agreement,
      assessmentAgreement,
      mean,
      stdDev,
      scores
    };
  }
  
  /**
   * Analyze disagreement between judges
   */
  analyzeDisagreement(results) {
    if (results.length < 2) {
      return { hasDisagreement: false };
    }
    
    const scores = results.map(r => r.score).filter(s => s !== null);
    const assessments = results.map(r => r.assessment || (r.score >= 7 ? 'pass' : 'fail'));
    
    const scoreRange = Math.max(...scores) - Math.min(...scores);
    const uniqueAssessments = new Set(assessments);
    
    return {
      hasDisagreement: scoreRange > 2 || uniqueAssessments.size > 1,
      scoreRange,
      assessmentDisagreement: uniqueAssessments.size > 1,
      uniqueAssessments: Array.from(uniqueAssessments),
      maxScore: Math.max(...scores),
      minScore: Math.min(...scores)
    };
  }
  
  /**
   * Calculate confidence in aggregated result
   */
  calculateConfidence(results, avgScore) {
    const agreement = this.calculateAgreement(results);
    const disagreement = this.analyzeDisagreement(results);
    
    // Confidence based on agreement and number of judges
    const agreementConfidence = agreement.score;
    const judgeCountConfidence = Math.min(1.0, results.length / 3); // More judges = more confidence
    const disagreementPenalty = disagreement.hasDisagreement ? 0.2 : 0;
    
    return Math.max(0, Math.min(1.0, (agreementConfidence * 0.7 + judgeCountConfidence * 0.3) - disagreementPenalty));
  }
}

/**
 * Create an ensemble judge with multiple providers
 * 
 * @param {string[]} [providers=['gemini', 'openai']] - Array of provider names
 * @param {import('./index.mjs').EnsembleJudgeOptions} [options={}] - Ensemble configuration
 * @returns {EnsembleJudge} Configured ensemble judge
 */
export function createEnsembleJudge(providers = ['gemini', 'openai'], options = {}) {
  const judges = providers.map(provider => {
    const judge = new VLLMJudge({ provider });
    return judge;
  });
  
  return new EnsembleJudge({
    ...options,
    judges
  });
}

