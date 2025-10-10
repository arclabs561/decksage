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

	fmt.Println("Scanning for collections...")

	// Find all collection files
	var files []string
	err := filepath.Walk(dataDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() && filepath.Ext(path) == ".zst" {
			files = append(files, path)
		}
		return nil
	})
	if err != nil {
		fmt.Printf("Error scanning directory: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Found %d collection files\n", len(files))

	// Build co-occurrence map
	pairCounts := make(map[pair]*counts)
	total := 0
	totalCards := 0
	totalEdges := 0

	for i, file := range files {
		col, err := loadCollection(file)
		if err != nil {
			fmt.Printf("⚠️  [%d/%d] Failed to load %s: %v\n", i+1, len(files), filepath.Base(file), err)
			continue
		}

		collectionCards := 0
		collectionEdges := 0

		// Process each partition
		for _, partition := range col.Partitions {
			cards := partition.Cards
			n := len(cards)
			collectionCards += n

			for i := 0; i < n; i++ {
				c := cards[i]

				// Self-pairs (if count > 1)
				if c.Count > 1 {
					p := makePair(c.Name, c.Name)
					if pairCounts[p] == nil {
						pairCounts[p] = &counts{}
					}
					pairCounts[p].multiset += c.Count - 1
					collectionEdges++
				}

				// Other pairs
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

		total++
		totalCards += collectionCards
		totalEdges += collectionEdges

		// Progress with details
		pct := float64(total) / float64(len(files)) * 100
		fmt.Printf("✓ [%d/%d %.1f%%] %s: %d cards, %d edges → %d unique pairs total\n",
			total, len(files), pct, filepath.Base(file), collectionCards, collectionEdges, len(pairCounts))
	}

	fmt.Printf("\n📊 Summary:\n")
	fmt.Printf("   Collections processed: %d\n", total)
	fmt.Printf("   Total unique cards: %d\n", totalCards)
	fmt.Printf("   Total edges created: %d\n", totalEdges)
	fmt.Printf("   Unique card pairs: %d\n", len(pairCounts))
	fmt.Printf("   Compression ratio: %.1fx\n", float64(totalEdges)/float64(len(pairCounts)))

	// Write to CSV
	f, err := os.Create(outputFile)
	if err != nil {
		fmt.Printf("Error creating output file: %v\n", err)
		os.Exit(1)
	}
	defer f.Close()

	w := csv.NewWriter(f)
	defer w.Flush()

	// Header
	w.Write([]string{"NAME_1", "NAME_2", "COUNT_SET", "COUNT_MULTISET"})

	// Sort pairs for deterministic output
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

	// Write data
	for _, p := range sortedPairs {
		c := pairCounts[p]
		w.Write([]string{
			p.card1,
			p.card2,
			fmt.Sprintf("%d", c.set),
			fmt.Sprintf("%d", c.multiset),
		})
	}

	fmt.Printf("✅ Successfully exported to %s\n", outputFile)
}

func loadCollection(path string) (*game.Collection, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	// Decompress if .zst
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
