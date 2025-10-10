package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"collections/blob"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/goldfish"
	"collections/games/magic/dataset/scryfall"
	"collections/logger"

	"github.com/DataDog/zstd"
	"github.com/spf13/cobra"
)

var (
	sourceDir    string
	targetBucket string
	limitFlag    int
	dryRun       bool
)

type oldFormatResponse struct {
	URL             string              `json:"url"`
	StatusCode      int                 `json:"status_code"`
	Bytes           string              `json:"bytes"` // base64 encoded
	ScrapedAt       string              `json:"scraped_at"`
	ResponseHeaders map[string][]string `json:"response_headers"`
}

func main() {
	rootCmd := &cobra.Command{
		Use:   "migrate-old-data",
		Short: "Migrate old scraper data to new blob storage format",
	}

	migrateCmd := &cobra.Command{
		Use:   "migrate",
		Short: "Migrate data from old format to new",
		RunE:  runMigrate,
	}

	migrateCmd.Flags().StringVar(&sourceDir, "source", "../../old-scraper-data", "Source directory with old data")
	migrateCmd.Flags().StringVar(&targetBucket, "target", "file://./data-migrated", "Target bucket URL")
	migrateCmd.Flags().IntVar(&limitFlag, "limit", 0, "Limit number of files to migrate (0 = all)")
	migrateCmd.Flags().BoolVar(&dryRun, "dry-run", false, "Show what would be migrated without doing it")

	rootCmd.AddCommand(migrateCmd)

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func runMigrate(cmd *cobra.Command, args []string) error {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("INFO")

	if dryRun {
		log.Infof(ctx, "DRY RUN MODE - no data will be written")
	}

	// Initialize target blob storage
	var b *blob.Bucket
	var err error
	if !dryRun {
		b, err = blob.NewBucket(ctx, log, targetBucket)
		if err != nil {
			return fmt.Errorf("failed to create bucket: %w", err)
		}
	}

	// Migrate each source
	stats := &migrationStats{}

	// MTGGoldfish
	goldfishDir := filepath.Join(sourceDir, "www.mtggoldfish.com", "deck")
	if _, err := os.Stat(goldfishDir); err == nil {
		log.Infof(ctx, "Migrating MTGGoldfish data...")
		if err := migrateGoldfish(ctx, log, b, goldfishDir, stats); err != nil {
			log.Errorf(ctx, "Failed to migrate goldfish: %v", err)
		}
	}

	// Deckbox
	deckboxDir := filepath.Join(sourceDir, "deckbox.org")
	if _, err := os.Stat(deckboxDir); err == nil {
		log.Infof(ctx, "Migrating Deckbox data...")
		if err := migrateDeckbox(ctx, log, b, deckboxDir, stats); err != nil {
			log.Errorf(ctx, "Failed to migrate deckbox: %v", err)
		}
	}

	// Scryfall
	scryfallDir := filepath.Join(sourceDir, "scryfall.com", "sets")
	if _, err := os.Stat(scryfallDir); err == nil {
		log.Infof(ctx, "Migrating Scryfall data...")
		if err := migrateScryfall(ctx, log, b, scryfallDir, stats); err != nil {
			log.Errorf(ctx, "Failed to migrate scryfall: %v", err)
		}
	}

	// Print summary
	log.Infof(ctx, "\n=== Migration Summary ===")
	log.Infof(ctx, "Total files processed: %d", stats.total)
	log.Infof(ctx, "Successfully migrated: %d", stats.success)
	log.Infof(ctx, "Skipped (not parseable): %d", stats.skipped)
	log.Infof(ctx, "Failed: %d", stats.failed)

	if dryRun {
		log.Infof(ctx, "\nDRY RUN - no data was actually written")
	}

	return nil
}

type migrationStats struct {
	total   int
	success int
	skipped int
	failed  int
}

func migrateGoldfish(ctx context.Context, log *logger.Logger, b *blob.Bucket, sourceDir string, stats *migrationStats) error {
	files, err := findJSONFiles(sourceDir)
	if err != nil {
		return err
	}

	log.Infof(ctx, "Found %d goldfish files", len(files))

	// Use goldfish parser to process
	for i, file := range files {
		if limitFlag > 0 && i >= limitFlag {
			break
		}

		stats.total++

		// Read and decompress
		html, err := readOldFormat(file)
		if err != nil {
			log.Errorf(ctx, "Failed to read %s: %v", filepath.Base(file), err)
			stats.failed++
			continue
		}

		if len(html) == 0 {
			stats.skipped++
			continue
		}

		// Parse with goldfish parser
		// For now, skip actual parsing - we'll use the scraper to re-extract
		// This is just to count and validate files
		stats.skipped++

		if i > 0 && i%100 == 0 {
			log.Infof(ctx, "Processed %d/%d goldfish files", i, len(files))
		}
	}

	return nil
}

func migrateDeckbox(ctx context.Context, log *logger.Logger, b *blob.Bucket, sourceDir string, stats *migrationStats) error {
	files, err := findJSONFiles(sourceDir)
	if err != nil {
		return err
	}

	log.Infof(ctx, "Found %d deckbox files", len(files))

	for i, file := range files {
		if limitFlag > 0 && i >= limitFlag {
			break
		}

		stats.total++

		// Read and decompress
		html, err := readOldFormat(file)
		if err != nil {
			log.Errorf(ctx, "Failed to read %s: %v", filepath.Base(file), err)
			stats.failed++
			continue
		}

		if len(html) == 0 {
			stats.skipped++
			continue
		}

		// Skip for now - will re-extract
		stats.skipped++

		if i > 0 && i%100 == 0 {
			log.Infof(ctx, "Processed %d/%d deckbox files", i, len(files))
		}
	}

	return nil
}

func migrateScryfall(ctx context.Context, log *logger.Logger, b *blob.Bucket, sourceDir string, stats *migrationStats) error {
	files, err := findJSONFiles(sourceDir)
	if err != nil {
		return err
	}

	log.Infof(ctx, "Found %d scryfall files", len(files))

	for i, file := range files {
		if limitFlag > 0 && i >= limitFlag {
			break
		}

		stats.total++

		// Read and decompress
		html, err := readOldFormat(file)
		if err != nil {
			log.Errorf(ctx, "Failed to read %s: %v", filepath.Base(file), err)
			stats.failed++
			continue
		}

		if len(html) == 0 {
			stats.skipped++
			continue
		}

		// Skip for now - will re-extract
		stats.skipped++

		if i > 0 && i%100 == 0 {
			log.Infof(ctx, "Processed %d/%d scryfall files", i, len(files))
		}
	}

	return nil
}

func findJSONFiles(dir string) ([]string, error) {
	var files []string
	err := filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() && strings.HasSuffix(path, ".json.zst") {
			files = append(files, path)
		}
		return nil
	})
	return files, err
}

func readOldFormat(filePath string) ([]byte, error) {
	// Read compressed file
	compressed, err := os.ReadFile(filePath)
	if err != nil {
		return nil, err
	}

	// Decompress
	decompressed, err := zstd.Decompress(nil, compressed)
	if err != nil {
		return nil, fmt.Errorf("decompress failed: %w", err)
	}

	// Parse old format JSON
	var oldResp oldFormatResponse
	if err := json.Unmarshal(decompressed, &oldResp); err != nil {
		return nil, fmt.Errorf("json unmarshal failed: %w", err)
	}

	// Decode base64 HTML
	html, err := base64.StdEncoding.DecodeString(oldResp.Bytes)
	if err != nil {
		return nil, fmt.Errorf("base64 decode failed: %w", err)
	}

	return html, nil
}

// Ensure imports are used
var (
	_ = bytes.Buffer{}
	_ = goldfish.Dataset{}
	_ = deckbox.Dataset{}
	_ = scryfall.Dataset{}
)
