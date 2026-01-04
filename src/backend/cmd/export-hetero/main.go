package main

// Export heterogeneous graph preserving deck context
// Output: JSONL with deck structure intact

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/DataDog/zstd"
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
	Cards      []CardInDeck `json:"cards"`
}

type CardInDeck struct {
	Name      string `json:"name"`
	Count     int    `json:"count"`
	Partition string `json:"partition"`
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: export-hetero <data-dir> <output.jsonl>")
		os.Exit(1)
	}

	dataDir := os.Args[1]
	outputFile := os.Args[2]

	fmt.Println("Exporting heterogeneous graph structure...")

	var files []string
	filepath.Walk(dataDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Ext(path) == ".zst" {
			files = append(files, path)
		}
		return nil
	})

	out, _ := os.Create(outputFile)
	defer out.Close()

	encoder := json.NewEncoder(out)
	exported := 0

	errorCount := 0
	maxErrorsToLog := 10

	for _, file := range files {
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

		var obj map[string]interface{}
		if err := json.Unmarshal(decompressed, &obj); err != nil {
			errorCount++
			if errorCount <= maxErrorsToLog {
				fmt.Printf("⚠️  Failed to parse JSON in %s: %v\n", filepath.Base(file), err)
			}
			continue
		}

		// FIXED: Data is at root level, not under "collection"
		scrapedAt := time.Now().UTC().Format(time.RFC3339)
		deck := DeckRecord{
			DeckID:    filepath.Base(file),
			URL:       getString(obj, "url"),
			Source:    getString(obj, "source"),
			ScrapedAt: scrapedAt,
		}

		// Backfill source from URL or file path if missing
		if deck.Source == "" {
			deck.Source = inferSourceFromPath(deck.URL, file)
		}

		// Get type info - FIXED structure
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
			// Create map with timestamp aliases for backward compatibility
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
				"timestamp":  deck.ScrapedAt, // Alias for backward compatibility
				"created_at": deck.ScrapedAt, // Alias for backward compatibility
				"cards":      deck.Cards,
			}
			encoder.Encode(deckMap)
			exported++
		}
	}

	fmt.Printf("✓ Exported %d decks with full context\n", exported)
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
	return 0 // Fixed: Default to 0, not 1 (0 = unknown/missing)
}

func inferSourceFromPath(url string, filePath string) string {
	// Try URL first
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

	// Fallback to file path
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
		return "limitless-web" // Default for Pokemon
	}
	if strings.Contains(pathLower, "yugioh") || strings.Contains(pathLower, "ygo") {
		return "ygoprodeck-tournament" // Default for Yu-Gi-Oh
	}

	// Final fallback: use directory name
	dir := filepath.Base(filepath.Dir(filePath))
	if dir != "" && dir != "." {
		return dir
	}

	return "unknown"
}
