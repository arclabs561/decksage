/**
 * Natural Language Specs Sub-Module
 * 
 * Natural language specification parsing and execution.
 * 
 * Import from 'ai-visual-test/specs'
 */

// Core spec functions
export {
  parseSpec,
  mapToInterfaces,
  executeSpec,
  generatePropertyTests,
  testBehavior,
  validateSpec
} from '../natural-language-specs.mjs';

// Spec templates
export {
  TEMPLATES,
  createSpecFromTemplate,
  composeTemplates,
  inheritTemplate,
  registerTemplate,
  listTemplates,
  getTemplate,
  validateTemplate
} from '../spec-templates.mjs';

// Spec config
export {
  createSpecConfig,
  getSpecConfig,
  setSpecConfig,
  resetSpecConfig
} from '../spec-config.mjs';

