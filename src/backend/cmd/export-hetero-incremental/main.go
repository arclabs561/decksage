package main

// Export-hetero-incremental: Only exports decks that are new or have changed since last export

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/DataDog/zstd"

	"collections/blob"
	"collections/games"
	"collections/logger"
)

type DeckRecord struct {
	DeckID     string       `json:"deck_id"`
	Archetype  string       `json:"archetype"`
	Format     string       `json:"format"`
	URL        string       `json:"url"`
	Source     string       `json:"source,omitempty"`
	Player     string       `json:"player,omitempty"`
	Event      string       `json:"event,omitempty"`
	Placement  int          `json:"placement,omitempty"`
	EventDate  string       `json:"event_date,omitempty"`
	ScrapedAt  string       `json:"scraped_at,omitempty"`
	UpdatedAt  string       `json:"updated_at,omitempty"`
	Version    int          `json:"version,omitempty"`
	Cards      []CardInDeck `json:"cards"`
}

type CardInDeck struct {
	Name      string `json:"name"`
	Count     int    `json:"count"`
	Partition string `json:"partition"`
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: export-hetero-incremental <data-dir> <output.jsonl> [tracker-prefix]")
		fmt.Println("  tracker-prefix: Optional prefix for export tracking (default: data-dir)")
		os.Exit(1)
	}

	dataDir := os.Args[1]
	outputFile := os.Args[2]
	trackerPrefix := dataDir
	if len(os.Args) >= 4 {
		trackerPrefix = os.Args[3]
	}

	ctx := context.Background()
	log := logger.NewLogger(ctx)

	// Create blob bucket for tracking (using file:// for local storage)
	trackerBlob, err := blob.NewBucket(ctx, log, "file://"+filepath.Dir(dataDir))
	if err != nil {
		fmt.Printf("Error: Failed to create blob bucket: %v\n", err)
		os.Exit(1)
	}
	defer trackerBlob.Close(ctx)

	// Load export tracker
	tracker := games.NewExportTracker(log, trackerBlob, trackerPrefix)
	if err := tracker.Load(ctx); err != nil {
		fmt.Printf("Warning: Failed to load export tracker: %v (starting fresh)\n", err)
	}

	fmt.Println("Exporting new/changed decks incrementally...")

	var files []string
	filepath.Walk(dataDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Ext(path) == ".zst" {
			files = append(files, path)
		}
		return nil
	})

	// Determine relative blob key for tracking
	relPath := func(fullPath string) string {
		rel, _ := filepath.Rel(dataDir, fullPath)
		return rel
	}

	out, err := os.OpenFile(outputFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		fmt.Printf("Error: Failed to open output file: %v\n", err)
		os.Exit(1)
	}
	defer out.Close()

	encoder := json.NewEncoder(out)
	exported := 0
	skipped := 0

	errorCount := 0
	maxErrorsToLog := 10

	for _, file := range files {
		blobKey := relPath(file)
		info, err := os.Stat(file)
		if err != nil {
			errorCount++
			if errorCount <= maxErrorsToLog {
				fmt.Printf("⚠️  Failed to stat %s: %v\n", filepath.Base(file), err)
			}
			continue
		}

		data, err := os.ReadFile(file)
		if err != nil {
			errorCount++
			if errorCount <= maxErrorsToLog {
				fmt.Printf("⚠️  Failed to read %s: %v\n", filepath.Base(file), err)
			}
			continue
		}

		decompressed, err := zstd.Decompress(nil, data)
		if err != nil {
			errorCount++
			if errorCount <= maxErrorsToLog {
				fmt.Printf("⚠️  Failed to decompress %s: %v\n", filepath.Base(file), err)
			}
			continue
		}

		// Extract Collection metadata for better change detection
		var collectionUpdatedAt time.Time
		var collectionVersion int
		if len(decompressed) > 0 {
			var obj map[string]interface{}
			if json.Unmarshal(decompressed, &obj) == nil {
				// Try to get updated_at or scraped_at
				if updatedAtStr := getString(obj, "updated_at"); updatedAtStr != "" {
					if t, err := time.Parse(time.RFC3339, updatedAtStr); err == nil {
						collectionUpdatedAt = t
					}
				} else if scrapedAtStr := getString(obj, "scraped_at"); scrapedAtStr != "" {
					if t, err := time.Parse(time.RFC3339, scrapedAtStr); err == nil {
						collectionUpdatedAt = t
					}
				}
				// Get version if available
				if v := getInt(obj, "version"); v > 0 {
					collectionVersion = v
				}
			}
		}

		// Check if should export (using Collection metadata if available)
		if !tracker.ShouldExport(ctx, blobKey, info.ModTime(), collectionUpdatedAt, collectionVersion) {
			skipped++
			continue
		}

		var obj map[string]interface{}
		if err := json.Unmarshal(decompressed, &obj); err != nil {
			errorCount++
			if errorCount <= maxErrorsToLog {
				fmt.Printf("⚠️  Failed to parse JSON in %s: %v\n", filepath.Base(file), err)
			}
			continue
		}

		// Extract versioning metadata
		scrapedAt := getString(obj, "scraped_at")
		updatedAt := getString(obj, "updated_at")
		version := getInt(obj, "version")
		if scrapedAt == "" {
			scrapedAt = time.Now().UTC().Format(time.RFC3339)
		}

		deck := DeckRecord{
			DeckID:    filepath.Base(file),
			URL:       getString(obj, "url"),
			Source:    getString(obj, "source"),
			ScrapedAt: scrapedAt,
			UpdatedAt: updatedAt,
			Version:   version,
		}

		// Backfill source from URL or file path if missing
		if deck.Source == "" {
			deck.Source = inferSourceFromPath(deck.URL, file)
		}

		// Get type info
		if typeObj, ok := obj["type"].(map[string]interface{}); ok {
			if inner, ok := typeObj["inner"].(map[string]interface{}); ok {
				deck.Archetype = getString(inner, "archetype")
				deck.Format = getString(inner, "format")
				deck.Player = getString(inner, "player")
				deck.Event = getString(inner, "event")
				deck.Placement = getInt(inner, "placement")
				deck.EventDate = getString(inner, "event_date")
			}
		}

		// Get cards
		if parts, ok := obj["partitions"].([]interface{}); ok {
			for _, p := range parts {
				part := p.(map[string]interface{})
				partName := getString(part, "name")

				if cards, ok := part["cards"].([]interface{}); ok {
					for _, c := range cards {
						card := c.(map[string]interface{})
						deck.Cards = append(deck.Cards, CardInDeck{
							Name:      getString(card, "name"),
							Count:     getInt(card, "count"),
							Partition: partName,
						})
					}
				}
			}
		}

		if len(deck.Cards) > 0 {
			deckMap := map[string]interface{}{
				"deck_id":    deck.DeckID,
				"archetype":  deck.Archetype,
				"format":     deck.Format,
				"url":        deck.URL,
				"source":     deck.Source,
				"player":     deck.Player,
				"event":      deck.Event,
				"placement":  deck.Placement,
				"event_date": deck.EventDate,
				"scraped_at": deck.ScrapedAt,
				"updated_at": deck.UpdatedAt,
				"version":    deck.Version,
				"timestamp":  deck.ScrapedAt, // Alias for backward compatibility
				"created_at": deck.ScrapedAt, // Alias for backward compatibility
				"cards":      deck.Cards,
			}
			encoder.Encode(deckMap)
			exported++
			tracker.MarkExported(blobKey)
		}
	}

	// Save tracker
	if err := tracker.Save(ctx); err != nil {
		fmt.Printf("Warning: Failed to save export tracker: %v\n", err)
	}

	total, recent := tracker.GetStats()
	fmt.Printf("✓ Exported %d new/changed decks (skipped %d unchanged)\n", exported, skipped)
	fmt.Printf("  Total tracked: %d, Recent (24h): %d\n", total, recent)
	if errorCount > 0 {
		if errorCount > maxErrorsToLog {
			fmt.Printf("⚠️  %d additional errors occurred (showing first %d)\n", errorCount-maxErrorsToLog, maxErrorsToLog)
		}
		fmt.Printf("⚠️  Total errors: %d\n", errorCount)
	}
}

