/**
 * Programmatic Accessibility Validator
 * 
 * Fast, deterministic accessibility checks using DOM inspection.
 * Use this when you have Playwright page access and need fast feedback (<100ms).
 * 
 * For semantic evaluation (design principles, context-aware checks), use AccessibilityValidator (VLLM-based).
 * 
 * Based on WCAG 2.1 contrast ratio algorithm: https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
 */

import { ValidationError } from '../errors.mjs';
import { assertString, assertNumber } from '../type-guards.mjs';

/**
 * Parse RGB color string to [r, g, b] array
 * Supports rgb(r, g, b), rgba(r, g, b, a), and hex (#rrggbb or #rgb) formats
 * 
 * @param {string} rgb - Color string
 * @returns {number[]} [r, g, b] array (0-255)
 */
function parseRgb(rgb) {
  if (!rgb || typeof rgb !== 'string') {
    return [255, 255, 255]; // Default to white
  }
  
  // Handle rgb(r, g, b) or rgba(r, g, b, a) format
  const match = rgb.match(/\d+/g);
  if (match && match.length >= 3) {
    return match.slice(0, 3).map(Number);
  }
  
  // Handle hex format (#rrggbb or #rgb)
  if (rgb.startsWith('#')) {
    const hex = rgb.slice(1);
    if (hex.length === 3) {
      return hex.split('').map(c => parseInt(c + c, 16));
    }
    if (hex.length === 6) {
      return [
        parseInt(hex.slice(0, 2), 16),
        parseInt(hex.slice(2, 4), 16),
        parseInt(hex.slice(4, 6), 16)
      ];
    }
  }
  
  return [255, 255, 255]; // Default to white
}

/**
 * Calculate relative luminance (WCAG algorithm)
 * 
 * @param {number[]} rgb - [r, g, b] array (0-255)
 * @returns {number} Relative luminance (0-1)
 */
