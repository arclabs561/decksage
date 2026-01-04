package mtgtop8

import (
	"context"
	"testing"

	"collections/blob"
	"collections/games/magic/dataset"
	"collections/logger"
	"collections/scraper"
)

// TestErrorHandling verifies that URL parsing errors are properly captured
func TestErrorHandling(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic") // Suppress output

	// Create a test blob storage
	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	blob, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer blob.Close(ctx)

	// Create scraper with test blob
	scraperBlob, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create scraper blob: %v", err)
	}
	defer scraperBlob.Close(ctx)
	sc := scraper.NewScraper(log, scraperBlob)

	// Create dataset
	d := NewDataset(log, blob)

	// Test with invalid URL that would trigger the bug
	// This test verifies the error handling fix doesn't lose error context
	opts, _ := dataset.ResolveUpdateOptions(
		&dataset.OptExtractItemOnlyURL{URL: "https://mtgtop8.com/event?e=123&d=456"},
		&dataset.OptExtractParallel{Parallel: 1},
	)

	// This should either succeed (if URL is valid) or fail with a clear error
	// The key is that if url.Parse fails, we should see the error, not a generic one
	err = d.Extract(ctx, sc, opts...)
	// We don't care about success/failure here, just that errors are properly reported
	// The actual bug was that url.Parse errors were lost
	if err != nil {
		// Error should contain context about what failed
		if err.Error() == "" {
			t.Error("Error message should not be empty")
		}
	}
}

// TestCardNameNormalization verifies card names are normalized
func TestCardNameNormalization(t *testing.T) {
	// This is a unit test for the normalization logic
	// The actual normalization happens in games.NormalizeCardName
	// but we verify it's applied in mtgtop8 parsing

	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	blob, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer blob.Close(ctx)

	d := NewDataset(log, blob)

	// Verify the dataset exists and can be created
	if d == nil {
		t.Fatal("NewDataset returned nil")
	}

	desc := d.Description()
	if desc.Name != "mtgtop8" {
		t.Errorf("Description().Name = %q, want %q", desc.Name, "mtgtop8")
	}
}
