/**
 * Attention-Based Multi-Modal Fusion
 * 
 * Implements structured fusion with attention mechanisms for combining
 * screenshot, HTML, CSS, and rendered code modalities.
 * 
 * Research:
 * - "Multimodal Fusion and Vision-Language Models: A Survey for Robot Vision" - Comprehensive survey
 * - "Cross-Modal Consistency in Multimodal Large Language Models" - Consistency issues in GPT-4V
 * - "Post-pre-training for Modality Alignment in Vision-Language Foundation Models" - CLIP-Refine
 * - "Attention-Based Multimodal Fusion" - Various papers on attention mechanisms
 * 
 * Key findings: Structured fusion outperforms simple concatenation. Modality gap exists even
 * after contrastive training. Cross-attention enables selective information integration.
 * Hallucination is a major issue, especially with stylized images.
 * 
 * Note: This implementation uses heuristic-based attention weighting. Full research implementation
 * would use learned cross-attention mechanisms and address the modality gap.
 */

/**
 * Calculate attention weights for different modalities
 * 
 * @param {Object} modalities - Available modalities
 * @param {string} [modalities.screenshot] - Screenshot path
 * @param {Object} [modalities.renderedCode] - Rendered code (HTML, CSS, DOM)
 * @param {Object} [modalities.gameState] - Game state
 * @param {string} prompt - Validation prompt
 * @returns {Object} Attention weights for each modality
 */
export function calculateModalityWeights(modalities, prompt) {
  const weights = {
    screenshot: 0.4, // Base weight for visual
    html: 0.2,
    css: 0.2,
    dom: 0.1,
    gameState: 0.1
  };
  
  // Adjust weights based on prompt content
  const promptLower = prompt.toLowerCase();
  
  // If prompt mentions visual/design, increase screenshot weight
  if (promptLower.includes('visual') || promptLower.includes('design') || promptLower.includes('appearance')) {
    weights.screenshot = 0.5;
    weights.html = 0.2;
    weights.css = 0.2;
    weights.dom = 0.05;
    weights.gameState = 0.05;
  }
  
  // If prompt mentions structure/layout, increase HTML/DOM weight
  if (promptLower.includes('structure') || promptLower.includes('layout') || promptLower.includes('html')) {
    weights.html = 0.3;
    weights.dom = 0.2;
    weights.screenshot = 0.3;
    weights.css = 0.15;
    weights.gameState = 0.05;
  }
  
  // If prompt mentions styling, increase CSS weight
  if (promptLower.includes('style') || promptLower.includes('css') || promptLower.includes('styling')) {
    weights.css = 0.3;
    weights.screenshot = 0.35;
    weights.html = 0.2;
    weights.dom = 0.1;
    weights.gameState = 0.05;
  }
  
  // If prompt mentions state/functionality, increase gameState weight
  if (promptLower.includes('state') || promptLower.includes('function') || promptLower.includes('game')) {
    weights.gameState = 0.2;
    weights.screenshot = 0.35;
    weights.html = 0.2;
    weights.css = 0.15;
    weights.dom = 0.1;
  }
  
  // Normalize weights
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  for (const key in weights) {
    weights[key] = weights[key] / total;
  }
  
  return weights;
}

/**
 * Build structured fusion prompt with attention weights
 * 
 * @param {string} basePrompt - Base validation prompt
 * @param {Object} modalities - Available modalities
 * @param {string} [modalities.screenshot] - Screenshot path
 * @param {Object} [modalities.renderedCode] - Rendered code
 * @param {Object} [modalities.gameState] - Game state
 * @returns {string} Structured fusion prompt
 */
