package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"

	"collections/blob"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/goldfish"
	"collections/games/magic/dataset/mtgtop8"
	"collections/games/magic/dataset/scryfall"
	"collections/logger"
	"collections/scraper"

	"github.com/spf13/cobra"
)

var (
	datasetFlag string
	urlFlag     string
	outputFlag  string
)

func main() {
	rootCmd := &cobra.Command{
		Use:   "testdata",
		Short: "Manage test fixtures for dataset tests",
	}

	refreshCmd := &cobra.Command{
		Use:   "refresh",
		Short: "Refresh test fixtures from live sources",
		RunE:  runRefresh,
	}
	refreshCmd.Flags().StringVar(&datasetFlag, "dataset", "", "Specific dataset to refresh (scryfall, deckbox, goldfish, mtgtop8)")

	saveCmd := &cobra.Command{
		Use:   "save",
		Short: "Save a specific URL as a test fixture",
		RunE:  runSave,
	}
	saveCmd.Flags().StringVar(&urlFlag, "url", "", "URL to fetch and save")
	saveCmd.Flags().StringVar(&outputFlag, "output", "", "Output path relative to testdata/")
	saveCmd.MarkFlagRequired("url")
	saveCmd.MarkFlagRequired("output")

	rootCmd.AddCommand(refreshCmd, saveCmd)

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func runRefresh(cmd *cobra.Command, args []string) error {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("INFO")

	testdataDir := filepath.Join("games", "magic", "dataset", "testdata")

	if datasetFlag == "" || datasetFlag == "scryfall" {
		if err := refreshScryfall(ctx, log, testdataDir); err != nil {
			return fmt.Errorf("failed to refresh scryfall: %w", err)
		}
	}

	if datasetFlag == "" || datasetFlag == "deckbox" {
		if err := refreshDeckbox(ctx, log, testdataDir); err != nil {
			return fmt.Errorf("failed to refresh deckbox: %w", err)
		}
	}

	if datasetFlag == "" || datasetFlag == "goldfish" {
		if err := refreshGoldfish(ctx, log, testdataDir); err != nil {
			return fmt.Errorf("failed to refresh goldfish: %w", err)
		}
	}

	if datasetFlag == "" || datasetFlag == "mtgtop8" {
		if err := refreshMTGTop8(ctx, log, testdataDir); err != nil {
			return fmt.Errorf("failed to refresh mtgtop8: %w", err)
		}
	}

	log.Infof(ctx, "✓ Test fixtures refreshed successfully")
	return nil
}

func runSave(cmd *cobra.Command, args []string) error {
	resp, err := http.Get(urlFlag)
	if err != nil {
		return fmt.Errorf("failed to fetch URL: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	testdataDir := filepath.Join("games", "magic", "dataset", "testdata")
	outputPath := filepath.Join(testdataDir, outputFlag)

	if err := os.MkdirAll(filepath.Dir(outputPath), 0755); err != nil {
		return fmt.Errorf("failed to create directory: %w", err)
	}

	f, err := os.Create(outputPath)
	if err != nil {
		return fmt.Errorf("failed to create file: %w", err)
	}
	defer f.Close()

	if _, err := io.Copy(f, resp.Body); err != nil {
		return fmt.Errorf("failed to write file: %w", err)
	}

	fmt.Printf("✓ Saved %s to %s\n", urlFlag, outputPath)
	return nil
}

func refreshScryfall(ctx context.Context, log *logger.Logger, testdataDir string) error {
	log.Infof(ctx, "Refreshing Scryfall fixtures...")

	// Fetch bulk data API response
	resp, err := http.Get("https://api.scryfall.com/bulk-data")
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	bulkDataPath := filepath.Join(testdataDir, "scryfall", "bulk_data.json")
	if err := saveResponse(resp, bulkDataPath); err != nil {
		return err
	}

	// Fetch a sample set page
	resp, err = http.Get("https://scryfall.com/sets/dmu")
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	setPagePath := filepath.Join(testdataDir, "scryfall", "set_page.html")
	if err := saveResponse(resp, setPagePath); err != nil {
		return err
	}

	log.Infof(ctx, "  ✓ Scryfall: bulk_data.json, set_page.html")
	return nil
}

func refreshDeckbox(ctx context.Context, log *logger.Logger, testdataDir string) error {
	log.Infof(ctx, "Refreshing Deckbox fixtures...")

	// Example deck page
	resp, err := http.Get("https://deckbox.org/sets/3174326")
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	deckPath := filepath.Join(testdataDir, "deckbox", "deck_page.html")
	if err := saveResponse(resp, deckPath); err != nil {
		return err
	}

	log.Infof(ctx, "  ✓ Deckbox: deck_page.html")
	return nil
}

func refreshGoldfish(ctx context.Context, log *logger.Logger, testdataDir string) error {
	log.Infof(ctx, "Refreshing MTGGoldfish fixtures...")

	// Example deck page - use a known valid archetype
	resp, err := http.Get("https://www.mtggoldfish.com/archetype/standard-mono-red-aggro")
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		log.Infof(ctx, "  ⚠ MTGGoldfish returned status %d, trying alternate URL", resp.StatusCode)
		resp.Body.Close()
		// Try the metagame page which is more stable
		resp, err = http.Get("https://www.mtggoldfish.com/metagame/standard")
		if err != nil {
			return err
		}
		defer resp.Body.Close()
	}

	deckPath := filepath.Join(testdataDir, "goldfish", "deck_page.html")
	if err := saveResponse(resp, deckPath); err != nil {
		return err
	}

	log.Infof(ctx, "  ✓ MTGGoldfish: deck_page.html")
	return nil
}

func refreshMTGTop8(ctx context.Context, log *logger.Logger, testdataDir string) error {
	log.Infof(ctx, "Refreshing MTGTop8 fixtures...")

	// Example deck page
	resp, err := http.Get("https://mtgtop8.com/event?e=45678&d=545678")
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	deckPath := filepath.Join(testdataDir, "mtgtop8", "deck_page.html")
	if err := saveResponse(resp, deckPath); err != nil {
		return err
	}

	// Search results page
	client := &http.Client{}
	req, err := http.NewRequest("POST", "https://mtgtop8.com/search", nil)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err = client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	searchPath := filepath.Join(testdataDir, "mtgtop8", "search_page.html")
	if err := saveResponse(resp, searchPath); err != nil {
		return err
	}

	log.Infof(ctx, "  ✓ MTGTop8: deck_page.html, search_page.html")
	return nil
}

func saveResponse(resp *http.Response, path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}

	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()

	_, err = io.Copy(f, resp.Body)
	return err
}

// Ensure imports are used
var (
	_ = blob.Bucket{}
	_ = deckbox.Dataset{}
	_ = goldfish.Dataset{}
	_ = mtgtop8.Dataset{}
	_ = scryfall.Dataset{}
	_ = scraper.Scraper{}
)
