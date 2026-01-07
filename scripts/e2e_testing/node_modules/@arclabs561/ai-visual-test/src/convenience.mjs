/**
 * High-Level Convenience Functions
 * 
 * Provides simplified APIs for common workflows, reducing boilerplate
 * and making the library easier to use for common patterns.
 * 
 * Based on common visual testing workflows and usage patterns.
 */

import { validateScreenshot } from './judge.mjs';
import { normalizeValidationResult } from './validation-result-normalizer.mjs';
import { experiencePageAsPersona, experiencePageWithPersonas } from './persona-experience.mjs';
import { extractRenderedCode, captureTemporalScreenshots, multiPerspectiveEvaluation } from './multi-modal.mjs';
import { aggregateTemporalNotes, formatNotesForPrompt } from './temporal.mjs';
import { aggregateMultiScale } from './temporal-decision.mjs';
import { generateGamePrompt, createGameGoal, createGameGoals } from './game-goal-prompts.mjs';
import { checkCrossModalConsistency, validateExperienceConsistency } from './cross-modal-consistency.mjs';
import { trackPropagation } from './experience-propagation.mjs';
import { ValidationError } from './errors.mjs';
import { log, warn } from './logger.mjs';
import { TEMPORAL_CONSTANTS } from './constants.mjs';

/**
 * Test gameplay with variable goals
 * 
 * Complete workflow for testing games with variable goals/prompts.
 * Originally motivated by interactive web applications that require
 * real-time validation, variable goals, and temporal understanding.
 * 
 * Handles persona experience, temporal capture, goal evaluation, and consistency checks.
 * 
 * Supports interactive games:
 * - Games that activate from payment screens (not just standalone games)
 * - Game activation via keyboard shortcuts (e.g., 'g' key)
 * - Game state extraction (window.gameState)
 * - Temporal preprocessing for better performance
 * 
 * @param {import('playwright').Page} page - Playwright page object
 * @param {Object} options - Test options
 * @param {string} options.url - Game URL (or page URL if game activates from page)
 * @param {string | Object | Array | Function} [options.goals] - Variable goals (string, object, array, or function)
 * @param {Array<Object>} [options.personas] - Personas to test with
 * @param {boolean} [options.captureTemporal] - Capture temporal screenshots
 * @param {number} [options.fps] - FPS for temporal capture
 * @param {number} [options.duration] - Duration for temporal capture (ms)
 * @param {boolean} [options.captureCode] - Extract rendered code
 * @param {boolean} [options.checkConsistency] - Check cross-modal consistency
 * @param {string} [options.gameActivationKey] - Keyboard key to activate game (e.g., 'g')
 * @param {string} [options.gameSelector] - Selector to wait for game activation (e.g., '#game-paddle')
 * @param {boolean} [options.useTemporalPreprocessing] - Use temporal preprocessing for better performance
 * @param {boolean} [options.play] - If true, actually play the game (uses playGame() internally)
 * @returns {Promise<Object>} Test results
 */
