/**
 * Dynamic Few-Shot Example Selection
 * 
 * Research: ES-KNN (semantically similar in-context examples) outperforms
 * random examples. Examples should be semantically similar to evaluation task.
 * 
 * Papers:
 * - ES-KNN: arXiv:2506.05614 (Exemplar Selection KNN using semantic similarity)
 * - KATE: arXiv:2101.06804 (Foundational work on kNN-augmented in-context examples)
 * 
 * Note: This implementation uses keyword-based similarity (Jaccard) rather than
 * true semantic embeddings due to npm package constraints. For full ES-KNN,
 * embedding-based cosine similarity would be required.
 * 
 * This module provides dynamic few-shot example selection based on similarity
 * to the evaluation prompt.
 */

/**
 * Select few-shot examples based on semantic similarity to prompt
 * 
 * @param {string} prompt - Evaluation prompt
 * @param {Array<import('./index.mjs').FewShotExample>} examples - Available examples
 * @param {{
 *   maxExamples?: number;
 *   similarityThreshold?: number;
 *   useSemanticMatching?: boolean;
 * }} [options={}] - Selection options
 * @returns {Array<import('./index.mjs').FewShotExample>} Selected examples
 */
export function selectFewShotExamples(prompt, examples = [], options = {}) {
  const {
    maxExamples = 3,
    similarityThreshold = 0.3,
    useSemanticMatching = true
  } = options;
  
  // Validate inputs
  if (!examples || !Array.isArray(examples) || examples.length === 0) {
    return [];
  }
  
  // Validate prompt
  if (typeof prompt !== 'string') {
    return examples.slice(0, maxExamples); // Fallback to simple selection
  }
  
  if (!useSemanticMatching || examples.length <= maxExamples) {
    // Return all examples if we have few enough, or just first N
    return examples.slice(0, maxExamples);
  }
  
  // Simple keyword-based similarity (for npm package - full semantic matching would require embeddings)
  const promptKeywords = extractKeywords(prompt.toLowerCase());
  
  // Score each example by keyword overlap
  const scored = examples.map(example => {
    const exampleKeywords = extractKeywords(
      (example.description || '') + ' ' + (example.evaluation || '')
    );
    
    // Jaccard similarity (intersection over union)
    const intersection = new Set(
      [...promptKeywords].filter(k => exampleKeywords.has(k))
    );
    const union = new Set([...promptKeywords, ...exampleKeywords]);
    const similarity = union.size > 0 ? intersection.size / union.size : 0;
    
    return {
      example,
      similarity
    };
  });
  
  // Sort by similarity and take top N
  return scored
    .filter(s => s.similarity >= similarityThreshold)
    .sort((a, b) => b.similarity - a.similarity)
    .slice(0, maxExamples)
    .map(s => s.example);
}

/**
 * Extract keywords from text (simple implementation)
 * 
 * @param {string} text - Text to extract keywords from
 * @returns {Set<string>} Set of keywords
 */
function extractKeywords(text) {
  // Remove common stop words and extract meaningful terms
  const stopWords = new Set([
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should',
    'could', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those'
  ]);
  
  // Extract words (alphanumeric, at least 3 chars)
  const words = text.match(/\b[a-z]{3,}\b/gi) || [];
  
  return new Set(
    words
      .map(w => w.toLowerCase())
      .filter(w => !stopWords.has(w))
  );
}

/**
 * Format few-shot examples for prompt
 * 
 * @param {Array<import('./index.mjs').FewShotExample>} examples - Examples to format
 * @param {string} [format='default'] - Format style
 * @returns {string} Formatted examples text
 */
export function formatFewShotExamples(examples, format = 'default') {
  if (examples.length === 0) {
    return '';
  }
  
  if (format === 'json') {
    // JSON format for structured output
    return `\n\n### Few-Shot Examples:\n\n${examples.map((ex, i) => 
      `**Example ${i + 1}**\n\`\`\`json\n${JSON.stringify(ex, null, 2)}\n\`\`\``
    ).join('\n\n')}`;
  }
  
  // Default format (matches rubrics.mjs style)
  return examples.map((ex, i) => {
    const score = ex.score ?? ex.result?.score ?? 'N/A';
    const desc = ex.description || ex.screenshot || 'Screenshot';
    const evaluation = ex.evaluation || ex.result?.reasoning || '';
    const json = ex.json || ex.result ? JSON.stringify(ex.result || ex.json, null, 2) : '';
    
    return `**Example ${i + 1} - ${ex.quality || 'Quality'} (Score: ${score})**
Screenshot: ${desc}
Evaluation: "${evaluation}"
${json ? `JSON: ${json}` : ''}`;
  }).join('\n\n');
}

