package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/DataDog/zstd"
	"github.com/dgraph-io/badger/v3"
)

var (
	dryRun       = flag.Bool("dry-run", false, "Preview what would be extracted without writing")
	onConflict   = flag.String("on-conflict", "skip", "What to do if file exists: skip|overwrite")
	workers      = flag.Int("workers", 8, "Number of parallel workers")
	sourceFilter = flag.String("source", "", "Only extract specific source (e.g., 'goldfish')")
	onlyGames    = flag.Bool("only-games", false, "Only extract game data, skip scraper HTTP cache")
	onlyScraper  = flag.Bool("only-scraper", false, "Only extract scraper HTTP cache, skip game data")
)

func main() {
	flag.Parse()

	fmt.Println("🔄 CACHE EXTRACTION TOOL")
	fmt.Println(strings.Repeat("=", 80))
	fmt.Println()

	if *dryRun {
		fmt.Println("🔍 DRY RUN MODE - No files will be written")
		fmt.Println()
	}

	opts := badger.DefaultOptions("../../cache")
	opts.ReadOnly = true
	opts.Logger = nil

	db, err := badger.Open(opts)
	if err != nil {
		fmt.Printf("❌ Failed to open cache: %v\n", err)
		os.Exit(1)
	}
	defer db.Close()

	fmt.Println("✅ Cache opened successfully")
	fmt.Println()

	// Collect keys to extract
	var keysToExtract []string
	categories := make(map[string]int)

	err = db.View(func(txn *badger.Txn) error {
		it := txn.NewIterator(badger.DefaultIteratorOptions)
		defer it.Close()

		checked := 0
		for it.Rewind(); it.Valid(); it.Next() {
			key := string(it.Item().Key())
			checked++

			// Filter based on flags
			includeEntry := false
			if strings.HasPrefix(key, "games/") && !*onlyScraper {
				includeEntry = true
			}
			if strings.HasPrefix(key, "scraper/") && !*onlyGames {
				includeEntry = true
			}

			if !includeEntry {
				continue
			}

			// Filter by source if specified
			if *sourceFilter != "" && strings.HasPrefix(key, "games/") {
				parts := strings.Split(key, "/")
				if len(parts) >= 3 && parts[2] != *sourceFilter {
					continue
				}
			}

			// Check if exists on disk
			diskPath := "../../data-full/" + key
			if _, err := os.Stat(diskPath); err == nil {
				if *onConflict == "skip" {
					continue // Already exists, skip
				}
			}

			keysToExtract = append(keysToExtract, key)

			// Categorize for stats
			if strings.HasPrefix(key, "games/") {
				parts := strings.Split(key, "/")
				if len(parts) >= 3 {
					categories[strings.Join(parts[:3], "/")]++
				}
			} else if strings.HasPrefix(key, "scraper/") {
				parts := strings.Split(key, "/")
				if len(parts) >= 2 {
					categories["scraper/"+parts[1]]++
				}
			}

			if checked%50000 == 0 {
				fmt.Printf("\rScanning... %d entries", checked)
			}
		}
		fmt.Printf("\rScanned %d entries\n\n", checked)
		return nil
	})

	if err != nil {
		fmt.Printf("❌ Error scanning cache: %v\n", err)
		os.Exit(1)
	}

	if len(keysToExtract) == 0 {
		fmt.Println("✅ No missing entries - all cache data already on disk")
		return
	}

	fmt.Printf("📋 Found %d entries to extract:\n\n", len(keysToExtract))
	for category, count := range categories {
		fmt.Printf("   %-35s %8d entries\n", category, count)
	}
	fmt.Println()

	// Estimate size
	totalSize := int64(0)
	db.View(func(txn *badger.Txn) error {
		for _, key := range keysToExtract[:min(1000, len(keysToExtract))] {
			item, err := txn.Get([]byte(key))
			if err == nil {
				totalSize += item.ValueSize()
			}
		}
		return nil
	})
	avgSize := totalSize / int64(min(1000, len(keysToExtract)))
	estimatedTotal := avgSize * int64(len(keysToExtract))
	fmt.Printf("📊 Estimated extraction size: %.2f GB\n", float64(estimatedTotal)/(1024*1024*1024))
	fmt.Println()

	if *dryRun {
		fmt.Println("Sample keys that would be extracted:")
		for i, key := range keysToExtract {
			if i >= 20 {
				fmt.Printf("   ... and %d more\n", len(keysToExtract)-20)
				break
			}
			fmt.Printf("   %s\n", key)
		}
		fmt.Println()
		fmt.Println("Run without --dry-run to actually extract")
		return
	}

	// Confirm extraction
	fmt.Printf("⚠️  About to extract %d entries (%.2f GB estimated)\n",
		len(keysToExtract), float64(estimatedTotal)/(1024*1024*1024))
	fmt.Print("Continue? [y/N]: ")
	var response string
	fmt.Scanln(&response)
	if strings.ToLower(response) != "y" {
		fmt.Println("Aborted")
		return
	}

	// Extract in parallel
	fmt.Println()
	fmt.Println("🚀 Starting extraction...")
	fmt.Println()

	var (
		extracted atomic.Int64
		skipped   atomic.Int64
		errors    atomic.Int64
	)

	start := time.Now()

	// Create work channel
	work := make(chan string, 100)
	wg := &sync.WaitGroup{}

	// Start workers
	for i := 0; i < *workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			extractWorker(db, work, &extracted, &skipped, &errors)
		}()
	}

	// Progress reporter
	done := make(chan bool)
	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		lastPrinted := ""
		for {
			select {
			case <-done:
				// Clear the line
				fmt.Print("\r" + strings.Repeat(" ", len(lastPrinted)) + "\r")
				return
			case <-ticker.C:
				e := extracted.Load()
				total := int64(len(keysToExtract))
				pct := 100.0 * float64(e) / float64(total)
				rate := float64(e) / time.Since(start).Seconds()
				remaining := time.Duration(float64(total-e)/rate) * time.Second
				line := fmt.Sprintf("📈 Progress: %d/%d (%.1f%%) - %.1f/s - ETA: %v         ",
					e, total, pct, rate, remaining.Round(time.Second))
				fmt.Print("\r" + line)
				lastPrinted = line
			}
		}
	}()

	// Send work
	for _, key := range keysToExtract {
		work <- key
	}
	close(work)

	// Wait for completion
	wg.Wait()
	done <- true

	elapsed := time.Since(start)

	fmt.Println()
	fmt.Println()
	fmt.Println(strings.Repeat("=", 80))
	fmt.Println("EXTRACTION COMPLETE")
	fmt.Println(strings.Repeat("=", 80))
	fmt.Println()
	fmt.Printf("✅ Extracted: %d\n", extracted.Load())
	fmt.Printf("⏭️  Skipped:   %d\n", skipped.Load())
	fmt.Printf("❌ Errors:    %d\n", errors.Load())
	fmt.Printf("⏱️  Duration:  %v\n", elapsed.Round(time.Second))
	if elapsed.Seconds() > 0 {
		fmt.Printf("📈 Rate:      %.1f entries/sec\n", float64(extracted.Load())/elapsed.Seconds())
	}
	fmt.Println()

	if errors.Load() > 0 {
		fmt.Println("⚠️  Some entries failed to extract")
	} else {
		fmt.Println("🎉 All entries extracted successfully!")
		fmt.Println()
		fmt.Println("Next steps:")
		fmt.Println("  1. Verify game data: go run cmd/analyze-decks/main.go data-full/games/magic")
		fmt.Println("  2. Count HTTP cache: find data-full/scraper -name '*.zst' | wc -l")
		fmt.Println("  3. Re-parse with updated parsers if needed")
	}
}

