/**
 * TypeScript definitions for ai-visual-test
 * 
 * Provides type safety and IntelliSense support for the package.
 */

// Utility Types
/**
 * Make specific properties optional
 * @template T
 * @template K
 */
export type PartialBy<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

/**
 * Make specific properties required
 * @template T
 * @template K
 */
export type RequiredBy<T, K extends keyof T> = T & Required<Pick<T, K>>;

/**
 * Extract return type from a function
 * @template T
 */
export type ReturnType<T extends (...args: any[]) => any> = T extends (...args: any[]) => infer R ? R : never;

/**
 * Extract parameter types from a function
 * @template T
 */
export type Parameters<T extends (...args: any[]) => any> = T extends (...args: infer P) => any ? P : never;

/**
 * Deep partial - makes all nested properties optional
 * @template T
 */
export type DeepPartial<T> = T extends object ? { [P in keyof T]?: DeepPartial<T[P]> } : T;

/**
 * Deep required - makes all nested properties required
 * @template T
 */
export type DeepRequired<T> = T extends object ? { [P in keyof T]-?: DeepRequired<T[P]> } : T;

/**
 * Non-nullable - removes null and undefined from type
 * @template T
 */
export type NonNullable<T> = T extends null | undefined ? never : T;

/**
 * Function type for validation functions
 * @template T
 */
export type ValidationFunction<T = ValidationResult> = (
  imagePath: string,
  prompt: string,
  context?: ValidationContext
) => Promise<T>;

// Error Types
export class AIBrowserTestError extends Error {
  code: string;
  details: Record<string, unknown>;
  constructor(message: string, code: string, details?: Record<string, unknown>);
  toJSON(): {
    name: string;
    code: string;
    message: string;
    details: Record<string, unknown>;
    stack?: string;
  };
}

export class ValidationError extends AIBrowserTestError {
  constructor(message: string, details?: Record<string, unknown>);
}

export class CacheError extends AIBrowserTestError {
  constructor(message: string, details?: Record<string, unknown>);
}

export class ConfigError extends AIBrowserTestError {
  constructor(message: string, details?: Record<string, unknown>);
}

export class ProviderError extends AIBrowserTestError {
  provider: string;
  constructor(message: string, provider: string, details?: Record<string, unknown>);
}

export class TimeoutError extends AIBrowserTestError {
  timeout: number;
  constructor(message: string, timeout: number, details?: Record<string, unknown>);
}

export class FileError extends AIBrowserTestError {
  filePath: string;
  constructor(message: string, filePath: string, details?: Record<string, unknown>);
}

export class StateMismatchError extends ValidationError {
  discrepancies: string[];
  extracted: unknown;
  expected: unknown;
  constructor(discrepancies: string[], extracted: unknown, expected: unknown, message?: string);
}

export function isAIBrowserTestError(error: unknown): error is AIBrowserTestError;
export function isErrorType<T extends AIBrowserTestError>(error: unknown, errorClass: new (...args: any[]) => T): error is T;

// Rubrics
export interface Rubric {
  score: {
    description: string;
    criteria: Record<string, string>;
  };
  dimensions?: Record<string, {
    description: string;
    criteria: string[];
  }>;
}

export const DEFAULT_RUBRIC: Rubric;
export function buildRubricPrompt(rubric?: Rubric | null, includeDimensions?: boolean): string;
export function getRubricForTestType(testType: string): Rubric;

// Bias Detection
export interface BiasDetectionResult {
  hasBias: boolean;
  biases: Array<{
    type: string;
    detected: boolean;
    score: number;
    evidence: Record<string, unknown>;
  }>;
  severity: 'none' | 'low' | 'medium' | 'high';
  recommendations: string[];
}

export function detectBias(judgment: string | object, options?: {
  checkVerbosity?: boolean;
  checkLength?: boolean;
  checkFormatting?: boolean;
  checkPosition?: boolean;
  checkAuthority?: boolean;
}): BiasDetectionResult;

export interface PositionBiasResult {
  detected: boolean;
  firstBias?: boolean;
  lastBias?: boolean;
  reason?: string;
  evidence?: {
    firstScore: number;
    lastScore: number;
    avgMiddle: number;
    allScores: number[];
  };
}