export async function testGameplay(page, options = {}) {
  const {
    url,
    goals = ['fun', 'accessibility', 'performance'],
    personas = null,
    captureTemporal = false,
    fps = 2,
    duration = 5000,
    captureCode = true,
    checkConsistency = true,
    gameActivationKey = null, // e.g., 'g' to activate game
    gameSelector = null, // e.g., '#game-paddle' selector
    useTemporalPreprocessing = false,
    play = false // NEW: Option to actually play the game
  } = options;
  
  // If play mode, use playGame() function
  if (play) {
    const { playGame } = await import('./game-player.mjs');
    const goal = Array.isArray(goals) ? goals[0] : goals;
    const goalString = typeof goal === 'string' ? goal : goal?.description || 'Play the game well';
    
    return await playGame(page, {
      goal: goalString,
      maxSteps: options.maxSteps || 100,
      fps: options.fps || 2,
      gameActivationKey,
      gameSelector,
      url
    });
  }

  if (!url) {
    throw new ValidationError('testGameplay: url is required', { function: 'testGameplay', parameter: 'url' });
  }

  log('[Convenience] Testing gameplay:', { url, goals, gameActivationKey, gameSelector });

  const result = {
    url,
    goals: Array.isArray(goals) ? goals : [goals],
    experiences: [],
    evaluations: [],
    aggregated: null,
    consistency: null,
    propagation: []
  };

  try {
    // Navigate to game/page
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForLoadState('networkidle');

    // Activate game if needed (for games that activate from other screens)
    if (gameActivationKey) {
      log(`[Convenience] Activating game with key: ${gameActivationKey}`);
      await page.keyboard.press(gameActivationKey);
      
      // Wait for game to activate
      if (gameSelector) {
        await page.waitForSelector(gameSelector, { timeout: 5000 }).catch(() => {
          warn(`[Convenience] Game selector ${gameSelector} not found after activation`);
        });
      }
      
      // Wait a bit for game to initialize
      await page.waitForTimeout(500);
    }

    // Extract rendered code
    let renderedCode = null;
    if (captureCode) {
      renderedCode = await extractRenderedCode(page);
      trackPropagation('capture', { renderedCode }, 'Captured HTML/CSS for gameplay test');
    }

    // Extract game state (handles window.gameState structure and other games)
    const gameState = await page.evaluate(() => {
      const state = window.gameState || {};
      return {
        gameActive: state.gameActive || false,
        score: state.score || 0,
        level: state.level || 0,
        lives: state.lives || 3,
        ball: state.ball || null,
        paddle: state.paddle || null,
        bricks: state.bricks || null,
        // Include any other game state properties
        ...state
      };
    });

    // Experience with personas (if provided)
    if (personas && personas.length > 0) {
      const experiences = await experiencePageWithPersonas(page, personas, {
        url,
        captureScreenshots: true,
        captureCode: captureCode,
        captureState: true
      });
      result.experiences = experiences;
    } else {
      // Single experience
      const experience = await experiencePageAsPersona(page, {
        name: 'Game Tester',
        perspective: 'Testing gameplay experience',
        focus: ['gameplay', 'fun', 'accessibility']
      }, {
        url,
        captureScreenshots: true,
        captureCode: captureCode,
        captureState: true
      });
      result.experiences = [experience];
    }

    // IMPROVEMENT: Capture temporal screenshots with preprocessing support
    if (captureTemporal) {
      const temporalScreenshots = await captureTemporalScreenshots(page, fps, duration);
      result.temporalScreenshots = temporalScreenshots;
      trackPropagation('temporal', { count: temporalScreenshots.length }, 'Captured temporal screenshots');
      
      // IMPROVEMENT: Use temporal preprocessing if requested (better performance)
      if (useTemporalPreprocessing && temporalScreenshots.length > 0) {
        const { createTemporalPreprocessingManager, createAdaptiveTemporalProcessor } = await import('./temporal-preprocessor.mjs');
        const preprocessingManager = createTemporalPreprocessingManager();
        const adaptiveProcessor = createAdaptiveTemporalProcessor(preprocessingManager);
        
        const notes = temporalScreenshots.map((frame, index) => ({
          timestamp: frame.timestamp,
          elapsed: frame.elapsed || index * (1000 / fps),
          screenshotPath: frame.path,
          step: `gameplay_frame_${index}`,
          observation: `Frame ${index} of gameplay`
        }));
        
        const processed = await adaptiveProcessor.process(notes, {
          testType: 'gameplay-temporal',
          viewport: await page.viewportSize()
        });
        
        result.processedTemporalNotes = processed;
        trackPropagation('temporal-preprocessing', { 
          original: notes.length, 
          processed: processed.length 
        }, 'Processed temporal notes with adaptive preprocessing');
      }
    }

    // Evaluate with variable goals
    const goalArray = Array.isArray(goals) ? goals : [goals];
    const goalEvaluations = [];

    for (const goal of goalArray) {
      // Use last screenshot from experience
      const screenshotPath = result.experiences[0]?.screenshots?.[result.experiences[0].screenshots.length - 1]?.path;
      if (!screenshotPath) {
        warn('[Convenience] No screenshot available for goal evaluation');
        continue;
      }

      // Generate prompt from goal (for display/debugging, goal also used by prompt composition)
      const prompt = generateGamePrompt(goal, {
        gameState,
        renderedCode,
        stage: 'gameplay'
      });

      // Use aggregated notes from experience if available
      const experience = result.experiences[0];
      const temporalNotes = experience?.aggregated || null;
      
      // Validate with goal in context (prompt composition system will use goal)
      // Include temporal notes for richer context
      const evaluation = await validateScreenshot(screenshotPath, prompt, {
        testType: 'gameplay-goal',
        gameState,
        renderedCode,
        goal: goal, // Pass goal in context - prompt composition system will use it
        temporalNotes: temporalNotes, // Include aggregated temporal notes
        enableUncertaintyReduction: true // Enable uncertainty reduction for gameplay testing
      });

      goalEvaluations.push({
        goal: typeof goal === 'string' ? goal : goal.description || 'unknown',
        evaluation,
        prompt
      });
    }

    result.evaluations = goalEvaluations;

    // Use aggregated notes from experiences (automatically included)
    // Also aggregate across all experiences for cross-experience analysis
    const allNotes = result.experiences.flatMap(exp => exp.notes || []);
    
      // Always return aggregated notes (even if empty) for consistency
    if (allNotes.length > 0) {
      // Use fixed temporal aggregation system
      const aggregated = aggregateTemporalNotes(allNotes, {
        windowSize: 5000,
        decayFactor: 0.9
      });
      result.aggregated = aggregated;
      
      // Also use multi-scale aggregation for richer analysis
      // Always return multi-scale result (even if empty) for consistency
      try {
        const { aggregateMultiScale } = await import('./temporal-decision.mjs');
        const aggregatedMultiScale = aggregateMultiScale(allNotes, {
          attentionWeights: true
        });
        // Ensure it has the expected structure
        if (!aggregatedMultiScale.scales) {
          aggregatedMultiScale.scales = {};
        }
        if (!aggregatedMultiScale.coherence) {
          aggregatedMultiScale.coherence = {};
        }
        result.aggregatedMultiScale = aggregatedMultiScale;
      } catch (error) {
        warn(`[Convenience] Multi-scale aggregation failed: ${error.message}`);
        // Return empty multi-scale result instead of null
        result.aggregatedMultiScale = {
          scales: {},
          summary: 'Multi-scale aggregation failed',
          coherence: {}
        };
      }
      
      trackPropagation('aggregation', { 
        windows: aggregated.windows.length,
        coherence: aggregated.coherence,
        scales: Object.keys(result.aggregatedMultiScale.scales || {})
      }, 'Aggregated temporal notes with multi-scale');
    } else {
      // Return empty aggregated structure if no notes (for consistency)
      result.aggregated = {
        windows: [],
        coherence: 0,
        summary: 'No notes to aggregate',
        timeSpan: 0
      };
      result.aggregatedMultiScale = {
        scales: {},
        summary: 'No notes to aggregate',
        coherence: {}
      };
    }
    
    // Use aggregated notes from individual experiences too
    result.experiences.forEach((exp, i) => {
      if (exp.aggregated) {
        trackPropagation('experience-aggregation', {
          experienceIndex: i,
          windows: exp.aggregated.windows.length,
          coherence: exp.aggregated.coherence
        }, `Experience ${i} has aggregated notes`);
      }
    });

    // Check cross-modal consistency (if requested)
    if (checkConsistency && renderedCode && result.experiences[0]?.screenshots?.length > 0) {
      const screenshotPath = result.experiences[0].screenshots[result.experiences[0].screenshots.length - 1].path;
      const consistency = checkCrossModalConsistency({
        screenshot: screenshotPath,
        renderedCode,
        pageState: gameState
      });
      result.consistency = consistency;
      trackPropagation('consistency', { isConsistent: consistency.isConsistent }, 'Checked cross-modal consistency');
    }

    // Get propagation history
    const { getPropagationTracker } = await import('./experience-propagation.mjs');
    result.propagation = getPropagationTracker().getHistory();

  } catch (error) {
    warn(`[Convenience] Gameplay test failed: ${error.message}`);
    result.error = error.message;
    
    // Ensure aggregated structures are always present even on error
    if (!result.aggregated) {
      result.aggregated = {
        windows: [],
        coherence: 0,
        summary: 'Error during aggregation',
        timeSpan: 0
      };
    }
    if (!result.aggregatedMultiScale) {
      result.aggregatedMultiScale = {
        scales: {},
        summary: 'Error during aggregation',
        coherence: {}
      };
    }
  }

  // Final check - ensure aggregated structures are always present
  if (!result.aggregated) {
    result.aggregated = {
      windows: [],
      coherence: 0,
      summary: 'No aggregation performed',
      timeSpan: 0
    };
  }
  if (!result.aggregatedMultiScale) {
    result.aggregatedMultiScale = {
      scales: {},
      summary: 'No aggregation performed',
      coherence: {}
    };
  }

  return result;
}

