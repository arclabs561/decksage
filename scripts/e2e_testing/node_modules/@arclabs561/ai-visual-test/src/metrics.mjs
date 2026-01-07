/**
 * Evaluation Metrics
 * 
 * Provides comprehensive metrics for evaluation results, including:
 * - Spearman's rank correlation (for ordinal ratings)
 * - Pearson's correlation
 * - Agreement metrics
 * - Rank-based metrics
 * 
 * Research: Spearman's ρ is more appropriate than Pearson's r for LLM evaluation
 * (arXiv:2506.02945).
 */

/**
 * Calculate Spearman's rank correlation coefficient
 * 
 * @param {Array<number>} x - First set of values
 * @param {Array<number>} y - Second set of values
 * @returns {number | null} Spearman's ρ (rho), or null if insufficient data
 */
export function spearmanCorrelation(x, y) {
  if (x.length !== y.length || x.length < 2) {
    return null;
  }
  
  // Remove pairs with null/undefined values
  const pairs = x.map((xi, i) => [xi, y[i]])
    .filter(([xi, yi]) => xi != null && yi != null);
  
  if (pairs.length < 2) {
    return null;
  }
  
  const xValues = pairs.map(p => p[0]);
  const yValues = pairs.map(p => p[1]);
  
  // Rank the values
  const xRanks = rank(xValues);
  const yRanks = rank(yValues);
  
  // Calculate Pearson correlation on ranks
  return pearsonCorrelation(xRanks, yRanks);
}

/**
 * Calculate Pearson's correlation coefficient
 * 
 * @param {Array<number>} x - First set of values
 * @param {Array<number>} y - Second set of values
 * @returns {number | null} Pearson's r, or null if insufficient data
 */
export function pearsonCorrelation(x, y) {
  if (x.length !== y.length || x.length < 2) {
    return null;
  }
  
  const n = x.length;
  const xMean = x.reduce((a, b) => a + b, 0) / n;
  const yMean = y.reduce((a, b) => a + b, 0) / n;
  
  let numerator = 0;
  let xVariance = 0;
  let yVariance = 0;
  
  for (let i = 0; i < n; i++) {
    const xDiff = x[i] - xMean;
    const yDiff = y[i] - yMean;
    numerator += xDiff * yDiff;
    xVariance += xDiff * xDiff;
    yVariance += yDiff * yDiff;
  }
  
  const denominator = Math.sqrt(xVariance * yVariance);
  
  if (denominator === 0) {
    return null; // No variance
  }
  
  return numerator / denominator;
}

/**
 * Rank values (handle ties by averaging)
 * 
 * @param {Array<number>} values - Values to rank
 * @returns {Array<number>} Ranks (1-indexed)
 */
function rank(values) {
  const indexed = values.map((v, i) => ({ value: v, index: i }));
  indexed.sort((a, b) => a.value - b.value);
  
  const ranks = new Array(values.length);
  let currentRank = 1;
  
  for (let i = 0; i < indexed.length; i++) {
    // Check for ties
    let tieCount = 1;
    let tieSum = currentRank;
    
    while (i + tieCount < indexed.length && 
           indexed[i].value === indexed[i + tieCount].value) {
      tieSum += currentRank + tieCount;
      tieCount++;
    }
    
    // Average rank for ties
    const avgRank = tieSum / tieCount;
    
    for (let j = 0; j < tieCount; j++) {
      ranks[indexed[i + j].index] = avgRank;
    }
    
    i += tieCount - 1;
    currentRank += tieCount;
  }
  
  return ranks;
}

/**
 * Calculate agreement between two rankings
 * 
 * @param {Array<number>} ranking1 - First ranking (indices or scores)
 * @param {Array<number>} ranking2 - Second ranking (indices or scores)
 * @returns {{
 *   spearman: number | null;
 *   pearson: number | null;
 *   kendall: number | null;
 *   exactMatches: number;
 *   totalItems: number;
 * }} Agreement metrics
 */
export function calculateRankAgreement(ranking1, ranking2) {
  const spearman = spearmanCorrelation(ranking1, ranking2);
  const pearson = pearsonCorrelation(ranking1, ranking2);
  const kendall = kendallTau(ranking1, ranking2);
  
  // Count exact matches
  const exactMatches = ranking1.filter((r1, i) => r1 === ranking2[i]).length;
  
  return {
    spearman,
    pearson,
    kendall,
    exactMatches,
    totalItems: ranking1.length,
    agreementRate: exactMatches / ranking1.length
  };
}

/**
 * Calculate Kendall's tau (rank correlation)
 * 
 * @param {Array<number>} x - First ranking
 * @param {Array<number>} y - Second ranking
 * @returns {number | null} Kendall's τ, or null if insufficient data
 */
function kendallTau(x, y) {
  if (x.length !== y.length || x.length < 2) {
    return null;
  }
  
  let concordant = 0;
  let discordant = 0;
  
  for (let i = 0; i < x.length; i++) {
    for (let j = i + 1; j < x.length; j++) {
      const xOrder = x[i] - x[j];
      const yOrder = y[i] - y[j];
      
      if (xOrder * yOrder > 0) {
        concordant++;
      } else if (xOrder * yOrder < 0) {
        discordant++;
      }
      // Ties (xOrder === 0 or yOrder === 0) are ignored
    }
  }
  
  const total = concordant + discordant;
  if (total === 0) {
    return null;
  }
  
  return (concordant - discordant) / total;
}

