package scryfall

import (
	"bytes"
	"context"
	"strings"
	"testing"

	"github.com/PuerkitoBio/goquery"
	"collections/blob"
	"collections/games"
	"collections/games/magic/dataset"
	"collections/logger"
	"collections/scraper"
)

// TestPartitionNameExtraction tests the partition name extraction logic
// with various HTML structures that appear on Scryfall set pages
func TestPartitionNameExtraction(t *testing.T) {

	// Test cases based on actual error messages from the logs
	testCases := []struct {
		name     string
		html     string
		expected string
	}{
		{
			name: "Draft Boosters with dot and anchor",
			html: `
				<div class="card-grid-header-content">
					Draft Boosters
					<span class="card-grid-header-dot">•</span>
					<a href="/search?order=set&q=e%3Acmm+cn%E2%89%A51+cn%E2%89%A4451&unique=prints">451 cards</a>
				</div>`,
			expected: "Draft Boosters",
		},
		{
			name: "New Cards with dot and anchor",
			html: `
				<div class="card-grid-header-content">
					New Cards
					<span class="card-grid-header-dot">•</span>
					<a href="/search?order=set&q=e%3Ahbg+cn%E2%89%A520+cn%E2%89%A481&unique=prints">62 cards</a>
				</div>`,
			expected: "New Cards",
		},
		{
			name: "In Boosters with dot and anchor",
			html: `
				<div class="card-grid-header-content">
					In Boosters
					<span class="card-grid-header-dot">•</span>
					<a href="/search?order=set&q=e%3Altr+cn%E2%89%A51+cn%E2%89%A4281&unique=prints">281 cards</a>
				</div>`,
			expected: "In Boosters",
		},
		{
			name: "Commanders partition",
			html: `
				<div class="card-grid-header-content">
					Commanders
					<span class="card-grid-header-dot">•</span>
					<a href="/search?order=set&q=e%3Ac21+cn%E2%89%A51+cn%E2%89%A410&unique=prints">10 cards</a>
				</div>`,
			expected: "Commanders",
		},
		{
			name: "Amonkhet Invocations",
			html: `
				<div class="card-grid-header-content">
					Amonkhet Invocations
					<span class="card-grid-header-dot">•</span>
					<a href="/search?order=set&q=e%3Amp2+cn%E2%89%A51+cn%E2%89%A430&unique=prints">30 cards</a>
				</div>`,
			expected: "Amonkhet Invocations",
		},
		{
			name: "Booster Cards (lowercase)",
			html: `
				<div class="card-grid-header-content">
					Booster cards
					<span class="card-grid-header-dot">•</span>
					<a href="/search?order=set&q=e%3Apor+cn%E2%89%A51+cn%E2%89%A4215&unique=prints">215 cards</a>
				</div>`,
			expected: "Booster cards",
		},
		{
			name: "Legacy format with id attribute",
			html: `
				<div class="card-grid-header-content">
					<a id="Main" href="/search?order=set&q=e%3Apor+cn%E2%89%A51+cn%E2%89%A4215&unique=prints">215 cards</a>
				</div>`,
			expected: "Main",
		},
		{
			name: "HTML entity in name",
			html: `
				<div class="card-grid-header-content">
					Everyone&#39;s Invited!
					<span class="card-grid-header-dot">•</span>
					<a href="/search?order=set&q=e%3Aplst+date%3A2025-05-12&unique=prints">74 cards</a>
				</div>`,
			expected: "Everyone's Invited!",
		},
		{
			name: "Multiple spaces and newlines",
			html: `
				<div class="card-grid-header-content">

					Holiday Promos

					<span class="card-grid-header-dot">•</span>
					<a href="/search?order=set&q=e%3Ahho+cn%E2%89%A51+cn%E2%89%A4999&unique=prints">23 cards</a>
				</div>`,
			expected: "Holiday Promos",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			doc, err := goquery.NewDocumentFromReader(bytes.NewReader([]byte(tc.html)))
			if err != nil {
				t.Fatalf("failed to parse HTML: %v", err)
			}

			headerSel := doc.Find(".card-grid-header-content")
			if headerSel.Length() == 0 {
				t.Fatal("failed to find .card-grid-header-content")
			}

			// Extract partition name using the same logic as parseCollection
			anchorSel := headerSel.Find("a:first-of-type")
			partitionName, hasID := anchorSel.Attr("id")

			if !hasID {
				textSel := headerSel.Clone()
				textSel.Find("a").Remove()
				textSel.Find(".card-grid-header-dot").Remove()
				textSel.Find("span").Remove()
				partitionName = textSel.Text()
				partitionName = strings.TrimSpace(partitionName)
				partitionName = strings.TrimPrefix(partitionName, "•")
				partitionName = strings.TrimSpace(partitionName)

				if partitionName == "" {
					allText := headerSel.Text()
					lines := strings.Split(allText, "\n")
					for _, line := range lines {
						line = strings.TrimSpace(line)
						if line != "" &&
						   !strings.Contains(strings.ToLower(line), "cards") &&
						   !strings.Contains(line, "•") &&
						   !strings.HasPrefix(line, "<") {
							partitionName = line
							break
						}
					}
				}

				partitionName = strings.TrimSpace(partitionName)
				partitionName = strings.TrimPrefix(partitionName, "•")
				partitionName = strings.TrimSuffix(partitionName, "•")
				partitionName = strings.TrimSpace(partitionName)
			}

			if partitionName != tc.expected {
				t.Errorf("partitionName = %q, want %q", partitionName, tc.expected)
			}
		})
	}
}

