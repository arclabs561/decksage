/**
 * Hallucination Detection for VLLM Outputs
 * 
 * Minimal implementation for detecting when VLLM generates unfaithful outputs.
 * Research: arXiv:2506.19513, 2507.19024, 2509.10345
 * 
 * Kept minimal for npm package - focuses on core faithfulness checking.
 */

/**
 * Detect hallucination in VLLM judgment
 * 
 * @param {string} judgment - VLLM judgment text
 * @param {string} [imagePath] - Optional: path to screenshot for visual grounding
 * @param {{
 *   checkFaithfulness?: boolean;
 *   checkUncertainty?: boolean;
 *   logprobs?: any;
 * }} [options={}] - Detection options
 * @returns {import('./index.mjs').HallucinationDetectionResult} Detection result
 */
export function detectHallucination(judgment, imagePath = null, options = {}) {
  const {
    checkFaithfulness = true,
    checkUncertainty = true,
    logprobs = null
  } = options;
  
  const issues = [];
  let confidence = 1.0;
  
  // 1. Faithfulness checking: Look for claims that can't be verified from visual content
  if (checkFaithfulness) {
    const faithfulness = checkFaithfulnessToVisual(judgment);
    if (!faithfulness.faithful) {
      issues.push(...faithfulness.issues);
      confidence *= 0.7; // Reduce confidence if unfaithful
    }
  }
  
  // 2. Uncertainty estimation: Use logprobs if available
  if (checkUncertainty && logprobs) {
    const uncertainty = estimateUncertaintyFromLogprobs(logprobs);
    if (uncertainty.high) {
      issues.push('High uncertainty detected in model output');
      confidence *= uncertainty.confidence;
    }
  }
  
  // 3. Contradiction detection: Check for self-contradictions
  const contradictions = detectContradictions(judgment);
  if (contradictions.length > 0) {
    issues.push(...contradictions);
    confidence *= 0.8;
  }
  
  return {
    hasHallucination: issues.length > 0,
    issues,
    confidence: Math.max(0, Math.min(1, confidence)),
    severity: issues.length > 2 ? 'high' : issues.length > 0 ? 'medium' : 'low'
  };
}

/**
 * Check if judgment is faithful to visual content
 * Minimal heuristic-based approach
 */
function checkFaithfulnessToVisual(judgment) {
  const issues = [];
  
  // Red flags for potential hallucination:
  // 1. Overly specific claims without evidence
  const specificClaims = /(exactly|precisely|specifically|definitely)\s+\d+/gi;
  if (specificClaims.test(judgment)) {
    issues.push('Overly specific numerical claims without visual evidence');
  }
  
  // 2. Claims about non-visible elements
  const nonVisible = /(hidden|invisible|behind|underneath|not visible|cannot see)/gi;
  if (nonVisible.test(judgment) && !judgment.includes('cannot be seen')) {
    issues.push('Claims about non-visible elements may be hallucinated');
  }
  
  // 3. Excessive detail beyond what's reasonable from screenshot
  const wordCount = judgment.split(/\s+/).length;
  const detailDensity = (judgment.match(/(color|size|position|font|layout|spacing)/gi) || []).length;
  if (detailDensity > wordCount / 10) {
    issues.push('Excessive detail density may indicate hallucination');
  }
  
  return {
    faithful: issues.length === 0,
    issues
  };
}

/**
 * Estimate uncertainty from logprobs
 * Minimal implementation - just checks if logprobs indicate low confidence
 */
function estimateUncertaintyFromLogprobs(logprobs) {
  if (!logprobs || typeof logprobs !== 'object') {
    return { high: false, confidence: 1.0 };
  }
  
  // Extract average logprob if available
  // OpenAI format: { tokens: [...], token_logprobs: [...] }
  // Gemini format: varies
  let avgLogprob = null;
  
  if (Array.isArray(logprobs.token_logprobs)) {
    const valid = logprobs.token_logprobs.filter(p => p !== null);
    if (valid.length > 0) {
      avgLogprob = valid.reduce((a, b) => a + b, 0) / valid.length;
    }
  } else if (typeof logprobs === 'number') {
    avgLogprob = logprobs;
  }
  
  // Low logprob (more negative) = high uncertainty
  // Threshold: -2.0 is roughly 13% probability
  const high = avgLogprob !== null && avgLogprob < -2.0;
  const confidence = avgLogprob !== null 
    ? Math.max(0, Math.min(1, (avgLogprob + 3) / 3)) // Map -3 to 0, 0 to 1
    : 1.0;
  
  return { high, confidence };
}

/**
 * Detect self-contradictions in judgment
 */
function detectContradictions(judgment) {
  const issues = [];
  const lower = judgment.toLowerCase();
  
  // Common contradiction patterns
  const patterns = [
    { positive: /(good|excellent|high|great)/i, negative: /(bad|poor|low|terrible)/i },
    { positive: /(pass|correct|valid)/i, negative: /(fail|incorrect|invalid)/i },
    { positive: /(accessible|usable)/i, negative: /(inaccessible|unusable)/i }
  ];
  
  for (const { positive, negative } of patterns) {
    if (positive.test(judgment) && negative.test(judgment)) {
      issues.push('Contradictory statements detected in judgment');
      break; // Only flag once
    }
  }
  
  return issues;
}


