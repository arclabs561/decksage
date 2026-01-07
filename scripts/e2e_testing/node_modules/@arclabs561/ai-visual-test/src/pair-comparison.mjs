/**
 * Pair Comparison Evaluation
 * 
 * Implements pairwise comparison evaluation method.
 * Research shows Pair Comparison is more reliable than absolute scoring
 * (MLLM-as-a-Judge, arXiv:2402.04788).
 * 
 * Instead of scoring each screenshot independently, compares pairs
 * to determine which is better, then derives relative scores.
 */

import { VLLMJudge } from './judge.mjs';
import { detectBias, detectPositionBias } from './bias-detector.mjs';
import { composeComparisonPrompt } from './prompt-composer.mjs';

/**
 * Compare two screenshots and determine which is better
 * 
 * @param {string} imagePath1 - Path to first screenshot
 * @param {string} imagePath2 - Path to second screenshot
 * @param {string} prompt - Evaluation prompt describing what to compare
 * @param {import('./index.mjs').ValidationContext} [context={}] - Validation context
 * @returns {Promise<import('./index.mjs').PairComparisonResult>} Comparison result
 */
export async function comparePair(imagePath1, imagePath2, prompt, context = {}) {
  const judge = new VLLMJudge(context);
  
  if (!judge.enabled) {
    return {
      enabled: false,
      winner: null,
      confidence: null,
      reasoning: 'VLLM validation is disabled',
      comparison: null
    };
  }
  
  const comparisonPrompt = buildComparisonPrompt(prompt, context);
  
  // Randomize order to reduce position bias
  const [first, second, order] = Math.random() > 0.5
    ? [imagePath1, imagePath2, 'original']
    : [imagePath2, imagePath1, 'reversed'];
  
  const fullPrompt = `${comparisonPrompt}

You are comparing two screenshots. Screenshot A is shown first, then Screenshot B.

SCREENSHOT A:
[First screenshot will be provided]

SCREENSHOT B:
[Second screenshot will be provided]

Compare them and determine which is better based on the evaluation criteria. Return JSON:
{
  "winner": "A" | "B" | "tie",
  "confidence": 0.0-1.0,
  "reasoning": "explanation of comparison",
  "differences": ["key difference 1", "key difference 2"],
  "scores": {
    "A": 0-10,
    "B": 0-10
  }
}`;
  
  try {
    // TRUE MULTI-IMAGE COMPARISON: Send both images in single API call
    // This is the research-optimal approach (MLLM-as-a-Judge, arXiv:2402.04788)
    const comparisonResult = await judge.judgeScreenshot([first, second], comparisonPrompt, {
      ...context,
      comparisonContext: { position: 'both', total: 2 }
    });
    
    if (!comparisonResult.enabled || comparisonResult.error) {
      return {
        enabled: false,
        winner: null,
        confidence: null,
        reasoning: comparisonResult.error || 'Comparison failed',
        comparison: null,
        error: comparisonResult.error || 'API disabled'
      };
    }
    
    // Parse comparison result - expect JSON with winner, scores, reasoning
    const judgment = comparisonResult.judgment || '';
    let parsedComparison = null;
    
    try {
      const jsonMatch = judgment.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        parsedComparison = JSON.parse(jsonMatch[0]);
      }
    } catch (e) {
      // Fall through to score-based comparison
    }
    
    // If we got structured comparison, use it
    if (parsedComparison && parsedComparison.winner) {
      const winner = parsedComparison.winner.toLowerCase();
      const scoreA = parsedComparison.scores?.A ?? parsedComparison.scores?.['A'] ?? null;
      const scoreB = parsedComparison.scores?.B ?? parsedComparison.scores?.['B'] ?? null;
      
      // Map winner back to original order
      const mappedWinner = order === 'reversed' 
        ? (winner === 'a' ? 'B' : winner === 'b' ? 'A' : 'tie')
        : (winner === 'a' ? 'A' : winner === 'b' ? 'B' : 'tie');
      
      return {
        enabled: true,
        winner: mappedWinner,
        confidence: parsedComparison.confidence ?? 0.5,
        reasoning: parsedComparison.reasoning || comparisonResult.reasoning || 'Direct comparison completed',
        differences: parsedComparison.differences || [],
        comparison: {
          score1: scoreA ?? (mappedWinner === 'A' ? 8 : mappedWinner === 'B' ? 6 : 7),
          score2: scoreB ?? (mappedWinner === 'B' ? 8 : mappedWinner === 'A' ? 6 : 7),
          difference: scoreA && scoreB ? Math.abs(scoreA - scoreB) : null,
          order: order === 'reversed' ? 'reversed' : 'original',
          method: 'multi-image'
        },
        biasDetection: {
          positionBias: false, // Multi-image eliminates position bias
          adjusted: false
        },
        metadata: {
          provider: comparisonResult.provider,
          cached: comparisonResult.cached || false,
          responseTime: comparisonResult.responseTime || 0,
          estimatedCost: comparisonResult.estimatedCost,
          logprobs: comparisonResult.logprobs || null // Include if available
        }
      };
    }
    
    // Fallback: If structured parse failed, treat as tie (multi-image should return structured JSON)
    // This should rarely happen if prompt is clear
    return {
      enabled: true,
      winner: 'tie',
      confidence: 0.5,
      reasoning: comparisonResult.reasoning || 'Comparison completed but could not parse structured result. Treating as tie.',
      comparison: {
        score1: comparisonResult.score ?? 7,
        score2: comparisonResult.score ?? 7,
        difference: 0,
        order: order === 'reversed' ? 'reversed' : 'original',
        method: 'multi-image-fallback'
      },
      biasDetection: {
        positionBias: false,
        adjusted: false
      },
      metadata: {
        provider: comparisonResult.provider,
        cached: comparisonResult.cached || false,
        responseTime: comparisonResult.responseTime || 0,
        estimatedCost: comparisonResult.estimatedCost,
        logprobs: comparisonResult.logprobs || null,
        warning: 'Structured comparison parse failed - using fallback'
      }
    };
  } catch (error) {
    return {
      enabled: false,
      winner: null,
      confidence: null,
      reasoning: `Comparison failed: ${error.message}`,
      comparison: null,
      error: error.message
    };
  }
}