// TestParseCollectionWithVariousPartitions tests parsing collections with
// different partition name formats
func TestParseCollectionWithVariousPartitions(t *testing.T) {
	// This is an integration test that would require actual HTTP requests
	// For now, we test the extraction logic in isolation
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	bucket, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer bucket.Close(ctx)

	scraperBlob, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create scraper blob: %v", err)
	}
	defer scraperBlob.Close(ctx)

	sc := scraper.NewScraper(log, scraperBlob)
	d := NewDataset(log, bucket)

	// Test with a known problematic set URL
	// This will make an actual HTTP request, so we skip if network is unavailable
	testURLs := []string{
		"https://scryfall.com/sets/cmm", // Commander Masters - has "Draft Boosters"
		"https://scryfall.com/sets/c21", // Commander 2021 - has "Commanders"
	}

	for _, url := range testURLs {
		t.Run(url, func(t *testing.T) {
			stats := games.NewExtractStats(log)
			ctxWithStats := games.WithExtractStats(ctx, stats)

			err := d.Extract(ctxWithStats, sc,
				&dataset.OptExtractItemOnlyURL{URL: url},
				&dataset.OptExtractParallel{Parallel: 1},
				&dataset.OptExtractReparse{},
				&dataset.OptExtractSectionOnly{Section: "collections"},
			)
			if err != nil {
				// Network errors are acceptable in tests
				if strings.Contains(err.Error(), "network") ||
				   strings.Contains(err.Error(), "timeout") ||
				   strings.Contains(err.Error(), "connection") {
					t.Skipf("Skipping due to network error: %v", err)
				}
				t.Errorf("Extract failed: %v", err)
				return
			}

			// Verify that at least one partition was extracted
			summary := stats.Summary()
			if stats.Total == 0 {
				t.Errorf("No items extracted, summary: %s", summary)
			}

			// Check that the collection was written
			setID := url[strings.LastIndex(url, "/")+1:]
			bkey := "magic/scryfall/collections/" + setID + ".json"
			exists, err := bucket.Exists(ctx, bkey)
			if err != nil {
				t.Errorf("Failed to check if collection exists: %v", err)
			}
			if !exists {
				t.Errorf("Collection was not written to blob storage")
			}
		})
	}
}

// TestPartitionNameEdgeCases tests edge cases in partition name extraction
func TestPartitionNameEdgeCases(t *testing.T) {
	testCases := []struct {
		name     string
		html     string
		expected string // empty string means should be skipped
	}{
		{
			name: "Empty partition name should be skipped",
			html: `
				<div class="card-grid-header-content">
					<span class="card-grid-header-dot">•</span>
					<a href="/search">cards</a>
				</div>`,
			expected: "", // Should be skipped
		},
		{
			name: "Only anchor with no text",
			html: `
				<div class="card-grid-header-content">
					<a href="/search">451 cards</a>
				</div>`,
			expected: "", // Should be skipped
		},
		{
			name: "Whitespace only",
			html: `
				<div class="card-grid-header-content">

					<span class="card-grid-header-dot">•</span>
					<a href="/search">cards</a>
				</div>`,
			expected: "", // Should be skipped
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			doc, err := goquery.NewDocumentFromReader(bytes.NewReader([]byte(tc.html)))
			if err != nil {
				t.Fatalf("failed to parse HTML: %v", err)
			}

			headerSel := doc.Find(".card-grid-header-content")
			if headerSel.Length() == 0 {
				t.Fatal("failed to find .card-grid-header-content")
			}

			// Use same extraction logic
			anchorSel := headerSel.Find("a:first-of-type")
			partitionName, hasID := anchorSel.Attr("id")

			if !hasID {
				textSel := headerSel.Clone()
				textSel.Find("a").Remove()
				textSel.Find(".card-grid-header-dot").Remove()
				textSel.Find("span").Remove()
				partitionName = textSel.Text()
				partitionName = strings.TrimSpace(partitionName)
				partitionName = strings.TrimPrefix(partitionName, "•")
				partitionName = strings.TrimSpace(partitionName)

				if partitionName == "" {
					allText := headerSel.Text()
					lines := strings.Split(allText, "\n")
					for _, line := range lines {
						line = strings.TrimSpace(line)
						if line != "" &&
						   !strings.Contains(strings.ToLower(line), "cards") &&
						   !strings.Contains(line, "•") &&
						   !strings.HasPrefix(line, "<") {
							partitionName = line
							break
						}
					}
				}

				partitionName = strings.TrimSpace(partitionName)
				partitionName = strings.TrimPrefix(partitionName, "•")
				partitionName = strings.TrimSuffix(partitionName, "•")
				partitionName = strings.TrimSpace(partitionName)
			}

			if partitionName != tc.expected {
				t.Errorf("partitionName = %q, want %q", partitionName, tc.expected)
			}
		})
	}
}
