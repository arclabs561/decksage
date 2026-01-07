package games

import (
	"context"
	"testing"
	"time"

	"collections/blob"
	"collections/logger"
)

func TestComputeDeckSignature(t *testing.T) {
	col1 := &Collection{
		ID:          "deck1",
		URL:         "https://example.com/deck1",
		Source:      "mtgtop8",
		ReleaseDate: time.Now(),
		Partitions: []Partition{
			{
				Name: "Main",
				Cards: []CardDesc{
					{Name: "Lightning Bolt", Count: 4},
					{Name: "Mountain", Count: 20},
				},
			},
		},
	}

	col2 := &Collection{
		ID:          "deck2",
		URL:         "https://example.com/deck2",
		Source:      "goldfish",
		ReleaseDate: time.Now(),
		Partitions: []Partition{
			{
				Name: "Main",
				Cards: []CardDesc{
					{Name: "Lightning Bolt", Count: 4},
					{Name: "Mountain", Count: 20},
				},
			},
		},
	}

	sig1 := ComputeDeckSignature(col1)
	sig2 := ComputeDeckSignature(col2)

	if sig1 != sig2 {
		t.Error("Same deck content should produce same signature")
	}

	// Different content
	col2.Partitions[0].Cards[0].Count = 3
	sig2 = ComputeDeckSignature(col2)
	if sig1 == sig2 {
		t.Error("Different deck content should produce different signature")
	}
}

func TestDeduplicationTracker(t *testing.T) {
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

	tracker := NewDeduplicationTracker(log, blob, "test")

	col1 := &Collection{
		ID:          "deck1",
		URL:         "https://mtgtop8.com/deck1",
		Source:      "mtgtop8",
		ReleaseDate: time.Now(),
		Partitions: []Partition{
			{
				Name: "Main",
				Cards: []CardDesc{
					{Name: "Lightning Bolt", Count: 4},
				},
			},
		},
	}

	// First deck - not a duplicate
	isDup, canonID, canonURL := tracker.FindDuplicate(col1)
	if isDup {
		t.Error("First deck should not be duplicate")
	}
	if canonID != col1.ID {
		t.Errorf("Canonical ID = %s, want %s", canonID, col1.ID)
	}

	// Same deck from different source - should be duplicate
	col2 := &Collection{
		ID:          "deck2",
		URL:         "https://goldfish.com/deck2",
		Source:      "goldfish",
		ReleaseDate: time.Now(),
		Partitions: []Partition{
			{
				Name: "Main",
				Cards: []CardDesc{
					{Name: "Lightning Bolt", Count: 4},
				},
			},
		},
	}
	isDup, canonID, canonURL = tracker.FindDuplicate(col2)
	if !isDup {
		t.Error("Same deck from different source should be duplicate")
	}
	if canonID != col1.ID {
		t.Errorf("Canonical ID = %s, want %s", canonID, col1.ID)
	}
	if canonURL != col1.URL {
		t.Errorf("Canonical URL = %s, want %s", canonURL, col1.URL)
	}

	// Save and reload
	if err := tracker.Save(ctx); err != nil {
		t.Fatalf("failed to save tracker: %v", err)
	}

	tracker2 := NewDeduplicationTracker(log, blob, "test")
	if err := tracker2.Load(ctx); err != nil {
		t.Fatalf("failed to reload tracker: %v", err)
	}

	// Should still recognize duplicate after reload
	isDup, canonID, _ = tracker2.FindDuplicate(col2)
	if !isDup {
		t.Error("Should recognize duplicate after reload")
	}
	if canonID != col1.ID {
		t.Errorf("Canonical ID after reload = %s, want %s", canonID, col1.ID)
	}
}

func TestGetCanonicalSource(t *testing.T) {
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

	tracker := NewDeduplicationTracker(log, blob, "test")

	col := &Collection{
		ID:          "deck1",
		URL:         "https://example.com/deck1",
		Source:      "goldfish",
		ReleaseDate: time.Now(),
		Partitions: []Partition{
			{
				Name: "Main",
				Cards: []CardDesc{
					{Name: "Lightning Bolt", Count: 4},
				},
			},
		},
	}

	sig := ComputeDeckSignature(col)
	tracker.FindDuplicate(col) // Register it

	// Add scryfall as another source (higher priority)
	col2 := &Collection{
		ID:          "deck2",
		URL:         "https://scryfall.com/deck2",
		Source:      "scryfall",
		ReleaseDate: time.Now(),
		Partitions: []Partition{
			{
				Name: "Main",
				Cards: []CardDesc{
					{Name: "Lightning Bolt", Count: 4},
				},
			},
		},
	}
	tracker.FindDuplicate(col2)

	canonSource := tracker.GetCanonicalSource(sig)
	if canonSource != "scryfall" {
		t.Errorf("Canonical source = %s, want scryfall", canonSource)
	}
}

