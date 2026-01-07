/**
 * Bias Detection for LLM-as-a-Judge
 * 
 * Detects common biases in LLM judge evaluations:
 * - Superficial feature bias (verbosity, length, formatting)
 * - Position bias (favoring first/last responses) - Systematic study shows position bias is not random
 *   and varies significantly across judges and tasks (arXiv:2406.07791)
 * - Verbosity bias (favoring longer responses) - LLMs prefer longer answers more than humans
 *   (arXiv:2310.10076, arXiv:2407.01085)
 * - Recency bias (favoring recent information)
 * - Authority bias (favoring authoritative-sounding responses)
 * 
 * Research shows these biases can significantly impact evaluation quality.
 * Position bias is particularly severe and requires counter-balancing (arXiv:2406.07791, arXiv:2508.02020).
 */

/**
 * Detect superficial feature bias in judgment
 * 
 * @param {string | object} judgment - Judgment object or text
 * @param {{
 *   checkVerbosity?: boolean;
 *   checkLength?: boolean;
 *   checkFormatting?: boolean;
 *   checkPosition?: boolean;
 *   checkAuthority?: boolean;
 * }} [options={}] - Detection options
 * @returns {import('./index.mjs').BiasDetectionResult} Bias detection results
 */
export function detectBias(judgment, options = {}) {
  const {
    checkVerbosity = true,
    checkLength = true,
    checkFormatting = true,
    checkPosition = false,
    checkAuthority = true
  } = options;

  const judgmentText = typeof judgment === 'string' 
    ? judgment 
    : JSON.stringify(judgment);
  
  const biases = {
    verbosity: checkVerbosity ? detectVerbosityBias(judgmentText) : null,
    length: checkLength ? detectLengthBias(judgmentText) : null,
    formatting: checkFormatting ? detectFormattingBias(judgmentText) : null,
    authority: checkAuthority ? detectAuthorityBias(judgmentText) : null
  };

  const detectedBiases = Object.entries(biases)
    .filter(([_, result]) => result && result.detected)
    .map(([type, result]) => ({ type, ...result }));

  return {
    hasBias: detectedBiases.length > 0,
    biases: detectedBiases,
    severity: calculateSeverity(detectedBiases),
    recommendations: generateRecommendations(detectedBiases)
  };
}

/**
 * Detect verbosity bias (favoring longer responses)
 */
function detectVerbosityBias(text) {
  const wordCount = text.split(/\s+/).length;
  const avgWordLength = text.split(/\s+/).reduce((sum, word) => sum + word.length, 0) / wordCount;
  
  // Flags: excessive length, repetitive phrases, filler words
  const fillerWords = ['very', 'really', 'quite', 'rather', 'somewhat', 'rather', 'extremely'];
  const fillerCount = fillerWords.reduce((count, word) => {
    const regex = new RegExp(`\\b${word}\\b`, 'gi');
    return count + (text.match(regex) || []).length;
  }, 0);
  
  const repetitivePhrases = findRepetitivePhrases(text);
  
  const detected = wordCount > 500 || fillerCount > 10 || repetitivePhrases.length > 3;
  
  return {
    detected,
    score: detected ? Math.min(1.0, (wordCount / 1000) + (fillerCount / 20) + (repetitivePhrases.length / 5)) : 0,
    evidence: {
      wordCount,
      fillerCount,
      repetitivePhrases: repetitivePhrases.slice(0, 3),
      avgWordLength
    }
  };
}

/**
 * Detect length bias (favoring responses based on length alone)
 */
function detectLengthBias(text) {
  const length = text.length;
  const hasLengthBasedReasoning = /length|size|long|short|brief|extensive/i.test(text);
  
  return {
    detected: hasLengthBasedReasoning && length > 200,
    score: hasLengthBasedReasoning ? 0.7 : 0,
    evidence: {
      length,
      mentionsLength: hasLengthBasedReasoning
    }
  };
}

/**
 * Detect formatting bias (favoring well-formatted responses)
 */