/**
 * Test browser experience with multiple stages
 * 
 * Complete workflow for testing browser experiences across multiple stages
 * (initial, form, payment, gameplay, etc.).
 * 
 * @param {import('playwright').Page} page - Playwright page object
 * @param {Object} options - Test options
 * @param {string} options.url - Page URL
 * @param {Array<Object>} [options.personas] - Personas to test with
 * @param {Array<string>} [options.stages] - Stages to test ('initial', 'form', 'payment', 'gameplay')
 * @param {boolean} [options.captureCode] - Extract rendered code
 * @param {boolean} [options.captureTemporal] - Capture temporal screenshots
 * @returns {Promise<Object>} Test results
 */
export async function testBrowserExperience(page, options = {}) {
  const {
    url,
    personas = null,
    stages = ['initial', 'form', 'payment'],
    captureCode = true,
    captureTemporal = false
  } = options;

  if (!url) {
    throw new ValidationError('testBrowserExperience: url is required', { function: 'testBrowserExperience', parameter: 'url' });
  }

  log('[Convenience] Testing browser experience:', { url, stages });

  const result = {
    url,
    stages: [],
    experiences: [],
    evaluations: []
  };

  try {
    // Navigate to page
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForLoadState('networkidle');

    // Test each stage
    for (const stage of stages) {
      log(`[Convenience] Testing stage: ${stage}`);

      // Extract rendered code for this stage
      let renderedCode = null;
      if (captureCode) {
        renderedCode = await extractRenderedCode(page);
      }

      // Get page state
      const pageState = await page.evaluate(() => {
        return {
          title: document.title,
          url: window.location.href,
          viewport: {
            width: window.innerWidth,
            height: window.innerHeight
          }
        };
      });

      // Experience with personas (if provided)
      if (personas && personas.length > 0) {
        const experiences = await experiencePageWithPersonas(page, personas, {
          url,
          captureScreenshots: true,
          captureCode: captureCode,
          captureState: true
        });
        result.experiences.push(...experiences);
      } else {
        // Single experience
        const experience = await experiencePageAsPersona(page, {
          name: 'Browser Tester',
          perspective: `Testing ${stage} stage`,
          focus: ['usability', 'accessibility']
        }, {
          url,
          captureScreenshots: true,
          captureCode: captureCode,
          captureState: true
        });
        result.experiences.push(experience);
      }

      // Evaluate this stage
      // Use aggregated notes from experience if available
      const lastExperience = result.experiences[result.experiences.length - 1];
      const screenshotPath = lastExperience?.screenshots?.[0]?.path;
      if (screenshotPath) {
        const prompt = `Evaluate the ${stage} stage. Check for usability, accessibility, and user experience.`;
        
        // Include temporal notes from experience
        const temporalNotes = lastExperience?.aggregated || null;
        
        const evaluation = await validateScreenshot(screenshotPath, prompt, {
          testType: `browser-experience-${stage}`,
          renderedCode,
          pageState,
          temporalNotes: temporalNotes, // Include aggregated temporal notes
          enableUncertaintyReduction: true // Enable uncertainty reduction for comprehensive testing
        });
        result.evaluations.push({
          stage,
          evaluation
        });
      }

      result.stages.push(stage);
      
      // Aggregate temporal notes across all stages
      const allStageNotes = result.experiences.flatMap(exp => exp.notes || []);
      if (allStageNotes.length > 0) {
        const stageAggregated = aggregateTemporalNotes(allStageNotes, {
          windowSize: 10000,
          decayFactor: 0.9
        });
        result.aggregated = stageAggregated;
        
        // Multi-scale aggregation across stages
        const stageMultiScale = aggregateMultiScale(allStageNotes, {
          attentionWeights: true
        });
        result.aggregatedMultiScale = stageMultiScale;
      }

      // Navigate to next stage (if needed)
      if (stage === 'form' && stages.includes('payment')) {
        // Fill form to get to payment
        try {
          await page.fill('#name', 'Test User');
          await page.fill('#amount', '5');
          await page.click('#continue-btn');
          await page.waitForSelector('#payment:not(.hidden)', { timeout: 10000 });
        } catch (e) {
          warn(`[Convenience] Could not navigate to payment stage: ${e.message}`);
        }
      }
    }

  } catch (error) {
    warn(`[Convenience] Browser experience test failed: ${error.message}`);
    result.error = error.message;
  }

  return result;
}

