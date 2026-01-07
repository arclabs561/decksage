/**
 * Variable Goal/Prompt System for Games
 * 
 * Allows games to accept variable prompts and goals, not just hardcoded game states.
 * 
 * Research:
 * - "Goal-Conditioned Reinforcement Learning: Problems and Solutions" (arXiv:2201.08299)
 *   - Comprehensive survey of goal-conditioned RL
 * - "Accelerating Goal-Conditioned RL Algorithms and Research" (arXiv:2408.11052)
 *   - Fast RL benchmarks, flexible tasks, multiple goals
 * - "OGBench: Benchmarking Offline Goal-Conditioned RL" (arXiv:2410.20092)
 *   - Benchmark with dynamic goal-based evaluation
 * - "Test-Time Graph Search for Goal-Conditioned Control" (arXiv:2510.07257)
 *   - Adaptive, context-aware goal fulfillment
 * 
 * This implementation provides flexible goal specification for game evaluation, supporting
 * multiple goal formats (string, object, array, function) and context-aware generation.
 */

import { log, warn } from './logger.mjs';

/**
 * Generate game prompt from variable goal/prompt
 * 
 * Supports multiple formats:
 * 1. String prompt - Direct prompt text
 * 2. Goal object - Structured goal with criteria
 * 3. Goal array - Multiple goals to evaluate
 * 4. Function - Dynamic goal generation
 * 
 * @param {string | Object | Array | Function} goalOrPrompt - Goal or prompt specification
 * @param {Object} context - Game context
 * @param {Object} context.gameState - Current game state
 * @param {Object} [context.previousState] - Previous game state
 * @param {Object} [context.renderedCode] - Rendered code (HTML/CSS)
 * @param {Object} [context.persona] - Persona configuration
 * @param {string} [context.stage] - Current stage
 * @returns {string} Generated prompt
 */
export function generateGamePrompt(goalOrPrompt, context = {}) {
  const {
    gameState = {},
    previousState = null,
    renderedCode = null,
    persona = null,
    stage = 'gameplay'
  } = context;

  // Handle different input types
  if (typeof goalOrPrompt === 'string') {
    // Direct prompt string
    return buildPromptFromString(goalOrPrompt, context);
  } else if (typeof goalOrPrompt === 'function') {
    // Function that generates prompt
    return goalOrPrompt(context);
  } else if (Array.isArray(goalOrPrompt)) {
    // Array of goals
    return buildPromptFromGoals(goalOrPrompt, context);
  } else if (goalOrPrompt && typeof goalOrPrompt === 'object') {
    // Goal object
    return buildPromptFromGoal(goalOrPrompt, context);
  } else {
    // Fallback to default gameplay prompt
    warn('[Game Goal] Invalid goal/prompt format, using default');
    return buildDefaultGameplayPrompt(context);
  }
}

/**
 * Build prompt from string (with context interpolation)
 */
function buildPromptFromString(promptString, context) {
  const { gameState = {}, previousState = null, persona = null } = context;
  
  // Interpolate context variables
  let prompt = promptString;
  
  // Replace ${gameState.*} patterns
  prompt = prompt.replace(/\$\{gameState\.(\w+)\}/g, (match, key) => {
    return gameState[key] !== undefined ? String(gameState[key]) : match;
  });
  
  // Replace ${previousState.*} patterns
  if (previousState) {
    prompt = prompt.replace(/\$\{previousState\.(\w+)\}/g, (match, key) => {
      return previousState[key] !== undefined ? String(previousState[key]) : match;
    });
  }
  
  // Add context if not already present
  if (!prompt.includes('CURRENT GAME STATE') && gameState && Object.keys(gameState).length > 0) {
    prompt += `\n\nCURRENT GAME STATE:\n${formatGameState(gameState)}`;
  }
  
  // Add persona context if provided
  if (persona && !prompt.includes('PERSONA')) {
    prompt += `\n\nPERSONA PERSPECTIVE: ${persona.name}\n${persona.perspective || ''}`;
  }
  
  return prompt;
}