function detectFormattingBias(text) {
  const hasMarkdown = /#{1,6}\s|^\*\s|^-\s|^\d+\.\s/m.test(text);
  const hasLists = (text.match(/^\s*[-*]\s/gm) || []).length > 3;
  const hasHeaders = (text.match(/^#{1,6}\s/gm) || []).length > 2;
  
  // Check if judgment mentions formatting
  const mentionsFormatting = /format|structure|organized|well-formatted|markdown/i.test(text);
  
  return {
    detected: mentionsFormatting && (hasMarkdown || hasLists || hasHeaders),
    score: mentionsFormatting ? 0.6 : 0,
    evidence: {
      hasMarkdown,
      hasLists,
      hasHeaders,
      mentionsFormatting
    }
  };
}

/**
 * Detect authority bias (favoring authoritative-sounding responses)
 */
function detectAuthorityBias(text) {
  const authorityPhrases = [
    'according to', 'research shows', 'studies indicate', 'experts say',
    'it is well-known', 'commonly accepted', 'standard practice',
    'best practice', 'industry standard', 'widely recognized'
  ];
  
  const authorityCount = authorityPhrases.reduce((count, phrase) => {
    const regex = new RegExp(phrase, 'gi');
    return count + (text.match(regex) || []).length;
  }, 0);
  
  return {
    detected: authorityCount > 2,
    score: Math.min(1.0, authorityCount / 5),
    evidence: {
      authorityPhrasesFound: authorityCount
    }
  };
}

/**
 * Find repetitive phrases in text
 */
function findRepetitivePhrases(text) {
  const words = text.toLowerCase().split(/\s+/);
  const phrases = [];
  
  // Check for 3-word phrases that repeat
  for (let i = 0; i < words.length - 2; i++) {
    const phrase = words.slice(i, i + 3).join(' ');
    const count = (text.toLowerCase().match(new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length;
    if (count > 2) {
      phrases.push({ phrase, count });
    }
  }
  
  return phrases
    .filter((p, i, arr) => arr.findIndex(x => x.phrase === p.phrase) === i)
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
}

/**
 * Calculate overall bias severity
 */
function calculateSeverity(detectedBiases) {
  if (detectedBiases.length === 0) return 'none';
  
  const avgScore = detectedBiases.reduce((sum, b) => sum + (b.score || 0), 0) / detectedBiases.length;
  
  if (avgScore >= 0.7) return 'high';
  if (avgScore >= 0.4) return 'medium';
  return 'low';
}

/**
 * Generate recommendations based on detected biases
 */
function generateRecommendations(detectedBiases) {
  const recommendations = [];
  
  if (detectedBiases.some(b => b.type === 'verbosity')) {
    recommendations.push('Judge may be favoring verbose responses. Focus evaluation on content quality, not length.');
  }
  
  if (detectedBiases.some(b => b.type === 'length')) {
    recommendations.push('Judge may be biased by response length. Use rubric to focus on substantive content.');
  }
  
  if (detectedBiases.some(b => b.type === 'formatting')) {
    recommendations.push('Judge may be favoring well-formatted responses. Evaluate content regardless of formatting.');
  }
  
  if (detectedBiases.some(b => b.type === 'authority')) {
    recommendations.push('Judge may be biased by authoritative language. Focus on factual correctness, not tone.');
  }
  
  if (recommendations.length === 0) {
    recommendations.push('No significant biases detected. Consider using ensemble judging for high-stakes evaluations.');
  }
  
  return recommendations;
}

/**
 * Detect position bias in array of judgments
 * 
 * Research: arXiv:2406.07791 introduces three metrics:
 * - Repetition Stability (RS): Consistency across repeated evaluations (threshold: RS > 0.85)
 * - Position Consistency (PC): Ratio of consistent judgments when order is swapped
 * - Preference Fairness (PF): Extent to which judges favor specific positions
 *   - PF = 0: no bias
 *   - PF > 0: recency bias (favoring later positions)
 *   - PF < 0: primacy bias (favoring earlier positions)
 * 
 * Key findings from research:
 * - Quality gap strongly affects bias: parabolic relationship where PC increases with quality gap
 * - Small quality gaps (δ_q ≈ 0.5) cause maximum confusion and position bias
 * - Large quality gaps (δ_q → 0 or 1) lead to more consistent, fair judgments
 * - Judge-level factors: model family, context window, max output length
 * - Candidate-level factors: quality gap is primary, but also verbosity/length bias
 * - Task-level factors: input/output length, prompt length, benchmark difficulty
 * 
 * @param {Array<{ score: number | null }>} judgments - Array of judgment results with scores
 * @param {{
 *   calculateMetrics?: boolean;
 *   swappedJudgments?: Array<{ score: number | null }>;
 *   qualityGap?: number; // Quality gap (δ_q) between candidates (0-1, where 0.5 = tie)
 *   judgeModel?: string; // Judge model identifier for judge-level analysis
 *   taskMetadata?: { inputLength?: number; outputLength?: number; promptLength?: number };
 * }} [options={}] - Options for calculating research metrics
 * @returns {import('./index.mjs').PositionBiasResult} Position bias detection result
 */
export function detectPositionBias(judgments, options = {}) {
  const { 
    calculateMetrics = false, 
    swappedJudgments = null,
    qualityGap = null,
    judgeModel = null,
    taskMetadata = {}
  } = options;
  
  if (judgments.length < 2) {
    return { detected: false, reason: 'Need at least 2 judgments to detect position bias' };
  }
  
  const scores = judgments.map(j => {
    const score = typeof j === 'object' ? j.score : null;
    return score !== null && score !== undefined ? score : null;
  }).filter(s => s !== null);
  
  if (scores.length < 2) {
    return { detected: false, reason: 'Not enough scores to detect position bias' };
  }
  
  // Check if first or last scores are consistently higher
  const firstScore = scores[0];
  const lastScore = scores[scores.length - 1];
  const middleScores = scores.slice(1, -1);
  const avgMiddle = middleScores.length > 0 
    ? middleScores.reduce((a, b) => a + b, 0) / middleScores.length 
    : (firstScore + lastScore) / 2;
  
  const firstBias = Math.abs(firstScore - avgMiddle) > 2;
  const lastBias = Math.abs(lastScore - avgMiddle) > 2;
  
  // Calculate quality gap if not provided (estimate from score differences)
  let estimatedQualityGap = qualityGap;
  if (estimatedQualityGap === null && scores.length >= 2) {
    const scoreRange = Math.max(...scores) - Math.min(...scores);
    const maxPossibleRange = 10; // Assuming 0-10 scale
    // Estimate quality gap: 0.5 = tie, 0 or 1 = large gap
    estimatedQualityGap = 0.5 - Math.abs((scoreRange / maxPossibleRange) - 0.5);
  }
  
  // Research finding: small quality gaps (≈0.5) cause maximum position bias
  const isEquivocalCase = estimatedQualityGap !== null && Math.abs(estimatedQualityGap - 0.5) < 0.1;
  const qualityGapSeverity = estimatedQualityGap !== null 
    ? (isEquivocalCase ? 'high' : estimatedQualityGap < 0.2 ? 'low' : 'medium')
    : 'unknown';
  
  const result = {
    detected: firstBias || lastBias,
    firstBias,
    lastBias,
    evidence: {
      firstScore,
      lastScore,
      avgMiddle,
      allScores: scores
    },
    // Research-based quality gap analysis
    qualityGap: {
      value: estimatedQualityGap,
      severity: qualityGapSeverity,
      isEquivocal: isEquivocalCase,
      note: isEquivocalCase 
        ? 'Equivocal case (quality gap ≈0.5) - maximum position bias risk per arXiv:2406.07791'
        : 'Quality gap analysis per research findings'
    },
    // Judge-level and task-level factors
    factors: {
      judgeModel: judgeModel || 'unknown',
      taskMetadata: taskMetadata || {},
      note: 'Judge-level and task-level factors influence bias per research'
    }
  };
  
  // Calculate research metrics if requested and swapped judgments provided
  if (calculateMetrics && swappedJudgments && swappedJudgments.length === judgments.length) {
    const swappedScores = swappedJudgments.map(j => {
      const score = typeof j === 'object' ? j.score : null;
      return score !== null && score !== undefined ? score : null;
    }).filter(s => s !== null);
    
    if (swappedScores.length === scores.length) {
      // Position Consistency (PC): Ratio of consistent judgments when order is swapped
      let consistentCount = 0;
      for (let i = 0; i < scores.length; i++) {
        const original = scores[i];
        const swapped = swappedScores[swappedScores.length - 1 - i]; // Reversed order
        // Consider consistent if difference is small (within 1 point)
        if (Math.abs(original - swapped) <= 1.0) {
          consistentCount++;
        }
      }
      result.positionConsistency = consistentCount / scores.length;
      
      // Preference Fairness (PF): Measure of position preference
      // Simplified: check if first position is consistently preferred
      const firstPrefCount = scores.filter((s, i) => {
        if (i === 0) return false; // Skip first itself
        return s < firstScore;
      }).length;
      result.preferenceFairness = {
        firstPositionPreference: firstPrefCount / (scores.length - 1),
        lastPositionPreference: scores.filter((s, i) => {
          if (i === scores.length - 1) return false;
          return s < lastScore;
        }).length / (scores.length - 1)
      };
      
      // Note: Repetition Stability (RS) requires multiple evaluation runs with same order
      // This would need to be calculated externally with repeated evaluations
      result.metrics = {
        positionConsistency: result.positionConsistency,
        preferenceFairness: result.preferenceFairness,
        note: 'Repetition Stability (RS) requires multiple runs - calculate externally'
      };
    }
  }
  
  return result;
}