/**
 * Build comparison prompt from base prompt
 * 
 * Now uses unified prompt composition system for research-backed consistency.
 */
function buildComparisonPrompt(basePrompt, context) {
  try {
    return composeComparisonPrompt(basePrompt, context, {
      includeRubric: context.includeRubric !== false // Default true (research-backed)
    });
  } catch (error) {
    // Fallback to basic comparison prompt
    return `Compare the two screenshots based on the following criteria:

${basePrompt}

Focus on:
- Which screenshot better meets the criteria?
- What are the key differences?
- Which has fewer issues?
- Which provides better user experience?

Be specific about what makes one better than the other.`;
  }
}

/**
 * Rank multiple screenshots using pairwise comparisons
 * Uses tournament-style ranking
 * 
 * @param {Array<string>} imagePaths - Array of screenshot paths
 * @param {string} prompt - Evaluation prompt
 * @param {import('./index.mjs').ValidationContext} [context={}] - Validation context
 * @returns {Promise<import('./index.mjs').BatchRankingResult>} Ranking result
 */
export async function rankBatch(imagePaths, prompt, context = {}) {
  if (imagePaths.length < 2) {
    return {
      enabled: false,
      rankings: [],
      error: 'Need at least 2 screenshots for ranking'
    };
  }
  
  // For efficiency, compare each pair
  // In practice, you might use a tournament bracket or sampling
  const comparisons = [];
  const scores = new Map();
  
  // Compare all pairs
  for (let i = 0; i < imagePaths.length; i++) {
    for (let j = i + 1; j < imagePaths.length; j++) {
      const comparison = await comparePair(
        imagePaths[i],
        imagePaths[j],
        prompt,
        context
      );
      
      if (comparison.enabled && comparison.winner !== 'tie') {
        comparisons.push({
          image1: i,
          image2: j,
          winner: comparison.winner === 'A' ? i : j,
          confidence: comparison.confidence
        });
        
        // Update scores based on wins
        const winnerIdx = comparison.winner === 'A' ? i : j;
        const loserIdx = comparison.winner === 'A' ? j : i;
        
        scores.set(winnerIdx, (scores.get(winnerIdx) || 0) + comparison.confidence);
        scores.set(loserIdx, (scores.get(loserIdx) || 0) + (1 - comparison.confidence));
      }
    }
  }
  
  // Rank by scores
  const rankings = Array.from(scores.entries())
    .map(([idx, score]) => ({
      index: idx,
      path: imagePaths[idx],
      score,
      wins: comparisons.filter(c => c.winner === idx).length
    }))
    .sort((a, b) => b.score - a.score)
    .map((r, rank) => ({
      ...r,
      rank: rank + 1
    }));
  
  return {
    enabled: true,
    rankings,
    comparisons: comparisons.length,
    metadata: {
      totalScreenshots: imagePaths.length,
      totalComparisons: comparisons.length
    }
  };
}

