/**
 * Multi-Modal Validator
 * 
 * Enhanced validation using:
 * 1. Multi-modal inputs: Screenshots + rendered HTML/CSS + game state + principles
 * 2. Multi-perspective: Multiple personas evaluating same state
 * 3. Temporal: Screenshots at different Hz for animations
 * 
 * Note: This module requires Playwright Page object.
 * It's designed to work with @playwright/test but doesn't require it as a hard dependency.
 */

import { ValidationError } from './errors.mjs';
import { warn } from './logger.mjs';

/**
 * Extract rendered HTML/CSS for dual-view validation
 * 
 * Captures both source code (HTML/CSS) and rendered state for multi-modal validation.
 * This enables validation against both the "source of truth" (code) and the "rendered output" (visuals).
 * 
 * Dual View Benefits:
 * - Detect CSS rendering issues (code says one thing, visual shows another)
 * - Validate structural correctness (DOM matches expectations)
 * - Check computed styles vs. source styles
 * - Identify layout bugs (positioning, z-index, visibility)
 * - Verify accessibility attributes in code vs. visual rendering
 * 
 * @param {any} page - Playwright page object
 * @param {Object} [options] - Extraction options
 * @param {string[]} [options.selectors] - Custom selectors to extract (defaults to common patterns)
 * @param {number} [options.htmlLimit=10000] - Max HTML chars to extract (default 10k)
 * @param {boolean} [options.includeAllCSS=false] - Include all computed styles (default: only critical)
 * @returns {Promise<import('./index.mjs').RenderedCode>} Rendered code structure
 * @throws {ValidationError} If page is not a valid Playwright Page object
 */
export async function extractRenderedCode(page, options = {}) {
  if (!page || typeof page.evaluate !== 'function') {
    throw new ValidationError('extractRenderedCode requires a Playwright Page object', {
      received: typeof page,
      hasEvaluate: typeof page?.evaluate === 'function'
    });
  }

  const { 
    selectors = null, // Custom selectors, or null for auto-detection
    htmlLimit = 10000,
    includeAllCSS = false
  } = options;

  // Extract full HTML (source of truth)
  const html = await page.content();
  
  // Extract all stylesheets (source CSS)
  const stylesheets = await page.evaluate(() => {
    const sheets = [];
    for (const sheet of document.styleSheets) {
      try {
        const rules = [];
        for (const rule of sheet.cssRules || []) {
          rules.push({
            selectorText: rule.selectorText,
            cssText: rule.cssText,
            style: rule.style ? Object.fromEntries(
              Array.from(rule.style).map(prop => [prop, rule.style.getPropertyValue(prop)])
            ) : null
          });
        }
        sheets.push({
          href: sheet.href,
          rules: rules.slice(0, 100) // Limit to first 100 rules per sheet
        });
      } catch (e) {
        // Cross-origin stylesheets may throw
        sheets.push({ href: sheet.href, error: 'Cross-origin or inaccessible' });
      }
    }
    return sheets;
  });
  
  // Extract critical CSS (computed styles for key elements)
  // This is the "rendered" CSS (what actually applies, not source)
  const criticalCSS = await page.evaluate((customSelectors) => {
    const styles = {};
    
    // Auto-detect common selectors if not provided
    const selectorsToCheck = customSelectors || [
      'body',
      'main',
      'header',
      'footer',
      '[role="main"]',
      '[role="banner"]',
      '[role="contentinfo"]',
      'button',
      'a',
      'input',
      'form',
      '#app',
      '#root',
      '.container',
      '.main-content'
    ];
    
    selectorsToCheck.forEach(selector => {
      try {
        const el = document.querySelector(selector);
        if (el) {
          const computed = window.getComputedStyle(el);
          styles[selector] = {
            position: computed.position,
            top: computed.top,
            bottom: computed.bottom,
            left: computed.left,
            right: computed.right,
            width: computed.width,
            height: computed.height,
            backgroundColor: computed.backgroundColor,
            color: computed.color,
            display: computed.display,
            visibility: computed.visibility,
            zIndex: computed.zIndex,
            transform: computed.transform,
            opacity: computed.opacity,
            fontSize: computed.fontSize,
            fontFamily: computed.fontFamily,
            lineHeight: computed.lineHeight,
            margin: computed.margin,
            padding: computed.padding,
            border: computed.border,
            borderRadius: computed.borderRadius,
            boxShadow: computed.boxShadow,
            overflow: computed.overflow,
            textAlign: computed.textAlign
          };
        }
      } catch (e) {
        // Skip invalid selectors
      }
    });
    
    return styles;
  }, selectors);
  
  // Extract DOM structure (text-encoded representation)
  const domStructure = await page.evaluate(() => {
    const structure = {
      body: {
        tagName: document.body?.tagName,
        children: document.body?.children?.length || 0,
        textContent: document.body?.textContent?.substring(0, 500) || '',
        attributes: Array.from(document.body?.attributes || []).reduce((acc, attr) => {
          acc[attr.name] = attr.value;
          return acc;
        }, {})
      },
      head: {
        title: document.title,
        meta: Array.from(document.querySelectorAll('meta')).map(m => ({
          name: m.getAttribute('name') || m.getAttribute('property'),
          content: m.getAttribute('content')
        })),
        links: Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map(l => ({
          href: l.href,
          rel: l.rel
        }))
      },
      mainElements: []
    };
    
    // Extract key elements (auto-detect)
    const keySelectors = [
      'main', '[role="main"]', '#app', '#root', 
      'header', '[role="banner"]',
      'footer', '[role="contentinfo"]',
      'nav', '[role="navigation"]',
      'article', '[role="article"]',
      'section'
    ];
    
    keySelectors.forEach(selector => {
      try {
        const el = document.querySelector(selector);
        if (el) {
          structure.mainElements.push({
            selector: selector,
            tagName: el.tagName,
            id: el.id,
            className: el.className,
            textContent: el.textContent?.substring(0, 200) || '',
            attributes: Array.from(el.attributes).reduce((acc, attr) => {
              acc[attr.name] = attr.value;
              return acc;
            }, {}),
            boundingRect: el.getBoundingClientRect(),
            computedStyles: {
              display: window.getComputedStyle(el).display,
              visibility: window.getComputedStyle(el).visibility,
              position: window.getComputedStyle(el).position
            }
          });
        }
      } catch (e) {
        // Skip invalid selectors
      }
    });
    
    return structure;
  });
  
  return {
    // Source code (text-encoded HTML)
    html: html.substring(0, htmlLimit),
    
    // Source CSS (from stylesheets)
    stylesheets: stylesheets,
    
    // Rendered CSS (computed styles - what actually applies)
    criticalCSS,
    
    // DOM structure (text-encoded representation)
    domStructure,
    
    // Metadata
    timestamp: Date.now(),
    url: page.url(),
    viewport: {
      width: page.viewportSize()?.width || 0,
      height: page.viewportSize()?.height || 0
    }
  };
}

