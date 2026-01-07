/**
 * Dynamic Prompt Generation for UX and Gameplay Testing
 *
 * Generates context-aware prompts based on:
 * - Page state (initial load, form filled, game active, etc.)
 * - User interactions (click, type, scroll, etc.)
 * - Testing goals (UX improvement, gameplay validation, accessibility, etc.)
 * - Persona perspectives
 *
 * Prompts adapt to the current context for more relevant and actionable feedback.
 */

/**
 * Generate dynamic prompt based on context
 *
 * @param {Object} context - Testing context
 * @param {string} context.stage - Current stage ('initial', 'form', 'payment', 'gameplay', etc.)
 * @param {Object} context.interaction - Last interaction (if any)
 * @param {Object} context.pageState - Current page state
 * @param {Object} context.gameState - Game state (if applicable)
 * @param {string} context.testingGoal - Testing goal ('ux-improvement', 'gameplay', 'accessibility', etc.)
 * @param {Object} context.persona - Persona configuration (optional)
 * @param {Array} context.experienceNotes - Previous experience notes (optional)
 * @returns {string} Generated prompt
 */
export function generateDynamicPrompt(context) {
  const {
    stage = 'initial',
    interaction = null,
    pageState = {},
    gameState = null,
    testingGoal = 'ux-improvement',
    persona = null,
    experienceNotes = []
  } = context;

  // Base prompt components
  const basePrompt = buildBasePrompt(stage, testingGoal);
  const contextPrompt = buildContextPrompt(stage, interaction, pageState, gameState);
  const personaPrompt = persona ? buildPersonaPrompt(persona) : '';
  const experiencePrompt = experienceNotes.length > 0 ? buildExperiencePrompt(experienceNotes) : '';
  const specificQuestions = buildSpecificQuestions(stage, testingGoal, gameState);

  return `${basePrompt}

${contextPrompt}

${personaPrompt}

${experiencePrompt}

${specificQuestions}`.trim();
}

/**
 * Build base prompt based on stage and testing goal
 */
function buildBasePrompt(stage, testingGoal) {
  const stagePrompts = {
    initial: {
      'ux-improvement': `Evaluate the initial page load from a UX perspective. Focus on first impressions, clarity of purpose, and immediate usability.`,
      'gameplay': `Evaluate the initial page state. Is the game accessible? Is the purpose clear? Can users understand how to start?`,
      'accessibility': `Evaluate accessibility of the initial page. Check for screen reader compatibility, keyboard navigation, color contrast, and semantic HTML.`,
      'performance': `Evaluate the initial page load performance. Check for layout shifts, loading states, and perceived performance.`
    },
    form: {
      'ux-improvement': `Evaluate the form interaction experience. Is the form intuitive? Are labels clear? Is there helpful feedback?`,
      'gameplay': `Evaluate form completion in context of accessing gameplay. Is the flow clear? Does it feel like a barrier or a natural step?`,
      'accessibility': `Evaluate form accessibility. Check label associations, error messages, keyboard navigation, and ARIA attributes.`,
      'performance': `Evaluate form interaction performance. Check for input lag, validation feedback speed, and form submission responsiveness.`
    },
    payment: {
      'ux-improvement': `Evaluate the payment screen UX. Is the payment code clear? Are payment links obvious? Is the flow trustworthy?`,
      'gameplay': `Evaluate payment screen in context of gameplay access. Is the connection between payment and game clear? Is the wait reasonable?`,
      'accessibility': `Evaluate payment screen accessibility. Can screen readers access payment codes? Are links keyboard accessible?`,
      'performance': `Evaluate payment screen performance. Is the code visible immediately? Are links responsive?`
    },
    gameplay: {
      'ux-improvement': `Evaluate gameplay UX. Is the game fun? Are controls intuitive? Is feedback clear?`,
      'gameplay': `Evaluate gameplay mechanics. Is the game balanced? Are controls responsive? Is the experience engaging?`,
      'accessibility': `Evaluate gameplay accessibility. Can the game be played with keyboard? Are visual indicators clear? Is there audio feedback?`,
      'performance': `Evaluate gameplay performance. Is the frame rate smooth? Are there lag spikes? Is the game responsive?`
    }
  };

  return stagePrompts[stage]?.[testingGoal] ||
         `Evaluate the ${stage} stage from a ${testingGoal} perspective.`;
}

/**
 * Build context-specific prompt
 */
