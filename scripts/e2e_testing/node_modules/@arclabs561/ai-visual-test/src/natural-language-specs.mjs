/**
 * Natural Language Specifications
 * 
 * Parses plain English test specifications and executes them against our validation interfaces.
 * 
 * NOT formal specs (TLA+, Alloy, Z) - just LLM-parseable natural language.
 * 
 * Based on real-world usage patterns from interactive web applications:
 * - Direct natural language prompts in validateScreenshot() calls
 * - Goal-based validation with testGameplay()
 * - Multi-modal validation (screenshot + rendered code + game state)
 * - Temporal sequences for gameplay over time
 * - Game activation patterns (keyboard shortcuts, game selectors)
 * 
 * Research Context:
 * - Property-based testing (framework structure, not full fast-check/Hypothesis implementation)
 * - BDD-style Given/When/Then (but LLM-parsed, not Gherkin)
 * - Temporal decision-making (arXiv:2406.12125 - NOT IMPLEMENTED in spec parsing, see temporal-decision.mjs for related concepts)
 * - Human perception time (NN/g, PMC - 0.1s threshold, used in temporal aggregation)
 * 
 * Use Cases:
 * - Flash website games
 * - News pages
 * - GitHub PR pages
 * - Interactive web applications with games
 * - Websites in development
 * - Any web experience that needs validation
 */

import { validateScreenshot } from './judge.mjs';
import { validateAccessibilitySmart, validateStateSmart, validateSmart } from './smart-validator.mjs';
import { testGameplay, testBrowserExperience, validateWithGoals } from './convenience.mjs';
import { playGame, GameGym } from './game-player.mjs';
import { log, warn } from './logger.mjs';
import { getSpecConfig } from './spec-config.mjs';

/**
 * Extract context from natural language spec text using LLM
 * 
 * Uses LLM to parse natural language and extract structured context.
 * Falls back to regex heuristics if LLM is unavailable (for code assist).
 * 
 * @param {string} spec - Natural language spec text
 * @param {Object} [options] - Extraction options
 * @returns {Promise<Object>} Extracted context
 */
async function extractContextFromSpec(spec, options = {}) {
  const specConfig = getSpecConfig();
  const { useLLM = specConfig.useLLM, fallback = specConfig.fallback, provider = specConfig.provider } = options;
  
  // Try LLM-based extraction first (more robust)
  if (useLLM) {
    try {
      const { extractStructuredData } = await import('./data-extractor.mjs');
      
      const schema = {
        url: { 
          type: 'string', 
          required: false,
          description: 'The URL or domain to visit (e.g., "example.com", "https://example.com"). Extract from phrases like "I visit example.com" or "Given I visit example.com"'
        },
        viewport: { type: 'object', required: false }, // Will be parsed as string then converted
        viewportWidth: { type: 'number', required: false },
        viewportHeight: { type: 'number', required: false },
        device: { type: 'string', required: false },
        persona: { type: 'string', required: false },
        activationKey: { type: 'string', required: false },
        gameActivationKey: { type: 'string', required: false },
        selector: { type: 'string', required: false },
        gameSelector: { type: 'string', required: false },
        fps: { type: 'number', required: false },
        duration: { type: 'number', required: false }, // In seconds, will convert to ms
        captureTemporal: { type: 'boolean', required: false }
      };
      
      const extracted = await extractStructuredData(spec, schema, {
        fallback: fallback === 'regex' ? 'auto' : 'llm',
        provider: options.provider
      });
      
      if (extracted) {
        const context = {};
        
        // Normalize URL
        if (extracted.url) {
          let url = extracted.url.trim();
          if (!url.startsWith('http://') && !url.startsWith('https://')) {
            url = `https://${url}`;
          }
          context.url = url;
        }
        
        // Build viewport from width/height or object
        if (extracted.viewportWidth && extracted.viewportHeight) {
          context.viewport = {
            width: extracted.viewportWidth,
            height: extracted.viewportHeight
          };
        } else if (extracted.viewport && typeof extracted.viewport === 'object') {
          context.viewport = extracted.viewport;
        } else if (typeof extracted.viewport === 'string') {
          // Parse "1280x720" format
          const match = extracted.viewport.match(/(\d+)\s*[x×]\s*(\d+)/i);
          if (match) {
            context.viewport = {
              width: parseInt(match[1]),
              height: parseInt(match[2])
            };
          }
        }
        
        // Copy other fields
        if (extracted.device) context.device = extracted.device.toLowerCase();
        if (extracted.persona) context.persona = extracted.persona.trim();
        if (extracted.activationKey) {
          context.activationKey = extracted.activationKey.toLowerCase();
          context.gameActivationKey = context.activationKey; // Backward compat
        }
        if (extracted.gameActivationKey) {
          context.gameActivationKey = extracted.gameActivationKey.toLowerCase();
          if (!context.activationKey) context.activationKey = context.gameActivationKey;
        }
        if (extracted.selector) {
          context.selector = extracted.selector;
          if (spec.toLowerCase().includes('game') || extracted.selector.includes('game')) {
            context.gameSelector = extracted.selector;
          }
        }
        if (extracted.gameSelector) {
          context.gameSelector = extracted.gameSelector;
          if (!context.selector) context.selector = extracted.gameSelector;
        }
        if (extracted.fps) context.fps = extracted.fps;
        if (extracted.duration) context.duration = extracted.duration * 1000; // Convert to ms
        if (extracted.captureTemporal !== undefined) context.captureTemporal = extracted.captureTemporal;
        
        // Special handling for Konami code
        if (spec.toLowerCase().includes('konami')) {
          context.activationKey = 'konami';
          context.gameActivationKey = 'konami';
        }
        
        // If critical fields are missing, try regex fallback to fill gaps
        const needsFallback = !context.url || !context.viewport || !context.activationKey || context.captureTemporal === undefined;
        if (needsFallback && (spec.toLowerCase().includes('visit') || spec.toLowerCase().includes('navigate') || spec.toLowerCase().includes('goto') || spec.toLowerCase().includes('context'))) {
          const regexContext = extractContextFromSpecRegex(spec);
          // Fill in missing fields from regex fallback
          if (!context.url && regexContext.url) {
            context.url = regexContext.url;
          }
          if (!context.viewport && regexContext.viewport) {
            context.viewport = regexContext.viewport;
          }
          if (!context.activationKey && regexContext.activationKey) {
            context.activationKey = regexContext.activationKey;
            context.gameActivationKey = regexContext.activationKey;
          }
          if (!context.gameSelector && regexContext.gameSelector) {
            context.gameSelector = regexContext.gameSelector;
            if (!context.selector) context.selector = regexContext.gameSelector;
          }
          if (context.captureTemporal === undefined && regexContext.captureTemporal !== undefined) {
            context.captureTemporal = regexContext.captureTemporal;
          }
        }
        
        return context;
      }
    } catch (error) {
      warn('[NaturalLanguageSpecs] LLM extraction failed, falling back to regex:', error.message);
      // Fall through to regex fallback
    }
  }
  
  // Fallback: Regex heuristics (for code assist when LLM unavailable)
  return extractContextFromSpecRegex(spec);
}