export function detectPositionBias(judgments: Array<{ score: number | null }>): PositionBiasResult;

// Ensemble Judging
export interface EnsembleJudgeOptions {
  judges?: Array<VLLMJudge>;
  votingMethod?: 'weighted_average' | 'majority' | 'consensus';
  weights?: number[];
  minAgreement?: number;
  enableBiasDetection?: boolean;
}

export interface EnsembleResult {
  score: number | null;
  assessment: string;
  issues: string[];
  reasoning: string;
  confidence: number;
  agreement: {
    score: number;
    scoreAgreement: number;
    assessmentAgreement: number;
    mean: number;
    stdDev: number;
    scores: number[];
  };
  disagreement: {
    hasDisagreement: boolean;
    scoreRange: number;
    assessmentDisagreement: boolean;
    uniqueAssessments: string[];
    maxScore: number;
    minScore: number;
  };
  biasDetection?: {
    individual: BiasDetectionResult[];
    position: PositionBiasResult;
  };
  individualJudgments: Array<{
    judgeIndex: number;
    score: number | null;
    assessment: string | null;
    issues: string[];
    reasoning: string | null;
    provider: string;
    error?: string;
  }>;
  judgeCount: number;
  votingMethod: string;
}

export class EnsembleJudge {
  constructor(options?: EnsembleJudgeOptions);
  evaluate(imagePath: string, prompt: string, context?: Record<string, unknown>): Promise<EnsembleResult>;
}

export function createEnsembleJudge(providers?: string[], options?: EnsembleJudgeOptions): EnsembleJudge;

// Core Types
export interface ValidationContext {
  testType?: string;
  viewport?: { width: number; height: number };
  gameState?: Record<string, unknown>;
  useCache?: boolean;
  timeout?: number;
  useRubric?: boolean;
  includeDimensions?: boolean;
  url?: string;
  description?: string;
  step?: string;
  promptBuilder?: (prompt: string, context: ValidationContext) => string;
}

export interface EstimatedCost {
  inputTokens: number;
  outputTokens: number;
  inputCost: string;
  outputCost: string;
  totalCost: string;
  currency: string;
}

export interface SemanticInfo {
  score: number | null;
  issues: string[];
  assessment: string | null;
  reasoning: string;
  brutalistViolations?: string[];
  zeroToleranceViolations?: string[];
}

export interface ValidationResult {
  enabled: boolean;
  provider: string;
  score: number | null;
  issues: string[];
  assessment: string | null;
  reasoning: string;
  estimatedCost?: EstimatedCost | null;
  responseTime: number;
  cached?: boolean;
  judgment?: string;
  raw?: unknown;
  semantic?: SemanticInfo;
  error?: string;
  message?: string;
  pricing?: { input: number; output: number };
  timestamp?: string;
  testName?: string;
  viewport?: { width: number; height: number } | null;
}

export interface ConfigOptions {
  provider?: 'gemini' | 'openai' | 'claude' | null;
  apiKey?: string | null;
  env?: NodeJS.ProcessEnv;
  cacheDir?: string | null;
  cacheEnabled?: boolean;
  maxConcurrency?: number;
  timeout?: number;
  verbose?: boolean;
}

export interface Config {
  provider: string;
  apiKey: string | null;
  providerConfig: {
    name: string;
    apiUrl: string;
    model: string;
    freeTier: boolean;
    pricing: { input: number; output: number };
    priority: number;
  };
  enabled: boolean;
  cache: {
    enabled: boolean;
    dir: string | null;
  };
  performance: {
    maxConcurrency: number;
    timeout: number;
  };
  debug: {
    verbose: boolean;
  };
}

// VLLMJudge Class
export class VLLMJudge {
  constructor(options?: ConfigOptions);
  provider: string;
  apiKey: string | null;
  providerConfig: Config['providerConfig'];
  enabled: boolean;
  
  imageToBase64(imagePath: string): string;
  buildPrompt(prompt: string, context: ValidationContext): string;
  extractSemanticInfo(judgment: string | object): SemanticInfo;
  estimateCost(data: unknown, provider: string): EstimatedCost | null;
  judgeScreenshot(imagePath: string, prompt: string, context?: ValidationContext): Promise<ValidationResult>;
}

