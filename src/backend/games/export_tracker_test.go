package games

import (
	"context"
	"testing"
	"time"

	"collections/blob"
	"collections/logger"
)

func TestExportTracker(t *testing.T) {
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

	tracker := NewExportTracker(log, blob, "test")

	// Test initial state
	if err := tracker.Load(ctx); err != nil {
		t.Fatalf("failed to load tracker: %v", err)
	}

	blobKey := "test/deck.json"
	now := time.Now()
	yesterday := now.Add(-24 * time.Hour)
	tomorrow := now.Add(24 * time.Hour)

	// Never exported - should export
	if !tracker.ShouldExport(ctx, blobKey, now, time.Time{}, 0) {
		t.Error("Should export if never exported")
	}

	// Mark as exported
	tracker.MarkExported(blobKey)

	// Save and reload
	if err := tracker.Save(ctx); err != nil {
		t.Fatalf("failed to save tracker: %v", err)
	}

	tracker2 := NewExportTracker(log, blob, "test")
	if err := tracker2.Load(ctx); err != nil {
		t.Fatalf("failed to reload tracker: %v", err)
	}

	// Should not export if not modified
	if tracker2.ShouldExport(ctx, blobKey, yesterday, time.Time{}, 0) {
		t.Error("Should not export if not modified since last export")
	}

	// Should export if modified after last export
	if !tracker2.ShouldExport(ctx, blobKey, tomorrow, time.Time{}, 0) {
		t.Error("Should export if modified after last export")
	}

	// Test with Collection metadata
	collectionUpdatedAt := tomorrow
	if !tracker2.ShouldExport(ctx, blobKey, yesterday, collectionUpdatedAt, 0) {
		t.Error("Should export if Collection.UpdatedAt is after last export")
	}

	// Should prefer Collection metadata over file mtime
	if tracker2.ShouldExport(ctx, blobKey, yesterday, yesterday, 0) {
		t.Error("Should not export if Collection.UpdatedAt is before last export (even if file mtime is after)")
	}
}

func TestExportTrackerStats(t *testing.T) {
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

	tracker := NewExportTracker(log, blob, "test")

	// Mark some items as exported
	tracker.MarkExported("item1")
	tracker.MarkExported("item2")
	tracker.MarkExported("item3")

	total, recent := tracker.GetStats()
	if total != 3 {
		t.Errorf("Total = %d, want 3", total)
	}
	if recent < 3 {
		t.Errorf("Recent (24h) = %d, want at least 3", recent)
	}
}