/**
 * Build prompt from goal object
 */
function buildPromptFromGoal(goal, context) {
  const {
    description,
    criteria = [],
    focus = [],
    questions = [],
    minScore = null,
    maxScore = null
  } = goal;
  
  const { gameState = {}, previousState = null, persona = null } = context;
  
  const parts = [];
  
  // Goal description
  if (description) {
    parts.push(`GOAL: ${description}`);
  }
  
  // Evaluation criteria
  if (criteria.length > 0) {
    parts.push(`\nEVALUATION CRITERIA:\n${criteria.map((c, i) => `${i + 1}. ${c}`).join('\n')}`);
  }
  
  // Focus areas
  if (focus.length > 0) {
    parts.push(`\nFOCUS AREAS: ${focus.join(', ')}`);
  }
  
  // Specific questions
  if (questions.length > 0) {
    parts.push(`\nQUESTIONS TO ANSWER:\n${questions.map((q, i) => `${i + 1}. ${q}`).join('\n')}`);
  }
  
  // Score expectations
  if (minScore !== null || maxScore !== null) {
    const range = minScore !== null && maxScore !== null 
      ? `${minScore}-${maxScore}`
      : minScore !== null 
        ? `≥${minScore}`
        : `≤${maxScore}`;
    parts.push(`\nEXPECTED SCORE RANGE: ${range}/10`);
  }
  
  // Game state context
  if (gameState && Object.keys(gameState).length > 0) {
    parts.push(`\n\nCURRENT GAME STATE:\n${formatGameState(gameState)}`);
  }
  
  // Previous state comparison
  if (previousState) {
    parts.push(`\n\nPREVIOUS STATE:\n${formatGameState(previousState)}`);
    parts.push(`\nCHANGES: ${formatStateChanges(previousState, gameState)}`);
  }
  
  // Persona context
  if (persona) {
    parts.push(`\n\nPERSONA PERSPECTIVE: ${persona.name}`);
    if (persona.perspective) parts.push(persona.perspective);
    if (persona.goals) parts.push(`GOALS: ${persona.goals.join(', ')}`);
  }
  
  return parts.join('\n');
}

/**
 * Build prompt from array of goals
 */
function buildPromptFromGoals(goals, context) {
  if (goals.length === 0) {
    return buildDefaultGameplayPrompt(context);
  }
  
  if (goals.length === 1) {
    return generateGamePrompt(goals[0], context);
  }
  
  // Multiple goals - evaluate all
  const parts = ['EVALUATE THE FOLLOWING GOALS:'];
  
  goals.forEach((goal, i) => {
    if (typeof goal === 'string') {
      parts.push(`\n${i + 1}. ${goal}`);
    } else if (goal && typeof goal === 'object' && goal.description) {
      parts.push(`\n${i + 1}. ${goal.description}`);
      if (goal.criteria && goal.criteria.length > 0) {
        parts.push(`   Criteria: ${goal.criteria.join(', ')}`);
      }
    }
  });
  
  // Add context
  const { gameState = {}, previousState = null, persona = null } = context;
  
  if (gameState && Object.keys(gameState).length > 0) {
    parts.push(`\n\nCURRENT GAME STATE:\n${formatGameState(gameState)}`);
  }
  
  if (previousState) {
    parts.push(`\n\nPREVIOUS STATE:\n${formatGameState(previousState)}`);
  }
  
  if (persona) {
    parts.push(`\n\nPERSONA: ${persona.name}`);
  }
  
  parts.push(`\n\nEvaluate how well the game state meets each goal. Provide a score (0-10) and specific feedback for each goal.`);
  
  return parts.join('\n');
}

/**
 * Build default gameplay prompt (fallback)
 */
