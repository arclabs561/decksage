/**
 * Cross-Modal Consistency Checker
 * 
 * Validates consistency between screenshot (visual) and HTML/CSS (structural).
 * Detects mismatches between what's shown visually and what the code structure indicates.
 * 
 * Research:
 * - "Cross-Modal Consistency in Multimodal Large Language Models" - Consistency issues in GPT-4V
 * - "Verifying Cross-modal Entity Consistency in News using Vision-language Models" (LVLM4CEC)
 * - "Hallucination Detection in Vision-Language Models" - Multiple papers on detecting unfaithful outputs
 * 
 * Key findings: Consistency is a major challenge. Entity verification is critical.
 * Hallucination detection is needed. Modality gap contributes to issues.
 * 
 * Note: This implementation uses heuristic-based checking. Full research implementation
 * would use VLLM-based verification and entity-level consistency checking as in LVLM4CEC.
 */

import { warn, log } from './logger.mjs';

/**
 * Check consistency between screenshot and HTML/CSS
 * 
 * @param {Object} options - Consistency check options
 * @param {string} [options.screenshot] - Screenshot path
 * @param {Object} [options.renderedCode] - Rendered code (HTML/CSS/DOM)
 * @param {Object} [options.gameState] - Game state
 * @param {Object} [options.pageState] - Page state
 * @param {boolean} [options.strict=false] - Strict mode (warn on all inconsistencies)
 * @returns {Object} Consistency check result
 */
export function checkCrossModalConsistency(options = {}) {
  const {
    screenshot,
    renderedCode,
    gameState,
    pageState,
    strict = false
  } = options;

  const issues = [];
  const warnings = [];
  const checks = {
    hasScreenshot: !!screenshot,
    hasRenderedCode: !!renderedCode,
    hasHTML: !!renderedCode?.html,
    hasCSS: !!renderedCode?.criticalCSS,
    hasDOM: !!renderedCode?.domStructure,
    hasGameState: !!gameState,
    hasPageState: !!pageState
  };

  // Check 1: Basic presence
  if (!screenshot && !renderedCode) {
    issues.push('Missing both screenshot and rendered code - cannot check consistency');
    return {
      isConsistent: false,
      issues,
      warnings,
      checks,
      score: 0
    };
  }

  // Check 2: HTML structure vs visual expectations
  if (renderedCode?.html && renderedCode?.domStructure) {
    // Check if key elements exist in DOM but might not be visible
    const domElements = Object.keys(renderedCode.domStructure);
    if (domElements.length === 0) {
      warnings.push('DOM structure is empty - may indicate missing elements');
    }

    // Check for hidden elements that should be visible
    if (renderedCode.domStructure.prideParade && !renderedCode.domStructure.prideParade.exists) {
      warnings.push('Pride parade element missing from DOM structure');
    }
  }

  // Check 3: CSS positioning vs visual layout
  if (renderedCode?.criticalCSS) {
    const cssElements = Object.keys(renderedCode.criticalCSS);
    
    // Check for positioning issues
    for (const [selector, styles] of Object.entries(renderedCode.criticalCSS)) {
      if (styles.position === 'absolute' && (styles.top === 'auto' || styles.left === 'auto')) {
        warnings.push(`Element '${selector}' has absolute positioning but auto top/left - may cause layout issues`);
      }
      
      if (styles.display === 'none' && selector.includes('game')) {
        warnings.push(`Game element '${selector}' has display:none - may not be visible`);
      }
      
      if (styles.visibility === 'hidden' && selector.includes('game')) {
        warnings.push(`Game element '${selector}' has visibility:hidden - may not be visible`);
      }
    }
  }

  // Check 4: Game state vs visual display
  if (gameState && renderedCode?.domStructure) {
    // Check if game state indicates active game but DOM doesn't show game elements
    if (gameState.gameActive && !renderedCode.domStructure.game) {
      warnings.push('Game state indicates active game but game elements not found in DOM');
    }

    // Check score consistency (if score is in game state and visible in DOM)
    if (gameState.score !== undefined) {
      // This would require VLLM to extract score from screenshot
      // For now, just note that we should check this
      if (strict) {
        warnings.push('Game state has score - should verify it matches visual display');
      }
    }
  }

  // Check 5: Page state vs rendered code
  if (pageState && renderedCode?.html) {
    // Check if page title matches
    if (pageState.title && !renderedCode.html.includes(pageState.title)) {
      warnings.push(`Page title '${pageState.title}' not found in HTML`);
    }
  }

  // Calculate consistency score
  const totalChecks = Object.values(checks).filter(Boolean).length;
  const issueCount = issues.length;
  const warningCount = warnings.length;
  const maxIssues = 5; // Normalize to 0-1 scale
  const consistencyScore = Math.max(0, 1 - (issueCount / maxIssues) - (warningCount / (maxIssues * 2)));

  const isConsistent = issueCount === 0 && (strict ? warningCount === 0 : true);

  // Log warnings if any
  if (warnings.length > 0) {
    log(`[Cross-Modal Consistency] ${warnings.length} warning(s):`, warnings);
  }

  if (issues.length > 0) {
    warn(`[Cross-Modal Consistency] ${issues.length} issue(s):`, issues);
  }

  return {
    isConsistent,
    issues,
    warnings,
    checks,
    score: consistencyScore,
    summary: issueCount === 0 && warningCount === 0
      ? 'All consistency checks passed'
      : `${issueCount} issue(s), ${warningCount} warning(s)`
  };
}

/**
 * Validate experience consistency (convenience function)
 * 
 * @param {Object} experience - Experience object from experiencePageAsPersona
 * @param {Object} [options={}] - Validation options
 * @returns {Object} Consistency check result
 */
export function validateExperienceConsistency(experience, options = {}) {
  return checkCrossModalConsistency({
    screenshot: experience.screenshots?.[0]?.path,
    renderedCode: experience.renderedCode,
    gameState: experience.pageState?.gameState || experience.gameState,
    pageState: experience.pageState,
    ...options
  });
}

