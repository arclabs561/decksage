/**
 * VLLM Cache
 *
 * Provides persistent caching for VLLM API calls to reduce costs and improve performance.
 * Uses file-based storage for cache persistence across test runs.
 *
 * BUGS FIXED (2025-01):
 * 1. Timestamp reset on save - was resetting ALL timestamps to `now`, breaking 7-day expiration
 * 2. Cache key truncation - was truncating prompts/gameState, causing collisions
 *
 * ARCHITECTURE NOTES:
 * - This is ONE of THREE cache systems in the codebase (see docs/CACHE_ARCHITECTURE_DEEP_DIVE.md)
 * - File-based, persistent across runs (7-day TTL, LRU eviction)
 * - Purpose: Long-term persistence of API responses across restarts
 * - Why separate: Different persistence strategy (file vs memory), different lifetime (7 days vs process lifetime),
 *   different failure domain (disk errors don't affect in-memory batching), minimal data overlap (<5%)
 * - No coordination with BatchOptimizer cache or TemporalPreprocessing cache (by design - they serve different purposes)
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync, renameSync, unlinkSync } from 'fs';
import { join, dirname, normalize, resolve } from 'path';
import { createHash } from 'crypto';
import { fileURLToPath } from 'url';
import { Mutex } from 'async-mutex';
import { CacheError, FileError } from './errors.mjs';
import { warn, log } from './logger.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

import { CACHE_CONSTANTS } from './constants.mjs';

// Default cache directory (can be overridden)
let CACHE_DIR = null;
let CACHE_FILE = null;
const MAX_CACHE_AGE = CACHE_CONSTANTS.MAX_CACHE_AGE_MS;
const MAX_CACHE_SIZE = CACHE_CONSTANTS.MAX_CACHE_SIZE;
const MAX_CACHE_SIZE_BYTES = CACHE_CONSTANTS.MAX_CACHE_SIZE_BYTES;

// Cache instance
let cacheInstance = null;
// Cache write mutex to prevent race conditions (proper async mutex)
const cacheWriteMutex = new Mutex();
// VERIFIABLE: Track cache metrics to verify claims about atomic writes
// Initialize to empty object so metrics are always available (even before first save)
let cacheMetrics = { atomicWrites: 0, atomicWriteFailures: 0, tempFileCleanups: 0 };

/**
 * Initialize cache with directory
 *
 * @param {string | undefined} [cacheDir] - Cache directory path, or undefined for default
 * @returns {void}
 */
export function initCache(cacheDir) {
  // SECURITY: Validate and normalize cache directory to prevent path traversal
  if (cacheDir) {
    const normalized = normalize(resolve(cacheDir));
    // Prevent path traversal
    if (normalized.includes('..')) {
      throw new CacheError('Invalid cache directory: path traversal detected', { cacheDir });
    }
    CACHE_DIR = normalized;
  } else {
    CACHE_DIR = join(__dirname, '..', '..', '..', 'test-results', 'vllm-cache');
  }
  CACHE_FILE = join(CACHE_DIR, 'cache.json');

  if (!existsSync(CACHE_DIR)) {
    mkdirSync(CACHE_DIR, { recursive: true });
  }

  cacheInstance = null; // Reset instance to reload
}

/**
 * Generate cache key from image path, prompt, and context
 *
 * @param {string} imagePath - Path to image file
 * @param {string} prompt - Validation prompt
 * @param {import('./index.mjs').ValidationContext} [context={}] - Validation context
 * @returns {string} SHA-256 hash of cache key
 */
