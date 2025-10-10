package main

// Export heterogeneous graph preserving deck context
// Output: JSONL with deck structure intact

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/DataDog/zstd"
)

type DeckRecord struct {
	DeckID    string       `json:"deck_id"`
	Archetype string       `json:"archetype"`
	Format    string       `json:"format"`
	URL       string       `json:"url"`
	Source    string       `json:"source,omitempty"`
	Player    string       `json:"player,omitempty"`
	Event     string       `json:"event,omitempty"`
	Placement int          `json:"placement,omitempty"`
	EventDate string       `json:"event_date,omitempty"`
	Cards     []CardInDeck `json:"cards"`
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

	for _, file := range files {
		data, err := os.ReadFile(file)
		if err != nil {
			continue
		}

		decompressed, err := zstd.Decompress(nil, data)
		if err != nil {
			continue
		}

		var obj map[string]interface{}
		if err := json.Unmarshal(decompressed, &obj); err != nil {
			continue
		}

		// FIXED: Data is at root level, not under "collection"
		deck := DeckRecord{
			DeckID: filepath.Base(file),
			URL:    getString(obj, "url"),
			Source: getString(obj, "source"),
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
			encoder.Encode(deck)
			exported++
		}
	}

	fmt.Printf("✓ Exported %d decks with full context\n", exported)
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
