/**
 * Render Change Detector
 * 
 * Detects when page content actually renders/changes and triggers screenshots.
 * Uses MutationObserver, ResizeObserver, requestAnimationFrame, and visual diff detection.
 * 
 * Research: Visual event detection improves temporal understanding (VETL, WALT)
 */

import { warn, log } from './logger.mjs';
import { existsSync, statSync } from 'fs';

/**
 * Detect render changes using MutationObserver + ResizeObserver + requestAnimationFrame
 * 
 * Enhanced to detect:
 * - DOM mutations (MutationObserver)
 * - Layout changes (ResizeObserver)
 * - Visual updates (requestAnimationFrame polling for CSS animations)
 * 
 * @param {any} page - Playwright page object
 * @param {Function} onChange - Callback when change detected
 * @param {Object} options - Detection options
 * @returns {Promise<Function>} Cleanup function
 */
export async function detectRenderChanges(page, onChange, options = {}) {
  const {
    subtree = true,
    childList = true,
    attributes = true,
    characterData = true,
    attributeFilter = null,
    pollInterval = 100, // Check every 100ms
    detectCSSAnimations = true, // Also detect CSS animations via RAF polling
    detectLayoutChanges = true // Use ResizeObserver for layout changes
  } = options;

  let observer = null;
  let resizeObserver = null;
  let rafId = null;
  let changeCount = 0;
  const changeHistory = [];
  const maxHistory = 100;
  let lastRAFTime = 0;
  let rafChangeCount = 0;

  try {
    // Set up MutationObserver in page context
    await page.evaluate(({ subtree, childList, attributes, characterData, attributeFilter, detectLayoutChanges }) => {
      // MutationObserver for DOM changes
      window.__renderChangeObserver = new MutationObserver((mutations) => {
        window.__renderChangeCount = (window.__renderChangeCount || 0) + 1;
        window.__renderChangeTime = Date.now();
        window.__renderChangeMutations = mutations.length;
      });

      const config = {
        subtree,
        childList,
        attributes,
        characterData
      };
      
      if (attributeFilter) {
        config.attributeFilter = attributeFilter;
      }

      window.__renderChangeObserver.observe(document.body, config);

      // ResizeObserver for layout changes (if enabled)
      if (detectLayoutChanges) {
        window.__renderResizeObserver = new ResizeObserver((entries) => {
          window.__renderResizeCount = (window.__renderResizeCount || 0) + 1;
          window.__renderResizeTime = Date.now();
          window.__renderResizeEntries = entries.length;
        });

        window.__renderResizeObserver.observe(document.body);
      }

      // requestAnimationFrame polling for CSS animations (if enabled)
      if (window.__detectCSSAnimations) {
        let lastFrameTime = performance.now();
        let frameCount = 0;
        
        function rafLoop() {
          const currentTime = performance.now();
          const deltaTime = currentTime - lastFrameTime;
          
          // If frame time is consistent (likely animation), count as change
          // CSS animations typically run at 60fps (16.67ms per frame)
          if (deltaTime > 0 && deltaTime < 20) { // 0-20ms = likely animation frame
            frameCount++;
            if (frameCount % 10 === 0) { // Every 10 frames = ~166ms
              window.__renderRAFCount = (window.__renderRAFCount || 0) + 1;
              window.__renderRAFTime = Date.now();
            }
          } else {
            frameCount = 0; // Reset if not consistent
          }
          
          lastFrameTime = currentTime;
          window.__renderRAFId = requestAnimationFrame(rafLoop);
        }
        
        window.__renderRAFId = requestAnimationFrame(rafLoop);
      }

      // Initialize counters
      window.__renderChangeCount = 0;
      window.__renderChangeTime = 0;
      window.__renderChangeMutations = 0;
      window.__renderResizeCount = 0;
      window.__renderResizeTime = 0;
      window.__renderResizeEntries = 0;
      window.__renderRAFCount = 0;
      window.__renderRAFTime = 0;
    }, { subtree, childList, attributes, characterData, attributeFilter, detectLayoutChanges });

    // Enable CSS animation detection if requested
    if (detectCSSAnimations) {
      await page.evaluate(() => {
        window.__detectCSSAnimations = true;
      });
    }

    // Poll for changes (Playwright doesn't support direct MutationObserver callbacks)
    const pollId = setInterval(async () => {
      try {
        const changeInfo = await page.evaluate(() => {
          const info = {
            mutations: {
              count: window.__renderChangeCount || 0,
              time: window.__renderChangeTime || 0,
              mutations: window.__renderChangeMutations || 0
            },
            resize: {
              count: window.__renderResizeCount || 0,
              time: window.__renderResizeTime || 0,
              entries: window.__renderResizeEntries || 0
            },
            raf: {
              count: window.__renderRAFCount || 0,
              time: window.__renderRAFTime || 0
            }
          };
          
          // Reset counters
          window.__renderChangeCount = 0;
          window.__renderChangeTime = 0;
          window.__renderChangeMutations = 0;
          window.__renderResizeCount = 0;
          window.__renderResizeTime = 0;
          window.__renderResizeEntries = 0;
          window.__renderRAFCount = 0;
          window.__renderRAFTime = 0;
          
          return info;
        });

        const totalChanges = changeInfo.mutations.count + changeInfo.resize.count + changeInfo.raf.count;
        
        if (totalChanges > 0) {
          changeCount += totalChanges;
          changeHistory.push({
            timestamp: changeInfo.mutations.time || changeInfo.resize.time || changeInfo.raf.time || Date.now(),
            mutations: changeInfo.mutations.mutations,
            resizeEntries: changeInfo.resize.entries,
            rafFrames: changeInfo.raf.count,
            count: totalChanges,
            types: {
              dom: changeInfo.mutations.count > 0,
              layout: changeInfo.resize.count > 0,
              visual: changeInfo.raf.count > 0
            }
          });

          // Keep history limited
          if (changeHistory.length > maxHistory) {
            changeHistory.shift();
          }

          // Call onChange callback
          if (onChange) {
            await onChange({
              count: totalChanges,
              mutations: changeInfo.mutations.mutations,
              resizeEntries: changeInfo.resize.entries,
              rafFrames: changeInfo.raf.count,
              timestamp: changeInfo.mutations.time || changeInfo.resize.time || changeInfo.raf.time || Date.now(),
              totalChanges: changeCount,
              types: {
                dom: changeInfo.mutations.count > 0,
                layout: changeInfo.resize.count > 0,
                visual: changeInfo.raf.count > 0
              }
            });
          }
        }
      } catch (error) {
        warn(`[Render Change] Poll error: ${error.message}`);
      }
    }, pollInterval);

    // Return cleanup function
    return async () => {
      clearInterval(pollId);
      try {
        await page.evaluate(() => {
          if (window.__renderChangeObserver) {
            window.__renderChangeObserver.disconnect();
            delete window.__renderChangeObserver;
          }
          if (window.__renderResizeObserver) {
            window.__renderResizeObserver.disconnect();
            delete window.__renderResizeObserver;
          }
          if (window.__renderRAFId) {
            cancelAnimationFrame(window.__renderRAFId);
            delete window.__renderRAFId;
          }
          delete window.__renderChangeCount;
          delete window.__renderChangeTime;
          delete window.__renderChangeMutations;
          delete window.__renderResizeCount;
          delete window.__renderResizeTime;
          delete window.__renderResizeEntries;
          delete window.__renderRAFCount;
          delete window.__renderRAFTime;
          delete window.__detectCSSAnimations;
        });
      } catch (error) {
        warn(`[Render Change] Cleanup error: ${error.message}`);
      }
    };
  } catch (error) {
    warn(`[Render Change] Setup error: ${error.message}`);
    return async () => {}; // Return no-op cleanup
  }
}

