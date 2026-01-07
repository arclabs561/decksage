/**
 * Persona Sub-Module
 * 
 * Persona-based experience testing and evaluation.
 * 
 * Import from 'ai-visual-test/persona'
 */

// Core persona experience
export {
  experiencePageAsPersona,
  experiencePageWithPersonas
} from '../persona-experience.mjs';

// Enhanced persona
export {
  createEnhancedPersona,
  experiencePageWithEnhancedPersona,
  calculatePersonaConsistency,
  calculatePersonaDiversity
} from '../persona-enhanced.mjs';

// Experience tracing
export {
  ExperienceTrace,
  ExperienceTracerManager,
  getTracerManager
} from '../experience-tracer.mjs';

// Experience propagation
export {
  ExperiencePropagationTracker,
  getPropagationTracker,
  trackPropagation
} from '../experience-propagation.mjs';

// Explanation manager
export {
  ExplanationManager,
  getExplanationManager
} from '../explanation-manager.mjs';

