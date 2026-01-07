/**
 * Persona-Based Page Experience Testing
 * 
 * Tests page experience from different persona perspectives with human-interpreted time scales.
 * 
 * Not just gameplay - any page experience can be tested with personas.
 * Time scales are human-interpreted (reading time, interaction time, etc.) not mechanical fps.
 */

import { warn, log } from './logger.mjs';
import { trackPropagation } from './experience-propagation.mjs';
import { checkCrossModalConsistency } from './cross-modal-consistency.mjs';

// Lazy import for variable goals
let generateGamePrompt = null;
async function getGenerateGamePrompt() {
  if (!generateGamePrompt) {
    try {
      const module = await import('./game-goal-prompts.mjs');
      generateGamePrompt = module.generateGamePrompt;
    } catch (error) {
      return null;
    }
  }
  return generateGamePrompt;
}

/**
 * Experience a page from a persona's perspective
 * 
 * @param {any} page - Playwright page object
 * @param {import('./index.mjs').Persona} persona - Persona configuration
 * @param {import('./index.mjs').PersonaExperienceOptions} [options={}] - Experience options
 * @returns {Promise<import('./index.mjs').PersonaExperienceResult>} Experience result with notes, screenshots, and evaluation
 */
export async function experiencePageAsPersona(page, persona, options = {}) {
  const {
    viewport = { width: 1280, height: 720 },
    device = 'desktop',
    darkMode = false,
    timeScale = 'human', // 'human' (reading/interaction time) or 'mechanical' (fps)
    captureScreenshots = true,
    captureState = true,
    captureCode = true,
    notes = [],
    trace = null // Optional ExperienceTrace instance
  } = options;

  const experienceNotes = [...notes];
  const screenshots = [];
  const startTime = Date.now();
  
  // If trace provided, add initial event
  if (trace) {
    trace.addEvent('experience-start', {
      persona: persona.name,
      viewport,
      device,
      timeScale
    });
  }
  
  // Helper to capture screenshot at current state
  const captureScreenshotNow = async (step, description) => {
    if (!captureScreenshots) return null;
    
    const timestamp = Date.now();
    const elapsed = timestamp - startTime;
    const screenshotPath = `test-results/persona-${persona.name.toLowerCase().replace(/\s+/g, '-')}-${step}-${timestamp}.png`;
    
    try {
      await page.screenshot({ path: screenshotPath, fullPage: true });
      screenshots.push({
        path: screenshotPath,
        timestamp,
        elapsed,
        step,
        description
      });
      
      // Add to trace if available
      if (trace) {
        trace.addScreenshot(screenshotPath, description || step);
      }
      
      return screenshotPath;
    } catch (error) {
      // Silently fail - screenshot capture is optional
      return null;
    }
  };

  // Set viewport based on persona device preference
  // 
  // BUG FIX (2025-01): Viewports were only set if persona.device existed.
  // This caused mobile/tablet personas to get desktop viewports (1280x720) when
  // persona.device was not set but options.device was.
  // 
  // The fix: Check both persona.device AND options.device
  // 
  // Viewport sizes:
  // - mobile: 375x667 (iPhone SE - smallest common mobile)
  // - tablet: 768x1024 (iPad - standard tablet)
  // - desktop: 1280x720 (standard desktop resolution)
  // 
  // DON'T CHANGE VIEWPORT SIZES without:
  // - Understanding why these sizes were chosen
  // - Testing with different viewports
  // - Validating persona diversity tests
  const deviceToUse = persona.device || device;
  if (deviceToUse) {
    const deviceViewports = {
      mobile: { width: 375, height: 667 },
      tablet: { width: 768, height: 1024 },
      desktop: { width: 1280, height: 720 }
    };
    const targetViewport = deviceViewports[deviceToUse];
    if (targetViewport) {
      await page.setViewportSize(targetViewport);
    } else {
      await page.setViewportSize(viewport);
    }
  } else {
    await page.setViewportSize(viewport);
  }

  // Navigate to page
  await page.goto(options.url || options.baseURL || 'about:blank', {
    waitUntil: 'domcontentloaded'
  });
  
  // Capture screenshot immediately after page load
  const pageLoadScreenshot = await captureScreenshotNow('page-load', 'Page loaded');
  // Screenshot already added to trace in captureScreenshotNow

  // Step 1: Initial page load experience (human time scale)
  const initialLoadTime = await humanTimeScale('page-load', {
    minTime: 1000, // Minimum 1 second to read page
    maxTime: 5000, // Maximum 5 seconds for slow readers
    timeScale
  });

  await page.waitForTimeout(initialLoadTime);
  
  // Capture after initial reading time
  await captureScreenshotNow('after-initial-read', 'After initial reading time');

  // Extract initial state
  let renderedCode = null;
  let pageState = null;

  if (captureCode) {
    renderedCode = await extractRenderedCode(page);
    // Track HTML/CSS capture
    trackPropagation('capture', { renderedCode }, 'Captured HTML/CSS from page');
  }

  if (captureState) {
    pageState = await page.evaluate(() => {
      return {
        title: document.title,
        h1: document.querySelector('h1')?.textContent || '',
        description: document.querySelector('meta[name="description"]')?.content || '',
        viewport: { width: window.innerWidth, height: window.innerHeight },
        darkMode: document.documentElement.classList.contains('dark') || 
                 window.matchMedia('(prefers-color-scheme: dark)').matches
      };
    });
  }

  // Persona's initial observation
  // Preserve more HTML/CSS context (increased from 500 to 2000 chars, and always include critical CSS/DOM)
  const initialNote = {
    step: 'initial_experience',
    persona: persona.name,
    device: persona.device || device,
    viewport: await page.viewportSize(),
    observation: `Arrived at page - ${pageState?.title || 'unknown'}`,
    pageState,
    renderedCode: renderedCode ? {
      html: renderedCode.html?.substring(0, 2000), // Increased from 500 to 2000
      criticalCSS: renderedCode.criticalCSS, // Always preserve CSS
      domStructure: renderedCode.domStructure // Always preserve DOM structure
    } : null,
    timestamp: Date.now(),
    elapsed: Date.now() - startTime
  };
  experienceNotes.push(initialNote);
  
  // Track HTML/CSS in notes
  trackPropagation('notes', { renderedCode: initialNote.renderedCode, pageState: initialNote.pageState }, 'Added HTML/CSS to experience notes');
  
  // Check cross-modal consistency
  if (captureScreenshots && renderedCode) {
    const consistency = checkCrossModalConsistency({
      screenshot: pageLoadScreenshot,
      renderedCode,
      pageState
    });
    if (!consistency.isConsistent && consistency.issues.length > 0) {
      warn(`[Experience] Cross-modal consistency issues: ${consistency.issues.join(', ')}`);
    }
  }
  
  // Add to trace if available
  if (trace) {
    trace.addEvent('observation', {
      step: 'initial_experience',
      observation: initialNote.observation,
      pageState: initialNote.pageState,
      renderedCode: initialNote.renderedCode
    });
    if (pageState) {
      trace.addStateSnapshot(pageState, 'initial_experience');
    }
  }

  // Step 2: Reading/scanning experience (human time scale)
  if (trace) {
    trace.addEvent('observation', {
      step: 'before-reading',
      observation: 'About to read/scan page content'
    });
  }
  await captureScreenshotNow('before-reading', 'Before reading/scanning');
  
  const readingTime = await humanTimeScale('reading', {
    minTime: 2000, // Minimum 2 seconds to read/scan
    maxTime: 10000, // Maximum 10 seconds for thorough reading
    timeScale,
    contentLength: pageState?.h1?.length || 0
  });

  await page.waitForTimeout(readingTime);
  
  // Capture after reading
  if (trace) {
    trace.addEvent('observation', {
      step: 'after-reading',
      observation: 'Finished reading/scanning page content'
    });
  }
  await captureScreenshotNow('after-reading', 'After reading/scanning');

  // Step 3: Interaction experience (if persona has goals)
  if (persona.goals && persona.goals.length > 0) {
    for (const goal of persona.goals) {
      // Capture before interaction
      if (trace) {
        trace.addEvent('interaction', {
          step: `before-${goal}`,
          goal,
          observation: `Preparing to ${goal}`
        });
      }
      await captureScreenshotNow(`before-${goal}`, `Before ${goal}`);
      
      const interactionTime = await humanTimeScale('interaction', {
        minTime: 500, // Minimum 0.5 seconds to interact
        maxTime: 3000, // Maximum 3 seconds for complex interactions
        timeScale,
        interactionType: goal
      });

      // Simulate persona trying to achieve goal
      // This is extensible - different personas interact differently
      await simulatePersonaInteraction(page, persona, goal);
      
      // Capture immediately after interaction (before delay)
      if (trace) {
        trace.addEvent('interaction', {
          step: `during-${goal}`,
          goal,
          observation: `Performing ${goal}`
        });
      }
      await captureScreenshotNow(`during-${goal}`, `During ${goal}`);

      await page.waitForTimeout(interactionTime);
      
      // Capture after interaction delay
      if (trace) {
        trace.addEvent('interaction', {
          step: `after-${goal}`,
          goal,
          observation: `Completed ${goal}`
        });
      }
      await captureScreenshotNow(`after-${goal}`, `After ${goal}`);

      // Update state
      if (captureState) {
        pageState = await page.evaluate(() => {
          return {
            title: document.title,
            viewport: { width: window.innerWidth, height: window.innerHeight },
            activeElement: document.activeElement?.tagName || null
          };
        });
      }

      const interactionNote = {
        step: `interaction_${goal}`,
        persona: persona.name,
        goal,
        observation: `Attempted to ${goal}`,
        pageState,
        timestamp: Date.now(),
        elapsed: Date.now() - startTime
      };
      experienceNotes.push(interactionNote);
      
      // Add to trace if available
      if (trace) {
        trace.addEvent('interaction', {
          step: `interaction_${goal}`,
          goal,
          observation: interactionNote.observation,
          pageState: interactionNote.pageState
        });
        if (pageState) {
          trace.addStateSnapshot(pageState, `after-${goal}`);
        }
      }
    }
  }
  
  // Capture final state
  const finalScreenshot = await captureScreenshotNow('final-state', 'Final state');
  // Screenshot already added to trace in captureScreenshotNow
  
  // Add final event to trace
  if (trace) {
    trace.addEvent('experience-end', {
      duration: Date.now() - startTime,
      noteCount: experienceNotes.length,
      screenshotCount: screenshots.length
    });
  }

  // Track final propagation
  trackPropagation('experience-complete', {
    renderedCode,
    pageState,
    screenshot: screenshots.length > 0 ? screenshots[0].path : null
  }, 'Experience complete');
  
  // Final consistency check
  let consistency = null;
  if (captureScreenshots && renderedCode && screenshots.length > 0) {
    consistency = checkCrossModalConsistency({
      screenshot: screenshots[screenshots.length - 1].path,
      renderedCode,
      pageState
    });
  }

  // Automatically aggregate temporal notes (use fixed temporal system)
  let aggregated = null;
  let aggregatedMultiScale = null;
  if (experienceNotes.length > 0) {
    try {
      const { aggregateTemporalNotes } = await import('./temporal.mjs');
      const { aggregateMultiScale } = await import('./temporal-decision.mjs');
      
      // Standard temporal aggregation
      aggregated = aggregateTemporalNotes(experienceNotes, {
        windowSize: 10000, // 10 second windows
        decayFactor: 0.9
      });
      
      // Multi-scale aggregation for richer analysis
      // Always return multi-scale result (even if empty) for consistency
      try {
        aggregatedMultiScale = aggregateMultiScale(experienceNotes, {
          attentionWeights: true
        });
        // Ensure it has the expected structure
        if (!aggregatedMultiScale.scales) {
          aggregatedMultiScale.scales = {};
        }
        if (!aggregatedMultiScale.coherence) {
          aggregatedMultiScale.coherence = {};
        }
      } catch (error) {
        // Return empty multi-scale result instead of null
        warn(`[Experience] Multi-scale aggregation failed: ${error.message}`);
        aggregatedMultiScale = {
          scales: {},
          summary: 'Multi-scale aggregation failed',
          coherence: {}
        };
      }
      
      trackPropagation('temporal-aggregation', {
        windows: aggregated.windows.length,
        coherence: aggregated.coherence,
        scales: Object.keys(aggregatedMultiScale.scales || {})
      }, 'Aggregated temporal notes automatically');
    } catch (error) {
      warn(`[Experience] Temporal aggregation failed: ${error.message}`);
    }
  }

  // Get actual viewport size (may differ from requested if browser clamped it)
  // This ensures we return what was actually set, not what we requested
  const actualViewport = await page.viewportSize();
  
  return {
    persona: persona.name,
    device: persona.device || device,
    viewport: actualViewport,
    notes: experienceNotes,
    aggregated, // Include aggregated temporal notes
    aggregatedMultiScale, // Include multi-scale aggregation
    screenshots,
    renderedCode,
    pageState,
    duration: Date.now() - startTime,
    timeScale,
    trace: trace ? trace.getSummary() : null,
    consistency // Include consistency check result
  };
}