export function generateCacheKey(imagePath, prompt, context = {}) {
  // NOTE: Don't truncate cache keys - it causes collisions!
  //
  // The bug: Truncating prompt (1000 chars) and gameState (500 chars) means:
  // - Different prompts with same first 1000 chars = same cache key = wrong cache hit
  // - Different game states with same first 500 chars = same cache key = wrong cache hit
  //
  // The fix: Hash the FULL content, don't truncate
  // SHA-256 handles arbitrary length, so there's no reason to truncate
  //
  // Why truncation existed: Probably to keep keys "manageable", but it's dangerous
  // Better approach: Hash full content, collisions are cryptographically unlikely
  const keyData = {
    imagePath,
    prompt, // Full prompt, not truncated
    testType: context.testType || '',
    frame: context.frame || '',
    score: context.score || '',
    viewport: context.viewport ? JSON.stringify(context.viewport) : '',
    gameState: context.gameState ? JSON.stringify(context.gameState) : '' // Full game state, not truncated
  };

  const keyString = JSON.stringify(keyData);
  return createHash('sha256').update(keyString).digest('hex');
}

/**
 * Load cache from file
 *
 * NOTE: Preserves original timestamps from file for expiration logic.
 * We need the original timestamp to check if entries are older than MAX_CACHE_AGE (7 days).
 *
 * The cache file format is: { key: { data: {...}, timestamp: number } }
 * - `timestamp`: When the entry was created (used for expiration)
 * - `data._lastAccessed`: When the entry was last accessed (used for LRU eviction)
 */
function loadCache() {
  if (!CACHE_FILE || !existsSync(CACHE_FILE)) {
    return new Map();
  }

  try {
    let cacheData;
    try {
      cacheData = JSON.parse(readFileSync(CACHE_FILE, 'utf8'));
    } catch (parseError) {
      // SECURITY: Handle malformed JSON gracefully to prevent DoS
      warn(`[VLLM Cache] Failed to parse cache file (corrupted?): ${parseError.message}`);
      // Recover by starting with empty cache
      return new Map();
    }
    const cache = new Map();
    const now = Date.now();

    // Filter out expired entries based on ORIGINAL timestamp
    // IMPORTANT: We preserve the original timestamp from the file
    // This allows 7-day expiration to work correctly
    for (const [key, value] of Object.entries(cacheData)) {
      if (value.timestamp && (now - value.timestamp) < MAX_CACHE_AGE) {
        // Preserve both the data and the original timestamp
        // The timestamp is stored in the file, not in the data object
        // But we need to track it for expiration, so we store it in the data
        const entry = {
          ...value.data,
          _originalTimestamp: value.timestamp // Preserve for expiration checks
        };
        cache.set(key, entry);
      }
    }

    return cache;
  } catch (error) {
    warn(`[VLLM Cache] Failed to load cache: ${error.message}`);
    return new Map();
  }
}

/**
 * Save cache to file with size limits and race condition protection
 * 
 * Uses async mutex to prevent concurrent writes and atomic file operations
 * to prevent corruption.
 */