/**
 * Capture temporal screenshots (for animations)
 * 
 * @param {any} page - Playwright page object
 * @param {number} [fps=2] - Frames per second to capture
 * @param {number} [duration=2000] - Duration in milliseconds
 * @returns {Promise<import('./index.mjs').TemporalScreenshot[]>} Array of temporal screenshots
 * @throws {ValidationError} If page is not a valid Playwright Page object
 */
export async function captureTemporalScreenshots(page, fps = 2, duration = 2000, options = {}) {
  if (!page || typeof page.screenshot !== 'function') {
    throw new ValidationError('captureTemporalScreenshots requires a Playwright Page object', {
      received: typeof page,
      hasScreenshot: typeof page?.screenshot === 'function'
    });
  }

  const {
    optimizeForSpeed = false, // Optimize screenshot quality for high FPS
    outputDir = 'test-results'
  } = options;

  const screenshots = [];
  const interval = 1000 / fps; // ms between frames
  const frames = Math.floor(duration / interval);
  
      // Optimize screenshot quality for high FPS to reduce overhead
  const screenshotOptions = {
    type: 'png'
  };
  
  if (optimizeForSpeed && fps > 30) {
    // For high FPS (>30fps), use lower quality to reduce overhead
    screenshotOptions.quality = 70; // Lower quality (if supported by format)
  }
  
  for (let i = 0; i < frames; i++) {
    const timestamp = Date.now();
    const path = `${outputDir}/temporal-${timestamp}-${i}.png`;
    
    try {
      await page.screenshot({ ...screenshotOptions, path });
      screenshots.push({ path, frame: i, timestamp });
      
        // Use more efficient timing for high FPS
      // For very high FPS (>30), use smaller wait intervals to maintain accuracy
      if (fps > 30) {
        // Calculate actual elapsed time and adjust wait
        const elapsed = Date.now() - timestamp;
        const waitTime = Math.max(0, interval - elapsed);
        if (waitTime > 0) {
          await page.waitForTimeout(waitTime);
        }
      } else {
        await page.waitForTimeout(interval);
      }
    } catch (error) {
      warn(`[Temporal Capture] Screenshot ${i} failed: ${error.message}`);
      // Continue with next frame
    }
  }
  
  return screenshots;
}

