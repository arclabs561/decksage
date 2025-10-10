package games

import (
	"collections/blob"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"sync/atomic"
	"testing"
	"time"
)

// Simple test item that doesn't require type registry
type testItem struct {
	ID int `json:"id"`
}

func (i *testItem) Kind() string { return "Test" }
func (i *testItem) item()        {}

func deserializeTestItem(_ string, data []byte) (Item, error) {
	var item testItem
	if err := json.Unmarshal(data, &item); err != nil {
		return nil, err
	}
	return &item, nil
}

// TestIterItemsConcurrent tests parallel iteration behavior
func TestIterItemsConcurrent(t *testing.T) {
	ctx := context.Background()

	// Create temp blob storage
	tmpDir := t.TempDir()
	tmpBlob, err := blob.NewBucket(ctx, nil, "file://"+tmpDir)
	if err != nil {
		t.Fatal(err)
	}
	defer tmpBlob.Close(ctx)

	// Write test items (simple JSON)
	for i := 0; i < 100; i++ {
		key := fmt.Sprintf("test/item-%03d.json", i)
		data := []byte(fmt.Sprintf(`{"id": %d}`, i))
		if err := tmpBlob.Write(ctx, key, data); err != nil {
			t.Fatal(err)
		}
	}

	t.Run("all_items_processed", func(t *testing.T) {
		var processed atomic.Int32

		err := IterItemsBlobPrefix(
			ctx,
			tmpBlob,
			"test/",
			deserializeTestItem,
			func(item Item) error {
				processed.Add(1)
				return nil
			},
			&OptIterItemsParallel{Parallel: 16},
		)

		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if processed.Load() != 100 {
			t.Errorf("expected 100 items processed, got %d", processed.Load())
		}
	})

	t.Run("early_stop", func(t *testing.T) {
		var processed atomic.Int32

		err := IterItemsBlobPrefix(
			ctx,
			tmpBlob,
			"test/",
			deserializeTestItem,
			func(item Item) error {
				if processed.Add(1) >= 10 {
					return ErrIterItemsStop
				}
				return nil
			},
			&OptIterItemsParallel{Parallel: 4},
		)

		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		count := processed.Load()
		// Should stop around 10 (might be slightly more due to parallelism)
		if count < 10 || count > 20 {
			t.Errorf("expected ~10 items processed with early stop, got %d", count)
		}
	})

	t.Run("context_cancellation", func(t *testing.T) {
		cancelCtx, cancel := context.WithCancel(ctx)

		var processed atomic.Int32

		// Cancel after processing a few items
		go func() {
			for {
				if processed.Load() >= 5 {
					cancel()
					return
				}
				time.Sleep(1 * time.Millisecond)
			}
		}()

		err := IterItemsBlobPrefix(
			cancelCtx,
			tmpBlob,
			"test/",
			deserializeTestItem,
			func(item Item) error {
				processed.Add(1)
				time.Sleep(10 * time.Millisecond) // Slow processing
				return nil
			},
			&OptIterItemsParallel{Parallel: 4},
		)

		if !errors.Is(err, context.Canceled) {
			t.Errorf("expected context.Canceled, got %v", err)
		}
	})

	t.Run("parallel_errors_no_deadlock", func(t *testing.T) {
		// This tests the critical race condition fix
		err := IterItemsBlobPrefix(
			ctx,
			tmpBlob,
			"test/",
			deserializeTestItem,
			func(item Item) error {
				// All goroutines error - should not deadlock
				return fmt.Errorf("intentional error")
			},
			&OptIterItemsParallel{Parallel: 32},
		)

		if err == nil {
			t.Error("expected error, got nil")
		}

		if errors.Is(err, context.DeadlineExceeded) {
			t.Error("test timed out - likely deadlock!")
		}
	})

	t.Run("invalid_parallel_value", func(t *testing.T) {
		err := IterItemsBlobPrefix(
			ctx,
			tmpBlob,
			"test/",
			deserializeTestItem,
			func(item Item) error { return nil },
			&OptIterItemsParallel{Parallel: 0}, // Invalid
		)

		if err == nil {
			t.Error("expected error for parallel=0")
		}

		err = IterItemsBlobPrefix(
			ctx,
			tmpBlob,
			"test/",
			deserializeTestItem,
			func(item Item) error { return nil },
			&OptIterItemsParallel{Parallel: 2000}, // Too high
		)

		if err == nil {
			t.Error("expected error for parallel=2000")
		}
	})
}

// TestSectionRegexCaching tests that Section() caches compiled regexes
func TestSectionRegexCaching(t *testing.T) {
	opts := ResolvedUpdateOptions{
		SectionOnly: []string{"cards", "collections"},
	}

	// Call Section() multiple times - should not recompile
	for i := 0; i < 1000; i++ {
		if !opts.Section("cards") {
			t.Error("expected true for 'cards'")
		}
	}

	// Verify cache was populated
	if opts.sectionRegexCache == nil || len(opts.sectionRegexCache) == 0 {
		t.Error("regex cache should be populated")
	}

	if _, exists := opts.sectionRegexCache["cards"]; !exists {
		t.Error("'cards' pattern should be cached")
	}
}

// BenchmarkSectionWithoutCache benchmarks the old implementation
func BenchmarkSectionWithoutCache(b *testing.B) {
	sectionOnly := []string{"cards", "collections", "decks"}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		// Old implementation (recompiles every time)
		re, _ := regexp.Compile("(?i)cards")
		for _, s := range sectionOnly {
			re.MatchString(s)
		}
	}
}

// BenchmarkSectionWithCache benchmarks the new implementation
func BenchmarkSectionWithCache(b *testing.B) {
	opts := ResolvedUpdateOptions{
		SectionOnly: []string{"cards", "collections", "decks"},
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		opts.Section("cards")
	}
}