// Core Functions
export function validateScreenshot(
  imagePath: string,
  prompt: string,
  context?: ValidationContext
): Promise<ValidationResult>;

export function extractSemanticInfo(judgment: string | object): SemanticInfo;

// Multi-Modal Types
export interface RenderedCode {
  html: string;
  criticalCSS: Record<string, Record<string, string>>;
  domStructure: {
    prideParade?: {
      computedTop: string;
      flagRowCount: number;
    };
    footer?: {
      computedBottom: string;
      hasStripe: boolean;
    };
    paymentCode?: {
      visible: boolean;
    };
  };
}

export interface TemporalScreenshot {
  path: string;
  timestamp: number;
  elapsed: number;
}

export interface Persona {
  name: string;
  perspective: string;
  focus: string[];
}

export interface PerspectiveEvaluation {
  persona: Persona;
  evaluation: ValidationResult;
}

// Multi-Modal Functions
export function extractRenderedCode(page: any): Promise<RenderedCode>;
export function captureTemporalScreenshots(
  page: any,
  fps?: number,
  duration?: number
): Promise<TemporalScreenshot[]>;
export function multiPerspectiveEvaluation(
  validateFn: ValidationFunction,
  screenshotPath: string,
  renderedCode: RenderedCode,
  gameState?: Record<string, unknown>,
  personas?: Persona[] | null
): Promise<PerspectiveEvaluation[]>;
export function multiModalValidation(
  validateFn: ValidationFunction,
  page: any,
  testName: string,
  options?: {
    fps?: number;
    duration?: number;
    captureCode?: boolean;
    captureState?: boolean;
    multiPerspective?: boolean;
  }
): Promise<{
  screenshotPath: string;
  renderedCode: RenderedCode | null;
  gameState: Record<string, unknown>;
  temporalScreenshots: TemporalScreenshot[];
  perspectives: PerspectiveEvaluation[];
  codeValidation: Record<string, boolean>;
  aggregatedScore: number | null;
  aggregatedIssues: string[];
  timestamp: number;
}>;

// Temporal Types
export interface TemporalNote {
  timestamp?: number;
  elapsed?: number;
  score?: number;
  observation?: string;
  step?: string;
}

export interface TemporalWindow {
  index: number;
  startTime: number;
  endTime: number;
  notes: TemporalNote[];
  weightedScore: number;
  totalWeight: number;
  avgScore: number;
  observations: Set<string>;
}

export interface AggregatedTemporalNotes {
  windows: TemporalWindow[];
  summary: string;
  coherence: number;
  conflicts: Array<{
    window1: number;
    window2: number;
    type: string;
    description: string;
  }>;
}

// Temporal Functions
export function aggregateTemporalNotes(
  notes: TemporalNote[],
  options?: {
    windowSize?: number;
    decayFactor?: number;
    coherenceThreshold?: number;
  }
): AggregatedTemporalNotes;

export function formatNotesForPrompt(aggregated: AggregatedTemporalNotes): string;

export function calculateCoherence(windows: TemporalWindow[]): number;

// Cache Types
export interface CacheStats {
  hits: number;
  misses: number;
  size: number;
  hitRate: number;
}

// Cache Functions
export function initCache(cacheDir?: string): void;
export function generateCacheKey(imagePath: string, prompt: string, context?: ValidationContext): string;
export function getCached(imagePath: string, prompt: string, context?: ValidationContext): ValidationResult | null;
export function setCached(
  imagePath: string,
  prompt: string,
  context: ValidationContext,
  result: ValidationResult
): void;
export function clearCache(): void;
export function getCacheStats(): CacheStats;

// Config Functions
export function createConfig(options?: ConfigOptions): Config;
export function getConfig(): Config;
export function setConfig(config: Config): void;
export function getProvider(providerName?: string | null): Config['providerConfig'];

// Utility Functions
export function loadEnv(basePath?: string | null): void;
export function initErrorHandlers(): void;