/**
 * Multi-perspective evaluation
 * Multiple personas evaluate the same state
 * 
 * @param {(path: string, prompt: string, context: import('./index.mjs').ValidationContext) => Promise<import('./index.mjs').ValidationResult>} validateFn - Function to validate screenshot
 * @param {string} screenshotPath - Path to screenshot
 * @param {import('./index.mjs').RenderedCode} renderedCode - Rendered code structure
 * @param {Record<string, unknown>} [gameState={}] - Game state (optional)
 * @param {import('./index.mjs').Persona[] | null} [personas=null] - Array of persona objects (optional)
 * @returns {Promise<import('./index.mjs').PerspectiveEvaluation[]>} Array of perspective evaluations
 * @throws {ValidationError} If validateFn is not a function
 */
export async function multiPerspectiveEvaluation(validateFn, screenshotPath, renderedCode, gameState = {}, personas = null) {
  if (!validateFn || typeof validateFn !== 'function') {
    throw new ValidationError('multiPerspectiveEvaluation requires a validate function', {
      received: typeof validateFn
    });
  }

  // Default personas if not provided
  const defaultPersonas = [
    {
      name: 'Brutalist Designer',
      perspective: 'I evaluate based on brutalist design principles. Function over decoration. High contrast. Minimal UI.',
      focus: ['brutalist', 'contrast', 'minimalism', 'function']
    },
    {
      name: 'Accessibility Advocate',
      perspective: 'I evaluate based on accessibility standards. WCAG compliance. Keyboard navigation. Screen reader support.',
      focus: ['accessibility', 'wcag', 'keyboard', 'screen-reader']
    },
    {
      name: 'Queer Community Member',
      perspective: 'I evaluate based on queer community values. Inclusivity. Representation. Safe space.',
      focus: ['inclusivity', 'representation', 'community', 'values']
    },
    {
      name: 'Game Designer',
      perspective: 'I evaluate based on game design principles. Game feel. Mechanics. Balance.',
      focus: ['game-feel', 'mechanics', 'balance', 'polish']
    },
    {
      name: 'Product Purpose Validator',
      perspective: 'I evaluate based on product purpose alignment. Primary purpose clarity. Easter egg appropriateness.',
      focus: ['purpose', 'clarity', 'easter-egg', 'alignment']
    }
  ];

  const personasToUse = personas || defaultPersonas;
  
  const evaluations = await Promise.all(
    personasToUse.map(async (persona) => {
      // Build prompt with persona perspective
      const prompt = buildPersonaPrompt(persona, renderedCode, gameState);
      
      // Support variable goals in context for cohesive integration
      const evaluationContext = {
        gameState,
        renderedCode,
        persona: persona.name,
        perspective: persona.perspective,
        focus: persona.focus,
        ...gameState
      };
      
      // If persona has a goal property, pass it through
      if (persona.goal) {
        evaluationContext.goal = persona.goal;
      }
      
      const evaluation = await validateFn(screenshotPath, prompt, evaluationContext).catch(err => {
        warn(`[Multi-Modal] Perspective ${persona.name} failed: ${err.message}`);
        return null;
      });
      
      if (evaluation) {
        return {
          persona: persona.name,
          perspective: persona.perspective,
          focus: persona.focus,
          evaluation
        };
      }
      return null;
    })
  );
  
  return evaluations.filter(e => e !== null);
}

/**
 * Build persona-specific prompt
 */
function buildPersonaPrompt(persona, renderedCode, gameState) {
  const renderedHTML = renderedCode.html ? 
    renderedCode.html.substring(0, 5000) : 
    'HTML not captured';
  
  return `PERSONA PERSPECTIVE: ${persona.name}
${persona.perspective}

FOCUS AREAS: ${persona.focus.join(', ')}

RENDERED CODE ANALYSIS (DOM STRUCTURE):
${JSON.stringify(renderedCode.domStructure, null, 2)}

CSS VALIDATION (COMPUTED STYLES):
${JSON.stringify(renderedCode.criticalCSS, null, 2)}

GAME STATE (IF APPLICABLE):
${JSON.stringify(gameState, null, 2)}

EVALUATION TASK:
Evaluate this state from your persona's perspective. Consider:
1. Visual appearance (from screenshot)
2. Code correctness (from rendered code - check positioning, structure, styles)
3. State consistency (does visual match code and game state?)
4. Principles alignment (does it match design principles and product purpose?)

Provide evaluation from your persona's perspective.`;
}