/**
 * Extract context using regex heuristics (fallback for code assist)
 * 
 * @param {string} spec - Natural language spec text
 * @returns {Object} Extracted context
 */
function extractContextFromSpecRegex(spec) {
  const context = {};
  const lower = spec.toLowerCase();
  
  // Extract URL
  const urlPatterns = [
    /(?:visit|open|navigate to|goto|go to|navigate)\s+(https?:\/\/[^\s\n]+)/i,
    /(?:visit|open|navigate to|goto|go to|navigate)\s+([a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?::\d+)?(?:\/[^\s\n]*)?)/i,
    /(?:I\s+)?(?:visit|open|navigate to|goto|go to|navigate)\s+([a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?::\d+)?(?:\/[^\s\n]*)?)/i, // Handle "I visit example.com"
    /url[=:]\s*(https?:\/\/[^\s\n]+|[a-z0-9][a-z0-9.-]*\.[a-z]{2,})/i
  ];
  
  for (const pattern of urlPatterns) {
    const urlMatch = spec.match(pattern);
    if (urlMatch) {
      let url = urlMatch[1].trim();
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = `https://${url}`;
      }
      context.url = url;
      break;
    }
  }
  
  // Extract viewport
  const viewportPatterns = [
    /viewport[=:]\s*(\d+)\s*[x×]\s*(\d+)/i,
    /(\d+)\s*[x×]\s*(\d+)\s*(?:viewport|screen|resolution|px)/i,
    /(\d+)\s*[x×]\s*(\d+)(?:\s|$)/i
  ];
  
  for (const pattern of viewportPatterns) {
    const viewportMatch = spec.match(pattern);
    if (viewportMatch) {
      const width = parseInt(viewportMatch[1]);
      const height = parseInt(viewportMatch[2]);
      if (width && height && width > 100 && height > 100) {
        context.viewport = { width, height };
        break;
      }
    }
  }
  
  // Extract device
  const deviceMatch = spec.match(/device[=:]\s*(\w+)|(?:on|using|with)\s+(desktop|mobile|tablet|phone)/i);
  if (deviceMatch) {
    context.device = (deviceMatch[1] || deviceMatch[2]).toLowerCase();
  }
  
  // Extract persona
  const personaMatch = spec.match(/persona[=:]\s*([^\n,]+)|as\s+([A-Z][^\n,]+?)(?:\s+persona)?/i);
  if (personaMatch) {
    context.persona = (personaMatch[1] || personaMatch[2]).trim();
  }
  
  // Extract activation key
  const keyPatterns = [
    /(?:press|key|activation key|shortcut)[=:]\s*['"]?([a-z0-9])['"]?/i,
    /press\s+['"]([a-z0-9])['"]/i,
    /(?:press|hit|type)\s+([a-z0-9])(?:\s|$)/i
  ];
  
  for (const pattern of keyPatterns) {
    const keyMatch = spec.match(pattern);
    if (keyMatch) {
      context.activationKey = (keyMatch[1] || keyMatch[2]).toLowerCase();
      context.gameActivationKey = context.activationKey;
      break;
    }
  }
  
  if (lower.includes('konami')) {
    context.activationKey = 'konami';
    context.gameActivationKey = 'konami';
  }
  
  // Extract selector
  const selectorPatterns = [
    /selector[=:]\s*(#[a-z0-9-]+|\.?[a-z0-9-]+|\w+)/i,
    /(#[a-z0-9-]+)(?:\s|\)|$)/i, // Match #game-paddle) or #game-paddle
    /selector\s+(#[a-z0-9-]+|\.?[a-z0-9-]+)/i,
    /element[=:]\s*(#[a-z0-9-]+|\.?[a-z0-9-]+)/i
  ];
  
  for (const pattern of selectorPatterns) {
    const selectorMatch = spec.match(pattern);
    if (selectorMatch) {
      let selector = (selectorMatch[1] || selectorMatch[2]).trim();
      // Remove trailing ) if present (from "selector: #game-paddle)")
      if (selector.endsWith(')')) {
        selector = selector.slice(0, -1);
      }
      if (selector.startsWith('#') || selector.startsWith('.') || /^[a-z]/.test(selector)) {
        context.selector = selector;
        if (lower.includes('game') || selector.includes('game')) {
          context.gameSelector = selector;
        }
        break;
      }
    }
  }
  
  // Extract FPS
  const fpsMatch = spec.match(/fps[=:]\s*(\d+)|(\d+)\s*fps/i);
  if (fpsMatch) {
    context.fps = parseInt(fpsMatch[1] || fpsMatch[2]);
  }
  
  // Extract duration
  const durationMatch = spec.match(/(?:duration|for)[=:]\s*(\d+)|(\d+)\s*(?:second|sec|s)(?:onds)?/i);
  if (durationMatch) {
    const seconds = parseInt(durationMatch[1] || durationMatch[2]);
    context.duration = seconds * 1000;
  }
  
  // Extract temporal flag
  // Check for explicit temporal: true in Context line, or temporal keywords
  // Also detect from fps + duration combination (implicit temporal)
  if (lower.includes('temporal') || lower.includes('over time') || lower.includes('sequence') || 
      lower.match(/temporal[=:]\s*(true|yes|1)/i)) {
    context.captureTemporal = true;
  } else if (lower.includes('fps') && lower.includes('duration')) {
    // Implicit temporal: if fps and duration are both present, it's likely temporal
    context.captureTemporal = true;
  }
  
  return context;
}

/**
 * Parse natural language spec into structured test description
 * 
 * Uses LLM to parse plain English into executable test structure.
 * Auto-extracts context from spec text (URLs, viewports, devices, etc.).
 * 
 * @param {string} spec - Natural language spec (Given/When/Then or property description)
 * @returns {Promise<Object>} Parsed spec structure with extracted context
 */
export async function parseSpec(spec, options = {}) {
  // Extract context from spec text using LLM (with regex fallback)
  const extractedContext = await extractContextFromSpec(spec, options);
  
  // Use LLM to parse natural language
  // For now, simple keyword-based parsing (can be enhanced with LLM)
  
  const lines = spec.split('\n').map(l => l.trim()).filter(l => l.length > 0);
  
  const parsed = {
    type: 'behavior', // 'behavior' or 'property'
    given: [],
    when: [],
    then: [],
    properties: [],
    keywords: [],
    interfaces: [],
    context: extractedContext || {} // Include extracted context (ensure it's an object)
  };
  
  let currentSection = null;
  
  for (const line of lines) {
    const lower = line.toLowerCase();
    
    // Skip context lines (already extracted)
    if (lower.startsWith('context:') || lower.startsWith('options:')) {
      continue;
    }
    
    // Detect section
    if (lower.startsWith('given')) {
      currentSection = 'given';
      parsed.given.push(line.replace(/^given\s+/i, '').trim());
    } else if (lower.startsWith('when')) {
      currentSection = 'when';
      parsed.when.push(line.replace(/^when\s+/i, '').trim());
    } else if (lower.startsWith('then')) {
      currentSection = 'then';
      parsed.then.push(line.replace(/^then\s+/i, '').trim());
    } else if (lower.startsWith('and')) {
      // Continue current section
      const content = line.replace(/^and\s+/i, '').trim();
      if (currentSection && parsed[currentSection] && Array.isArray(parsed[currentSection])) {
        parsed[currentSection].push(content);
      } else if (content) {
        // If no current section, treat as property
        parsed.properties.push(content);
      }
    } else if (lower.startsWith('for all') || lower.includes('should always')) {
      // Property description
      parsed.type = 'property';
      parsed.properties.push(line);
    } else {
      // Generic line - add to current section or as property
      if (currentSection && parsed[currentSection] && Array.isArray(parsed[currentSection])) {
        parsed[currentSection].push(line);
      } else if (line) {
        parsed.properties.push(line);
      }
    }
    
    // Extract keywords for interface selection
    // Note: Multiple interfaces can be detected (e.g., accessibility + browser experience)
    if (lower.includes('accessible') || lower.includes('accessibility')) {
      parsed.keywords.push('accessibility');
      if (!parsed.interfaces.includes('validateAccessibilitySmart')) {
        parsed.interfaces.push('validateAccessibilitySmart');
      }
    }
    // Game detection: be more careful - "game should work" in unstructured spec might not mean gameplay testing
    // Only detect game if there's clear gameplay context (play, activate, playable) or structured spec
    if ((lower.includes('play') || lower.includes('playable') || lower.includes('activate')) ||
        (lower.includes('game') && (parsed.given.length > 0 || parsed.when.length > 0 || parsed.then.length > 0))) {
      parsed.keywords.push('game');
      if (!parsed.interfaces.includes('testGameplay')) {
        parsed.interfaces.push('testGameplay');
      }
    }
    if (lower.includes('state') || lower.includes('position') || lower.includes('consistency')) {
      parsed.keywords.push('state');
      if (!parsed.interfaces.includes('validateStateSmart')) {
        parsed.interfaces.push('validateStateSmart');
      }
    }
    // Only add validateScreenshot if explicitly mentioned or as fallback
    // Don't add it just because of "visual" (too broad - catches "visually impaired", "visual representation")
    // Only trigger on explicit screenshot mention or standalone "visual" (not in phrases)
    if (lower.includes('screenshot') || 
        (lower.includes(' visual ') && !lower.includes('visually') && !lower.includes('visual representation'))) {
      parsed.keywords.push('visual');
      if (!parsed.interfaces.includes('validateScreenshot')) {
        parsed.interfaces.push('validateScreenshot');
      }
    }
    // Browser experience keywords: journey, experience, navigate, browse, checkout, form, payment
    if (lower.includes('experience') || lower.includes('journey') || 
        lower.includes('navigate') || lower.includes('browse') || 
        lower.includes('checkout') || lower.includes('cart') ||
        lower.includes('payment') || lower.includes('form')) {
      parsed.keywords.push('experience');
      if (!parsed.interfaces.includes('testBrowserExperience')) {
        parsed.interfaces.push('testBrowserExperience');
      }
    }
  }
  
  // For property-based specs, extract interface from property scope/content
  if (parsed.type === 'property' && parsed.properties.length > 0) {
    const propertyText = parsed.properties.join(' ').toLowerCase();
    
    // Extract interface from property scope (e.g., "For all screenshots" → validateScreenshot)
    if (propertyText.includes('screenshot')) {
      if (!parsed.interfaces.includes('validateScreenshot')) {
        parsed.interfaces.push('validateScreenshot');
      }
    }
    if (propertyText.includes('game state') || propertyText.includes('state')) {
      if (!parsed.interfaces.includes('validateStateSmart')) {
        parsed.interfaces.push('validateStateSmart');
      }
    }
    if (propertyText.includes('game')) {
      if (!parsed.interfaces.includes('testGameplay')) {
        parsed.interfaces.push('testGameplay');
      }
    }
  }
  
  // Default interface if none detected
  if (parsed.interfaces.length === 0) {
    parsed.interfaces.push('validateScreenshot');
  }
  
  return parsed;
}

/**
 * Map parsed spec to interface calls
 * 
 * Merges extracted context from spec with provided context/options.
 * Extracted context takes precedence (spec is source of truth).
 * 
 * @param {Object} parsedSpec - Parsed spec structure (includes extracted context)
 * @param {Object} context - Execution context (page, url, etc.)
 * @returns {Promise<Array>} Array of interface calls to execute
 */
export async function mapToInterfaces(parsedSpec, context = {}) {
  // Validate parsedSpec
  if (!parsedSpec || typeof parsedSpec !== 'object') {
    throw new Error('mapToInterfaces: parsedSpec must be a valid object');
  }
  
  const { page, url, screenshotPath, options = {} } = context;
  const calls = [];
  
  // Ensure parsedSpec has required properties with defaults
  parsedSpec.interfaces = parsedSpec.interfaces || [];
  parsedSpec.context = parsedSpec.context || {};
  parsedSpec.given = parsedSpec.given || [];
  parsedSpec.when = parsedSpec.when || [];
  parsedSpec.then = parsedSpec.then || [];
  parsedSpec.properties = parsedSpec.properties || [];
  
  // Merge extracted context with provided options (extracted context takes precedence)
  const mergedContext = {
    ...options,
    ...parsedSpec.context, // Extracted from spec (source of truth)
    // But allow explicit overrides from options
    url: parsedSpec.context?.url || url || options.url,
    gameActivationKey: parsedSpec.context?.gameActivationKey || options.gameActivationKey,
    gameSelector: parsedSpec.context?.gameSelector || options.gameSelector,
    viewport: parsedSpec.context?.viewport || options.viewport,
    device: parsedSpec.context?.device || options.device,
    persona: parsedSpec.context?.persona || options.persona,
    fps: parsedSpec.context?.fps || options.fps,
    duration: parsedSpec.context?.duration || options.duration,
    captureTemporal: parsedSpec.context?.captureTemporal !== undefined 
      ? parsedSpec.context.captureTemporal 
      : options.captureTemporal
  };
  
  // Support multiple interfaces when detected (e.g., accessibility + browser experience)
  // Build interface calls for all detected interfaces
  const detectedInterfaces = parsedSpec.interfaces.length > 0 
    ? parsedSpec.interfaces 
    : ['validateScreenshot']; // Default fallback
  
  // Remove duplicates while preserving order
  const uniqueInterfaces = [...new Set(detectedInterfaces)];
  
  // Build interface calls based on spec content
  // Note: page is passed separately, not in options
  for (const primaryInterface of uniqueInterfaces) {
    if (primaryInterface === 'validateAccessibilitySmart') {
      const { page: _, ...accessibilityOptions } = options; // Remove page from options
      calls.push({
        interface: 'validateAccessibilitySmart',
        page: page, // Pass page separately
        args: {
          page: page, // validateAccessibilitySmart accepts page in options
          screenshotPath: screenshotPath,
          minContrast: 4.5,
          ...accessibilityOptions
        }
      });
    } else if (primaryInterface === 'testGameplay') {
      // Extract game-specific options from spec
      // Use extracted context first, then fall back to parsing spec text, then options
      const gameActivationKey = mergedContext.gameActivationKey || 
        mergedContext.activationKey ||
        parsedSpec.given.find(g => 
          g.includes('activate') || g.includes('press')
        )?.match(/press\s+['"]?([a-z])['"]?/i)?.[1] || 
        parsedSpec.given.find(g => g.includes('konami')) ? 'konami' :
        options.gameActivationKey;
      
      const gameSelector = mergedContext.gameSelector || 
        mergedContext.selector ||
        parsedSpec.given.find(g => 
          g.includes('selector') || g.includes('#')
        )?.match(/#[\w-]+/)?.[0] || options.gameSelector;
      
      // Extract goals from spec (common goals: fun, accessibility, performance, visual-consistency)
      const goals = [];
      const allText = [...parsedSpec.given, ...parsedSpec.when, ...parsedSpec.then].join(' ').toLowerCase();
      if (allText.includes('fun') || allText.includes('playable') || allText.includes('enjoyable')) {
        goals.push('fun');
      }
      if (allText.includes('accessible') || allText.includes('accessibility')) {
        goals.push('accessibility');
      }
      if (allText.includes('performance') || allText.includes('smooth') || allText.includes('fast')) {
        goals.push('performance');
      }
      if (allText.includes('visual') || allText.includes('consistency') || allText.includes('layout')) {
        goals.push('visual-consistency');
      }
      
      // Extract temporal options (temporal capture for gameplay sequences)
      const captureTemporal = allText.includes('temporal') || allText.includes('over time') || 
                             allText.includes('sequence') || options.captureTemporal;
      const fps = allText.match(/fps[:\s]+(\d+)/i)?.[1] || options.fps || 2;
      const duration = allText.match(/(\d+)\s*(?:second|sec)/i)?.[1] ? parseInt(allText.match(/(\d+)\s*(?:second|sec)/i)?.[1]) * 1000 : options.duration || 5000;
      
      // Remove page from options - testGameplay expects (page, options)
      const { page: _, ...gameplayOptions } = options;
      calls.push({
        interface: 'testGameplay',
        page: page, // Pass page separately for testGameplay(page, options)
        args: {
          url: mergedContext.url,
          goals: goals.length > 0 ? goals : ['fun', 'accessibility'],
          gameActivationKey: mergedContext.gameActivationKey || gameActivationKey,
          gameSelector: mergedContext.gameSelector || gameSelector,
          captureTemporal: mergedContext.captureTemporal !== undefined ? mergedContext.captureTemporal : captureTemporal,
          fps: mergedContext.fps || fps,
          duration: mergedContext.duration || duration,
          captureCode: true, // Dual-view: screenshot (rendered) + HTML/CSS (source)
          checkConsistency: true, // Cross-modal consistency: visual vs. code
          viewport: mergedContext.viewport,
          device: mergedContext.device,
          persona: mergedContext.persona ? { name: mergedContext.persona } : undefined,
          // Research features integration
          useTemporalPreprocessing: options.useTemporalPreprocessing !== undefined ? options.useTemporalPreprocessing : false,
          // Pass through any other research-enhanced options
          enableUncertaintyReduction: options.enableUncertaintyReduction,
          enableHallucinationCheck: options.enableHallucinationCheck,
          adaptiveSelfConsistency: options.adaptiveSelfConsistency,
          ...gameplayOptions // Options without page (allows per-test overrides)
        }
      });
    } else if (primaryInterface === 'validateStateSmart') {
      const { page: _, ...stateOptions } = options; // Remove page from options
      calls.push({
        interface: 'validateStateSmart',
        page: page, // Pass page separately
        args: {
          page: page, // validateStateSmart accepts page in options
          screenshotPath: screenshotPath,
          ...stateOptions
        }
      });
    } else if (primaryInterface === 'testBrowserExperience') {
      // Extract stages from spec
      const stages = [];
      if (parsedSpec.given.some(g => g.includes('visit') || g.includes('open'))) {
        stages.push('initial');
      }
      if (parsedSpec.when.some(w => w.includes('form') || w.includes('fill'))) {
        stages.push('form');
      }
      if (parsedSpec.when.some(w => w.includes('payment') || w.includes('checkout'))) {
        stages.push('payment');
      }
      
      // Remove page from options - testBrowserExperience expects (page, options)
      const { page: _, ...browserOptions } = options;
      calls.push({
        interface: 'testBrowserExperience',
        page: page, // Pass page separately for testBrowserExperience(page, options)
        args: {
          url: mergedContext.url,
          stages: stages.length > 0 ? stages : ['initial'],
          ...browserOptions // Options without page
        }
      });
    } else if (primaryInterface === 'validateScreenshot') {
      // validateScreenshot (direct natural language prompts)
      // Build prompt from spec (detailed, context-rich prompts)
      const thenText = (parsedSpec.then || []).join(' ').trim();
      const propertiesText = (parsedSpec.properties || []).join(' ').trim();
      let prompt = thenText || propertiesText || 'Evaluate this page';
      
      // Enhance prompt with context (game state, rendered code, etc.)
      // Use safe JSON stringify to handle circular references
      // Note: JSON.stringify may detect circular references before replacer runs,
      // so we catch the error and return a safe message
      const safeStringify = (obj) => {
        if (obj === null || typeof obj !== 'object') {
          return JSON.stringify(obj, null, 2);
        }
        const seen = new WeakSet();
        // Add root object to seen set first
        seen.add(obj);
        const replacer = (key, value) => {
          if (key && typeof value === 'object' && value !== null) {
            // Check for circular reference
            if (seen.has(value)) {
              return '[Circular Reference]';
            }
            seen.add(value);
          }
          return value;
        };
        try {
          return JSON.stringify(obj, replacer, 2);
        } catch (e) {
          // Fallback: if JSON.stringify still fails (e.g., very deep circular refs),
          // return a safe error message
          return `[Error serializing: ${e.message.substring(0, 100)}]`;
        }
      };
      
      if (options.gameState) {
        prompt += `\n\nCURRENT GAME STATE:\n${safeStringify(options.gameState)}`;
      }
      if (options.renderedCode) {
        prompt += `\n\nRENDERED CODE:\n${safeStringify(options.renderedCode)}`;
      }
      if (options.state) {
        prompt += `\n\nCURRENT STATE:\n${safeStringify(options.state)}`;
      }
      
      // Dual-view validation: screenshot (rendered visuals) + HTML/CSS (source code)
      // This enables validation against both "source of truth" (code) and "rendered output" (visuals)
      const useMultiModal = options.captureCode !== false; // Default true
      
      // Build context with research enhancements support
      const context = {
        testType: 'natural-language-spec',
        spec: parsedSpec,
        gameState: options.gameState,
        renderedCode: options.renderedCode,
        useMultiModal: useMultiModal,
        // Research features integration
        enableUncertaintyReduction: options.enableUncertaintyReduction,
        enableHallucinationCheck: options.enableHallucinationCheck,
        adaptiveSelfConsistency: options.adaptiveSelfConsistency,
        enableBiasMitigation: options.enableBiasMitigation,
        useExplicitRubric: options.useExplicitRubric,
        ...options.context // Allow per-test context overrides
      };
    
      calls.push({
        interface: 'validateScreenshot',
        args: {
          imagePath: screenshotPath,
          prompt: prompt,
          context: context
        }
      });
    } else {
      // Unknown interface - log warning but don't crash
      warn(`[NaturalLanguageSpecs] Unknown interface detected: ${primaryInterface}, skipping`);
    }
  }
  
  // If no calls were generated (all interfaces were unknown), default to validateScreenshot
  if (calls.length === 0) {
    warn('[NaturalLanguageSpecs] No valid interfaces detected, defaulting to validateScreenshot');
    
    // Build prompt from available content (empty arrays are truthy, so check length)
    const thenText = parsedSpec.then.length > 0 ? parsedSpec.then.join(' ').trim() : '';
    const propertiesText = parsedSpec.properties.length > 0 ? parsedSpec.properties.join(' ').trim() : '';
    const prompt = thenText || propertiesText || 'Evaluate this page';
    
    calls.push({
      interface: 'validateScreenshot',
      args: {
        imagePath: screenshotPath,
        prompt: prompt,
        context: {
          testType: 'natural-language-spec',
          spec: parsedSpec,
          useMultiModal: options.captureCode !== false
        }
      }
    });
  }
  
  return calls;
}

/**
 * Execute natural language spec
 * 
 * Enhanced API: Supports both simple string spec and structured spec object.
 * Auto-extracts context from spec text (URLs, viewports, devices, etc.).
 * 
 * @param {import('playwright').Page} page - Playwright page object
 * @param {string | Object} spec - Natural language spec (string) or structured spec object
 * @param {Object} [options] - Execution options (merged with extracted context)
 * @returns {Promise<Object>} Test results
 * 
 * @example
 * // Simple string spec (backward compatible)
 * await executeSpec(page, 'Given I visit example.com...', { url: 'https://example.com' });
 * 
 * @example
 * // Structured spec object (new)
 * await executeSpec(page, {
 *   spec: 'Given I visit example.com...',
 *   context: { viewport: { width: 1280, height: 720 } },
 *   options: { captureTemporal: true }
 * });
 */
export async function executeSpec(page, spec, options = {}) {
  const specConfig = getSpecConfig();
  
  // Support both string spec and structured spec object
  let specText;
  let structuredOptions = {};
  let validateBeforeExecute = options.validate !== undefined 
    ? options.validate 
    : specConfig.validateBeforeExecute;
  
  if (typeof spec === 'string') {
    // Backward compatible: simple string spec
    specText = spec;
    structuredOptions = options;
  } else if (spec && typeof spec === 'object') {
    // New: structured spec object
    specText = spec.spec || spec.text || '';
    validateBeforeExecute = spec.validate !== false && options.validate !== false;
    structuredOptions = {
      ...spec.context,
      ...spec.options,
      ...options // Options parameter can override
    };
  } else {
    throw new Error('executeSpec: spec must be a string or object with spec/text property');
  }
  
  // Validate spec structure (optional, can be disabled)
  if (validateBeforeExecute) {
    const validation = validateSpec(specText);
    if (!validation.valid) {
      const errorMsg = `Spec validation failed:\n${validation.errors.join('\n')}\n\nSuggestions:\n${validation.suggestions.join('\n')}`;
      if (specConfig.strictValidation) {
        throw new Error(errorMsg);
      }
      warn('[NaturalLanguageSpecs]', errorMsg);
      // Don't throw - just warn, allow execution to continue (unless strict)
    } else if (validation.warnings.length > 0 || validation.suggestions.length > 0) {
      log('[NaturalLanguageSpecs] Validation warnings:', validation.warnings);
      if (validation.suggestions.length > 0) {
        log('[NaturalLanguageSpecs] Suggestions:', validation.suggestions);
      }
    }
  }
  
  log('[NaturalLanguageSpecs] Parsing spec:', specText.substring(0, 100));
  
  // Parse spec (auto-extracts context from spec text)
  const parsedSpec = await parseSpec(specText);
  
  log('[NaturalLanguageSpecs] Parsed spec:', {
    type: parsedSpec.type,
    interfaces: parsedSpec.interfaces,
    keywords: parsedSpec.keywords,
    extractedContext: parsedSpec.context
  });
  
  // Map to interfaces (merged context: extracted from spec + provided options)
  const calls = await mapToInterfaces(parsedSpec, {
    page: page,
    url: structuredOptions.url,
    screenshotPath: structuredOptions.screenshotPath,
    options: structuredOptions
  });
  
  // Execute interface calls
  const results = [];
  
  for (const call of calls) {
    try {
      let result;
      
      switch (call.interface) {
        case 'validateAccessibilitySmart':
          // validateAccessibilitySmart(options) - page is in options
          result = await validateAccessibilitySmart(call.args);
          break;
        case 'testGameplay':
          // testGameplay(page, options) - page is separate, not in options
          result = await testGameplay(call.page || page, call.args);
          break;
        case 'validateStateSmart':
          // validateStateSmart(options) - page is in options
          result = await validateStateSmart(call.args);
          break;
        case 'testBrowserExperience':
          // testBrowserExperience(page, options) - page is separate, not in options
          result = await testBrowserExperience(call.page || page, call.args);
          break;
        case 'validateScreenshot':
          // validateScreenshot(imagePath, prompt, context)
          result = await validateScreenshot(
            call.args.imagePath,
            call.args.prompt,
            call.args.context
          );
          break;
        default:
          warn(`[NaturalLanguageSpecs] Unknown interface: ${call.interface}`);
          continue;
      }
      
      results.push({
        interface: call.interface,
        result: result,
        success: result?.score !== null && result?.score !== undefined
      });
    } catch (error) {
      warn(`[NaturalLanguageSpecs] Error executing ${call.interface}:`, error.message);
      results.push({
        interface: call.interface,
        error: error.message,
        success: false
      });
    }
  }
  
  // Enhanced result with extracted context info
  return {
    spec: parsedSpec,
    extractedContext: parsedSpec.context, // Show what was auto-extracted
    results: results,
    success: results.every(r => r.success),
    summary: {
      totalCalls: results.length,
      successfulCalls: results.filter(r => r.success).length,
      failedCalls: results.filter(r => !r.success).length
    },
    // Include merged context for debugging
    mergedContext: calls.length > 0 ? calls[0].args : {}
  };
}

/**
 * Validate spec structure before execution
 * 
 * Provides early feedback on spec issues.
 * 
 * @param {string} spec - Natural language spec
 * @returns {Object} Validation result with errors and suggestions
 */
export function validateSpec(spec) {
  const errors = [];
  const warnings = [];
  const suggestions = [];
  
  if (!spec || typeof spec !== 'string') {
    errors.push('Spec must be a non-empty string');
    return { valid: false, errors, warnings, suggestions };
  }
  
  const lines = spec.split('\n').map(l => l.trim()).filter(l => l.length > 0);
  
  // Check for basic structure
  const hasGiven = lines.some(l => l.toLowerCase().startsWith('given'));
  const hasWhen = lines.some(l => l.toLowerCase().startsWith('when'));
  const hasThen = lines.some(l => l.toLowerCase().startsWith('then'));
  
  if (!hasGiven && !hasWhen && !hasThen) {
    warnings.push('Spec does not follow Given/When/Then structure - may be harder to parse');
    suggestions.push('Consider using: Given [precondition], When [action], Then [expected result]');
  }
  
  // Check for common mistakes
  if (spec.toLowerCase().includes('i should') && !spec.toLowerCase().includes('then')) {
    suggestions.push("Consider using 'Then' instead of 'I should' for better parsing");
  }
  
  // Check for context extraction opportunities
  const hasUrl = /(?:visit|open|navigate to|goto)\s+[^\s]+/i.test(spec);
  if (!hasUrl && !spec.includes('http')) {
    warnings.push('No URL detected in spec - may need to provide url in options');
  }
  
  // Check for interface keywords
  const hasKeywords = /(?:game|accessible|state|screenshot|experience)/i.test(spec);
  if (!hasKeywords) {
    warnings.push('No clear validation keywords detected - may default to validateScreenshot');
    suggestions.push('Consider including keywords like: game, accessible, state, screenshot, experience');
  }
  
  return {
    valid: errors.length === 0,
    errors,
    warnings,
    suggestions
  };
}

/**
 * Generate property-based tests from natural language properties
 * 
 * NOTE: This is a framework/structure for property tests, not a full
 * implementation of fast-check or Hypothesis. The actual property
 * testing logic would need to be implemented separately.
 * 
 * The structure returned provides a foundation for property-based testing
 * but does not include generators or the full property testing infrastructure
 * from libraries like fast-check or Hypothesis.
 * 
 * @param {Array<string>} properties - Natural language property descriptions
 * @param {Object} options - Generation options
 * @param {string} [options.generator='fast-check'] - Generator library name (not implemented)
 * @param {number} [options.numRuns=100] - Number of test runs (not implemented)
 * @returns {Promise<Object>} Property test structure with placeholder run() method
 */
export async function generatePropertyTests(properties, options = {}) {
  const { generator = 'fast-check', numRuns = 100 } = options;
  
  log('[NaturalLanguageSpecs] Generating property tests:', properties.length);
  
  const propertyTests = [];
  
  for (const property of properties) {
    // Parse property description
    const parsed = {
      description: property,
      type: 'invariant', // 'invariant', 'postcondition', 'precondition'
      check: null
    };
    
    // Extract property type and check
    const lower = property.toLowerCase();
    
    if (lower.includes('should always') || lower.includes('for all')) {
      parsed.type = 'invariant';
    } else if (lower.includes('should be') || lower.includes('must be')) {
      parsed.type = 'postcondition';
    }
    
    // Generate check function (simplified - would use LLM in production)
    parsed.check = generatePropertyCheck(property);
    
    propertyTests.push(parsed);
  }
  
  return {
    properties: propertyTests,
    generator: generator,
    numRuns: numRuns,
    run: async function() {
      // Execute property tests
      const results = [];
      
      for (const propertyTest of propertyTests) {
        try {
          // In production, would use fast-check or similar
          // For now, return structure
          results.push({
            property: propertyTest.description,
            type: propertyTest.type,
            status: 'pending' // Would be 'passed', 'failed', 'pending'
          });
        } catch (error) {
          results.push({
            property: propertyTest.description,
            type: propertyTest.type,
            status: 'error',
            error: error.message
          });
        }
      }
      
      return results;
    }
  };
}

/**
 * Generate property check function from natural language
 * 
 * @param {string} property - Natural language property description
 * @returns {Function} Property check function
 */
function generatePropertyCheck(property) {
  // Simplified - would use LLM to generate actual check function
  const lower = property.toLowerCase();
  
  if (lower.includes('score') && lower.includes('between 0 and 10')) {
    return (result) => {
      return result.score >= 0 && result.score <= 10;
    };
  } else if (lower.includes('issues') && lower.includes('array')) {
    return (result) => {
      return Array.isArray(result.issues);
    };
  } else if (lower.includes('non-negative')) {
    return (value) => {
      return value >= 0;
    };
  }
  
  // Default: always pass (would use LLM to generate actual check)
  return () => true;
}

/**
 * Test behavior described in natural language
 * 
 * @param {import('playwright').Page} page - Playwright page object
 * @param {string} behavior - Natural language behavior description
 * @param {Object} options - Test options
 * @returns {Promise<Object>} Behavior test results
 */
export async function testBehavior(page, behavior, options = {}) {
  // Parse behavior as spec
  const spec = behavior;
  
  // Execute as spec
  return await executeSpec(page, spec, options);
}

