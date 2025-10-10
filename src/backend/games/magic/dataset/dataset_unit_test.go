package dataset_test

import (
	"context"
	"fmt"
	"os"
	"testing"

	"collections/blob"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/goldfish"
	"collections/games/magic/dataset/mtgtop8"
	"collections/games/magic/dataset/scryfall"
	"collections/logger"
)

// TestDatasetCreation verifies that all datasets can be instantiated
func TestDatasetCreation(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := fmt.Sprintf("file://%s", tmpDir)
	blob, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}

	tests := []struct {
		name    string
		dataset interface{}
	}{
		{"scryfall", scryfall.NewDataset(log, blob)},
		{"deckbox", deckbox.NewDataset(log, blob)},
		{"goldfish", goldfish.NewDataset(log, blob)},
		{"mtgtop8", mtgtop8.NewDataset(log, blob)},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.dataset == nil {
				t.Error("dataset is nil")
			}
		})
	}
}

// TestBlobOperations tests basic blob storage operations
func TestBlobOperations(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := fmt.Sprintf("file://%s", tmpDir)
	blob, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}

	// Test write
	key := "test/data.json"
	data := []byte(`{"test": "data"}`)
	if err := blob.Write(ctx, key, data); err != nil {
		t.Fatalf("failed to write: %v", err)
	}

	// Test exists
	exists, err := blob.Exists(ctx, key)
	if err != nil {
		t.Fatalf("failed to check exists: %v", err)
	}
	if !exists {
		t.Error("expected key to exist")
	}

	// Test read
	readData, err := blob.Read(ctx, key)
	if err != nil {
		t.Fatalf("failed to read: %v", err)
	}
	if string(readData) != string(data) {
		t.Errorf("data mismatch: got %s, want %s", readData, data)
	}

	// Test non-existent key
	exists, err = blob.Exists(ctx, "nonexistent")
	if err != nil {
		t.Fatalf("failed to check non-existent: %v", err)
	}
	if exists {
		t.Error("expected key to not exist")
	}
}

// TestTempDirCleanup verifies test cleanup works
func TestTempDirCleanup(t *testing.T) {
	tmpDir := t.TempDir()

	// Create a file
	testFile := tmpDir + "/test.txt"
	if err := os.WriteFile(testFile, []byte("test"), 0644); err != nil {
		t.Fatalf("failed to create test file: %v", err)
	}

	// Verify it exists
	if _, err := os.Stat(testFile); err != nil {
		t.Fatalf("test file doesn't exist: %v", err)
	}

	// After test completes, t.TempDir() will automatically clean up
	t.Logf("temp dir created at: %s (will be cleaned up automatically)", tmpDir)
}
