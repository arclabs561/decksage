/**
 * Game Playing Module
 * 
 * Optional module for actually playing games (not just testing them).
 * Uses validation to understand game state, then makes decisions and executes actions.
 * 
 * Originally motivated by interactive web applications that require
 * real-time validation, variable goals, and temporal understanding.
 * 
 * Design: Game playing = validation + decision-making + action execution
 * - Validation: Understand game state from screenshots (we have this)
 * - Decision-making: Choose what action to take (we add this)
 * - Action execution: Execute actions via Playwright (we add this)
 * 
 * Provides two interfaces:
 * 1. `playGame()` - Internal loop (simple API for most users)
 * 2. `GameGym` - External iterator (advanced API for power users, RL integration, parallel games)
 */

import { validateScreenshot } from './index.mjs';
import { writeFileSync, mkdirSync, existsSync } from 'fs';
import { join } from 'path';
import { log, warn } from './logger.mjs';

/**
 * Decides what action to take based on game state
 * 
 * Uses VLLM to understand current state and decide next action.
 * 
 * @param {Object} gameState - Current game state from screenshot
 * @param {string} goal - Goal for gameplay (e.g., "maximize score", "survive")
 * @param {Array} history - Previous actions and results
 * @returns {Promise<Object>} Action to take { type: 'keyboard', key: 'ArrowRight', ... }
 */
export async function decideGameAction(gameState, goal, history = []) {
  const recentHistory = history.slice(-5); // Last 5 steps for context
  
  // Use VLLM to understand current state
  const stateEvaluation = await validateScreenshot(
    gameState.screenshot,
    `Evaluate current game state. Goal: ${goal}. Recent history: ${recentHistory.length} steps.`,
    {
      testType: 'gameplay-state',
      temporalNotes: recentHistory.map(h => ({
        step: h.step,
        action: h.action,
        result: h.result?.score
      }))
    }
  );
  
  // Use VLLM to decide action
  const actionPrompt = `Based on the game state, decide what action to take.
    Goal: ${goal}
    Current state: ${stateEvaluation.reasoning?.substring(0, 200) || 'Unknown'}
    Previous actions: ${recentHistory.slice(-3).map(h => h.action?.key || h.action?.type || 'unknown').join(', ')}
    
    Return action as JSON: { "type": "keyboard", "key": "ArrowRight" }
    Available actions:
    - keyboard: ArrowLeft, ArrowRight, ArrowUp, ArrowDown, Space, Enter
    - click: { "type": "click", "selector": "#button" }
    - wait: { "type": "wait", "duration": 100 }
    
    Choose the action that best achieves the goal.`;
  
  const actionResult = await validateScreenshot(
    gameState.screenshot,
    actionPrompt,
    { 
      extractStructured: true, 
      testType: 'gameplay-decision',
      goal: goal
    }
  );
  
  // Parse action from reasoning (VLLM returns reasoning, we extract JSON)
  const actionMatch = actionResult.reasoning?.match(/\{[\s\S]*"type"[\s\S]*\}/);
  if (actionMatch) {
    try {
      const parsed = JSON.parse(actionMatch[0]);
      if (parsed.type && (parsed.key || parsed.selector || parsed.duration !== undefined)) {
        return parsed;
      }
    } catch (e) {
      // Fall through to heuristic
    }
  }
  
  // Fallback: simple heuristic based on score
  // If score is low or decreasing, try different action
  const lastScore = recentHistory.length > 0 ? recentHistory[recentHistory.length - 1].result?.score : null;
  const currentScore = stateEvaluation.score;
  
  if (lastScore !== null && currentScore < lastScore) {
    // Score decreased, try different direction
    return { type: 'keyboard', key: 'ArrowLeft' };
  }
  
  // Default: move right
  return { type: 'keyboard', key: 'ArrowRight' };
}

/**
 * Executes a game action via Playwright
 * 
 * @param {import('playwright').Page} page - Playwright page object
 * @param {Object} action - Action to execute
 */
