/**
 * Enhanced Persona Structure
 *
 * Adds rich context to personas based on research findings:
 * - Workflows, frustrations, usage patterns
 * - Temporal evolution tracking
 * - Consistency metrics
 *
 * Research:
 * - "Can LLM be a Personalized Judge?" - Persona-based LLM judging with uncertainty estimation
 * - "The Prompt Makes the Person(a)" - Systematic evaluation of sociodemographic persona prompting
 * - "Persona-judge: Personalized Alignment of Large Language Models" - Personalized alignment
 * - "PERSONA: Evaluating Pluralistic Alignment in LLMs" - Pluralistic alignment with personas
 *
 * Note: Research shows direct persona-based judging has low reliability, but uncertainty
 * estimation improves performance to >80% agreement on high-certainty samples. LLMs struggle
 * to authentically simulate marginalized groups. Multi-agent debate can amplify bias.
 */

import { experiencePageAsPersona } from './persona-experience.mjs';

/**
 * Enhanced persona structure with rich context
 *
 * @typedef {Object} EnhancedPersona
 * @property {string} name - Persona name
 * @property {string} device - Device type
 * @property {string[]} goals - Primary goals
 * @property {string[]} concerns - Primary concerns
 * @property {Object} workflows - Documented workflows and use cases
 * @property {string[]} frustrations - Specific frustrations
 * @property {Object} usagePatterns - Historical usage patterns
 * @property {Object} temporalEvolution - Temporal usage evolution
 */

/**
 * Create enhanced persona with rich context
 *
 * @param {Object} basePersona - Base persona (name, device, goals, concerns)
 * @param {{
 *   workflows?: Object;
 *   frustrations?: string[];
 *   usagePatterns?: Object;
 *   temporalEvolution?: Object;
 * }} [context={}] - Rich context
 * @returns {EnhancedPersona} Enhanced persona
 */
export function createEnhancedPersona(basePersona, context = {}) {
  return {
    ...basePersona,
    workflows: context.workflows || {
      primary: [],
      secondary: [],
      edgeCases: []
    },
    frustrations: context.frustrations || [],
    usagePatterns: context.usagePatterns || {
      frequency: 'unknown',
      duration: 'unknown',
      peakTimes: []
    },
    temporalEvolution: context.temporalEvolution || {
      firstUse: null,
      lastUse: null,
      usageTrend: 'stable'
    }
  };
}

/**
 * Calculate consistency metrics for persona observations
 *
 * @param {Array} observations - Array of observations from persona
 * @returns {Object} Consistency metrics
 */
export function calculatePersonaConsistency(observations) {
  if (observations.length < 2) {
    return {
      promptToLine: 1.0,
      lineToLine: 1.0,
      overall: 1.0
    };
  }

  // Extract keywords from each observation
  const keywordSets = observations.map(obs => {
    const text = typeof obs === 'string' ? obs : obs.observation || '';
    const words = text.toLowerCase()
      .split(/\s+/)
      .filter(w => w.length > 3)
      .filter(w => !['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can'].includes(w));
    return new Set(words);
  });

  // Calculate prompt-to-line consistency (first vs all others)
  const firstKeywords = keywordSets[0];
  let promptToLineMatches = 0;
  for (let i = 1; i < keywordSets.length; i++) {
    const intersection = new Set([...firstKeywords].filter(x => keywordSets[i].has(x)));
    const union = new Set([...firstKeywords, ...keywordSets[i]]);
    const similarity = union.size > 0 ? intersection.size / union.size : 0;
    promptToLineMatches += similarity;
  }
  const promptToLine = promptToLineMatches / Math.max(1, keywordSets.length - 1);

  // Calculate line-to-line consistency (adjacent observations)
  let lineToLineMatches = 0;
  for (let i = 1; i < keywordSets.length; i++) {
    const prev = keywordSets[i - 1];
    const curr = keywordSets[i];
    const intersection = new Set([...prev].filter(x => curr.has(x)));
    const union = new Set([...prev, ...curr]);
    const similarity = union.size > 0 ? intersection.size / union.size : 0;
    lineToLineMatches += similarity;
  }
  const lineToLine = lineToLineMatches / Math.max(1, keywordSets.length - 1);

  // Overall consistency (weighted average)
  const overall = (promptToLine * 0.4 + lineToLine * 0.6);

  return {
    promptToLine,
    lineToLine,
    overall,
    observationCount: observations.length
  };
}

/**
 * Experience page with enhanced persona
 *
 * @param {any} page - Playwright page object
 * @param {EnhancedPersona} persona - Enhanced persona
 * @param {Object} options - Experience options
 * @returns {Promise<Object>} Experience result with consistency metrics
 */
export async function experiencePageWithEnhancedPersona(page, persona, options = {}) {
  // Use base experience function
  const experience = await experiencePageAsPersona(page, persona, options);

  // Extract observations
  const observations = experience.notes.map(n => n.observation || '');

  // Calculate consistency metrics
  const consistency = calculatePersonaConsistency(observations);

  // Add persona context to experience
  return {
    ...experience,
    persona: {
      ...persona,
      workflows: persona.workflows,
      frustrations: persona.frustrations,
      usagePatterns: persona.usagePatterns
    },
    consistency,
    observations
  };
}

/**
 * Compare persona observations for diversity
 *
 * @param {Array} personaExperiences - Array of persona experience results
 * @returns {Object} Diversity metrics
 */
export function calculatePersonaDiversity(personaExperiences) {
  if (personaExperiences.length < 2) {
    return {
      diversityRatio: 0,
      uniqueKeywords: 0,
      totalKeywords: 0
    };
  }

  // Extract all keywords from all personas
  const allKeywords = personaExperiences.flatMap(exp => {
    const observations = exp.observations || exp.notes?.map(n => n.observation || '') || [];
    return observations.flatMap(obs => {
      const words = obs.toLowerCase()
        .split(/\s+/)
        .filter(w => w.length > 3)
        .filter(w => !['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can'].includes(w));
      return words;
    });
  });

  const uniqueKeywords = new Set(allKeywords);
  const diversityRatio = uniqueKeywords.size / Math.max(1, allKeywords.length);

  return {
    diversityRatio,
    uniqueKeywords: uniqueKeywords.size,
    totalKeywords: allKeywords.length,
    personaCount: personaExperiences.length
  };
}