/**
 * Human-interpreted time scale
 * 
 * Not mechanical fps - human reading/interaction time based on content and context.
 * Now uses research-aligned humanPerceptionTime from temporal-decision.mjs
 * 
 * @param {string} action - Action type ('page-load', 'reading', 'interaction')
 * @param {Object} options - Time scale options
 * @returns {Promise<number>} Time in milliseconds
 */
async function humanTimeScale(action, options = {}) {
  const {
    minTime = 1000,
    maxTime = 5000,
    timeScale = 'human',
    contentLength = 0,
    interactionType = null,
    persona = null,
    attentionLevel = 'normal'
  } = options;

  if (timeScale === 'mechanical') {
    // Mechanical fps - fixed intervals
    return 1000 / 2; // 2 fps = 500ms
  }

  // Use research-aligned humanPerceptionTime if available
  try {
    const { humanPerceptionTime } = await import('./temporal-decision.mjs');
    
    // Map action types
    let perceptionAction = action;
    if (action === 'page-load') perceptionAction = 'reading';
    if (action === 'interaction') perceptionAction = 'interaction';
    
    const perceptionTime = humanPerceptionTime(perceptionAction, {
      persona,
      attentionLevel,
      actionComplexity: interactionType ? (interactionType === 'think' ? 'complex' : 'normal') : 'normal',
      contentLength
    });
    
    // Clamp to min/max if provided
    return Math.max(minTime || 0, Math.min(maxTime || Infinity, perceptionTime));
  } catch (error) {
    // Fallback to original implementation if import fails
    // Silently fall back - this is expected in some environments
  }

  // Fallback: Human-interpreted time scale (original implementation)
  switch (action) {
    case 'page-load':
      // Page load: 1-5 seconds depending on complexity
      return Math.random() * (maxTime - minTime) + minTime;

    case 'reading':
      // Reading: Based on content length
      // Average reading speed: 200-300 words per minute
      // Rough estimate: 1 word = 5 characters
      const words = contentLength / 5;
      const readingSpeed = 250; // words per minute
      const readingTime = (words / readingSpeed) * 60 * 1000; // milliseconds
      return Math.max(minTime, Math.min(maxTime, readingTime));

    case 'interaction':
      // Interaction: Based on interaction type
      const interactionTimes = {
        'click': 500,
        'type': 1000,
        'scroll': 800,
        'read': 2000,
        'think': 1500
      };
      return interactionTimes[interactionType] || minTime;

    default:
      return minTime;
  }
}