function buildContextPrompt(stage, interaction, pageState, gameState) {
  let context = `CURRENT CONTEXT:
- Stage: ${stage}`;

  if (interaction) {
    context += `\n- Last interaction: ${interaction.type} on ${interaction.target || 'unknown'}`;
    if (interaction.timestamp) {
      context += ` at ${new Date(interaction.timestamp).toISOString()}`;
    }
  }

  if (pageState) {
    if (pageState.title) context += `\n- Page title: ${pageState.title}`;
    if (pageState.activeElement) context += `\n- Active element: ${pageState.activeElement}`;
    if (pageState.viewport) context += `\n- Viewport: ${pageState.viewport.width}x${pageState.viewport.height}`;
  }

  if (gameState && gameState.gameActive) {
    context += `\n- Game state:
  - Active: ${gameState.gameActive}
  - Bricks remaining: ${gameState.bricks?.length || 0}
  - Ball position: ${gameState.ball ? 'visible' : 'not visible'}
  - Paddle position: ${gameState.paddle ? 'visible' : 'not visible'}`;
    if (gameState.score !== undefined) context += `\n  - Score: ${gameState.score}`;
  }

  return context;
}

/**
 * Build persona-specific prompt
 */
function buildPersonaPrompt(persona) {
  if (!persona) return '';

  return `PERSONA PERSPECTIVE: ${persona.name}
${persona.perspective || ''}
${persona.focus ? `Focus areas: ${Array.isArray(persona.focus) ? persona.focus.join(', ') : persona.focus}` : ''}

Evaluate from this persona's perspective.`;
}

/**
 * Build experience history prompt
 */
function buildExperiencePrompt(experienceNotes) {
  if (experienceNotes.length === 0) return '';

  const recentNotes = experienceNotes.slice(-5); // Last 5 notes
  const timeline = recentNotes.map((note, i) => {
    const elapsed = note.elapsed ? `${(note.elapsed / 1000).toFixed(1)}s` : `${i + 1}`;
    return `  ${elapsed}: ${note.observation || note.step || 'step'}`;
  }).join('\n');

  return `EXPERIENCE TIMELINE (recent):
${timeline}

Consider how the current state relates to the user's journey so far.`;
}

/**
 * Build specific questions based on stage and goal
 */
function buildSpecificQuestions(stage, testingGoal, gameState) {
  const questions = [];

  // Stage-specific questions
  if (stage === 'initial') {
    questions.push(
      'What is the first thing a user notices?',
      'Is the purpose of the page immediately clear?',
      'What action should the user take first?'
    );
  } else if (stage === 'form') {
    questions.push(
      'Are all form fields clearly labeled?',
      'Is there helpful placeholder text or instructions?',
      'Does the form provide feedback during interaction?',
      'Is the submit button clearly visible and enabled?'
    );
  } else if (stage === 'payment') {
    questions.push(
      'Is the payment code easy to read and copy?',
      'Are payment links (Venmo, CashApp) clearly visible?',
      'Is the connection between payment and game access clear?',
      'Does the screen feel trustworthy?'
    );
  } else if (stage === 'gameplay' && gameState) {
    questions.push(
      'Is the game visually engaging?',
      'Are controls intuitive and responsive?',
      'Is there clear visual feedback for actions?',
      'Is the game balanced and fun?',
      gameState.bricks?.length === 0 ? 'Did the user win? Is there celebration feedback?' : 'How many bricks remain? Is progress clear?'
    );
  }

  // Testing goal-specific questions
  if (testingGoal === 'ux-improvement') {
    questions.push(
      'What would improve the user experience?',
      'Are there any friction points?',
      'Is the flow intuitive?',
      'What would make this more delightful?'
    );
  } else if (testingGoal === 'gameplay') {
    questions.push(
      'Is the game fun and engaging?',
      'Are controls responsive?',
      'Is there clear feedback for actions?',
      'Is the difficulty appropriate?',
      'Would you want to play again?'
    );
  } else if (testingGoal === 'accessibility') {
    questions.push(
      'Can this be used with a screen reader?',
      'Is keyboard navigation possible?',
      'Is color contrast sufficient?',
      'Are interactive elements clearly indicated?',
      'Are error messages accessible?'
    );
  }

  if (questions.length === 0) return '';

  return `SPECIFIC QUESTIONS TO ANSWER:
${questions.map((q, i) => `${i + 1}. ${q}`).join('\n')}`;
}

/**
 * Generate prompt variations for A/B testing different perspectives
 *
 * @param {Object} context - Testing context
 * @param {Array} variations - Array of variation configs
 * @returns {Array} Array of prompt variations
 */
/**
 * Generate multiple prompt variations for testing
 *
 * @param {Record<string, unknown>} context - Testing context
 * @param {Array<{ testingGoal?: string; focus?: string }>} [variations=[]] - Array of variation configs
 * @returns {string[]} Array of prompt variations
 */