// ScoreTracker Class
export class ScoreTracker {
  constructor(options?: { baselineDir?: string; autoSave?: boolean });
  record(testName: string, score: number, metadata?: Record<string, unknown>): { score: number; timestamp: string; metadata: Record<string, unknown> };
  getBaseline(testName: string): number | null;
  getCurrent(testName: string): number | null;
  compare(testName: string, currentScore: number): { hasBaseline: boolean; baseline: number | null; current: number; improved: boolean; delta: number; percentage: number; regression?: boolean; trend?: string; history?: Array<{ score: number; timestamp: string; metadata?: Record<string, unknown> }> } | null;
  updateBaseline(testName: string, newBaseline?: number | null): boolean;
  getAll(): Record<string, { history: Array<{ score: number; timestamp: string; metadata?: Record<string, unknown> }>; current: number | null; baseline: number | null; firstRecorded: string; lastUpdated: string; baselineSetAt?: string }>;
  getStats(): {
    current: number | null;
    baseline: number | null;
    history: Array<{ score: number; timestamp: number; metadata?: Record<string, unknown> }>;
    average: number | null;
    min: number | null;
    max: number | null;
    totalTests?: number;
    testsWithBaselines?: number;
    testsWithRegressions?: number;
    testsWithImprovements?: number;
    averageScore?: number;
    averageBaseline?: number;
  };
}

// BatchOptimizer Class
export class BatchOptimizer {
  constructor(options?: { maxConcurrency?: number; batchSize?: number; cacheEnabled?: boolean });
  batchValidate(imagePaths: string | string[], prompt: string, context?: ValidationContext): Promise<ValidationResult[]>;
  clearCache(): void;
  getCacheStats(): { cacheSize: number; queueLength: number; activeRequests: number };
}

// Data Extractor
export function extractStructuredData(
  text: string,
  schema: object,
  options?: {
    method?: 'json' | 'llm' | 'regex';
    provider?: string;
    apiKey?: string;
  }
): Promise<unknown>;

// Feedback Aggregator
export interface AggregatedFeedback {
  averageScore: number;
  totalIssues: number;
  commonIssues: Array<{ issue: string; count: number }>;
  scoreDistribution: Record<string, number>;
  recommendations: string[];
}

export function aggregateFeedback(judgeResults: ValidationResult[]): AggregatedFeedback;
export function generateRecommendations(aggregated: AggregatedFeedback): string[];

// Context Compressor
export function compressContext(
  notes: TemporalNote[],
  options?: {
    maxLength?: number;
    preserveImportant?: boolean;
  }
): TemporalNote[];

export function compressStateHistory(
  stateHistory: Array<Record<string, unknown>>,
  options?: {
    maxLength?: number;
    preserveImportant?: boolean;
  }
): Array<Record<string, unknown>>;

// Persona Experience
export interface PersonaExperienceOptions {
  viewport?: { width: number; height: number };
  device?: string;
  darkMode?: boolean;
  timeScale?: 'human' | 'mechanical';
  captureScreenshots?: boolean;
  captureState?: boolean;
  captureCode?: boolean;
  notes?: TemporalNote[];
}

export interface PersonaExperienceResult {
  persona: Persona;
  notes: TemporalNote[];
  screenshots: TemporalScreenshot[];
  renderedCode?: RenderedCode;
  gameState?: Record<string, unknown>;
  evaluation?: ValidationResult;
  timestamp: number;
}

export function experiencePageAsPersona(
  page: any,
  persona: Persona,
  options?: PersonaExperienceOptions
): Promise<PersonaExperienceResult>;

export function experiencePageWithPersonas(
  page: any,
  personas: Persona[],
  options?: PersonaExperienceOptions
): Promise<PersonaExperienceResult[]>;

// Type Guards
export function isObject<T>(value: unknown): value is Record<string, T>;
export function isString(value: unknown): value is string;
export function isNumber(value: unknown): value is number;
export function isPositiveInteger(value: unknown): value is number;
export function isNonEmptyString(value: unknown): value is string;
export function isArray<T>(value: unknown): value is T[];
export function isFunction(value: unknown): value is Function;
export function isPromise<T>(value: unknown): value is Promise<T>;
export function isValidationResult(value: unknown): value is ValidationResult;
export function isValidationContext(value: unknown): value is ValidationContext;
export function isPersona(value: unknown): value is Persona;
export function isTemporalNote(value: unknown): value is TemporalNote;