/**
 * Simulate persona interaction
 * 
 * Different personas interact differently based on their goals and concerns.
 * 
 * @param {Page} page - Playwright page object
 * @param {Object} persona - Persona configuration
 * @param {string} goal - Goal to achieve
 */
async function simulatePersonaInteraction(page, persona, goal) {
  // This is extensible - different personas interact differently
  // For now, basic interaction simulation
  
  if (goal.includes('click') || goal.includes('button')) {
    // Try to find and click a button
    const button = await page.locator('button').first();
    if (await button.isVisible()) {
      await button.click();
    }
  } else if (goal.includes('type') || goal.includes('input')) {
    // Try to find and fill an input
    const input = await page.locator('input[type="text"]').first();
    if (await input.isVisible()) {
      await input.fill('Test');
    }
  } else if (goal.includes('scroll') || goal.includes('read')) {
    // Scroll to read more
    await page.evaluate(() => window.scrollBy(0, window.innerHeight));
  }
}

/**
 * Extract rendered code (re-export from multi-modal)
 */
async function extractRenderedCode(page) {
  // Re-export from multi-modal.mjs
  const { extractRenderedCode } = await import('./multi-modal.mjs');
  return extractRenderedCode(page);
}

/**
 * Experience page with multiple personas
 * 
 * @param {Page} page - Playwright page object
 * @param {Array} personas - Array of persona configurations
 * @param {Object} options - Experience options
 * @returns {Promise<Array>} Array of experience results
 */
/**
 * Experience a page from multiple persona perspectives
 * 
 * @param {any} page - Playwright page object
 * @param {import('./index.mjs').Persona[]} personas - Array of persona configurations
 * @param {import('./index.mjs').PersonaExperienceOptions} [options={}] - Experience options
 * @returns {Promise<import('./index.mjs').PersonaExperienceResult[]>} Array of experience results
 */
export async function experiencePageWithPersonas(page, personas, options = {}) {
  const experiences = [];

  for (const persona of personas) {
    const experience = await experiencePageAsPersona(page, persona, options);
    experiences.push(experience);
  }

  return experiences;
}