func getString(m map[string]interface{}, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

func getInt(m map[string]interface{}, key string) int {
	if v, ok := m[key].(float64); ok {
		return int(v)
	}
	return 0
}

func inferSourceFromPath(url string, filePath string) string {
	urlLower := strings.ToLower(url)
	if strings.Contains(urlLower, "mtgtop8.com") || strings.Contains(urlLower, "mtgtop8") {
		return "mtgtop8"
	}
	if strings.Contains(urlLower, "mtggoldfish.com") || strings.Contains(urlLower, "goldfish") {
		return "goldfish"
	}
	if strings.Contains(urlLower, "deckbox.org") || strings.Contains(urlLower, "deckbox") {
		return "deckbox"
	}
	if strings.Contains(urlLower, "limitlesstcg.com") || strings.Contains(urlLower, "limitless") {
		return "limitless-web"
	}
	if strings.Contains(urlLower, "ygoprodeck.com") || strings.Contains(urlLower, "ygoprodeck") {
		return "ygoprodeck-tournament"
	}
	if strings.Contains(urlLower, "scryfall.com") || strings.Contains(urlLower, "scryfall") {
		return "scryfall"
	}

	pathLower := strings.ToLower(filePath)
	if strings.Contains(pathLower, "mtgtop8") {
		return "mtgtop8"
	}
	if strings.Contains(pathLower, "goldfish") {
		return "goldfish"
	}
	if strings.Contains(pathLower, "deckbox") {
		return "deckbox"
	}
	if strings.Contains(pathLower, "limitless") {
		return "limitless-web"
	}
	if strings.Contains(pathLower, "ygoprodeck") {
		return "ygoprodeck-tournament"
	}
	if strings.Contains(pathLower, "scryfall") {
		return "scryfall"
	}
	if strings.Contains(pathLower, "pokemon") {
		return "limitless-web"
	}
	if strings.Contains(pathLower, "yugioh") || strings.Contains(pathLower, "ygo") {
		return "ygoprodeck-tournament"
	}

	dir := filepath.Base(filepath.Dir(filePath))
	if dir != "" && dir != "." {
		return dir
	}

	return "unknown"
}