// Type Assertions
export function assertObject<T>(value: unknown, name?: string): asserts value is Record<string, T>;
export function assertString(value: unknown, name?: string): asserts value is string;
export function assertNonEmptyString(value: unknown, name?: string): asserts value is string;
export function assertNumber(value: unknown, name?: string): asserts value is number;
export function assertArray<T>(value: unknown, name?: string): asserts value is T[];
export function assertFunction(value: unknown, name?: string): asserts value is Function;

// Utility Functions
export function pick<T, K extends keyof T>(obj: T, keys: K[]): Pick<T, K>;
export function getProperty<T, D>(obj: T, key: string, defaultValue: D): T[keyof T] | D;

// Experience Tracer
export class ExperienceTrace {
  constructor(sessionId: string, persona?: Persona | null);
  sessionId: string;
  persona: Persona | null;
  startTime: number;
  events: Array<Record<string, unknown>>;
  validations: Array<Record<string, unknown>>;
  screenshots: Array<Record<string, unknown>>;
  stateHistory: Array<Record<string, unknown>>;
  aggregatedNotes: AggregatedTemporalNotes | null;
  metaEvaluation: Record<string, unknown> | null;
  
  addEvent(type: string, data: Record<string, unknown>, timestamp?: number | null): Record<string, unknown>;
  addValidation(validation: ValidationResult, context?: Record<string, unknown>): Record<string, unknown>;
  addScreenshot(path: string, step: string, metadata?: Record<string, unknown>): Record<string, unknown>;
  addStateSnapshot(state: Record<string, unknown>, label?: string): Record<string, unknown>;
  aggregateNotes(
    aggregateTemporalNotes: (notes: TemporalNote[], options?: Record<string, unknown>) => AggregatedTemporalNotes,
    options?: Record<string, unknown>
  ): AggregatedTemporalNotes;
  getSummary(): Record<string, unknown>;
  getFullTrace(): Record<string, unknown>;
  exportToJSON(filePath: string): Promise<void>;
}

export class ExperienceTracerManager {
  constructor();
  createTrace(sessionId: string, persona?: Persona | null): ExperienceTrace;
  getTrace(sessionId: string): ExperienceTrace | null;
  getAllTraces(): ExperienceTrace[];
  metaEvaluateTrace(
    sessionId: string,
    validateScreenshot: ValidationFunction
  ): Promise<Record<string, unknown>>;
  getMetaEvaluationSummary(): {
    totalEvaluations: number;
    averageQuality: number | null;
    evaluations?: Array<Record<string, unknown>>;
  };
}

export function getTracerManager(): ExperienceTracerManager;

// Position Counter-Balance
export interface CounterBalanceOptions {
  enabled?: boolean;
  baselinePath?: string | null;
  contextOrder?: 'original' | 'reversed';
}

export interface CounterBalancedResult extends ValidationResult {
  counterBalanced: boolean;
  originalScore: number | null;
  reversedScore: number | null;
  scoreDifference: number | null;
  metadata: {
    counterBalancing: {
      enabled: boolean;
      originalResult: ValidationResult;
      reversedResult: ValidationResult;
      positionBiasDetected: boolean;
    };
  };
}

export function evaluateWithCounterBalance(
  evaluateFn: ValidationFunction<ValidationResult>,
  imagePath: string,
  prompt: string,
  context?: ValidationContext,
  options?: CounterBalanceOptions
): Promise<CounterBalancedResult>;

export function shouldUseCounterBalance(context: ValidationContext): boolean;

// Dynamic Few-Shot Examples
export interface FewShotExample {
  description?: string;
  evaluation?: string;
  score?: number | null;
  screenshot?: string;
  quality?: string;
  result?: {
    score?: number | null;
    reasoning?: string;
  };
  json?: unknown;
}

export interface FewShotOptions {
  maxExamples?: number;
  similarityThreshold?: number;
  useSemanticMatching?: boolean;
}

export function selectFewShotExamples(
  prompt: string,
  examples?: FewShotExample[],
  options?: FewShotOptions
): FewShotExample[];

export function formatFewShotExamples(
  examples: FewShotExample[],
  format?: 'default' | 'json'
): string;