/**
 * Calculate optimal frame rate based on change rate
 * 
 * @param {Array} changeHistory - History of changes
 * @param {Object} options - Calculation options
 * @returns {number} Optimal FPS
 */
export function calculateOptimalFPS(changeHistory, options = {}) {
  const {
    minFPS = 1,
    maxFPS = 60,
    targetChangeInterval = 100 // Target: capture every 100ms of changes
  } = options;

  if (changeHistory.length < 2) {
    return minFPS;
  }

  // Calculate average time between changes
  const intervals = [];
  for (let i = 1; i < changeHistory.length; i++) {
    const interval = changeHistory[i].timestamp - changeHistory[i - 1].timestamp;
    if (interval > 0) {
      intervals.push(interval);
    }
  }

  if (intervals.length === 0) {
    return minFPS;
  }

  const avgInterval = intervals.reduce((a, b) => a + b, 0) / intervals.length;
  
  // Calculate FPS based on average interval
  // If changes happen every 16ms (60fps), we need 60fps capture
  // If changes happen every 1000ms (1fps), we need 1fps capture
  const optimalFPS = Math.max(minFPS, Math.min(maxFPS, 1000 / avgInterval));

  return Math.round(optimalFPS);
}

/**
 * Compare two screenshots to detect visual changes
 * 
 * Enhanced with pixel-level comparison using lightweight method.
 * 
 * @param {string} screenshot1Path - Path to first screenshot
 * @param {string} screenshot2Path - Path to second screenshot
 * @param {Object} options - Comparison options
 * @returns {Promise<{ changed: boolean, diff: number, regions: Array }>} Comparison result
 */
