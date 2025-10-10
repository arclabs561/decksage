package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"collections/games/magic/game"

	"github.com/DataDog/zstd"
)

type pair struct {
	card1 string
	card2 string
}

type counts struct {
	set      int
	multiset int
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: go run main.go <data-dir> <output.csv>")
		os.Exit(1)
	}

	dataDir := os.Args[1]
	outputFile := os.Args[2]

	fmt.Println("🎯 Building DECK-ONLY co-occurrence graph...")
	fmt.Println("   (Excluding sets and cubes to avoid contamination)")
	fmt.Println()

	// Find all collection files
	var files []string
	filepath.Walk(dataDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Ext(path) == ".zst" {
			files = append(files, path)
		}
		return nil
	})

	// Build co-occurrence map
	pairCounts := make(map[pair]*counts)

	totalDecks := 0
	skippedSets := 0
	skippedCubes := 0
	totalCards := 0
	totalEdges := 0

	for i, file := range files {
		col, err := loadCollection(file)
		if err != nil {
			fmt.Printf("⚠️  Failed to load %s: %v\n", filepath.Base(file), err)
			continue
		}

		// CRITICAL: Skip sets and cubes
		if col.Type.Type == "Set" {
			skippedSets++
			continue
		}
		if col.Type.Type == "Cube" {
			skippedCubes++
			continue
		}

		// Only process decks
		collectionCards := 0
		collectionEdges := 0

		for _, partition := range col.Partitions {
			cards := partition.Cards
			n := len(cards)
			collectionCards += n

			for i := 0; i < n; i++ {
				c := cards[i]

				if c.Count > 1 {
					p := makePair(c.Name, c.Name)
					if pairCounts[p] == nil {
						pairCounts[p] = &counts{}
					}
					pairCounts[p].multiset += c.Count - 1
					collectionEdges++
				}

				for j := i + 1; j < n; j++ {
					d := cards[j]
					p := makePair(c.Name, d.Name)
					if pairCounts[p] == nil {
						pairCounts[p] = &counts{}
					}
					pairCounts[p].set += 1
					pairCounts[p].multiset += c.Count * d.Count
					collectionEdges++
				}
			}
		}

		totalDecks++
		totalCards += collectionCards
		totalEdges += collectionEdges

		pct := float64(i+1) / float64(len(files)) * 100
		fmt.Printf("✓ [%d/%d %.1f%%] Deck: %d cards, %d edges → %d unique pairs\n",
			i+1, len(files), pct, collectionCards, collectionEdges, len(pairCounts))
	}

	fmt.Printf("\n📊 Summary:\n")
	fmt.Printf("   Decks processed: %d\n", totalDecks)
	fmt.Printf("   Sets skipped: %d\n", skippedSets)
	fmt.Printf("   Cubes skipped: %d\n", skippedCubes)
	fmt.Printf("   Total cards: %d\n", totalCards)
	fmt.Printf("   Total edges: %d\n", totalEdges)
	fmt.Printf("   Unique pairs: %d\n", len(pairCounts))

	// Write CSV
	f, err := os.Create(outputFile)
	if err != nil {
		fmt.Printf("Error creating output: %v\n", err)
		os.Exit(1)
	}
	defer f.Close()

	w := csv.NewWriter(f)
	defer w.Flush()

	w.Write([]string{"NAME_1", "NAME_2", "COUNT_SET", "COUNT_MULTISET"})

	var sortedPairs []pair
	for p := range pairCounts {
		sortedPairs = append(sortedPairs, p)
	}
	sort.Slice(sortedPairs, func(i, j int) bool {
		if sortedPairs[i].card1 != sortedPairs[j].card1 {
			return sortedPairs[i].card1 < sortedPairs[j].card1
		}
		return sortedPairs[i].card2 < sortedPairs[j].card2
	})

	for _, p := range sortedPairs {
		c := pairCounts[p]
		w.Write([]string{
			p.card1,
			p.card2,
			fmt.Sprintf("%d", c.set),
			fmt.Sprintf("%d", c.multiset),
		})
	}

	fmt.Printf("\n✅ Deck-only graph exported to %s\n", outputFile)
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

func makePair(a, b string) pair {
	if a > b {
		a, b = b, a
	}
	return pair{card1: a, card2: b}
}
