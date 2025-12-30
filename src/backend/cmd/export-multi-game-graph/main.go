package main

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"collections/logger"

	"github.com/DataDog/zstd"
)

// MultiGamePair represents a card pair with game context
type MultiGamePair struct {
	Card1  string
	Card2  string
	Game1  string // MTG, YGO, PKM
	Game2  string
	Count  int
	DeckID string
	Source string
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: export-multi-game-graph <data-dir> <output.csv>")
		os.Exit(1)
	}

	dataDir := os.Args[1]
	outputFile := os.Args[2]

	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("INFO")

	fmt.Println("🎮 Building MULTI-GAME co-occurrence graph...")
	fmt.Println()

	// Find all collection files
	var files []string
	filepath.Walk(dataDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Ext(path) == ".zst" {
			files = append(files, path)
		}
		return nil
	})

	// Build co-occurrence map with game context
	pairCounts := make(map[string]*MultiGamePair) // key: "card1|card2|game1|game2"

	totalDecks := 0
	totalCards := 0
	totalEdges := 0
	gameStats := make(map[string]int)

	fmt.Printf("Found %d collection files\n", len(files))
	if len(files) == 0 {
		fmt.Println("⚠️  No .zst files found in data directory")
		return
	}

	processed := 0
	skipped := 0

	for _, file := range files {
		col, err := loadCollection(file)
		if err != nil {
			skipped++
			if skipped <= 5 {
				fmt.Printf("  ⚠️  Failed to load %s: %v\n", filepath.Base(file), err)
			}
			continue
		}

		// Infer game from collection type and file path
		game := inferGameFromCollection(col, file)
		if game == "" {
			skipped++
			if skipped <= 5 {
				fmt.Printf("  ⚠️  Could not infer game for %s\n", filepath.Base(file))
			}
			continue
		}

		processed++

		gameStats[game]++

		// Extract all cards from all partitions
		var allCards []string
		for _, part := range col.Partitions {
			for _, card := range part.Cards {
				for i := 0; i < card.Count; i++ {
					allCards = append(allCards, card.Name)
				}
			}
		}

		if len(allCards) < 2 {
			continue
		}

		totalDecks++
		totalCards += len(allCards)

		// Create pairs within this deck
		seenPairs := make(map[string]bool)
		for i := 0; i < len(allCards); i++ {
			for j := i + 1; j < len(allCards); j++ {
				card1, card2 := allCards[i], allCards[j]
				if card1 == card2 {
					continue
				}

				// Normalize pair (alphabetical)
				if card1 > card2 {
					card1, card2 = card2, card1
				}

				// Key includes game context
				key := fmt.Sprintf("%s|%s|%s|%s", card1, card2, game, game)
				if seenPairs[key] {
					continue
				}
				seenPairs[key] = true

				// Update count
				if pair, exists := pairCounts[key]; exists {
					pair.Count++
				} else {
					// Get source from collection, fallback to URL or file path
					source := col.Source
					if source == "" {
						// Try URL first
						urlLower := strings.ToLower(col.URL)
						if strings.Contains(urlLower, "deckbox") {
							source = "deckbox"
						} else if strings.Contains(urlLower, "scryfall") {
							source = "scryfall"
						} else if strings.Contains(urlLower, "mtgtop8") {
							source = "mtgtop8"
						} else if strings.Contains(urlLower, "goldfish") {
							source = "goldfish"
						} else {
							// Fallback to file path
							if strings.Contains(file, "deckbox") {
								source = "deckbox"
							} else if strings.Contains(file, "scryfall") {
								source = "scryfall"
							} else if strings.Contains(file, "mtgtop8") {
								source = "mtgtop8"
							} else {
								source = filepath.Base(filepath.Dir(file))
							}
						}
					}

					pairCounts[key] = &MultiGamePair{
						Card1:  card1,
						Card2:  card2,
						Game1:  game,
						Game2:  game,
						Count:  1,
						DeckID: filepath.Base(file),
						Source: source,
					}
					totalEdges++
				}
			}
		}
	}

	fmt.Printf("\n📊 Statistics:\n")
	fmt.Printf("   Files found: %d\n", len(files))
	fmt.Printf("   Files processed: %d\n", processed)
	fmt.Printf("   Files skipped: %d\n", skipped)
	fmt.Printf("   Total decks: %d\n", totalDecks)
	fmt.Printf("   Total cards: %d\n", totalCards)
	fmt.Printf("   Total edges: %d\n", totalEdges)
	fmt.Printf("\n   Game distribution:\n")
	for game, count := range gameStats {
		fmt.Printf("     %s: %d decks\n", game, count)
	}
	fmt.Println()

	// Write CSV
	out, err := os.Create(outputFile)
	if err != nil {
		log.Errorf(ctx, "Failed to create output file: %v", err)
		os.Exit(1)
	}
	defer out.Close()

	w := csv.NewWriter(out)
	defer w.Flush()

	// Header
	w.Write([]string{"NAME_1", "NAME_2", "GAME_1", "GAME_2", "COUNT", "DECK_ID", "SOURCE"})

	// Sort pairs for deterministic output
	var sortedPairs []*MultiGamePair
	for _, pair := range pairCounts {
		sortedPairs = append(sortedPairs, pair)
	}
	sort.Slice(sortedPairs, func(i, j int) bool {
		if sortedPairs[i].Card1 != sortedPairs[j].Card1 {
			return sortedPairs[i].Card1 < sortedPairs[j].Card1
		}
		if sortedPairs[i].Card2 != sortedPairs[j].Card2 {
			return sortedPairs[i].Card2 < sortedPairs[j].Card2
		}
		return sortedPairs[i].Game1 < sortedPairs[j].Game1
	})

	// Write data
	for _, pair := range sortedPairs {
		w.Write([]string{
			pair.Card1,
			pair.Card2,
			pair.Game1,
			pair.Game2,
			fmt.Sprintf("%d", pair.Count),
			pair.DeckID,
			pair.Source,
		})
	}

	fmt.Printf("✅ Successfully exported multi-game graph to %s\n", outputFile)
}