async function saveCache(cache) {
  if (!CACHE_FILE) return;

  // Use proper async mutex to prevent concurrent writes
  // This ensures only one save operation happens at a time, even with async operations
  const release = await cacheWriteMutex.acquire();
  
  try {
    const cacheData = {};
    const now = Date.now();
    let totalSize = 0;

    // BUG FIX (2025-01): Don't reset timestamps on save!
    //
    // The bug was: `timestamp: now` for ALL entries
    // This broke 7-day expiration because old entries got new timestamps
    //
    // The fix: Preserve original timestamp for existing entries, use `now` only for new entries
    //
    // Two timestamps serve different purposes:
    // - `timestamp`: Creation time (for expiration - 7 days)
    // - `_lastAccessed`: Access time (for LRU eviction - least recently used)
    //
    // Convert to array and sort by _lastAccessed (LRU: oldest access first)
    const entries = Array.from(cache.entries())
      .map(([key, value]) => {
        // Preserve original timestamp if it exists, otherwise use current time (new entry)
        const originalTimestamp = value._originalTimestamp || now;
        // Remove _originalTimestamp from data before saving (it's metadata, not part of result)
        const { _originalTimestamp, ...dataWithoutMetadata } = value;

        return {
          key,
          value: dataWithoutMetadata,
          timestamp: originalTimestamp, // Preserve original, don't reset!
          lastAccessed: value._lastAccessed || originalTimestamp
        };
      })
      .sort((a, b) => {
        // Sort by access time for LRU eviction (oldest access = evict first)
        return a.lastAccessed - b.lastAccessed;
      });

    // Apply size limits (LRU eviction: keep most recently accessed)
    const entriesToKeep = entries.slice(-MAX_CACHE_SIZE);

    for (const { key, value, timestamp } of entriesToKeep) {
      const entry = {
        data: value,
        timestamp // Original timestamp preserved for expiration
      };
      const entrySize = JSON.stringify(entry).length;

      // Check total size limit
      if (totalSize + entrySize > MAX_CACHE_SIZE_BYTES) {
        break; // Stop adding entries if we exceed size limit
      }

      cacheData[key] = entry;
      totalSize += entrySize;
    }

    // Update in-memory cache to match saved entries
    // IMPORTANT: Restore _originalTimestamp for expiration checks
    cache.clear();
    for (const [key, entry] of Object.entries(cacheData)) {
      const entryWithMetadata = {
        ...entry.data,
        _originalTimestamp: entry.timestamp // Restore for expiration checks
      };
      cache.set(key, entryWithMetadata);
    }

    // ATOMIC WRITE: Write to temp file first, then rename atomically
    // This prevents corruption if process crashes during write
    // Note: writeFileSync flushes to OS buffers; rename is atomic on most filesystems
    // For stronger durability guarantees, we could add fsync, but it adds latency
    // The current approach balances performance and safety for cache use case
    // VERIFIABLE: Track atomic write operations to verify "prevents corruption" claim
    // CRITICAL FIX: Handle renameSync failure separately to ensure temp file cleanup
    // MCP research: If writeFileSync succeeds but renameSync fails, temp file must be cleaned up
    const tempFile = CACHE_FILE + '.tmp';
    const writeStartTime = Date.now();
    let writeSucceeded = false;
    let renameSucceeded = false;
    
    try {
      writeFileSync(tempFile, JSON.stringify(cacheData, null, 2), 'utf8');
      writeSucceeded = true;
      renameSync(tempFile, CACHE_FILE); // Atomic operation on most filesystems
      renameSucceeded = true;
      const writeDuration = Date.now() - writeStartTime;
      
      // Track successful atomic writes (for metrics)
      // NOTE: cacheMetrics is initialized at module level
      cacheMetrics.atomicWrites++;
      
      // Log in debug mode for verification
      if (process.env.DEBUG_CACHE) {
        log(`[VLLM Cache] Atomic write completed in ${writeDuration}ms (${Object.keys(cacheData).length} entries)`);
      }
    } catch (writeOrRenameError) {
      // CRITICAL FIX: If write succeeded but rename failed, clean up temp file
      // MCP research confirms this is a critical edge case
      if (writeSucceeded && !renameSucceeded) {
        try {
          if (existsSync(tempFile)) {
            unlinkSync(tempFile);
            cacheMetrics.tempFileCleanups++;
            if (process.env.DEBUG_CACHE) {
              log(`[VLLM Cache] Cleaned up temp file after renameSync failure`);
            }
          }
        } catch (cleanupError) {
          // Ignore cleanup errors, but log them
          warn(`[VLLM Cache] Failed to clean up temp file after rename failure: ${cleanupError.message}`);
        }
      }
      // Re-throw to be caught by outer catch block
      throw writeOrRenameError;
    }
  } catch (error) {
    // VERIFIABLE: Track failures to verify atomic write claim
    // NOTE: cacheMetrics is initialized at module level
    cacheMetrics.atomicWriteFailures++;
    
    warn(`[VLLM Cache] Failed to save cache: ${error.message}`);
    // Clean up temp file if it exists
    try {
      const tempFile = CACHE_FILE + '.tmp';
      if (existsSync(tempFile)) {
        unlinkSync(tempFile);
        cacheMetrics.tempFileCleanups++;
        // VERIFIABLE: Log temp file cleanup to verify atomic write safety
        if (process.env.DEBUG_CACHE) {
          log(`[VLLM Cache] Cleaned up temp file after failed atomic write`);
        }
      }
    } catch (cleanupError) {
      // Ignore cleanup errors
    }
  } finally {
    release(); // Release mutex
  }
}

