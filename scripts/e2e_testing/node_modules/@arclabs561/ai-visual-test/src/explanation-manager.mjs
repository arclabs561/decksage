/**
 * Explanation Manager
 * 
 * Provides late interaction capabilities for explaining VLLM judgments.
 * Allows humans to ask questions about judgments after they've been made.
 */

import { VLLMJudge } from './judge.mjs';
import { getCached, setCached } from './cache.mjs';
import { log, warn } from './logger.mjs';
import { formatNotesForPrompt } from './temporal.mjs';

/**
 * Explanation Manager
 * 
 * Manages interactive explanations of VLLM judgments
 */
export class ExplanationManager {
  constructor(options = {}) {
    this.judge = options.judge || new VLLMJudge(options);
    this.cacheEnabled = options.cacheEnabled !== false;
    this.explanations = new Map(); // In-memory cache of explanations
  }

  /**
   * Get explanation for a judgment
   * 
   * @param {Object} vllmJudgment - VLLM judgment to explain
   * @param {string} question - Question about the judgment (optional)
   * @param {Object} options - Explanation options
   * @returns {Promise<Object>} Explanation response
   */
  async explainJudgment(vllmJudgment, question = null, options = {}) {
    const {
      screenshotPath = vllmJudgment.screenshot,
      prompt = vllmJudgment.prompt,
      context = vllmJudgment.context || {},
      useCache = true,
      // NEW: Temporal and experience context
      temporalNotes = vllmJudgment.temporalNotes || context.temporalNotes || null,
      aggregatedNotes = vllmJudgment.aggregatedNotes || context.aggregatedNotes || null,
      experienceTrace = vllmJudgment.experienceTrace || context.experienceTrace || null
    } = options;

    // Build explanation prompt with temporal context
    const explanationPrompt = this._buildExplanationPrompt(
      vllmJudgment, 
      question,
      { temporalNotes, aggregatedNotes, experienceTrace }
    );

    // Check cache
    if (useCache && this.cacheEnabled) {
      const cacheKey = `explain-${vllmJudgment.id}-${question || 'default'}`;
      const cached = getCached(cacheKey, explanationPrompt, context);
      if (cached) {
        return cached;
      }
    }

    // Get explanation from VLLM
    try {
      const result = await this.judge.judgeScreenshot(
        screenshotPath,
        explanationPrompt,
        {
          ...context,
          useCache: false, // Don't cache explanation requests
          enableHumanValidation: false // Don't collect explanations for validation
        }
      );

      const explanation = {
        question: question || 'Why did you score this the way you did?',
        answer: result.reasoning || result.assessment || 'No explanation available',
        confidence: this._extractConfidence(result),
        timestamp: new Date().toISOString(),
        judgmentId: vllmJudgment.id
      };

      // Cache explanation
      if (useCache && this.cacheEnabled) {
        const cacheKey = `explain-${vllmJudgment.id}-${question || 'default'}`;
        setCached(cacheKey, explanationPrompt, context, explanation);
      }

      this.explanations.set(vllmJudgment.id, explanation);
      return explanation;
    } catch (error) {
      warn('Failed to get explanation:', error.message);
      return {
        question: question || 'Why did you score this the way you did?',
        answer: 'Unable to generate explanation at this time.',
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Build explanation prompt with temporal and experience context
   * 
   * @param {Object} vllmJudgment - VLLM judgment
   * @param {string|null} question - Optional question
   * @param {Object} temporalContext - Temporal and experience context
   * @param {Object|null} temporalContext.temporalNotes - Raw temporal notes
   * @param {Object|null} temporalContext.aggregatedNotes - Aggregated temporal notes
   * @param {Object|null} temporalContext.experienceTrace - Experience trace data
   */
  _buildExplanationPrompt(vllmJudgment, question, temporalContext = {}) {
    const { temporalNotes, aggregatedNotes, experienceTrace } = temporalContext;
    
    let prompt = '';
    
    // Base judgment context
    if (question) {
      prompt = `You previously evaluated this screenshot and gave it a score of ${vllmJudgment.vllmScore}/10.

Your previous judgment:
- Score: ${vllmJudgment.vllmScore}/10
- Issues: ${vllmJudgment.vllmIssues.join(', ') || 'None'}
- Reasoning: ${vllmJudgment.vllmReasoning}

Question: ${question}

Please provide a clear, detailed explanation addressing this question.`;
    } else {
      prompt = `You previously evaluated this screenshot and gave it a score of ${vllmJudgment.vllmScore}/10.

Your previous judgment:
- Score: ${vllmJudgment.vllmScore}/10
- Issues: ${vllmJudgment.vllmIssues.join(', ') || 'None'}
- Reasoning: ${vllmJudgment.vllmReasoning}

Please provide a detailed explanation of:
1. Why you scored it ${vllmJudgment.vllmScore}/10
2. What specific evidence in the screenshot led to this score
3. What the main issues are and why they matter
4. What would need to change to improve the score

Be specific and reference visual elements in the screenshot.`;
    }
    
    // Add temporal context if available
    if (aggregatedNotes) {
      prompt += `\n\nTEMPORAL CONTEXT:\n`;
      prompt += formatNotesForPrompt(aggregatedNotes);
      prompt += `\n\nWhen explaining, reference specific time points, trends, and temporal relationships (before/after/during).`;
      prompt += ` Explain how the current judgment relates to previous observations and temporal patterns.`;
    } else if (temporalNotes && Array.isArray(temporalNotes) && temporalNotes.length > 0) {
      // Format raw temporal notes if aggregated notes not available
      prompt += `\n\nTEMPORAL CONTEXT:\n`;
      const recentNotes = temporalNotes.slice(-5);
      recentNotes.forEach((note, i) => {
        const time = note.elapsed ? `${(note.elapsed / 1000).toFixed(1)}s` : `step ${i + 1}`;
        prompt += `  ${time}: ${note.observation || note.step || 'step'}\n`;
        if (note.score !== null && note.score !== undefined) {
          prompt += `    Score: ${note.score}/10\n`;
        }
      });
      prompt += `\n\nWhen explaining, reference these temporal observations and explain how they relate to the current judgment.`;
    }
    
    // Add experience trace context if available
    if (experienceTrace) {
      prompt += `\n\nEXPERIENCE TRACE CONTEXT:\n`;
      prompt += `Session ID: ${experienceTrace.sessionId || 'unknown'}\n`;
      
      if (experienceTrace.persona) {
        prompt += `Persona: ${experienceTrace.persona.name || 'unknown'}\n`;
        if (experienceTrace.persona.goals) {
          prompt += `Persona Goals: ${experienceTrace.persona.goals.join(', ')}\n`;
        }
      }
      
      if (experienceTrace.events && experienceTrace.events.length > 0) {
        prompt += `\nRecent Events (last 5):\n`;
        const recentEvents = experienceTrace.events.slice(-5);
        recentEvents.forEach(event => {
          const time = event.elapsed ? `${(event.elapsed / 1000).toFixed(1)}s` : 'unknown';
          prompt += `  ${time}: ${event.type} - ${event.data.observation || event.data.action || ''}\n`;
        });
      }
      
      if (experienceTrace.validations && experienceTrace.validations.length > 0) {
        prompt += `\nPrevious Validations (last 3):\n`;
        const recentValidations = experienceTrace.validations.slice(-3);
        recentValidations.forEach(validation => {
          const time = validation.elapsed ? `${(validation.elapsed / 1000).toFixed(1)}s` : 'unknown';
          prompt += `  ${time}: Score ${validation.validation.score}/10 - ${validation.validation.reasoning?.substring(0, 100) || ''}\n`;
        });
      }
      
      prompt += `\n\nWhen explaining, consider the user's journey, previous states, and how the current judgment fits into the overall experience.`;
    }
    
    // Add VLLM-specific guidance for temporal explanations
    if (aggregatedNotes || temporalNotes || experienceTrace) {
      prompt += `\n\nIMPORTANT: As a Vision-Language Model, when explaining temporal aspects:
1. Visual citations: Reference specific image regions (coordinates, descriptions) when mentioning visual evidence
2. Temporal citations: Reference specific time points (e.g., "at t=5s", "after 12 seconds")
3. Temporal relationships: Explain before/after/during relationships and transitions
4. Experience context: Reference the user's journey and how previous states influenced the judgment
5. Trends: Explain improvement/decline trends and temporal coherence`;
    }
    
    return prompt;
  }

  /**
   * Extract confidence from result
   */
  _extractConfidence(result) {
    // Try to extract confidence from various sources
    if (result.semantic?.confidence !== undefined) {
      return result.semantic.confidence;
    }
    if (result.raw?.confidence !== undefined) {
      return result.raw.confidence;
    }
    // Estimate from uncertainty if available
    if (result.uncertainty !== undefined) {
      return 1.0 - result.uncertainty;
    }
    return null;
  }

  /**
   * Get confidence breakdown for different aspects
   */
  async getConfidenceBreakdown(vllmJudgment) {
    const questions = [
      'How confident are you in the overall score?',
      'How confident are you in the issues you identified?',
      'Are there any aspects you are uncertain about?'
    ];

    const breakdown = {
      overall: null,
      issues: null,
      uncertainty: null,
      aspects: []
    };

    // Get explanations for each question
    for (const question of questions) {
      const explanation = await this.explainJudgment(vllmJudgment, question, { useCache: true });
      // Parse explanation to extract confidence info
      // This is a simplified version - could be enhanced with structured output
      breakdown.aspects.push({
        question,
        explanation: explanation.answer
      });
    }

    return breakdown;
  }

  /**
   * Explain disagreement between human and VLLM
   */
  async explainDisagreement(vllmJudgment, humanJudgment) {
    const question = `A human reviewer scored this ${humanJudgment.humanScore}/10, but you scored it ${vllmJudgment.vllmScore}/10. 
The human identified these issues: ${humanJudgment.humanIssues.join(', ') || 'None'}.
You identified these issues: ${vllmJudgment.vllmIssues.join(', ') || 'None'}.

Please explain:
1. Why there might be a difference in scores
2. Whether you think the human's assessment is valid
3. What you might have missed or over-emphasized
4. How this could help improve future evaluations`;

    return await this.explainJudgment(vllmJudgment, question);
  }

  /**
   * Get cached explanation if available
   */
  getCachedExplanation(judgmentId, question = null) {
    const key = question ? `${judgmentId}-${question}` : judgmentId;
    return this.explanations.get(key) || null;
  }
}

/**
 * Global explanation manager instance
 */
let globalExplanationManager = null;

/**
 * Get or create global explanation manager
 */
export function getExplanationManager(options = {}) {
  if (!globalExplanationManager) {
    globalExplanationManager = new ExplanationManager(options);
  }
  return globalExplanationManager;
}

