//go:build integration
// +build integration

package dataset_test

import (
	"context"
	"fmt"
	"os"
	"testing"

	"collections/blob"
	"collections/games/magic/dataset"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/goldfish"
	"collections/games/magic/dataset/mtgtop8"
	"collections/games/magic/dataset/scryfall"
	"collections/logger"
	"collections/scraper"
)

// TestIntegrationAll runs full integration tests against live sources.
// This test is slow and makes real HTTP requests.
// Run with: go test -tags=integration -v ./games/magic/dataset/...
func TestIntegrationAll(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping integration test in short mode")
	}

	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("INFO")

	tmpDir, err := os.MkdirTemp("", "test-dataset-integration")
	if err != nil {
		t.Fatalf("failed to create tmp file: %v", err)
	}
	defer func() {
		if err := os.RemoveAll(tmpDir); err != nil {
			t.Errorf("failed to remove tmp dir %s: %v", tmpDir, err)
		}
	}()

	bucketURL := fmt.Sprintf("file://%s", tmpDir)
	t.Logf("using bucket url %s", bucketURL)
	blob, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create new blob: %v", err)
	}

	datasets := []dataset.Dataset{
		scryfall.NewDataset(log, blob),
		deckbox.NewDataset(log, blob),
		goldfish.NewDataset(log, blob),
		mtgtop8.NewDataset(log, blob),
	}
	scraper := scraper.NewScraper(log, blob)

	for _, d := range datasets {
		t.Run(d.Description().Name, func(t *testing.T) {
			err := d.Extract(ctx, scraper, &dataset.OptExtractItemLimit{Limit: 3})
			if err != nil {
				t.Fatalf("failed to extract dataset: %v", err)
			}
		})
	}
}