// Metrics
export function spearmanCorrelation(
  x: Array<number | null>,
  y: Array<number | null>
): number | null;

export function pearsonCorrelation(
  x: Array<number | null>,
  y: Array<number | null>
): number | null;

export interface RankAgreementResult {
  spearman: number | null;
  pearson: number | null;
  kendall: number | null;
  exactMatches: number;
  totalItems: number;
  agreementRate: number;
}

export function calculateRankAgreement(
  ranking1: Array<number | null>,
  ranking2: Array<number | null>
): RankAgreementResult;

// Validators
export interface StateValidatorOptions<T = unknown> {
  tolerance?: number;
  validateScreenshot?: ValidationFunction;
  stateExtractor?: (result: ValidationResult, expected: T) => Partial<T>;
  stateComparator?: (extracted: Partial<T>, expected: T, options: { tolerance: number }) => {
    matches: boolean;
    discrepancies: string[];
  };
}

export interface StateValidationOptions<T = unknown> {
  promptBuilder?: (expected: T, options: Record<string, unknown>) => string;
  testType?: string;
  context?: Record<string, unknown>;
  stateDescription?: string;
  extractionTasks?: string[];
}

export interface StateValidationResult<T = unknown> extends ValidationResult {
  extractedState: Partial<T>;
  expectedState: T;
  validation: {
    matches: boolean;
    discrepancies: string[];
  };
  matches: boolean;
}

export class StateValidator<T = unknown> {
  constructor(options?: StateValidatorOptions<T>);
  static validate<T = unknown>(
    screenshotPath: string | string[],
    expectedState: T,
    options?: StateValidationOptions<T>
  ): Promise<StateValidationResult<T>>;
  validateState(
    screenshotPath: string | string[],
    expectedState: T,
    options?: StateValidationOptions<T>
  ): Promise<StateValidationResult<T>>;
  buildStatePrompt(expectedState: T, options?: StateValidationOptions<T>): string;
}

export interface AccessibilityValidatorOptions {
  minContrast?: number;
  standards?: string[];
  zeroTolerance?: boolean;
  validateScreenshot?: ValidationFunction;
}

export interface AccessibilityOptions {
  customPrompt?: string;
  minContrast?: number;
  standards?: string[];
  testType?: string;
  [key: string]: unknown;
}

export interface AccessibilityResult extends ValidationResult {
  violations: {
    zeroTolerance: string[];
    critical: string[];
    warnings: string[];
  };
  passes: boolean;
  contrastCheck: {
    ratios: string[];
    minRatio: number | null;
    meetsRequirement: boolean | null;
  };
  standards: string[];
}

export class AccessibilityValidator {
  constructor(options?: AccessibilityValidatorOptions);
  static validate(
    screenshotPath: string | string[],
    options?: AccessibilityOptions
  ): Promise<AccessibilityResult>;
  validateAccessibility(
    screenshotPath: string | string[],
    options?: AccessibilityOptions
  ): Promise<AccessibilityResult>;
  buildAccessibilityPrompt(options?: AccessibilityOptions): string;
  detectViolations(result: ValidationResult): {
    zeroTolerance: string[];
    critical: string[];
    warnings: string[];
  };
  extractContrastInfo(result: ValidationResult): {
    ratios: string[];
    minRatio: number | null;
    meetsRequirement: boolean | null;
  };
}

export type PromptTemplate = (variables: Record<string, unknown>, context?: Record<string, unknown>) => string;

export interface PromptBuilderOptions {
  templates?: Record<string, PromptTemplate | string>;
  rubric?: Rubric;
  defaultContext?: Record<string, unknown>;
}

export interface PromptOptions {
  variables?: Record<string, unknown>;
  context?: Record<string, unknown>;
  includeRubric?: boolean;
  includeZeroTolerance?: boolean;
  includeScoring?: boolean;
  enforceZeroTolerance?: boolean;
  rubric?: Rubric;
}

export class PromptBuilder {
  constructor(options?: PromptBuilderOptions);
  buildPrompt(basePrompt: string, options?: PromptOptions): string;
  buildFromTemplate(templateName: string, variables?: Record<string, unknown>, options?: PromptOptions): string;
  registerTemplate(name: string, template: PromptTemplate | string): void;
}