function buildDefaultGameplayPrompt(context) {
  const { gameState = {}, previousState = null, persona = null } = context;
  
  const parts = [
    'Evaluate the gameplay experience.',
    'Consider:',
    '1. Is the game fun and engaging?',
    '2. Are controls responsive?',
    '3. Is there clear feedback for actions?',
    '4. Is the difficulty appropriate?',
    '5. Would you want to play again?'
  ];
  
  if (gameState && Object.keys(gameState).length > 0) {
    parts.push(`\n\nCURRENT GAME STATE:\n${formatGameState(gameState)}`);
  }
  
  if (previousState) {
    parts.push(`\n\nPREVIOUS STATE:\n${formatGameState(previousState)}`);
    parts.push(`\nCHANGES: ${formatStateChanges(previousState, gameState)}`);
  }
  
  if (persona) {
    parts.push(`\n\nPERSONA: ${persona.name}`);
    if (persona.perspective) parts.push(persona.perspective);
  }
  
  return parts.join('\n');
}

/**
 * Format game state for prompt
 */
function formatGameState(gameState) {
  if (!gameState || Object.keys(gameState).length === 0) {
    return 'No game state available';
  }
  
  const lines = [];
  
  // Common game state fields
  if (gameState.gameActive !== undefined) {
    lines.push(`- Active: ${gameState.gameActive}`);
  }
  if (gameState.score !== undefined) {
    lines.push(`- Score: ${gameState.score}`);
  }
  if (gameState.level !== undefined) {
    lines.push(`- Level: ${gameState.level}`);
  }
  if (gameState.lives !== undefined) {
    lines.push(`- Lives: ${gameState.lives}`);
  }
  if (gameState.bricks !== undefined) {
    lines.push(`- Bricks: ${Array.isArray(gameState.bricks) ? gameState.bricks.length : gameState.bricks} remaining`);
  }
  if (gameState.ball !== undefined) {
    lines.push(`- Ball: ${gameState.ball ? 'visible' : 'not visible'}`);
  }
  if (gameState.paddle !== undefined) {
    lines.push(`- Paddle: ${gameState.paddle ? 'visible' : 'not visible'}`);
  }
  
  // Any other fields
  const otherFields = Object.keys(gameState).filter(key => 
    !['gameActive', 'score', 'level', 'lives', 'bricks', 'ball', 'paddle'].includes(key)
  );
  
  if (otherFields.length > 0) {
    otherFields.forEach(key => {
      const value = gameState[key];
      if (value !== undefined && value !== null) {
        lines.push(`- ${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`);
      }
    });
  }
  
  return lines.join('\n');
}

/**
 * Format state changes between previous and current
 */
function formatStateChanges(previousState, currentState) {
  if (!previousState || !currentState) return 'No previous state';
  
  const changes = [];
  
  // Score change
  if (previousState.score !== undefined && currentState.score !== undefined) {
    const scoreChange = currentState.score - previousState.score;
    if (scoreChange !== 0) {
      changes.push(`Score: ${previousState.score} → ${currentState.score} (${scoreChange > 0 ? '+' : ''}${scoreChange})`);
    }
  }
  
  // Level change
  if (previousState.level !== undefined && currentState.level !== undefined) {
    if (previousState.level !== currentState.level) {
      changes.push(`Level: ${previousState.level} → ${currentState.level}`);
    }
  }
  
  // Lives change
  if (previousState.lives !== undefined && currentState.lives !== undefined) {
    if (previousState.lives !== currentState.lives) {
      changes.push(`Lives: ${previousState.lives} → ${currentState.lives}`);
    }
  }
  
  // Bricks change
  if (previousState.bricks !== undefined && currentState.bricks !== undefined) {
    const prevCount = Array.isArray(previousState.bricks) ? previousState.bricks.length : previousState.bricks;
    const currCount = Array.isArray(currentState.bricks) ? currentState.bricks.length : currentState.bricks;
    if (prevCount !== currCount) {
      const destroyed = prevCount - currCount;
      changes.push(`Bricks: ${prevCount} → ${currCount} (${destroyed > 0 ? `${destroyed} destroyed` : 'added'})`);
    }
  }
  
  // Game active change
  if (previousState.gameActive !== undefined && currentState.gameActive !== undefined) {
    if (previousState.gameActive !== currentState.gameActive) {
      changes.push(`Game: ${previousState.gameActive ? 'active' : 'paused'} → ${currentState.gameActive ? 'active' : 'paused'}`);
    }
  }
  
  return changes.length > 0 ? changes.join(', ') : 'No significant changes';
}