/**
 * Validate screenshot with variable goals
 * 
 * Simplified API for validating screenshots with variable goals/prompts.
 * Supports string goals, goal objects, arrays, and functions.
 * 
 * Originally motivated by interactive web applications
 * that requires real-time validation, variable goals, and temporal understanding.
 * 
 * Supports:
 * - Brutalist rubric goals
 * - Accessibility goals with contrast requirements
 * - Game state validation goals
 * - Better error messages and context
 * 
 * @param {string} screenshotPath - Path to screenshot
 * @param {Object} options - Validation options
 * @param {string | Object | Array | Function} options.goal - Variable goal (string, object, array, or function)
 * @param {Object} [options.gameState] - Game state (if applicable)
 * @param {Object} [options.renderedCode] - Rendered code (if available)
 * @param {Object} [options.persona] - Persona (if applicable)
 * @param {Object} [options.context] - Additional context
 * @returns {Promise<Object>} Validation result
 */
export async function validateWithGoals(screenshotPath, options = {}) {
  const {
    goal,
    gameState = null,
    renderedCode = null,
    persona = null,
    context = {}
  } = options;

  if (!screenshotPath) {
    throw new ValidationError('validateWithGoals: screenshotPath is required', { function: 'validateWithGoals', parameter: 'screenshotPath' });
  }

  if (!goal) {
    throw new ValidationError('validateWithGoals: goal is required', { function: 'validateWithGoals', parameter: 'goal' });
  }

  log('[Convenience] Validating with goal:', { screenshotPath, goal: typeof goal === 'string' ? goal : goal.description || 'object' });

  // Generate prompt from goal (for display/debugging; goal also used by prompt composition)
  const prompt = generateGamePrompt(goal, {
    gameState,
    renderedCode,
    persona,
    ...context
  });

  // Include temporal notes if available in context
  let temporalNotes = null;
  if (context.aggregated) {
    temporalNotes = context.aggregated;
  } else if (context.temporalNotes) {
    temporalNotes = context.temporalNotes;
  } else if (context.notes && context.notes.length > 0) {
    // Auto-aggregate if notes provided but not aggregated
    try {
      temporalNotes = aggregateTemporalNotes(context.notes, {
        windowSize: TEMPORAL_CONSTANTS.DEFAULT_WINDOW_SIZE_MS,
        decayFactor: TEMPORAL_CONSTANTS.DEFAULT_DECAY_FACTOR
      });
    } catch (error) {
      warn('[Convenience] Auto-aggregation failed, continuing without temporal notes:', error.message);
      temporalNotes = null;
    }
  }

  // Validate with goal in context (prompt composition system will use goal)
  // Include temporal notes for richer context
  // Merge context options (allow override of testType, enableUncertaintyReduction, etc.)
  const validationContext = {
    testType: 'goal-validation',
    gameState,
    renderedCode,
    goal: goal, // Pass goal in context - prompt composition system will use it
    temporalNotes: temporalNotes, // Include aggregated temporal notes
    ...context // Allow context to override defaults (e.g., testType, enableUncertaintyReduction)
  };
  
  const result = await validateScreenshot(screenshotPath, prompt, validationContext);

  // Normalize result structure (ensures consistent return type)
  const normalizedResult = normalizeValidationResult(result, 'validateWithGoals');

  return {
    goal: typeof goal === 'string' ? goal : goal.description || 'unknown',
    prompt,
    result: normalizedResult
  };
}