export interface RubricOptions {
  enforceZeroTolerance?: boolean;
  includeZeroTolerance?: boolean;
  includeScoring?: boolean;
}

export interface RubricCriterion {
  id: string;
  rule: string;
  weight?: number;
  zeroTolerance?: boolean;
  penalty?: number;
  description?: string;
}

export interface ExtendedRubric extends Rubric {
  criteria?: RubricCriterion[];
  name?: string;
  description?: string;
}

export function validateWithRubric(
  screenshotPath: string,
  prompt: string,
  rubric: ExtendedRubric,
  context?: ValidationContext,
  options?: RubricOptions
): Promise<ValidationResult & { zeroToleranceViolation?: boolean }>;

export interface BatchValidatorOptions {
  maxConcurrency?: number;
  batchSize?: number;
  cacheEnabled?: boolean;
  trackCosts?: boolean;
  trackStats?: boolean;
}

export interface BatchValidationStats {
  total: number;
  passed: number;
  failed: number;
  duration: number;
  costStats: ReturnType<CostTracker['getStats']> | null;
  performance: {
    totalRequests: number;
    avgDuration: number;
    minDuration: number;
    maxDuration: number;
    successRate: number;
  } | null;
}

export interface BatchValidationResult {
  results: ValidationResult[];
  stats: BatchValidationStats | null;
}

export class BatchValidator extends BatchOptimizer {
  constructor(options?: BatchValidatorOptions);
  batchValidate(
    screenshots: string | string[],
    prompt: string,
    context?: ValidationContext
  ): Promise<BatchValidationResult>;
  getCostStats(): ReturnType<CostTracker['getStats']>;
  getPerformanceStats(): {
    totalRequests: number;
    avgDuration: number;
    minDuration: number;
    maxDuration: number;
    successRate: number;
  };
  resetStats(): void;
}

// Programmatic Validators (fast, deterministic)
// Use these when you have Playwright page access and need fast feedback (<100ms)

/**
 * Calculate contrast ratio between two colors (WCAG algorithm)
 * 
 * @param color1 - First color (rgb, rgba, or hex)
 * @param color2 - Second color (rgb, rgba, or hex)
 * @returns Contrast ratio (1.0 to 21.0+)
 */
export function getContrastRatio(color1: string, color2: string): number;

/**
 * Contrast check result for a single element
 */
export interface ElementContrastResult {
  ratio: number;
  passes: boolean;
  foreground: string;
  background: string;
  foregroundRgb?: [number, number, number];
  backgroundRgb?: [number, number, number];
  error?: string;
  selector?: string;
}

/**
 * Check contrast ratio for an element
 * 
 * @param page - Playwright page object
 * @param selector - CSS selector for element
 * @param minRatio - Minimum required contrast ratio (default: 4.5 for WCAG-AA)
 * @returns Contrast check result
 */
export function checkElementContrast(
  page: any,
  selector: string,
  minRatio?: number
): Promise<ElementContrastResult>;

/**
 * Text contrast check result for all text elements
 */
export interface AllTextContrastResult {
  total: number;
  passing: number;
  failing: number;
  violations: Array<{
    element: string;
    ratio: string;
    required: number;
    foreground: string;
    background: string;
  }>;
  elements?: Array<{
    tag: string;
    id: string;
    className: string;
    ratio: number;
    passes: boolean;
    foreground: string;
    background: string;
  }>;
}

/**
 * Check contrast for all text elements on page
 * 
 * @param page - Playwright page object
 * @param minRatio - Minimum required contrast ratio (default: 4.5 for WCAG-AA)
 * @returns Contrast check results for all text elements
 */
export function checkAllTextContrast(
  page: any,
  minRatio?: number
): Promise<AllTextContrastResult>;

/**
 * Keyboard navigation check result
 */
export interface KeyboardNavigationResult {
  keyboardAccessible: boolean;
  focusableElements: number;
  violations: Array<{
    element: string;
    issue: string;
  }>;
  focusableSelectors: string[];
}

/**
 * Check keyboard navigation accessibility
 * 
 * @param page - Playwright page object
 * @returns Keyboard navigation check result
 */
