package dataset_test

import (
	"context"
	"fmt"
	"os"
	"testing"

	"collections/blob"
	"collections/games/magic/dataset"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/scryfall"
	"collections/logger"
	limpet "github.com/arclabs561/limpet"
	limpetblob "github.com/arclabs561/limpet/blob"
)

func TestAll(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("DEBUG")
	tmpDir, err := os.MkdirTemp("", "test-dataset")
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
	scraperBucket, err := limpetblob.NewBucket(ctx, bucketURL, nil)
	if err != nil {
		t.Fatalf("failed to create limpet bucket: %v", err)
	}
	sc, err := limpet.NewClient(ctx, scraperBucket)
	if err != nil {
		t.Fatalf("failed to create limpet client: %v", err)
	}
	defer sc.Close()
	datasets := []dataset.Dataset{
		scryfall.NewDataset(log, blob),
		deckbox.NewDataset(log, blob),
	}
	for _, d := range datasets {
		t.Run(d.Description().Name, func(t *testing.T) {
			err := d.Extract(ctx, sc, &dataset.OptExtractItemLimit{Limit: 10})
			if err != nil {
				t.Fatalf("failed to update collection: %v", err)
			}
		})
	}
}
