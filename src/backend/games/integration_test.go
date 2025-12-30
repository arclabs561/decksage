package games

import (
	"context"
	"testing"

	"collections/blob"
	"collections/logger"
)

// TestExtractStatsIntegration tests the ExtractStats integration
func TestExtractStatsIntegration(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic")
	
	stats := NewExtractStats(log)
	
	// Simulate extraction process
	stats.RecordSuccess()
	stats.RecordSuccess()
	stats.RecordError(ctx, "http://example.com/error1", "test-dataset", 
		&ValidationError{Message: "test error"})
	
	summary := stats.Summary()
	if summary == "" {
		t.Error("Summary should not be empty")
	}
	
	// Verify stats
	if stats.Total != 3 {
		t.Errorf("Total = %d, want 3", stats.Total)
	}
	if stats.Successful != 2 {
		t.Errorf("Successful = %d, want 2", stats.Successful)
	}
	if stats.Failed != 1 {
		t.Errorf("Failed = %d, want 1", stats.Failed)
	}
}

// TestNormalizationIntegration tests normalization across different inputs
func TestNormalizationIntegration(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{"html entities", "Fire &amp; Ice", "Fire & Ice"},
		{"whitespace", "  Lightning Bolt  ", "Lightning Bolt"},
		{"multiple spaces", "Lightning   Bolt", "Lightning Bolt"},
		{"unicode", "José", "José"},
	}
	
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := NormalizeCardName(tt.input)
			if result != tt.expected {
				t.Errorf("NormalizeCardName(%q) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}

// TestDateParsingIntegration tests date parsing with various formats
func TestDateParsingIntegration(t *testing.T) {
	tests := []struct {
		name      string
		input     string
		wantErr   bool
		checkYear func(int) bool
	}{
		{"ISO format", "2024-01-15", false, func(y int) bool { return y == 2024 }},
		{"MTG Goldfish format", "Jan 15, 2024", false, func(y int) bool { return y == 2024 }},
		{"Deckbox format", "15-Jan-2024 14:30", false, func(y int) bool { return y == 2024 }},
		{"invalid year", "1980-01-15", true, nil},
		{"invalid format", "not a date", true, nil},
	}
	
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := ParseDateWithValidation(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseDateWithValidation(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
				return
			}
			if !tt.wantErr && tt.checkYear != nil {
				if !tt.checkYear(result.Year()) {
					t.Errorf("ParseDateWithValidation(%q) year = %d, validation failed", tt.input, result.Year())
				}
			}
		})
	}
}

// TestValidationIntegration tests the enhanced validation
func TestValidationIntegration(t *testing.T) {
	// This is a placeholder for integration tests that would test
	// the full validation pipeline with real collection data
	// In a real scenario, this would:
	// 1. Create test blob storage
	// 2. Extract a small dataset
	// 3. Verify collections pass validation
	// 4. Check normalization is applied
	// 5. Verify date parsing works
	
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic")
	
	// Create temporary blob storage
	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	blob, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer blob.Close(ctx)
	
	// Verify blob storage works
	exists, err := blob.Exists(ctx, "test-key")
	if err != nil {
		t.Fatalf("failed to check existence: %v", err)
	}
	if exists {
		t.Error("test-key should not exist")
	}
}

// ValidationError is a simple error type for testing
type ValidationError struct {
	Message string
}

func (e *ValidationError) Error() string {
	return e.Message
}