export function checkKeyboardNavigation(page: any): Promise<KeyboardNavigationResult>;

/**
 * Programmatic state validation options
 */
export interface ProgrammaticStateOptions {
  selectors?: Record<string, string>;
  tolerance?: number;
  stateExtractor?: (page: any) => Promise<unknown>;
}

/**
 * Programmatic state validation result
 */
export interface ProgrammaticStateResult {
  matches: boolean;
  discrepancies: string[];
  visualState: Record<string, {
    x: number;
    y: number;
    width: number;
    height: number;
    visible: boolean;
  } | null>;
  expectedState: Record<string, unknown>;
  gameState?: unknown;
}

/**
 * Validate state matches visual representation
 * 
 * @param page - Playwright page object
 * @param expectedState - Expected state object
 * @param options - Validation options
 * @returns State validation result
 */
export function validateStateProgrammatic(
  page: any,
  expectedState: Record<string, unknown>,
  options?: ProgrammaticStateOptions
): Promise<ProgrammaticStateResult>;

/**
 * Element position validation result
 */
export interface ElementPositionResult {
  matches: boolean;
  actual: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  expected: {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
  };
  diff: {
    x: number;
    y: number;
    width?: number;
    height?: number;
  };
  tolerance: number;
  error?: string;
  selector?: string;
}

/**
 * Validate element position matches expected position
 * 
 * @param page - Playwright page object
 * @param selector - CSS selector for element
 * @param expectedPosition - Expected position {x, y} or {x, y, width, height}
 * @param tolerance - Pixel tolerance (default: 5)
 * @returns Position validation result
 */
export function validateElementPosition(
  page: any,
  selector: string,
  expectedPosition: {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
  },
  tolerance?: number
): Promise<ElementPositionResult>;

// Hybrid Validators (Programmatic + VLLM)
// Combine programmatic data with semantic LLM evaluation

/**
 * Hybrid accessibility validation result
 */
export interface AccessibilityHybridResult extends ValidationResult {
  programmaticData: {
    contrast: AllTextContrastResult;
    keyboard: KeyboardNavigationResult;
  };
}

/**
 * Hybrid accessibility validation
 * Combines programmatic contrast/keyboard checks with VLLM semantic evaluation
 * 
 * @param page - Playwright page object
 * @param screenshotPath - Path to screenshot
 * @param minContrast - Minimum contrast ratio (default: 4.5)
 * @param options - Validation options
 * @returns Hybrid validation result with programmatic data
 */
export function validateAccessibilityHybrid(
  page: any,
  screenshotPath: string,
  minContrast?: number,
  options?: ValidationContext
): Promise<AccessibilityHybridResult>;

/**
 * Hybrid state validation result
 */
export interface StateHybridResult extends ValidationResult {
  programmaticData: {
    gameState?: unknown;
    visualState: Record<string, {
      x: number;
      y: number;
      width: number;
      height: number;
      visible: boolean;
    } | null>;
    discrepancies: string[];
    matches: boolean;
  };
}

/**
 * Hybrid state validation
 * Combines programmatic state extraction with VLLM semantic evaluation
 * 
 * @param page - Playwright page object
 * @param screenshotPath - Path to screenshot
 * @param expectedState - Expected state object
 * @param options - Validation options
 * @returns Hybrid validation result with programmatic data
 */
export function validateStateHybrid(
  page: any,
  screenshotPath: string,
  expectedState: Record<string, unknown>,
  options?: ProgrammaticStateOptions & ValidationContext
): Promise<StateHybridResult>;

/**
 * Generic hybrid validator result
 */
export interface HybridValidationResult extends ValidationResult {
  programmaticData: Record<string, unknown>;
}

/**
 * Generic hybrid validator helper
 * Combines any programmatic data with VLLM evaluation
 * 
 * @param screenshotPath - Path to screenshot
 * @param prompt - Base evaluation prompt
 * @param programmaticData - Programmatic validation data
 * @param options - Validation options
 * @returns Hybrid validation result with programmatic data
 */
export function validateWithProgrammaticContext(
  screenshotPath: string,
  prompt: string,
  programmaticData: Record<string, unknown>,
  options?: ValidationContext
): Promise<HybridValidationResult>;

