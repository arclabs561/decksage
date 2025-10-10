package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"collections/blob"
	"collections/games/magic/game"
	"collections/logger"

	"github.com/DataDog/zstd"
	"github.com/spf13/cobra"
)

var (
	bucketURL string
	verbose   bool
)

func main() {
	rootCmd := &cobra.Command{
		Use:   "validate-data",
		Short: "Validate all collections in blob storage",
	}

	validateCmd := &cobra.Command{
		Use:   "validate",
		Short: "Validate all collections",
		RunE:  runValidate,
	}

	validateCmd.Flags().StringVar(&bucketURL, "bucket", "file://./data-full", "Bucket URL to validate")
	validateCmd.Flags().BoolVar(&verbose, "verbose", false, "Show details for each collection")

	rootCmd.AddCommand(validateCmd)

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

type validationStats struct {
	total      int
	valid      int
	invalid    int
	errors     []string
	byType     map[string]int
	byFormat   map[string]int
	totalCards int
}

func runValidate(cmd *cobra.Command, args []string) error {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	if verbose {
		log.SetLevel("INFO")
	} else {
		log.SetLevel("ERROR")
	}

	// Extract local path from file:// URL
	localPath := strings.TrimPrefix(bucketURL, "file://")

	stats := &validationStats{
		byType:   make(map[string]int),
		byFormat: make(map[string]int),
	}

	// Find all .json.zst files
	err := filepath.Walk(localPath, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		if !info.IsDir() && strings.HasSuffix(path, ".json.zst") {
			if err := validateCollection(ctx, log, path, stats); err != nil {
				stats.invalid++
				stats.errors = append(stats.errors, fmt.Sprintf("%s: %v", filepath.Base(path), err))
			} else {
				stats.valid++
			}
			stats.total++
		}

		return nil
	})

	if err != nil {
		return err
	}

	// Print summary
	fmt.Printf("\n=== Validation Summary ===\n")
	fmt.Printf("Total collections: %d\n", stats.total)
	fmt.Printf("Valid: %d (%.1f%%)\n", stats.valid, float64(stats.valid)/float64(stats.total)*100)
	fmt.Printf("Invalid: %d (%.1f%%)\n", stats.invalid, float64(stats.invalid)/float64(stats.total)*100)
	fmt.Printf("Total cards across all: %d\n", stats.totalCards)

	fmt.Printf("\nBy Type:\n")
	for typ, count := range stats.byType {
		fmt.Printf("  %s: %d\n", typ, count)
	}

	if len(stats.byFormat) > 0 {
		fmt.Printf("\nBy Format:\n")
		for format, count := range stats.byFormat {
			if format != "" {
				fmt.Printf("  %s: %d\n", format, count)
			}
		}
	}

	if len(stats.errors) > 0 {
		fmt.Printf("\n=== Errors (%d) ===\n", len(stats.errors))
		for i, err := range stats.errors {
			fmt.Printf("%d. %s\n", i+1, err)
			if i >= 9 { // Show first 10 errors
				fmt.Printf("... and %d more errors\n", len(stats.errors)-10)
				break
			}
		}
	}

	if stats.invalid > 0 {
		fmt.Printf("\n❌ Validation FAILED - %d invalid collections\n", stats.invalid)
		return fmt.Errorf("validation failed")
	}

	fmt.Printf("\n✅ All collections valid!\n")
	return nil
}

func validateCollection(ctx context.Context, log *logger.Logger, path string, stats *validationStats) error {
	// Read and decompress
	compressed, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read failed: %w", err)
	}

	decompressed, err := zstd.Decompress(nil, compressed)
	if err != nil {
		return fmt.Errorf("decompress failed: %w", err)
	}

	// Parse as collection
	var collection game.Collection
	if err := json.Unmarshal(decompressed, &collection); err != nil {
		return fmt.Errorf("json unmarshal failed: %w", err)
	}

	// Validate using built-in canonicalization
	if err := collection.Canonicalize(); err != nil {
		return fmt.Errorf("validation failed: %w", err)
	}

	// Collect stats
	stats.byType[string(collection.Type.Type)]++
	if deck, ok := collection.Type.Inner.(*game.CollectionTypeDeck); ok && deck.Format != "" {
		stats.byFormat[deck.Format]++
	}

	// Count cards
	for _, partition := range collection.Partitions {
		for _, card := range partition.Cards {
			stats.totalCards += card.Count
		}
	}

	if verbose {
		log.Infof(ctx, "✓ %s: %s (%d partitions, %d cards)",
			filepath.Base(path),
			collection.Type.Type,
			len(collection.Partitions),
			countCards(&collection))
	}

	return nil
}

func countCards(c *game.Collection) int {
	total := 0
	for _, partition := range c.Partitions {
		for _, card := range partition.Cards {
			total += card.Count
		}
	}
	return total
}

// Ensure imports are used
var _ = blob.Bucket{}