func extractWorker(db *badger.DB, work chan string, extracted, skipped, errors *atomic.Int64) {
	db.View(func(txn *badger.Txn) error {
		for key := range work {
			if err := extractEntry(txn, key); err != nil {
				errors.Add(1)
			} else {
				extracted.Add(1)
			}
		}
		return nil
	})
}

func extractEntry(txn *badger.Txn, key string) error {
	item, err := txn.Get([]byte(key))
	if err != nil {
		return fmt.Errorf("failed to get from cache: %w", err)
	}

	var data []byte
	err = item.Value(func(val []byte) error {
		data = make([]byte, len(val))
		copy(data, val)
		return nil
	})
	if err != nil {
		return fmt.Errorf("failed to read value: %w", err)
	}

	// Validate it's valid JSON (for both game data and scraper responses)
	var testUnmarshal interface{}
	if err := json.Unmarshal(data, &testUnmarshal); err != nil {
		return fmt.Errorf("invalid JSON in cache: %w", err)
	}

	// Write to disk with proper compression
	// BadgerDB stores uncompressed, but blob storage expects zstd compression
	diskPath := "../../data-full/" + key
	dir := filepath.Dir(diskPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("failed to create directory: %w", err)
	}

	// Compress data using zstd
	compressed, err := zstd.Compress(nil, data)
	if err != nil {
		return fmt.Errorf("failed to compress data: %w", err)
	}

	if err := os.WriteFile(diskPath, compressed, 0644); err != nil {
		return fmt.Errorf("failed to write file: %w", err)
	}

	// Create .attrs file for consistency
	attrsPath := diskPath + ".attrs"
	attrsData := []byte("{}")
	os.WriteFile(attrsPath, attrsData, 0644)
	// Ignore errors on attrs - not critical

	return nil
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