export function buildStructuredFusionPrompt(basePrompt, modalities) {
  const weights = calculateModalityWeights(modalities, basePrompt);
  
  const parts = [basePrompt];
  parts.push('\n\n=== MULTI-MODAL CONTEXT (Weighted by Relevance) ===\n');
  
  // Screenshot (always highest weight for visual validation)
  if (modalities.screenshot) {
    parts.push(`[VISUAL - Weight: ${(weights.screenshot * 100).toFixed(0)}%]`);
    parts.push(`Screenshot: ${modalities.screenshot}`);
    parts.push('Use this visual representation as the primary reference for appearance and layout.\n');
  }
  
  // HTML structure
  if (modalities.renderedCode?.html) {
    parts.push(`[STRUCTURE - Weight: ${(weights.html * 100).toFixed(0)}%]`);
    parts.push('HTML Structure:');
    parts.push(modalities.renderedCode.html.substring(0, 2000)); // Limit length
    parts.push('\nUse this for understanding semantic structure and element hierarchy.\n');
  }
  
  // CSS styling
  if (modalities.renderedCode?.criticalCSS) {
    parts.push(`[STYLING - Weight: ${(weights.css * 100).toFixed(0)}%]`);
    parts.push('Critical CSS:');
    const cssText = typeof modalities.renderedCode.criticalCSS === 'string'
      ? modalities.renderedCode.criticalCSS
      : JSON.stringify(modalities.renderedCode.criticalCSS, null, 2);
    parts.push(cssText.substring(0, 2000)); // Limit length
    parts.push('\nUse this for understanding visual styling, positioning, and layout rules.\n');
  }
  
  // DOM structure
  if (modalities.renderedCode?.domStructure) {
    parts.push(`[DOM - Weight: ${(weights.dom * 100).toFixed(0)}%]`);
    parts.push('DOM Structure:');
    const domText = typeof modalities.renderedCode.domStructure === 'string'
      ? modalities.renderedCode.domStructure
      : JSON.stringify(modalities.renderedCode.domStructure, null, 2);
    parts.push(domText.substring(0, 1000)); // Limit length
    parts.push('\nUse this for understanding element relationships and computed properties.\n');
  }
  
  // Game state
  if (modalities.gameState && Object.keys(modalities.gameState).length > 0) {
    parts.push(`[STATE - Weight: ${(weights.gameState * 100).toFixed(0)}%]`);
    parts.push('Game State:');
    parts.push(JSON.stringify(modalities.gameState, null, 2));
    parts.push('\nUse this for understanding functional state and dynamic behavior.\n');
  }
  
  parts.push('\n=== EVALUATION INSTRUCTIONS ===');
  parts.push('1. Primary: Use screenshot for visual assessment');
  parts.push('2. Secondary: Use HTML/CSS for structural validation');
  parts.push('3. Tertiary: Use DOM/State for functional validation');
  parts.push('4. Weight your assessment based on the relevance weights above');
  parts.push('5. Cross-reference modalities to identify inconsistencies');
  
  return parts.join('\n');
}

/**
 * Compare structured fusion vs simple concatenation
 * 
 * @param {string} basePrompt - Base prompt
 * @param {Object} modalities - Available modalities
 * @returns {Object} Comparison of fusion strategies
 */
export function compareFusionStrategies(basePrompt, modalities) {
  // Simple concatenation (current approach)
  const simplePrompt = `${basePrompt}\n\nSCREENSHOT:\n${modalities.screenshot || 'N/A'}\n\nRENDERED CODE:\n${JSON.stringify(modalities.renderedCode || {}, null, 2)}\n\nGAME STATE:\n${JSON.stringify(modalities.gameState || {}, null, 2)}`;
  
  // Structured fusion (new approach)
  const structuredPrompt = buildStructuredFusionPrompt(basePrompt, modalities);
  
  return {
    simple: {
      length: simplePrompt.length,
      modalityCount: Object.keys(modalities).length,
      hasWeights: false
    },
    structured: {
      length: structuredPrompt.length,
      modalityCount: Object.keys(modalities).length,
      hasWeights: true,
      weights: calculateModalityWeights(modalities, basePrompt)
    },
    recommendation: 'Use structured fusion for better modality integration'
  };
}



