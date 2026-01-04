package games

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"collections/logger"
)

func TestExtractStats(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic") // Suppress output in tests

	stats := NewExtractStats(log)

	// Record successes
	stats.RecordSuccess()
	stats.RecordSuccess()
	stats.RecordSuccess()

	// Record errors
	stats.RecordError(ctx, "http://example.com/1", "test-dataset", errors.New("test error 1"))
	stats.RecordError(ctx, "http://example.com/2", "test-dataset", errors.New("test error 2"))

	// Check counts
	if stats.Total != 5 {
		t.Errorf("Total = %d, want 5", stats.Total)
	}
	if stats.Successful != 3 {
		t.Errorf("Successful = %d, want 3", stats.Successful)
	}
	if stats.Failed != 2 {
		t.Errorf("Failed = %d, want 2", stats.Failed)
	}

	// Check errors stored
	errors := stats.GetErrors()
	if len(errors) != 2 {
		t.Errorf("GetErrors() returned %d errors, want 2", len(errors))
	}

	// Check summary
	summary := stats.Summary()
	if summary == "" {
		t.Error("Summary() returned empty string")
	}

	// Verify summary contains expected information
	if !contains(summary, "5") {
		t.Errorf("Summary should contain total count, got: %s", summary)
	}
	if !contains(summary, "3") {
		t.Errorf("Summary should contain success count, got: %s", summary)
	}
	if !contains(summary, "2") {
		t.Errorf("Summary should contain failure count, got: %s", summary)
	}
}

func TestExtractStatsQualityMetrics(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic")

	stats := NewExtractStats(log)

	// Record quality metrics
	stats.RecordNormalization()
	stats.RecordNormalization()
	stats.RecordValidationFailure("empty_partition")
	stats.RecordValidationFailure("empty_partition")
	stats.RecordValidationFailure("invalid_date")
	stats.RecordCacheHit()
	stats.RecordCacheHit()
	stats.RecordCacheMiss()

	// Check metrics
	if stats.NormalizedCount != 2 {
		t.Errorf("NormalizedCount = %d, want 2", stats.NormalizedCount)
	}
	if stats.ValidationFailures["empty_partition"] != 2 {
		t.Errorf("ValidationFailures[empty_partition] = %d, want 2", stats.ValidationFailures["empty_partition"])
	}
	if stats.ValidationFailures["invalid_date"] != 1 {
		t.Errorf("ValidationFailures[invalid_date] = %d, want 1", stats.ValidationFailures["invalid_date"])
	}
	if stats.CacheHits != 2 {
		t.Errorf("CacheHits = %d, want 2", stats.CacheHits)
	}
	if stats.CacheMisses != 1 {
		t.Errorf("CacheMisses = %d, want 1", stats.CacheMisses)
	}

	// Check cache hit rate
	hitRate := stats.GetCacheHitRate()
	expectedRate := 2.0 / 3.0
	if hitRate != expectedRate {
		t.Errorf("GetCacheHitRate() = %f, want %f", hitRate, expectedRate)
	}
}

func TestExtractStatsExportJSON(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic")

	stats := NewExtractStats(log)
	stats.RecordSuccess()
	stats.RecordError(ctx, "http://example.com/error", "test", errors.New("test error"))
	stats.RecordNormalization()
	stats.RecordCacheHit()

	jsonData, err := stats.ExportJSON()
	if err != nil {
		t.Fatalf("ExportJSON() error = %v", err)
	}

	// Verify it's valid JSON
	var export map[string]interface{}
	if err := json.Unmarshal(jsonData, &export); err != nil {
		t.Fatalf("ExportJSON() returned invalid JSON: %v", err)
	}

	// Check required fields
	if export["total"] == nil {
		t.Error("ExportJSON() missing 'total' field")
	}
	if export["success_rate"] == nil {
		t.Error("ExportJSON() missing 'success_rate' field")
	}
	if export["cache_hit_rate"] == nil {
		t.Error("ExportJSON() missing 'cache_hit_rate' field")
	}
}

func TestExtractStatsErrorLimit(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic")

	stats := NewExtractStats(log)

	// Record more than 100 errors
	for i := 0; i < 150; i++ {
		stats.RecordError(ctx, "http://example.com/test", "test", errors.New("error"))
	}

	// Should only keep last 100
	errors := stats.GetErrors()
	if len(errors) > 100 {
		t.Errorf("GetErrors() returned %d errors, should cap at 100", len(errors))
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(substr) == 0 ||
		(len(s) > len(substr) && (s[:len(substr)] == substr ||
		 s[len(s)-len(substr):] == substr ||
		 containsMiddle(s, substr))))
}

func containsMiddle(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