export async function executeGameAction(page, action) {
  switch (action.type) {
    case 'keyboard':
      await page.keyboard.press(action.key);
      break;
    case 'click':
      if (action.selector) {
        await page.click(action.selector);
      } else {
        warn('[GamePlayer] Click action missing selector');
      }
      break;
    case 'wait':
      await page.waitForTimeout(action.duration || 100);
      break;
    default:
      warn(`[GamePlayer] Unknown action type: ${action.type}, defaulting to wait`);
      await page.waitForTimeout(100);
  }
}

/**
 * Plays a game by taking screenshots, making decisions, and executing actions
 * 
 * Uses validation to understand game state, then makes decisions and executes actions.
 * This is slower than human gameplay (1-5 FPS for decision-making, not 60 FPS)
 * because VLLM calls take 1-3 seconds.
 * 
 * Originally motivated by interactive web applications, but works for any web game.
 * 
 * @param {import('playwright').Page} page - Playwright page object
 * @param {Object} options - Game playing options
 * @param {string} options.goal - Goal for gameplay (e.g., "maximize score")
 * @param {number} options.maxSteps - Maximum number of steps
 * @param {number} options.fps - Frames per second for decision-making (default: 2, not 60)
 * @param {string} [options.gameActivationKey] - Keyboard key to activate game
 * @param {string} [options.gameSelector] - Selector to wait for game activation
 * @param {string} [options.tempDir] - Directory for temporary screenshots
 * @returns {Promise<Object>} Gameplay result with history, final state, etc.
 */
export async function playGame(page, options = {}) {
  const {
    goal = 'Play the game well',
    maxSteps = 100,
    fps = 2, // 2 FPS for decision-making (not 60 FPS - AI needs time to think)
    gameSelector = null,
    gameActivationKey = null,
    tempDir = null
  } = options;
  
  log('[GamePlayer] Starting game play:', { goal, maxSteps, fps, gameActivationKey });
  
  // Activate game if needed
  if (gameActivationKey) {
    log(`[GamePlayer] Activating game with key: ${gameActivationKey}`);
    await page.keyboard.press(gameActivationKey);
    await page.waitForTimeout(500);
    
    if (gameSelector) {
      try {
        await page.waitForSelector(gameSelector, { timeout: 5000 });
      } catch (error) {
        warn(`[GamePlayer] Game selector ${gameSelector} not found after activation`);
      }
    }
  }
  
  // Create temp directory for screenshots
  const screenshotDir = tempDir || join(process.cwd(), 'temp-gameplay');
  if (!existsSync(screenshotDir)) {
    mkdirSync(screenshotDir, { recursive: true });
  }
  
  const history = [];
  let currentState = null;
  
  for (let step = 0; step < maxSteps; step++) {
    try {
      // 1. Capture current state (screenshot)
      const screenshot = await page.screenshot();
      const screenshotPath = join(screenshotDir, `gameplay-step-${step}.png`);
      writeFileSync(screenshotPath, screenshot);
      
      // 2. Understand current state (validation)
      currentState = {
        screenshot: screenshotPath,
        step,
        timestamp: Date.now()
      };
      
      const stateEvaluation = await validateScreenshot(
        screenshotPath,
        `Evaluate current game state. Goal: ${goal}`,
        {
          testType: 'gameplay',
          temporalNotes: history.map(h => ({
            step: h.step,
            action: h.action,
            result: h.result?.score
          }))
        }
      );
      
      currentState.evaluation = stateEvaluation;
      
      // 3. Decide what action to take (decision-making)
      const action = await decideGameAction(
        currentState,
        goal,
        history
      );
      
      log(`[GamePlayer] Step ${step}: score=${stateEvaluation.score}, action=${action.type}:${action.key || action.selector || ''}`);
      
      // 4. Execute action (Playwright)
      await executeGameAction(page, action);
      
      // 5. Wait for next frame
      await page.waitForTimeout(1000 / fps);
      
      // 6. Record history
      history.push({
        step,
        state: currentState,
        action,
        result: stateEvaluation
      });
      
      // 7. Check if game is over (optional)
      if (stateEvaluation.score === 0 || 
          stateEvaluation.issues?.some(i => i.toLowerCase().includes('game over')) ||
          stateEvaluation.issues?.some(i => i.toLowerCase().includes('game ended'))) {
        log(`[GamePlayer] Game over detected at step ${step}`);
        break;
      }
    } catch (error) {
      warn(`[GamePlayer] Error at step ${step}:`, error.message);
      // Continue with next step (graceful degradation)
      history.push({
        step,
        error: error.message,
        state: currentState
      });
    }
  }
  
  return {
    history,
    finalState: currentState,
    totalSteps: history.length,
    goal,
    success: currentState?.evaluation?.score !== null
  };
}