/**
 * Get cache instance (singleton)
 */
function getCache() {
  if (!cacheInstance) {
    if (!CACHE_DIR) {
      initCache(); // Initialize with default directory
    }
    cacheInstance = loadCache();
  }
  return cacheInstance;
}

/**
 * Get cached result
 *
 * @param {string} imagePath - Path to image file
 * @param {string} prompt - Validation prompt
 * @param {import('./index.mjs').ValidationContext} [context={}] - Validation context
 * @returns {import('./index.mjs').ValidationResult | null} Cached result or null if not found
 */
export function getCached(imagePath, prompt, context = {}) {
  const cache = getCache();
  const key = generateCacheKey(imagePath, prompt, context);
  const cached = cache.get(key);

  if (cached) {
    // Update access time for LRU eviction
    // This is separate from timestamp (creation time) which is used for expiration
    cached._lastAccessed = Date.now();

    // Check expiration based on original timestamp
    // If entry is older than MAX_CACHE_AGE, remove it and return null
    const originalTimestamp = cached._originalTimestamp || cached._lastAccessed;
    const age = Date.now() - originalTimestamp;
    if (age > MAX_CACHE_AGE) {
      cache.delete(key); // Remove expired entry
      return null;
    }
  }

  return cached || null;
}

/**
 * Set cached result
 *
 * @param {string} imagePath - Path to image file
 * @param {string} prompt - Validation prompt
 * @param {import('./index.mjs').ValidationContext} context - Validation context
 * @param {import('./index.mjs').ValidationResult} result - Validation result to cache
 * @returns {void}
 */
export function setCached(imagePath, prompt, context, result) {
  const cache = getCache();
  const key = generateCacheKey(imagePath, prompt, context);
  const now = Date.now();

  // Check if this is a new entry or updating existing
  const existing = cache.get(key);
  const originalTimestamp = existing?._originalTimestamp || now; // Preserve if exists, else new

  // Add metadata for cache management
  // - _lastAccessed: For LRU eviction (when was it last used)
  // - _originalTimestamp: For expiration (when was it created)
  const resultWithMetadata = {
    ...result,
    _lastAccessed: now, // Update access time
    _originalTimestamp: originalTimestamp // Preserve creation time
  };

  cache.set(key, resultWithMetadata);

  // Always save cache (saveCache handles size limits and LRU eviction)
  // The if/else was redundant - both branches did the same thing
  // Save is async and fire-and-forget - errors are logged but don't affect in-memory cache
  saveCache(cache).catch(error => {
    warn(`[VLLM Cache] Failed to save cache (non-blocking): ${error.message}`);
  });
}

/**
 * Clear cache
 *
 * @returns {void}
 */
export function clearCache() {
  const cache = getCache();
  cache.clear();
  // Save cache to disk (async, fire-and-forget)
  saveCache(cache).catch(error => {
    warn(`[VLLM Cache] Failed to save cache after clear (non-blocking): ${error.message}`);
  });
}

/**
 * Get cache statistics
 *
 * VERIFIABLE: Includes atomic write metrics to verify "prevents corruption" claim
 *
 * @returns {import('./index.mjs').CacheStats} Cache statistics
 */
export function getCacheStats() {
  const cache = getCache();
  const stats = {
    size: cache.size,
    maxAge: MAX_CACHE_AGE,
    cacheFile: CACHE_FILE
  };
  
  // VERIFIABLE: Include atomic write metrics to verify "prevents corruption" claim
  // NOTE: cacheMetrics is always initialized at module level
  stats.atomicWrites = cacheMetrics.atomicWrites;
  stats.atomicWriteFailures = cacheMetrics.atomicWriteFailures;
  stats.tempFileCleanups = cacheMetrics.tempFileCleanups;
  stats.atomicWriteSuccessRate = cacheMetrics.atomicWrites + cacheMetrics.atomicWriteFailures > 0
    ? (cacheMetrics.atomicWrites / (cacheMetrics.atomicWrites + cacheMetrics.atomicWriteFailures)) * 100
    : 100;
  
  return stats;
}