/**
 * Create goal from common game evaluation patterns
 * 
 * @param {string} goalType - Type of goal ('fun', 'accessibility', 'performance', 'balance', 'visuals', 'controls')
 * @param {Object} [options={}] - Goal options
 * @returns {Object} Goal object
 */
export function createGameGoal(goalType, options = {}) {
  const goalTemplates = {
    fun: {
      description: 'Evaluate if the game is fun and engaging',
      criteria: [
        'Is the game enjoyable to play?',
        'Does it provide a sense of achievement?',
        'Is there variety in gameplay?',
        'Would players want to replay?'
      ],
      focus: ['engagement', 'enjoyment', 'replayability'],
      questions: [
        'What makes this game fun?',
        'What would make it more engaging?',
        'Is there enough variety?'
      ]
    },
    accessibility: {
      description: 'Evaluate game accessibility',
      criteria: [
        'Can the game be played with keyboard only?',
        'Are visual indicators clear?',
        'Is there audio feedback?',
        'Are controls customizable?'
      ],
      focus: ['keyboard-navigation', 'visual-indicators', 'audio-feedback', 'customization'],
      questions: [
        'Can someone with motor disabilities play this?',
        'Can someone with visual impairments play this?',
        'Are controls accessible?'
      ]
    },
    performance: {
      description: 'Evaluate game performance',
      criteria: [
        'Is the frame rate smooth (60 FPS)?',
        'Are there lag spikes?',
        'Is the game responsive?',
        'Are there performance issues?'
      ],
      focus: ['frame-rate', 'responsiveness', 'lag', 'optimization'],
      questions: [
        'Is the game running smoothly?',
        'Are there any performance bottlenecks?',
        'Is input lag acceptable?'
      ]
    },
    balance: {
      description: 'Evaluate game balance',
      criteria: [
        'Is difficulty appropriate?',
        'Is progression clear?',
        'Is the game too easy or too hard?',
        'Is there a good learning curve?'
      ],
      focus: ['difficulty', 'progression', 'learning-curve', 'challenge'],
      questions: [
        'Is the game balanced?',
        'Is difficulty appropriate for target audience?',
        'Is progression satisfying?'
      ]
    },
    visuals: {
      description: 'Evaluate visual design',
      criteria: [
        'Are colors vibrant and clear?',
        'Is the layout clear?',
        'Are animations smooth?',
        'Is visual feedback clear?'
      ],
      focus: ['colors', 'layout', 'animations', 'visual-feedback'],
      questions: [
        'Is the visual design appealing?',
        'Are visual elements clear?',
        'Do animations enhance the experience?'
      ]
    },
    controls: {
      description: 'Evaluate game controls',
      criteria: [
        'Are controls responsive?',
        'Are controls intuitive?',
        'Is there clear feedback for actions?',
        'Are controls customizable?'
      ],
      focus: ['responsiveness', 'intuitiveness', 'feedback', 'customization'],
      questions: [
        'Are controls easy to learn?',
        'Is input lag acceptable?',
        'Do controls feel good?'
      ]
    }
  };
  
  const template = goalTemplates[goalType];
  if (!template) {
    warn(`[Game Goal] Unknown goal type: ${goalType}, using 'fun' as default`);
    return createGameGoal('fun', options);
  }
  
  // Merge with custom options
  return {
    ...template,
    ...options,
    // Allow overriding specific fields
    criteria: options.criteria || template.criteria,
    focus: options.focus || template.focus,
    questions: options.questions || template.questions
  };
}

/**
 * Create multiple goals for comprehensive evaluation
 * 
 * @param {string[]} goalTypes - Array of goal types
 * @param {Object} [options={}] - Options for all goals
 * @returns {Object[]} Array of goal objects
 */
export function createGameGoals(goalTypes, options = {}) {
  return goalTypes.map(type => createGameGoal(type, options));
}