/**
 * Game Gym - External Iterator Pattern (RL Gym-style)
 * 
 * Provides external iterator interface for game playing, enabling:
 * - Explicit control over iteration
 * - Batching across multiple games
 * - RL algorithm integration
 * - Parallel game instances
 * - Checkpointing and state management
 * 
 * Originally motivated by interactive web applications, but designed to work
 * with any RL algorithm or advanced use case.
 * 
 * @example
 * ```javascript
 * const gym = new GameGym(page, { goal: 'Maximize score' });
 * let obs = await gym.reset();
 * 
 * while (!gym.done) {
 *   const action = await decideAction(obs);
 *   const result = await gym.step(action);
 *   obs = result.observation;
 * }
 * ```
 */
export class GameGym {
  constructor(page, options = {}) {
    this.page = page;
    this.options = {
      goal: 'Play the game well',
      maxSteps: 100,
      fps: 2,
      gameSelector: null,
      gameActivationKey: null,
      tempDir: null,
      ...options
    };
    
    this.currentState = null;
    this.done = false;
    this.stepCount = 0;
    this.history = [];
    
    // Create temp directory
    const screenshotDir = this.options.tempDir || join(process.cwd(), 'temp-gameplay');
    if (!existsSync(screenshotDir)) {
      mkdirSync(screenshotDir, { recursive: true });
    }
    this.screenshotDir = screenshotDir;
    
    log('[GameGym] Created gym:', { goal: this.options.goal, maxSteps: this.options.maxSteps });
  }
  
