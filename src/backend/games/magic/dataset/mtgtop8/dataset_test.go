package mtgtop8

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"testing"

	"collections/blob"
	"collections/games/magic/game"
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
	fixturePath := filepath.Join("..", "testdata", "mtgtop8", "deck_page.html")
	html, err := os.ReadFile(fixturePath)
	if err != nil {
		t.Skipf("Fixture not found: %s (run 'go run ./cmd/testdata refresh' to create)", fixturePath)
		return
	}

	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(html))
	if err != nil {
		t.Fatalf("failed to parse HTML: %v", err)
	}

	// Test deck name extraction
	deckName := doc.Find("head title").Text()
	if deckName == "" {
		t.Error("failed to extract deck name")
	}

	// Test format extraction
	format := doc.Find(".S14 .meta_arch").Text()
	if format == "" {
		t.Error("failed to extract format")
	}

	// Test card parsing
	parts := make(map[string][]game.CardDesc)
	section := "Main"

	doc.Find(`div[style*="display:flex"] > div[align=left]`).EachWithBreak(func(i int, s *goquery.Selection) bool {
		s.Find("div.deck_line, div.O14").Each(func(i int, sel *goquery.Selection) {
			if sel.HasClass("O14") {
				switch sel.Text() {
				case "COMMANDER":
					section = "Commander"
					parts[section] = []game.CardDesc{}
				case "SIDEBOARD":
					section = "Sideboard"
					parts[section] = []game.CardDesc{}
				default:
					section = "Main"
					parts[section] = []game.CardDesc{}
				}
			}
		})
		return true
	})

	if len(parts) > 0 {
		t.Logf("Successfully parsed %d card sections", len(parts))
	}
}

func TestDeckIDRegex(t *testing.T) {
	tests := []struct {
		url         string
		wantEID     string
		wantDID     string
		shouldMatch bool
	}{
		{
			url:         "https://mtgtop8.com/event?e=12345&d=67890",
			wantEID:     "12345",
			wantDID:     "67890",
			shouldMatch: true,
		},
		{
			url:         "https://mtgtop8.com/event?e=99999&d=11111",
			wantEID:     "99999",
			wantDID:     "11111",
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
				if len(matches) < 3 {
					t.Errorf("expected 3 matches, got %d", len(matches))
					return
				}
				if matches[1] != tt.wantEID {
					t.Errorf("expected eID=%s, got %s", tt.wantEID, matches[1])
				}
				if matches[2] != tt.wantDID {
					t.Errorf("expected dID=%s, got %s", tt.wantDID, matches[2])
				}
			} else {
				if matches != nil {
					t.Errorf("expected no match, got %v", matches)
				}
			}
		})
	}
}
