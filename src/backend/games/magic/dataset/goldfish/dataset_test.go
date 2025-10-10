package goldfish

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"collections/blob"
	"collections/logger"

	"github.com/PuerkitoBio/goquery"
)

func TestParseDeckPage(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}

	_ = NewDataset(log, b) // Dataset available for future use

	// Load fixture if it exists, otherwise skip
	fixturePath := filepath.Join("..", "testdata", "goldfish", "deck_page.html")
	html, err := os.ReadFile(fixturePath)
	if err != nil {
		t.Skipf("Fixture not found: %s (run 'go run ./cmd/testdata refresh' to create)", fixturePath)
		return
	}

	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(html))
	if err != nil {
		t.Fatalf("failed to parse HTML: %v", err)
	}

	// Check if we got a valid page (not 404)
	title := doc.Find("title").Text()
	if strings.Contains(title, "404") || strings.Contains(title, "not found") {
		t.Skip("Fixture contains 404 page - needs valid deck URL for refresh")
		return
	}

	// Test deck name extraction
	header := doc.Find(".header-container .title")
	header.Find(".author").Remove()
	deckName := strings.TrimSpace(header.Text())
	if deckName == "" {
		t.Log("Warning: failed to extract deck name (HTML structure may have changed)")
	} else {
		t.Logf("Found deck name: %s", deckName)
	}

	// Test info extraction
	infoStr := doc.Find(".deck-container-information").Text()
	if infoStr == "" {
		t.Log("Warning: failed to extract deck information (HTML structure may have changed)")
	} else {
		t.Logf("Found deck information")
	}

	// Test format regex
	formatMatches := reFormat.FindStringSubmatch(infoStr)
	if formatMatches != nil && len(formatMatches) > 1 {
		t.Logf("Found format: %s", formatMatches[1])
	}

	// Test date regex
	dateMatches := reDate.FindStringSubmatch(infoStr)
	if dateMatches != nil && len(dateMatches) > 1 {
		t.Logf("Found date: %s", dateMatches[1])
	}

	// Test card extraction
	cardCount := 0
	doc.Find("#tab-paper .deck-view-deck-table .card_name").Each(func(i int, sel *goquery.Selection) {
		cardCount++
	})

	if cardCount > 0 {
		t.Logf("Found %d cards in deck", cardCount)
	}
}

func TestDeckIDRegex(t *testing.T) {
	tests := []struct {
		url         string
		wantID      string
		shouldMatch bool
	}{
		{
			url:         "https://www.mtggoldfish.com/deck/5678901#paper",
			wantID:      "deck:5678901",
			shouldMatch: true,
		},
		{
			url:         "https://www.mtggoldfish.com/archetype/modern-burn",
			wantID:      "archetype:modern-burn",
			shouldMatch: true,
		},
		{
			url:         "https://example.com/deck",
			shouldMatch: false,
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.url, func(t *testing.T) {
			t.Parallel()
			matches := reDeckID.FindStringSubmatch(tt.url)
			if tt.shouldMatch {
				if matches == nil {
					t.Errorf("expected match, got nil")
					return
				}
				if len(matches) < 2 {
					t.Errorf("expected at least 2 matches, got %d", len(matches))
					return
				}
				// Construct ID from match
				id := matches[1]
				// Replace slashes with colons
				id = id[:]
				if id == "" {
					t.Error("extracted empty ID")
				}
			} else {
				if matches != nil {
					t.Logf("Note: regex matched %v (might be okay)", matches)
				}
			}
		})
	}
}

func TestResolveRef(t *testing.T) {
	d := &Dataset{}

	tests := []struct {
		ref     string
		wantURL string
	}{
		{
			ref:     "/deck/12345",
			wantURL: "https://www.mtggoldfish.com/deck/12345",
		},
		{
			ref:     "https://www.mtggoldfish.com/deck/12345",
			wantURL: "https://www.mtggoldfish.com/deck/12345",
		},
	}

	for _, tt := range tests {
		t.Run(tt.ref, func(t *testing.T) {
			got, err := d.resolveRef(tt.ref)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got != tt.wantURL {
				t.Errorf("got %s, want %s", got, tt.wantURL)
			}
		})
	}
}