function getLuminance(rgb) {
  const [r, g, b] = rgb.map(val => {
    val = val / 255;
    return val <= 0.03928 ? val / 12.92 : Math.pow((val + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * Calculate contrast ratio between two colors (WCAG algorithm)
 * 
 * @param {string} color1 - First color (rgb, rgba, or hex)
 * @param {string} color2 - Second color (rgb, rgba, or hex)
 * @returns {number} Contrast ratio (1.0 to 21.0+)
 */
export function getContrastRatio(color1, color2) {
  const rgb1 = parseRgb(color1);
  const rgb2 = parseRgb(color2);
  
  const l1 = getLuminance(rgb1);
  const l2 = getLuminance(rgb2);
  
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Check contrast ratio for an element
 * 
 * @param {any} page - Playwright page object
 * @param {string} selector - CSS selector for element
 * @param {number} minRatio - Minimum required contrast ratio (default: 4.5 for WCAG-AA)
 * @returns {Promise<{ratio: number, passes: boolean, foreground: string, background: string, foregroundRgb?: number[], backgroundRgb?: number[], error?: string}>}
 * @throws {ValidationError} If page is not a valid Playwright Page object
 */
export async function checkElementContrast(page, selector, minRatio = 4.5) {
  // Validate inputs
  if (!page || typeof page.evaluate !== 'function') {
    throw new ValidationError('checkElementContrast requires a Playwright Page object', {
      received: typeof page,
      hasEvaluate: typeof page?.evaluate === 'function'
    });
  }
  
  assertString(selector, 'selector');
  assertNumber(minRatio, 'minRatio');
  
  if (minRatio < 1 || minRatio > 21) {
    throw new ValidationError('minRatio must be between 1 and 21', { received: minRatio });
  }
  
  const result = await page.evaluate(({ sel, min }) => {
    const element = document.querySelector(sel);
    if (!element) {
      return { error: 'Element not found', selector: sel };
    }
    
    const style = window.getComputedStyle(element);
    const color = style.color;
    const bgColor = style.backgroundColor;
    
    // Get effective background color from parent if element has transparent background
    let effectiveBg = bgColor;
    if (bgColor === 'rgba(0, 0, 0, 0)' || bgColor === 'transparent') {
      let parent = element.parentElement;
      while (parent && parent !== document.body) {
        const parentStyle = window.getComputedStyle(parent);
        const parentBg = parentStyle.backgroundColor;
        if (parentBg !== 'rgba(0, 0, 0, 0)' && parentBg !== 'transparent') {
          effectiveBg = parentBg;
          break;
        }
        parent = parent.parentElement;
      }
      
      // If still transparent, check document.body
      if ((effectiveBg === 'rgba(0, 0, 0, 0)' || effectiveBg === 'transparent') && document.body) {
        const bodyStyle = window.getComputedStyle(document.body);
        const bodyBg = bodyStyle.backgroundColor;
        if (bodyBg !== 'rgba(0, 0, 0, 0)' && bodyBg !== 'transparent') {
          effectiveBg = bodyBg;
        }
      }
    }
    
    // Parse RGB values
    const parseRgb = (rgb) => {
      if (!rgb || typeof rgb !== 'string') return [255, 255, 255];
      const match = rgb.match(/\d+/g);
      return match && match.length >= 3 ? match.slice(0, 3).map(Number) : [255, 255, 255];
    };
    
    const fg = parseRgb(color);
    const bg = parseRgb(effectiveBg);
    
    // Calculate relative luminance (WCAG algorithm)
    const getLuminance = (rgb) => {
      const [r, g, b] = rgb.map(val => {
        val = val / 255;
        return val <= 0.03928 ? val / 12.92 : Math.pow((val + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    
    const l1 = getLuminance(fg);
    const l2 = getLuminance(bg);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    
    return {
      ratio,
      passes: ratio >= min,
      foreground: color,
      background: effectiveBg,
      foregroundRgb: fg,
      backgroundRgb: bg
    };
  }, { sel: selector, min: minRatio });
  
  return result;
}

/**
 * Check contrast for all text elements on page
 * 
 * @param {any} page - Playwright page object
 * @param {number} minRatio - Minimum required contrast ratio (default: 4.5 for WCAG-AA)
 * @returns {Promise<{total: number, passing: number, failing: number, violations: Array<{element: string, ratio: string, required: number, foreground: string, background: string}>, elements?: Array}>}
 * @throws {ValidationError} If page is not a valid Playwright Page object
 */
export async function checkAllTextContrast(page, minRatio = 4.5) {
  // Validate inputs
  if (!page || typeof page.evaluate !== 'function') {
    throw new ValidationError('checkAllTextContrast requires a Playwright Page object', {
      received: typeof page,
      hasEvaluate: typeof page?.evaluate === 'function'
    });
  }
  
  assertNumber(minRatio, 'minRatio');
  
  if (minRatio < 1 || minRatio > 21) {
    throw new ValidationError('minRatio must be between 1 and 21', { received: minRatio });
  }
  
  const result = await page.evaluate((min) => {
    const all = document.querySelectorAll('*');
    const textElements = [];
    const violations = [];
    
    const parseRgb = (rgb) => {
      if (!rgb || typeof rgb !== 'string') return [255, 255, 255];
      const match = rgb.match(/\d+/g);
      return match && match.length >= 3 ? match.slice(0, 3).map(Number) : [255, 255, 255];
    };
    
    const getLuminance = (rgb) => {
      const [r, g, b] = rgb.map(val => {
        val = val / 255;
        return val <= 0.03928 ? val / 12.92 : Math.pow((val + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    
    for (const el of all) {
      const style = window.getComputedStyle(el);
      const color = style.color;
      const bgColor = style.backgroundColor;
      
      // Check if element has text content
      if (el.textContent && el.textContent.trim().length > 0 && 
          color && color !== 'rgba(0, 0, 0, 0)' && 
          bgColor && bgColor !== 'rgba(0, 0, 0, 0)') {
        
        // Get effective background (handle transparent)
        let effectiveBg = bgColor;
        if (bgColor === 'rgba(0, 0, 0, 0)' || bgColor === 'transparent') {
          let parent = el.parentElement;
          while (parent && parent !== document.body) {
            const parentStyle = window.getComputedStyle(parent);
            const parentBg = parentStyle.backgroundColor;
            if (parentBg !== 'rgba(0, 0, 0, 0)' && parentBg !== 'transparent') {
              effectiveBg = parentBg;
              break;
            }
            parent = parent.parentElement;
          }
          
          // If still transparent, check document.body
          if ((effectiveBg === 'rgba(0, 0, 0, 0)' || effectiveBg === 'transparent') && document.body) {
            const bodyStyle = window.getComputedStyle(document.body);
            const bodyBg = bodyStyle.backgroundColor;
            if (bodyBg !== 'rgba(0, 0, 0, 0)' && bodyBg !== 'transparent') {
              effectiveBg = bodyBg;
            }
          }
        }
        
        const fg = parseRgb(color);
        const bg = parseRgb(effectiveBg);
        
        const l1 = getLuminance(fg);
        const l2 = getLuminance(bg);
        const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        
        const elementInfo = {
          tag: el.tagName,
          id: el.id,
          className: el.className,
          ratio,
          passes: ratio >= min,
          foreground: color,
          background: effectiveBg
        };
        
        textElements.push(elementInfo);
        
        if (!elementInfo.passes) {
          violations.push({
            element: `${el.tagName}${el.id ? '#' + el.id : ''}${el.className ? '.' + el.className.split(' ')[0] : ''}`,
            ratio: ratio.toFixed(2),
            required: min,
            foreground: color,
            background: effectiveBg
          });
        }
      }
    }
    
    return {
      total: textElements.length,
      passing: textElements.filter(e => e.passes).length,
      failing: textElements.filter(e => !e.passes).length,
      violations: violations,
      elements: textElements.slice(0, 20) // First 20 for debugging
    };
  }, minRatio);
  
  return result;
}

/**
 * Check keyboard navigation accessibility
 * 
 * @param {any} page - Playwright page object
 * @returns {Promise<{keyboardAccessible: boolean, focusableElements: number, violations: Array<{element: string, issue: string}>, focusableSelectors: string[]}>}
 * @throws {ValidationError} If page is not a valid Playwright Page object
 */
export async function checkKeyboardNavigation(page) {
  // Validate inputs
  if (!page || typeof page.evaluate !== 'function') {
    throw new ValidationError('checkKeyboardNavigation requires a Playwright Page object', {
      received: typeof page,
      hasEvaluate: typeof page?.evaluate === 'function'
    });
  }
  
  const result = await page.evaluate(() => {
    const focusableSelectors = [
      'a[href]',
      'button:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])'
    ];
    
    const focusableElements = Array.from(document.querySelectorAll(focusableSelectors.join(', ')));
    const violations = [];
    
    // Check for missing focus indicators
    focusableElements.forEach(el => {
      const style = window.getComputedStyle(el, ':focus');
      // Note: :focus pseudo-class can't be checked directly in evaluate
      // This is a basic check - full focus indicator check would require interaction
    });
    
    return {
      keyboardAccessible: focusableElements.length > 0,
      focusableElements: focusableElements.length,
      violations: violations,
      focusableSelectors: focusableSelectors
    };
  });
  
  return result;
}

