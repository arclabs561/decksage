package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"collections/games/magic/game"

	"github.com/DataDog/zstd"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: go run main.go <data-dir>")
		os.Exit(1)
	}

	dataDir := os.Args[1]

	// Scan all collections
	var files []string
	filepath.Walk(dataDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Ext(path) == ".zst" {
			files = append(files, path)
		}
		return nil
	})

	fmt.Printf("📊 Analyzing %d collections...\n\n", len(files))

	// Track stats by collection type
	deckStats := struct {
		count      int
		totalCards int
		totalEdges int
		formats    map[string]int
	}{
		formats: make(map[string]int),
	}

	setStats := struct {
		count      int
		totalCards int
		totalEdges int
	}{}

	cubeStats := struct {
		count      int
		totalCards int
		totalEdges int
	}{}

	for _, file := range files {
		col, err := loadCollection(file)
		if err != nil {
			continue
		}

		// Count cards
		numCards := 0
		for _, p := range col.Partitions {
			numCards += len(p.Cards)
		}

		// Count potential edges (n choose 2)
		numEdges := 0
		for _, p := range col.Partitions {
			n := len(p.Cards)
			numEdges += n * (n - 1) / 2
		}

		switch col.Type.Type {
		case "Deck":
			deckStats.count++
			deckStats.totalCards += numCards
			deckStats.totalEdges += numEdges

			// Get format
			if deck, ok := col.Type.Inner.(*game.CollectionTypeDeck); ok {
				deckStats.formats[deck.Format]++
			}

		case "Set":
			setStats.count++
			setStats.totalCards += numCards
			setStats.totalEdges += numEdges

		case "Cube":
			cubeStats.count++
			cubeStats.totalCards += numCards
			cubeStats.totalEdges += numEdges
		}
	}

	// Print analysis
	fmt.Println("═══════════════════════════════════════════════════════════")
	fmt.Println("COLLECTION TYPE BREAKDOWN")
	fmt.Println("═══════════════════════════════════════════════════════════")

	total := deckStats.count + setStats.count + cubeStats.count
	totalEdges := deckStats.totalEdges + setStats.totalEdges + cubeStats.totalEdges

	fmt.Printf("\n📦 DECKS: %d collections (%.1f%%)\n", deckStats.count, 100.0*float64(deckStats.count)/float64(total))
	fmt.Printf("   Total cards: %d\n", deckStats.totalCards)
	fmt.Printf("   Potential edges: %d (%.1f%% of total)\n", deckStats.totalEdges, 100.0*float64(deckStats.totalEdges)/float64(totalEdges))
	fmt.Printf("   Avg cards per deck: %.1f\n", float64(deckStats.totalCards)/float64(deckStats.count))
	fmt.Printf("\n   Format distribution:\n")

	type formatCount struct {
		format string
		count  int
	}
	var formats []formatCount
	for f, c := range deckStats.formats {
		formats = append(formats, formatCount{f, c})
	}
	sort.Slice(formats, func(i, j int) bool {
		return formats[i].count > formats[j].count
	})
	for _, fc := range formats {
		fmt.Printf("     - %s: %d decks\n", fc.format, fc.count)
	}

	fmt.Printf("\n🎴 SETS: %d collections (%.1f%%)\n", setStats.count, 100.0*float64(setStats.count)/float64(total))
	fmt.Printf("   Total cards: %d\n", setStats.totalCards)
	fmt.Printf("   Potential edges: %d (%.1f%% of total)\n", setStats.totalEdges, 100.0*float64(setStats.totalEdges)/float64(totalEdges))
	fmt.Printf("   Avg cards per set: %.1f\n", float64(setStats.totalCards)/float64(setStats.count))

	if cubeStats.count > 0 {
		fmt.Printf("\n🎲 CUBES: %d collections (%.1f%%)\n", cubeStats.count, 100.0*float64(cubeStats.count)/float64(total))
		fmt.Printf("   Total cards: %d\n", cubeStats.totalCards)
		fmt.Printf("   Potential edges: %d (%.1f%% of total)\n", cubeStats.totalEdges, 100.0*float64(cubeStats.totalEdges)/float64(totalEdges))
	}

	fmt.Println("\n═══════════════════════════════════════════════════════════")
	fmt.Println("EDGE CONTAMINATION ANALYSIS")
	fmt.Println("═══════════════════════════════════════════════════════════")

	deckPct := 100.0 * float64(deckStats.totalEdges) / float64(totalEdges)
	setPct := 100.0 * float64(setStats.totalEdges) / float64(totalEdges)

	fmt.Printf("\nDeck edges: %d (%.1f%%)\n", deckStats.totalEdges, deckPct)
	fmt.Printf("Set edges:  %d (%.1f%%)\n", setStats.totalEdges, setPct)

	if setPct > 50 {
		fmt.Printf("\n⚠️  WARNING: Sets contribute %.1f%% of edges!\n", setPct)
		fmt.Printf("   This may contaminate embeddings with 'printed together'\n")
		fmt.Printf("   rather than 'played together' signals.\n")
		fmt.Printf("\n   Recommendation: Train deck-only embeddings\n")
	}

	fmt.Println("\n═══════════════════════════════════════════════════════════")
}

func loadCollection(path string) (*game.Collection, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	if filepath.Ext(path) == ".zst" {
		data, err = zstd.Decompress(nil, data)
		if err != nil {
			return nil, err
		}
	}

	var col game.Collection
	if err := json.Unmarshal(data, &col); err != nil {
		return nil, err
	}

	return &col, nil
}