// SimpleCollection is a minimal collection structure for export
type SimpleCollection struct {
	ID         string      `json:"id"`
	URL        string      `json:"url"`
	Type       TypeInfo    `json:"type"`
	Partitions []Partition `json:"partitions"`
	Source     string      `json:"source,omitempty"`
}

type TypeInfo struct {
	Type  string          `json:"type"`
	Inner json.RawMessage `json:"inner"`
}

type Partition struct {
	Name  string     `json:"name"`
	Cards []CardDesc `json:"cards"`
}

type CardDesc struct {
	Name  string `json:"name"`
	Count int    `json:"count"`
}

func loadCollection(path string) (*SimpleCollection, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	// Decompress
	if filepath.Ext(path) == ".zst" {
		data, err = zstd.Decompress(nil, data)
		if err != nil {
			return nil, err
		}
	}

	var col SimpleCollection
	if err := json.Unmarshal(data, &col); err != nil {
		return nil, err
	}

	return &col, nil
}

func inferGameFromCollection(col *SimpleCollection, filePath string) string {
	// Infer from file path first (most reliable)
	pathLower := strings.ToLower(filePath)
	if strings.Contains(pathLower, "/yugioh/") || strings.Contains(pathLower, "/ygo/") {
		return "YGO"
	}
	if strings.Contains(pathLower, "/pokemon/") || strings.Contains(pathLower, "/pkm/") {
		return "PKM"
	}
	if strings.Contains(pathLower, "/magic/") || strings.Contains(pathLower, "/mtg/") {
		return "MTG"
	}

	// Infer from collection type
	typeStr := col.Type.Type

	// Infer from source/URL (check both Source field and URL if available)
	source := strings.ToLower(col.Source)
	urlLower := strings.ToLower(col.URL)

	// If source is empty, try to infer from URL
	if source == "" {
		if strings.Contains(urlLower, "deckbox") {
			source = "deckbox"
		} else if strings.Contains(urlLower, "scryfall") {
			source = "scryfall"
		} else if strings.Contains(urlLower, "mtgtop8") {
			source = "mtgtop8"
		} else if strings.Contains(urlLower, "goldfish") {
			source = "goldfish"
		}
	}

	// MTG types
	if strings.Contains(typeStr, "Deck") || strings.Contains(typeStr, "Set") || strings.Contains(typeStr, "Cube") {
		// Check if it's actually MTG by looking at source or other hints
		if strings.Contains(source, "mtg") || strings.Contains(source, "scryfall") ||
			strings.Contains(source, "goldfish") || strings.Contains(source, "deckbox") ||
			strings.Contains(source, "mtgtop8") {
			return "MTG"
		}
	}

	// Yu-Gi-Oh types
	if strings.Contains(typeStr, "YGO") {
		return "YGO"
	}

	// Pokemon types
	if strings.Contains(typeStr, "Pokemon") {
		return "PKM"
	}

	// Infer from source
	if strings.Contains(source, "yugioh") || strings.Contains(source, "ygoprodeck") {
		return "YGO"
	}
	if strings.Contains(source, "pokemon") || strings.Contains(source, "limitless") {
		return "PKM"
	}
	if strings.Contains(source, "mtg") || strings.Contains(source, "scryfall") ||
		strings.Contains(source, "deckbox") || strings.Contains(source, "mtgtop8") {
		return "MTG"
	}

	// Default: infer from path (already checked above, but fallback)
	if strings.Contains(pathLower, "magic") || strings.Contains(pathLower, "mtg") {
		return "MTG"
	}

	// Final fallback
	return "MTG"
}
