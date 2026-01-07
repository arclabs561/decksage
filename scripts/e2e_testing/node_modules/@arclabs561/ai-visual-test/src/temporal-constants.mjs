/**
 * Temporal Constants
 * Centralized definitions for all temporal decision-making constants
 * 
 * Single source of truth for all magic numbers and time scales
 */

// Time Scales (based on research: NN/g, PMC, Lindgaard)
export const TIME_SCALES = {
  INSTANT: 100,           // 0.1s - perceived instant, direct manipulation threshold (NN/g)
  VISUAL_DECISION: 50,    // 50ms - visual appeal decision (Lindgaard research)
  QUICK: 1000,            // 1s - noticeable delay (NN/g)
  NORMAL: 3000,           // 3s - normal interaction
  EXTENDED: 10000,        // 10s - extended focus (NN/g)
  LONG: 60000             // 60s - deep evaluation
};

// Multi-Scale Windows
export const MULTI_SCALE_WINDOWS = {
  immediate: TIME_SCALES.INSTANT,
  short: TIME_SCALES.QUICK,
  medium: TIME_SCALES.EXTENDED,
  long: TIME_SCALES.LONG
};

// Reading Speeds (words per minute)
export const READING_SPEEDS = {
  SCANNING: 300,    // Fast scanning
  NORMAL: 250,      // Average reading
  DEEP: 200         // Deep reading
};

// Attention Multipliers
export const ATTENTION_MULTIPLIERS = {
  focused: 0.8,      // Faster when focused (reduced cognitive load)
  normal: 1.0,
  distracted: 1.5    // Slower when distracted (increased cognitive load)
};

// Complexity Multipliers
export const COMPLEXITY_MULTIPLIERS = {
  simple: 0.7,       // Simple actions are faster
  normal: 1.0,
  complex: 1.5        // Complex actions take longer
};

// Confidence Thresholds
export const CONFIDENCE_THRESHOLDS = {
  HIGH_VARIANCE: 1.0,    // Variance < 1.0 = high confidence
  MEDIUM_VARIANCE: 2.0,   // Variance < 2.0 = medium confidence
  LOW_VARIANCE: 2.0       // Variance >= 2.0 = low confidence
};

// Time Bounds
export const TIME_BOUNDS = {
  MIN_PERCEPTION: 100,        // Minimum perception time (0.1s)
  MIN_READING_SHORT: 1000,     // Minimum reading time for short content
  MIN_READING_LONG: 2000,      // Minimum reading time for long content
  MAX_READING_SHORT: 15000,    // Maximum reading time for short content
  MAX_READING_LONG: 30000      // Maximum reading time for long content
};

// Content Length Thresholds
export const CONTENT_THRESHOLDS = {
  SHORT: 100,      // Short content (< 100 chars)
  MEDIUM: 1000,    // Medium content (< 1000 chars)
  LONG: 1000       // Long content (>= 1000 chars)
};