export function generatePromptVariations(context, variations = []) {
  const defaultVariations = [
    { testingGoal: 'ux-improvement', focus: 'user experience and delight' },
    { testingGoal: 'accessibility', focus: 'inclusive design and accessibility' },
    { testingGoal: 'gameplay', focus: 'game mechanics and engagement' },
    { testingGoal: 'performance', focus: 'perceived performance and responsiveness' }
  ];

  const variationsToUse = variations.length > 0 ? variations : defaultVariations;

  return variationsToUse.map(variation => ({
    ...variation,
    prompt: generateDynamicPrompt({
      ...context,
      testingGoal: variation.testingGoal || context.testingGoal,
      persona: variation.persona || context.persona
    })
  }));
}

/**
 * Generate interaction-specific prompt
 *
 * @param {Record<string, unknown>} interaction - Interaction details
 * @param {Record<string, unknown>} beforeState - State before interaction
 * @param {Record<string, unknown>} afterState - State after interaction
 * @param {string} [testingGoal='ux-improvement'] - Testing goal
 * @returns {string} Interaction-specific prompt
 */
export function generateInteractionPrompt(interaction, beforeState, afterState, testingGoal = 'ux-improvement') {
  const interactionTypes = {
    click: 'button or link click',
    type: 'text input',
    scroll: 'page scroll',
    submit: 'form submission',
    keypress: 'keyboard input'
  };

  const interactionType = interactionTypes[interaction.type] || interaction.type;

  return `Evaluate the ${interactionType} interaction.

BEFORE INTERACTION:
${JSON.stringify(beforeState, null, 2)}

AFTER INTERACTION:
${JSON.stringify(afterState, null, 2)}

QUESTIONS:
1. Was the interaction successful?
2. Was there clear visual feedback?
3. Did the state change as expected?
4. Was there any delay or lag?
5. ${testingGoal === 'ux-improvement' ? 'How could this interaction be improved?' :
   testingGoal === 'accessibility' ? 'Was this interaction accessible?' :
   'Was this interaction responsive?'}`;
}

/**
 * Generate gameplay-specific prompt
 *
 * Now supports variable goals/prompts via game-goal-prompts.mjs
 *
 * @param {Record<string, unknown>} gameState - Current game state
 * @param {Record<string, unknown> | null} [previousState=null] - Previous game state (optional)
 * @param {string | Object | Array | Function} [goalOrPrompt='mechanics'] - Goal, prompt, or focus area
 * @param {Object} [context={}] - Additional context (persona, renderedCode, etc.)
 * @returns {string} Gameplay-specific prompt
 */
export async function generateGameplayPrompt(gameState, previousState = null, goalOrPrompt = 'mechanics', context = {}) {
  // Import variable goal system (lazy import to avoid circular dependencies)
  let generateGamePrompt;
  try {
    const gameGoalModule = await import('./game-goal-prompts.mjs');
    generateGamePrompt = gameGoalModule.generateGamePrompt;
  } catch (err) {
    // Fallback if module not available
    generateGamePrompt = null;
  }

  // If variable goal system available and goalOrPrompt is not a simple string focus
  if (generateGamePrompt && (typeof goalOrPrompt !== 'string' || !['mechanics', 'visuals', 'feedback', 'balance'].includes(goalOrPrompt))) {
    return generateGamePrompt(goalOrPrompt, {
      gameState,
      previousState,
      ...context
    });
  }

  // Legacy support for simple focus strings
  const focusPrompts = {
    mechanics: `Evaluate gameplay mechanics. Are controls responsive? Is collision detection accurate? Is the game balanced?`,
    visuals: `Evaluate visual design. Are colors vibrant? Is the layout clear? Are animations smooth?`,
    feedback: `Evaluate feedback systems. Are collisions visible? Is score clear? Are there celebration effects?`,
    balance: `Evaluate game balance. Is difficulty appropriate? Is progression clear? Is the game engaging?`
  };

  const focus = typeof goalOrPrompt === 'string' ? goalOrPrompt : 'mechanics';
  let prompt = `${focusPrompts[focus] || focusPrompts.mechanics}

CURRENT GAME STATE:
- Active: ${gameState.gameActive}
- Bricks: ${gameState.bricks?.length || 0} remaining
- Ball: ${gameState.ball ? 'visible' : 'not visible'}
- Paddle: ${gameState.paddle ? 'visible' : 'not visible'}`;

  if (gameState.score !== undefined) {
    prompt += `\n- Score: ${gameState.score}`;
  }

  if (previousState) {
    prompt += `\n\nPREVIOUS STATE:
- Bricks: ${previousState.bricks?.length || 0}
- Score: ${previousState.score || 0}`;

    const bricksDestroyed = (previousState.bricks?.length || 0) - (gameState.bricks?.length || 0);
    if (bricksDestroyed > 0) {
      prompt += `\n\nProgress: ${bricksDestroyed} brick(s) destroyed since last check.`;
    }
  }

  return prompt;
}