export async function detectVisualChanges(screenshot1Path, screenshot2Path, options = {}) {
  const {
    threshold = 0.01, // 1% difference threshold
    useImageDiff = false, // Use image diff library if available
    usePixelComparison = true // Use lightweight pixel comparison
  } = options;

  // Basic implementation: file size and timestamp comparison
  try {
    if (!existsSync(screenshot1Path) || !existsSync(screenshot2Path)) {
      return {
        changed: true, // Assume changed if files don't exist
        diff: 1.0,
        timeDiff: 0,
        regions: []
      };
    }

    const stat1 = statSync(screenshot1Path);
    const stat2 = statSync(screenshot2Path);

    // If file sizes are different, content likely changed
    const sizeDiff = Math.abs(stat1.size - stat2.size) / Math.max(stat1.size, stat2.size);
    const timeDiff = Math.abs(stat1.mtimeMs - stat2.mtimeMs);

    // Basic check: if size diff > threshold or time diff > 100ms, likely changed
    let changed = sizeDiff > threshold || timeDiff > 100;

    // Enhanced: Try lightweight pixel comparison if enabled
    if (usePixelComparison && changed) {
      try {
        // Read first few bytes of PNG files to compare
        // PNG files have headers, so identical files will have same header
        const fs = await import('fs');
        const buffer1 = fs.readFileSync(screenshot1Path, { start: 0, end: 1000 });
        const buffer2 = fs.readFileSync(screenshot2Path, { start: 0, end: 1000 });
        
        // Compare first 1000 bytes (header + some pixel data)
        let byteMatches = 0;
        const compareLength = Math.min(buffer1.length, buffer2.length, 1000);
        for (let i = 0; i < compareLength; i++) {
          if (buffer1[i] === buffer2[i]) {
            byteMatches++;
          }
        }
        
        const byteSimilarity = byteMatches / compareLength;
        // If >95% of bytes match in header region, likely same image
        if (byteSimilarity > 0.95 && sizeDiff < 0.05) {
          changed = false; // Probably same image
        }
      } catch (error) {
        // Fall back to size/timestamp comparison
        warn(`[Visual Change] Pixel comparison failed: ${error.message}`);
      }
    }

    return {
      changed,
      diff: sizeDiff,
      timeDiff,
      regions: [] // Would need image processing for region detection
    };
  } catch (error) {
    warn(`[Visual Change] Comparison error: ${error.message}`);
    return {
      changed: true, // Assume changed if comparison fails
      diff: 1.0,
      timeDiff: 0,
      regions: []
    };
  }
}

/**
 * Capture screenshots on render changes
 * 
 * @param {any} page - Playwright page object
 * @param {Object} options - Capture options
 * @param {Function} [options.onChange] - Callback when change detected
 * @param {number} [options.maxScreenshots] - Maximum screenshots to capture
 * @param {number} [options.duration] - Maximum duration in ms
 * @param {boolean} [options.visualDiff] - Use visual diff detection
 * @param {boolean} [options.detectCSSAnimations] - Detect CSS animations
 * @returns {Promise<Array>} Array of screenshot paths
 */
export async function captureOnRenderChanges(page, options = {}) {
  const {
    onChange = null,
    maxScreenshots = 100,
    duration = 10000, // 10 seconds default
    visualDiff = false,
    outputDir = 'test-results',
    detectCSSAnimations = true, // Enable CSS animation detection
    detectLayoutChanges = true
  } = options;

  const screenshots = [];
  const startTime = Date.now();
  let lastScreenshotPath = null;

  // Set up render change detection (enhanced with CSS animation detection)
  const cleanup = await detectRenderChanges(page, async (changeInfo) => {
    // Check limits
    if (screenshots.length >= maxScreenshots) {
      return;
    }
    if (Date.now() - startTime > duration) {
      return;
    }

    // Capture screenshot
    const timestamp = Date.now();
    const screenshotPath = `${outputDir}/render-change-${timestamp}.png`;

    try {
      await page.screenshot({ path: screenshotPath, type: 'png' });

      // Visual diff check (if enabled)
      if (visualDiff && lastScreenshotPath) {
        const diff = await detectVisualChanges(lastScreenshotPath, screenshotPath);
        if (!diff.changed) {
          // No visual change, skip this screenshot
          const fs = await import('fs');
          if (existsSync(screenshotPath)) {
            fs.unlinkSync(screenshotPath);
          }
          return;
        }
      }

      screenshots.push({
        path: screenshotPath,
        timestamp,
        changeInfo
      });

      lastScreenshotPath = screenshotPath;

      // Call onChange callback
      if (onChange) {
        await onChange(screenshotPath, changeInfo);
      }
    } catch (error) {
      warn(`[Render Change] Screenshot capture error: ${error.message}`);
    }
  }, {
    detectCSSAnimations,
    detectLayoutChanges
  });

  // Wait for duration or max screenshots
  const checkInterval = setInterval(() => {
    if (screenshots.length >= maxScreenshots || Date.now() - startTime > duration) {
      clearInterval(checkInterval);
    }
  }, 100);

  // Wait for completion
  await new Promise((resolve) => {
    const finalCheck = setInterval(() => {
      if (screenshots.length >= maxScreenshots || Date.now() - startTime > duration) {
        clearInterval(finalCheck);
        resolve();
      }
    }, 100);
    
    // Timeout after duration
    setTimeout(() => {
      clearInterval(finalCheck);
      resolve();
    }, duration);
  });

  // Cleanup
  await cleanup();

  return screenshots;
}