  /**
   * Reset game to initial state
   * 
   * @returns {Promise<Object>} Initial observation
   */
  async reset() {
    // Navigate to game if URL provided
    if (this.options.url) {
      await this.page.goto(this.options.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await this.page.waitForLoadState('networkidle');
    }
    
    // Activate game if needed
    if (this.options.gameActivationKey) {
      log(`[GameGym] Activating game with key: ${this.options.gameActivationKey}`);
      await this.page.keyboard.press(this.options.gameActivationKey);
      await this.page.waitForTimeout(500);
      
      if (this.options.gameSelector) {
        try {
          await this.page.waitForSelector(this.options.gameSelector, { timeout: 5000 });
        } catch (error) {
          warn(`[GameGym] Game selector ${this.options.gameSelector} not found`);
        }
      }
    }
    
    // Capture initial state
    const screenshot = await this.page.screenshot();
    const screenshotPath = join(this.screenshotDir, `gameplay-reset-${Date.now()}.png`);
    writeFileSync(screenshotPath, screenshot);
    
    const evaluation = await validateScreenshot(
      screenshotPath,
      `Evaluate initial game state. Goal: ${this.options.goal}`,
      {
        testType: 'gameplay-reset',
        goal: this.options.goal
      }
    );
    
    this.currentState = {
      observation: {
        screenshot: screenshotPath,
        evaluation: evaluation,
        step: 0,
        timestamp: Date.now()
      },
      reward: 0,
      done: false,
      info: {
        score: evaluation.score,
        issues: evaluation.issues || [],
        goal: this.options.goal
      }
    };
    
    this.done = false;
    this.stepCount = 0;
    this.history = [];
    
    log('[GameGym] Reset complete:', { score: evaluation.score });
    
    return this.currentState.observation;
  }
  
  /**
   * Execute action and return new observation
   * 
   * @param {Object} action - Action to execute
   * @returns {Promise<Object>} { observation, reward, done, info }
   */
  async step(action) {
    if (this.done) {
      warn('[GameGym] Step called after game is done, reset first');
      return this.currentState;
    }
    
    // Execute action
    await executeGameAction(this.page, action);
    
    // Wait for next frame
    await this.page.waitForTimeout(1000 / this.options.fps);
    
    // Capture new state
    const screenshot = await this.page.screenshot();
    const screenshotPath = join(this.screenshotDir, `gameplay-step-${this.stepCount + 1}.png`);
    writeFileSync(screenshotPath, screenshot);
    
    const evaluation = await validateScreenshot(
      screenshotPath,
      `Evaluate game state after action. Goal: ${this.options.goal}`,
      {
        testType: 'gameplay',
        temporalNotes: this.history.map(h => ({
          step: h.step,
          action: h.action,
          result: h.result?.score
        })),
        goal: this.options.goal
      }
    );
    
    // Calculate reward (based on goal)
    const previousScore = this.currentState?.observation?.evaluation?.score || 0;
    const currentScore = evaluation.score || 0;
    const reward = this.calculateReward(evaluation, this.currentState);
    
    // Update state
    this.stepCount++;
    this.currentState = {
      observation: {
        screenshot: screenshotPath,
        evaluation: evaluation,
        step: this.stepCount,
        timestamp: Date.now()
      },
      reward: reward,
      done: this.isDone(evaluation),
      info: {
        score: currentScore,
        scoreDelta: currentScore - previousScore,
        issues: evaluation.issues || [],
        goal: this.options.goal,
        step: this.stepCount
      }
    };
    
    // Record history
    this.history.push({
      step: this.stepCount,
      action: action,
      result: evaluation
    });
    
    this.done = this.currentState.done;
    
    log(`[GameGym] Step ${this.stepCount}: score=${currentScore}, reward=${reward}, done=${this.done}`);
    
    return this.currentState;
  }
  
  /**
   * Calculate reward based on goal
   * 
   * @param {Object} evaluation - Current evaluation
   * @param {Object} previousState - Previous state
   * @returns {number} Reward value
   */
  calculateReward(evaluation, previousState) {
    const currentScore = evaluation.score || 0;
    const previousScore = previousState?.observation?.evaluation?.score || 0;
    
    // Reward based on goal
    if (this.options.goal.includes('maximize') || this.options.goal.includes('score')) {
      // Reward for score increase
      return currentScore - previousScore;
    } else if (this.options.goal.includes('survive') || this.options.goal.includes('avoid')) {
      // Reward for staying alive (penalize score decrease)
      return currentScore > 0 ? 1 : -10;
    } else {
      // Default: reward for maintaining/improving score
      return currentScore - previousScore;
    }
  }
  
  /**
   * Check if game is done
   * 
   * @param {Object} evaluation - Current evaluation
   * @returns {boolean} True if game is done
   */
  isDone(evaluation) {
    // Game over conditions
    if (evaluation.score === 0) {
      return true;
    }
    
    if (evaluation.issues?.some(i => 
      i.toLowerCase().includes('game over') || 
      i.toLowerCase().includes('game ended') ||
      i.toLowerCase().includes('you lost')
    )) {
      return true;
    }
    
    // Max steps reached
    if (this.stepCount >= this.options.maxSteps) {
      return true;
    }
    
    return false;
  }
  
  /**
   * Get current observation without stepping
   * 
   * @returns {Object} Current observation
   */
  getObservation() {
    return this.currentState?.observation || null;
  }
  
  /**
   * Get game state for checkpointing
   * 
   * @returns {Object} Game state
   */
  getState() {
    return {
      observation: this.currentState?.observation,
      stepCount: this.stepCount,
      history: this.history,
      done: this.done
    };
  }
  
  /**
   * Restore game state from checkpoint
   * 
   * @param {Object} state - Game state from checkpoint
   */
  restore(state) {
    this.currentState = { observation: state.observation };
    this.stepCount = state.stepCount;
    this.history = state.history || [];
    this.done = state.done || false;
    
    log(`[GameGym] Restored from checkpoint: step ${this.stepCount}`);
  }
}

