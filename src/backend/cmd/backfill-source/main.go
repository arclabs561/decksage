package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	"collections/games"
	_ "collections/games/magic/game"   // Import for type registration
	_ "collections/games/pokemon/game" // Import for type registration
	_ "collections/games/yugioh/game"  // Import for type registration
	"collections/logger"

	"github.com/DataDog/zstd"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: go run main.go <data-dir>")
		fmt.Println("Example: go run main.go ../../data-full/games/magic")
		os.Exit(1)
	}

	dataDir := os.Args[1]
	ctx := context.Background()
	lgr := logger.NewLogger(ctx)

	fmt.Println("🔄 Backfilling source field for existing collections...")
	fmt.Printf("Directory: %s\n\n", dataDir)

	updated := 0
	skipped := 0
	errors := 0
	total := 0

	// Walk all .zst files
	err := filepath.Walk(dataDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		// Skip non-.zst files
		if info.IsDir() || filepath.Ext(path) != ".zst" {
			return nil
		}

		total++
		if total%1000 == 0 {
			fmt.Printf("Processed %d files...\n", total)
		}

		// Read compressed file
		data, err := os.ReadFile(path)
		if err != nil {
			lgr.Errorf(ctx, "Failed to read %s: %v", path, err)
			errors++
			return nil
		}

		// Decompress
		decompressed, err := zstd.Decompress(nil, data)
		if err != nil {
			lgr.Errorf(ctx, "Failed to decompress %s: %v", path, err)
			errors++
			return nil
		}

		// Parse as Collection
		var collection games.Collection
		if err := json.Unmarshal(decompressed, &collection); err != nil {
			// Not a collection, skip
			if total <= 5 {
				lgr.Warnf(ctx, "Failed to parse %s as collection: %v", filepath.Base(path), err)
			}
			return nil
		}

		// Skip if source already set
		if collection.Source != "" {
			skipped++
			if skipped <= 5 {
				lgr.Infof(ctx, "Skipped %s: already has source=%s", filepath.Base(path), collection.Source)
			}
			return nil
		}

		// Skip non-decks (sets, cubes, cards)
		if collection.Type.Type != "Deck" {
			if total <= 5 {
				lgr.Infof(ctx, "Skipped %s: type=%s (not a deck)", filepath.Base(path), collection.Type.Type)
			}
			return nil
		}

		// Infer source from path (more reliable than URL which might be empty)
		source := inferSourceFromPath(path)
		if source == "" {
			// Fallback to URL
			source = inferSource(collection.URL)
		}
		if source == "" {
			lgr.Warnf(ctx, "Could not infer source from path %s or URL %s", path, collection.URL)
			return nil
		}

		collection.Source = source

		if updated < 5 {
			lgr.Infof(ctx, "Backfilled %s: source=%s", filepath.Base(path), source)
		}

		// Re-marshal
		updatedJSON, err := json.Marshal(&collection)
		if err != nil {
			lgr.Errorf(ctx, "Failed to marshal %s: %v", path, err)
			errors++
			return nil
		}

		// Re-compress
		compressed, err := zstd.CompressLevel(nil, updatedJSON, zstd.DefaultCompression)
		if err != nil {
			lgr.Errorf(ctx, "Failed to compress %s: %v", path, err)
			errors++
			return nil
		}

		// Write back
		if err := os.WriteFile(path, compressed, 0644); err != nil {
			lgr.Errorf(ctx, "Failed to write %s: %v", path, err)
			errors++
			return nil
		}

		updated++
		if updated%100 == 0 {
			fmt.Printf("Updated %d collections...\n", updated)
		}

		return nil
	})

	if err != nil {
		log.Fatalf("Walk error: %v", err)
	}

	fmt.Println("\n✅ Backfill complete!")
	fmt.Printf("Total .zst files: %d\n", total)
	fmt.Printf("Updated: %d\n", updated)
	fmt.Printf("Skipped (already had source): %d\n", skipped)
	fmt.Printf("Errors: %d\n", errors)
}

func inferSource(url string) string {
	url = strings.ToLower(url)

	if strings.Contains(url, "mtgtop8.com") {
		return "mtgtop8"
	}
	if strings.Contains(url, "mtggoldfish.com") {
		return "goldfish"
	}
	if strings.Contains(url, "deckbox.org") {
		return "deckbox"
	}
	if strings.Contains(url, "scryfall.com") {
		return "scryfall"
	}

	return ""
}

func inferSourceFromPath(path string) string {
	path = strings.ToLower(path)

	if strings.Contains(path, "/mtgtop8/") {
		return "mtgtop8"
	}
	if strings.Contains(path, "/goldfish/") {
		return "goldfish"
	}
	if strings.Contains(path, "/deckbox/") {
		return "deckbox"
	}
	if strings.Contains(path, "/scryfall/") {
		return "scryfall"
	}

	return ""
}