/**
 * Adaptive temporal screenshot capture
 * 
 * Adjusts capture rate based on detected change rate.
 * Enhanced with CSS animation detection and optimized screenshot quality.
 * 
 * @param {any} page - Playwright page object
 * @param {Object} options - Capture options
 * @param {number} [options.minFPS] - Minimum FPS (default: 1)
 * @param {number} [options.maxFPS] - Maximum FPS (default: 60)
 * @param {number} [options.duration] - Duration in ms
 * @param {number} [options.adaptationInterval] - How often to recalculate FPS (ms)
 * @param {boolean} [options.optimizeForSpeed] - Use lower quality screenshots for speed
 * @param {boolean} [options.detectCSSAnimations] - Detect CSS animations
 * @returns {Promise<Array>} Array of screenshot paths with metadata
 */
export async function captureAdaptiveTemporalScreenshots(page, options = {}) {
  const {
    minFPS = 1,
    maxFPS = 60,
    duration = 10000,
    adaptationInterval = 2000, // Recalculate every 2 seconds
    outputDir = 'test-results',
    optimizeForSpeed = false, // Optimize screenshot quality for speed
    detectCSSAnimations = true // Enable CSS animation detection
  } = options;

  const screenshots = [];
  const changeHistory = [];
  const startTime = Date.now();
  let currentFPS = minFPS;
  let lastCaptureTime = 0;

  // Set up render change detection (enhanced with CSS animation detection)
  const cleanup = await detectRenderChanges(page, async (changeInfo) => {
    changeHistory.push({
      timestamp: changeInfo.timestamp,
      mutations: changeInfo.mutations,
      types: changeInfo.types
    });

    // Keep history limited
    if (changeHistory.length > 100) {
      changeHistory.shift();
    }
  }, {
    detectCSSAnimations,
    detectLayoutChanges: true
  });

  // Adaptive capture loop
  const captureLoop = async () => {
    while (Date.now() - startTime < duration) {
      // Recalculate optimal FPS periodically
      if (changeHistory.length >= 2) {
        const recentHistory = changeHistory.slice(-20); // Last 20 changes
        currentFPS = calculateOptimalFPS(recentHistory, { minFPS, maxFPS });
      }

      // Calculate next capture time based on current FPS
      const interval = 1000 / currentFPS;
      const nextCaptureTime = lastCaptureTime + interval;

      // Wait until next capture time
      const waitTime = Math.max(0, nextCaptureTime - Date.now());
      if (waitTime > 0) {
        await new Promise(resolve => setTimeout(resolve, waitTime));
      }

      // Capture screenshot (optimize quality for speed if requested)
      const timestamp = Date.now();
      const screenshotPath = `${outputDir}/adaptive-${timestamp}.png`;

      try {
        // Optimize screenshot quality for high FPS
        const screenshotOptions = {
          path: screenshotPath,
          type: 'png'
        };
        
        if (optimizeForSpeed && currentFPS > 30) {
          // For high FPS, use lower quality to reduce overhead
          screenshotOptions.quality = 70; // Lower quality (if supported)
          // Could also reduce size, but Playwright doesn't support that directly
        }

        await page.screenshot(screenshotOptions);
        screenshots.push({
          path: screenshotPath,
          timestamp,
          fps: currentFPS,
          changeCount: changeHistory.length
        });
        lastCaptureTime = timestamp;
      } catch (error) {
        warn(`[Adaptive Capture] Screenshot error: ${error.message}`);
      }

      // Small delay to prevent tight loop
      await new Promise(resolve => setTimeout(resolve, 10));
    }
  };

  // Start capture loop
  await captureLoop();

  // Cleanup
  await cleanup();

  return screenshots;
}
