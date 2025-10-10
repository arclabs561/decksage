package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/dgraph-io/badger/v3"
)

func main() {
	opts := badger.DefaultOptions("../../cache")
	opts.ReadOnly = true
	opts.Logger = nil

	db, err := badger.Open(opts)
	if err != nil {
		fmt.Printf("❌ Failed to open cache: %v\n", err)
		os.Exit(1)
	}
	defer db.Close()

	fmt.Println("📊 CACHE INVENTORY")
	fmt.Println("=" + strings.Repeat("=", 79))
	fmt.Println()

	// Count entries by category
	stats := make(map[string]int)
	onlyInCache := make(map[string][]string)

	err = db.View(func(txn *badger.Txn) error {
		it := txn.NewIterator(badger.DefaultIteratorOptions)
		defer it.Close()

		checked := 0
		for it.Rewind(); it.Valid(); it.Next() {
			key := string(it.Item().Key())
			checked++

			// Categorize
			if strings.HasPrefix(key, "games/") {
				parts := strings.Split(key, "/")
				if len(parts) >= 3 {
					category := strings.Join(parts[:3], "/")
					stats[category]++

					// Check if exists on disk
					diskPath := "../../data-full/" + key
					if _, err := os.Stat(diskPath); os.IsNotExist(err) {
						onlyInCache[category] = append(onlyInCache[category], key)
					}
				}
			} else if strings.HasPrefix(key, "scraper/") {
				stats["scraper/*"]++
			} else {
				stats["other"]++
			}

			if checked%50000 == 0 {
				fmt.Printf("\rProcessing... %d entries", checked)
			}
		}
		fmt.Printf("\rProcessed %d entries\n\n", checked)
		return nil
	})

	if err != nil {
		fmt.Printf("❌ Error: %v\n", err)
		os.Exit(1)
	}

	// Print statistics
	fmt.Println("Cache Contents:")
	for category, count := range stats {
		fmt.Printf("  %-30s %8d entries\n", category, count)
	}

	fmt.Println()
	fmt.Println("=" + strings.Repeat("=", 79))
	fmt.Println("MISSING FROM DISK (Only in Cache)")
	fmt.Println("=" + strings.Repeat("=", 79))
	fmt.Println()

	totalMissing := 0
	for category, keys := range onlyInCache {
		if len(keys) > 0 {
			fmt.Printf("  %-30s %8d missing\n", category, len(keys))
			totalMissing += len(keys)
		}
	}

	fmt.Println()
	fmt.Printf("🎯 Total entries only in cache: %d\n", totalMissing)
	fmt.Println()

	if totalMissing > 0 {
		fmt.Println("⚠️  These entries should be extracted to preserve paid proxy data!")
		fmt.Println("    Run: go run tools/cache-extract/main.go")
	} else {
		fmt.Println("✅ All cache data is already on disk")
	}
}
