package dataset_test

import (
	"context"
	"fmt"
	"os"
	"testing"

	"github.com/go-redis/redis/v9"

	"collections/blob"
	"collections/games/magic/dataset"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/scryfall"
	"collections/logger"
	"collections/scraper"
)

func TestAll(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("DEBUG")
	redisAddr, ok := os.LookupEnv("REDIS_ADDR")
	if !ok {
		t.Skipf("missing REDIS_ADDR")
	}

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
	redisClient := redis.NewClient(&redis.Options{
		Addr: redisAddr,
	})
	datasets := []dataset.Dataset{
		scryfall.NewDataset(log, blob),
		deckbox.NewDataset(log, blob),
	}
	scraper := scraper.NewScraper(log, redisClient, blob)
	for _, d := range datasets {
		t.Run(d.Description().Name, func(t *testing.T) {
			err := d.Extract(ctx, scraper, &dataset.OptUpdateCollectionLimit{10})
			if err != nil {
				t.Fatalf("failed to update collection: %v", err)
			}
		})
	}
}
