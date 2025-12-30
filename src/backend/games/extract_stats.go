package games

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"collections/logger"
)

// Context key for ExtractStats
type statsCtxKey struct{}

// WithExtractStats adds ExtractStats to context
func WithExtractStats(ctx context.Context, stats *ExtractStats) context.Context {
	return context.WithValue(ctx, statsCtxKey{}, stats)
}

// ExtractStatsFromContext retrieves ExtractStats from context
func ExtractStatsFromContext(ctx context.Context) *ExtractStats {
	if stats, ok := ctx.Value(statsCtxKey{}).(*ExtractStats); ok {
		return stats
	}
	return nil
}

// ExtractStats tracks extraction statistics and errors
type ExtractStats struct {
	Total      int
	Successful int
	Failed     int
	Errors     []ExtractError
	
	// Quality metrics
	NormalizedCount    int            // Cards normalized
	ValidationFailures map[string]int // Validation error types -> count
	CacheHits          int
	CacheMisses        int
	
	mu         sync.Mutex
	startTime  time.Time
	log        *logger.Logger
}

// ExtractError represents a single extraction error
type ExtractError struct {
	URL     string
	Error   string
	Dataset string
	Time    time.Time
}

// NewExtractStats creates a new stats tracker
func NewExtractStats(log *logger.Logger) *ExtractStats {
	return &ExtractStats{
		startTime:         time.Now(),
		Errors:            make([]ExtractError, 0, 100),
		ValidationFailures: make(map[string]int),
		log:               log,
	}
}

// RecordSuccess records a successful extraction
func (s *ExtractStats) RecordSuccess() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.Total++
	s.Successful++
}

// RecordError records an extraction error
func (s *ExtractStats) RecordError(ctx context.Context, url, dataset string, err error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.Total++
	s.Failed++
	if len(s.Errors) < 100 { // Keep last 100 errors
		s.Errors = append(s.Errors, ExtractError{
			URL:     url,
			Error:   err.Error(),
			Dataset: dataset,
			Time:    time.Now(),
		})
	}
	if s.log != nil {
		s.log.Field("url", url).
			Field("dataset", dataset).
			Errorf(ctx, "extraction error: %v", err)
	}
}

// Summary returns a formatted summary string
func (s *ExtractStats) Summary() string {
	s.mu.Lock()
	defer s.mu.Unlock()
	duration := time.Since(s.startTime)
	rate := float64(s.Total) / duration.Minutes()
	successRate := 0.0
	if s.Total > 0 {
		successRate = float64(s.Successful) / float64(s.Total) * 100
	}
	return fmt.Sprintf(
		"Extracted %d collections (%d successful, %d failed, %.1f%% success rate) in %v (%.1f/min)",
		s.Total, s.Successful, s.Failed, successRate, duration.Round(time.Second), rate,
	)
}

// GetErrors returns a copy of recent errors
func (s *ExtractStats) GetErrors() []ExtractError {
	s.mu.Lock()
	defer s.mu.Unlock()
	errors := make([]ExtractError, len(s.Errors))
	copy(errors, s.Errors)
	return errors
}

// RecordNormalization records a card name normalization
func (s *ExtractStats) RecordNormalization() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.NormalizedCount++
}

// RecordValidationFailure records a validation failure by type
func (s *ExtractStats) RecordValidationFailure(errorType string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.ValidationFailures[errorType]++
}

// RecordCacheHit records a cache hit
func (s *ExtractStats) RecordCacheHit() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.CacheHits++
}

// RecordCacheMiss records a cache miss
func (s *ExtractStats) RecordCacheMiss() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.CacheMisses++
}

// GetCacheHitRate returns the cache hit rate (0.0 to 1.0)
func (s *ExtractStats) GetCacheHitRate() float64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	total := s.CacheHits + s.CacheMisses
	if total == 0 {
		return 0.0
	}
	return float64(s.CacheHits) / float64(total)
}

// ExportJSON exports statistics to JSON format
func (s *ExtractStats) ExportJSON() ([]byte, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	
	type Export struct {
		Total              int            `json:"total"`
		Successful         int            `json:"successful"`
		Failed             int            `json:"failed"`
		SuccessRate        float64        `json:"success_rate"`
		NormalizedCount    int            `json:"normalized_count"`
		ValidationFailures map[string]int `json:"validation_failures"`
		CacheHits          int            `json:"cache_hits"`
		CacheMisses        int            `json:"cache_misses"`
		CacheHitRate       float64        `json:"cache_hit_rate"`
		Duration           string         `json:"duration"`
		Errors             []ExtractError  `json:"errors"`
	}
	
	duration := time.Since(s.startTime)
	successRate := 0.0
	if s.Total > 0 {
		successRate = float64(s.Successful) / float64(s.Total) * 100
	}
	
	export := Export{
		Total:              s.Total,
		Successful:         s.Successful,
		Failed:             s.Failed,
		SuccessRate:        successRate,
		NormalizedCount:    s.NormalizedCount,
		ValidationFailures: make(map[string]int),
		CacheHits:          s.CacheHits,
		CacheMisses:        s.CacheMisses,
		CacheHitRate:       s.GetCacheHitRate() * 100,
		Duration:           duration.Round(time.Second).String(),
		Errors:             make([]ExtractError, len(s.Errors)),
	}
	
	// Copy validation failures
	for k, v := range s.ValidationFailures {
		export.ValidationFailures[k] = v
	}
	
	// Copy errors
	copy(export.Errors, s.Errors)
	
	return json.MarshalIndent(export, "", "  ")
}