/**
 * Comprehensive multi-modal validation
 * 
 * @param {(path: string, prompt: string, context: import('./index.mjs').ValidationContext) => Promise<import('./index.mjs').ValidationResult>} validateFn - Function to validate screenshot
 * @param {any} page - Playwright page object
 * @param {string} testName - Test name
 * @param {{
 *   fps?: number;
 *   duration?: number;
 *   captureCode?: boolean;
 *   captureState?: boolean;
 *   multiPerspective?: boolean;
 * }} [options={}] - Validation options
 * @returns {Promise<{
 *   screenshotPath: string;
 *   renderedCode: import('./index.mjs').RenderedCode | null;
 *   gameState: Record<string, unknown>;
 *   temporalScreenshots: import('./index.mjs').TemporalScreenshot[];
 *   perspectives: import('./index.mjs').PerspectiveEvaluation[];
 *   codeValidation: Record<string, boolean>;
 *   aggregatedScore: number | null;
 *   aggregatedIssues: string[];
 *   timestamp: number;
 * }>} Comprehensive validation result
 * @throws {ValidationError} If validateFn is not a function or page is invalid
 */
export async function multiModalValidation(validateFn, page, testName, options = {}) {
  if (!validateFn || typeof validateFn !== 'function') {
    throw new ValidationError('multiModalValidation requires a validate function', {
      received: typeof validateFn
    });
  }
  if (!page || typeof page.screenshot !== 'function') {
    throw new ValidationError('multiModalValidation requires a Playwright Page object', {
      received: typeof page,
      hasScreenshot: typeof page?.screenshot === 'function'
    });
  }

  const {
    fps = 2, // Frames per second for temporal sampling
    duration = 2000, // Duration in ms
    captureCode = true,
    captureState = true,
    multiPerspective = true
  } = options;
  
  // 1. Capture screenshot
  const screenshotPath = `test-results/multimodal-${testName}-${Date.now()}.png`;
  await page.screenshot({ path: screenshotPath, type: 'png' });
  
  // 2. Extract rendered code
  const renderedCode = captureCode ? await extractRenderedCode(page) : null;
  
  // 3. Extract game state
  const gameState = captureState ? await page.evaluate(() => {
    return window.gameState || {
      gameActive: false,
      bricks: [],
      ball: null,
      paddle: null
    };
  }) : {};
  
  // 4. Capture temporal screenshots (for animations)
  const temporalScreenshots = fps > 0 ? await captureTemporalScreenshots(page, fps, duration) : [];
  
  // 5. Multi-perspective evaluation
  const perspectives = multiPerspective 
    ? await multiPerspectiveEvaluation(validateFn, screenshotPath, renderedCode, gameState)
    : [];
  
  // 6. Code validation (structural checks)
  const codeValidation = renderedCode ? {
    prideParadePosition: renderedCode.domStructure.prideParade?.computedTop === '0px' || renderedCode.domStructure.prideParade?.computedTop?.startsWith('calc'),
    prideParadeFlagCount: (renderedCode.domStructure.prideParade?.flagRowCount || 0) >= 15,
    flagsDynamicallyGenerated: (renderedCode.domStructure.prideParade?.flagRowCount || 0) >= 15,
    footerPosition: renderedCode.domStructure.footer?.computedBottom === '0px' || renderedCode.domStructure.footer?.computedBottom?.startsWith('calc'),
    footerStripeDynamicallyGenerated: renderedCode.domStructure.footer?.hasStripe === true,
    paymentCodeVisible: renderedCode.domStructure.paymentCode?.visible === true
  } : {};
  
  // 7. Aggregate evaluation
  const aggregatedScore = perspectives.length > 0
    ? perspectives.reduce((sum, p) => sum + (p.evaluation?.score || 0), 0) / perspectives.length
    : null;
  
  const aggregatedIssues = perspectives.length > 0
    ? [...new Set(perspectives.flatMap(p => p.evaluation?.issues || []))]
    : [];
  
  return {
    screenshotPath,
    renderedCode,
    gameState,
    temporalScreenshots,
    perspectives,
    codeValidation,
    aggregatedScore,
    aggregatedIssues,
    timestamp: Date.now()
  };
}

