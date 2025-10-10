package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"time"

	"collections/games/magic/game"

	"github.com/DataDog/zstd"
)

type deckInfo struct {
	id          string
	format      string
	archetype   string
	releaseDate time.Time
	numCards    int
	url         string
	source      string
	player      string
	event       string
	placement   int
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: go run main.go <data-dir>")
		os.Exit(1)
	}

	dataDir := os.Args[1]

	fmt.Println("🔍 DEEP DECK ANALYSIS")
	fmt.Println("═══════════════════════════════════════════════════════════")
	fmt.Println()

	var decks []deckInfo

	// Scan all collections
	filepath.Walk(dataDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Ext(path) == ".zst" {
			col, err := loadCollection(path)
			if err != nil {
				return nil
			}

			if col.Type.Type != "Deck" {
				return nil
			}

			deck, ok := col.Type.Inner.(*game.CollectionTypeDeck)
			if !ok {
				return nil
			}

			numCards := 0
			for _, p := range col.Partitions {
				numCards += len(p.Cards)
			}

			decks = append(decks, deckInfo{
				id:          col.ID,
				format:      deck.Format,
				archetype:   deck.Archetype,
				releaseDate: col.ReleaseDate,
				numCards:    numCards,
				url:         col.URL,
				source:      col.Source,
				player:      deck.Player,
				event:       deck.Event,
				placement:   deck.Placement,
			})
		}
		return nil
	})

	fmt.Printf("Found %d decks\n\n", len(decks))

	// Format distribution
	formatCounts := make(map[string][]deckInfo)
	for _, d := range decks {
		formatCounts[d.format] = append(formatCounts[d.format], d)
	}

	// Sort formats by count
	type formatStat struct {
		format string
		count  int
		decks  []deckInfo
	}
	var formats []formatStat
	for f, ds := range formatCounts {
		formats = append(formats, formatStat{f, len(ds), ds})
	}
	sort.Slice(formats, func(i, j int) bool {
		return formats[i].count > formats[j].count
	})

	// Print format analysis
	fmt.Println("FORMAT DISTRIBUTION & DIVERSITY")
	fmt.Println("═══════════════════════════════════════════════════════════")
	fmt.Println()

	for _, fs := range formats {
		fmt.Printf("📊 %s: %d decks\n", fs.format, fs.count)

		// Archetype diversity
		archetypes := make(map[string]int)
		for _, d := range fs.decks {
			archetypes[d.archetype]++
		}

		// Find most common archetypes
		type archetypeStat struct {
			name  string
			count int
		}
		var archStats []archetypeStat
		for a, c := range archetypes {
			archStats = append(archStats, archetypeStat{a, c})
		}
		sort.Slice(archStats, func(i, j int) bool {
			return archStats[i].count > archStats[j].count
		})

		// Calculate diversity (Shannon entropy)
		entropy := 0.0
		total := float64(fs.count)
		for _, as := range archStats {
			p := float64(as.count) / total
			if p > 0 {
				entropy -= p * (logBase2(p))
			}
		}

		fmt.Printf("   Unique archetypes: %d\n", len(archetypes))
		fmt.Printf("   Diversity (entropy): %.2f bits\n", entropy)
		fmt.Printf("   Top archetypes:\n")

		for i, as := range archStats {
			if i >= 5 {
				break
			}
			pct := 100.0 * float64(as.count) / total
			archName := as.name
			if archName == "" {
				archName = "[Unknown]"
			}
			fmt.Printf("     - %s: %d decks (%.1f%%)\n", archName, as.count, pct)
		}

		// Check for clustering (same event)
		events := make(map[string]int)
		for _, d := range fs.decks {
			// Extract event ID from URL (e.g., e=74272)
			eventID := extractEventID(d.url)
			events[eventID]++
		}

		if len(events) < fs.count/3 {
			maxEvent := ""
			maxCount := 0
			for e, c := range events {
				if c > maxCount {
					maxEvent = e
					maxCount = c
				}
			}
			fmt.Printf("   ⚠️  CLUSTERING DETECTED: %d decks from event %s\n", maxCount, maxEvent)
		}

		// Time span
		if len(fs.decks) > 0 {
			minDate := fs.decks[0].releaseDate
			maxDate := fs.decks[0].releaseDate
			for _, d := range fs.decks {
				if d.releaseDate.Before(minDate) {
					minDate = d.releaseDate
				}
				if d.releaseDate.After(maxDate) {
					maxDate = d.releaseDate
				}
			}
			span := maxDate.Sub(minDate)
			fmt.Printf("   Time span: %s to %s (%.0f days)\n",
				minDate.Format("2006-01-02"),
				maxDate.Format("2006-01-02"),
				span.Hours()/24)
		}

		fmt.Println()
	}

	fmt.Println("═══════════════════════════════════════════════════════════")
	fmt.Println("SOURCE & METADATA COVERAGE")
	fmt.Println("═══════════════════════════════════════════════════════════")
	fmt.Println()

	// Source distribution
	sourceCounts := make(map[string]int)
	for _, d := range decks {
		source := d.source
		if source == "" {
			source = "[unknown]"
		}
		sourceCounts[source]++
	}

	fmt.Println("📍 Source Distribution:")
	for source, count := range sourceCounts {
		pct := 100.0 * float64(count) / float64(len(decks))
		fmt.Printf("   %s: %d decks (%.1f%%)\n", source, count, pct)
	}

	// Metadata coverage
	hasPlayer := 0
	hasEvent := 0
	hasPlacement := 0
	for _, d := range decks {
		if d.player != "" {
			hasPlayer++
		}
		if d.event != "" {
			hasEvent++
		}
		if d.placement > 0 {
			hasPlacement++
		}
	}

	fmt.Println("\n📋 Metadata Coverage:")
	fmt.Printf("   Player name: %d/%d (%.1f%%)\n", hasPlayer, len(decks), 100.0*float64(hasPlayer)/float64(len(decks)))
	fmt.Printf("   Event name: %d/%d (%.1f%%)\n", hasEvent, len(decks), 100.0*float64(hasEvent)/float64(len(decks)))
	fmt.Printf("   Placement: %d/%d (%.1f%%)\n", hasPlacement, len(decks), 100.0*float64(hasPlacement)/float64(len(decks)))

	// Top players (if available)
	if hasPlayer > 0 {
		playerCounts := make(map[string]int)
		for _, d := range decks {
			if d.player != "" {
				playerCounts[d.player]++
			}
		}

		type playerStat struct {
			name  string
			count int
		}
		var players []playerStat
		for p, c := range playerCounts {
			players = append(players, playerStat{p, c})
		}
		sort.Slice(players, func(i, j int) bool {
			return players[i].count > players[j].count
		})

		fmt.Println("\n🏆 Top Players (most decks):")
		for i, ps := range players {
			if i >= 10 {
				break
			}
			fmt.Printf("   %s: %d decks\n", ps.name, ps.count)
		}
	}

	fmt.Println("\n═══════════════════════════════════════════════════════════")
	fmt.Println("RECOMMENDATIONS")
	fmt.Println("═══════════════════════════════════════════════════════════")
	fmt.Println()

	for _, fs := range formats {
		if fs.count < 30 {
			fmt.Printf("⚠️  %s: Only %d decks - extract 30+ more for better coverage\n", fs.format, fs.count)
		}

		// Check diversity
		archetypes := make(map[string]int)
		for _, d := range fs.decks {
			archetypes[d.archetype]++
		}

		// If one archetype is >40%, warn
		for arch, count := range archetypes {
			pct := 100.0 * float64(count) / float64(fs.count)
			if pct > 40 {
				archName := arch
				if archName == "" {
					archName = "[Unknown]"
				}
				fmt.Printf("⚠️  %s: '%s' is %.1f%% of decks - extract more diverse archetypes\n",
					fs.format, archName, pct)
			}
		}
	}

	fmt.Println("\n═══════════════════════════════════════════════════════════")
}

func extractEventID(url string) string {
	// Extract event ID from URL like https://mtgtop8.com/event?e=74272&d=763488
	// Simple approach: just use the full URL as event ID for now
	// Better: parse e= parameter
	if len(url) > 40 {
		return url[len(url)-20:]
	}
	return url
}

func logBase2(x float64) float64 {
	if x <= 0 {
		return 0
	}
	return 2.302585093 / 0.693147181 * (x - 1 + (x-1)*(x-1)/2) // Fast approximation
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
