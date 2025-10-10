package scryfall

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"collections/blob"
	"collections/games/magic/game"
	"collections/logger"

	"github.com/PuerkitoBio/goquery"
)

func TestParseCardJSON(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}

	d := &Dataset{log: log, blob: b}

	// Test single-faced card
	rawCard := card{
		cardProps: cardProps{
			Name:       "Lightning Bolt",
			ManaCost:   "{R}",
			TypeLine:   "Instant",
			OracleText: "Lightning Bolt deals 3 damage to any target.",
			Power:      "",
			Toughness:  "",
		},
		ScryfallURI: "https://scryfall.com/card/test/1",
		ImageURIs:   imageURIs{PNG: "https://example.com/image.png"},
	}

	if err := d.parseCard(ctx, rawCard); err != nil {
		t.Errorf("failed to parse single-faced card: %v", err)
	}

	// Verify card was written
	bkey := d.cardKey(rawCard.Name)
	data, err := b.Read(ctx, bkey)
	if err != nil {
		t.Fatalf("failed to read written card: %v", err)
	}

	var parsedCard game.Card
	if err := json.Unmarshal(data, &parsedCard); err != nil {
		t.Fatalf("failed to unmarshal card: %v", err)
	}

	if parsedCard.Name != rawCard.Name {
		t.Errorf("name mismatch: got %s, want %s", parsedCard.Name, rawCard.Name)
	}
	if len(parsedCard.Faces) != 1 {
		t.Errorf("expected 1 face, got %d", len(parsedCard.Faces))
	}
}

func TestParseDoubleFacedCard(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}

	d := &Dataset{log: log, blob: b}

	rawCard := card{
		cardProps: cardProps{
			Name: "Delver of Secrets // Insectile Aberration",
		},
		ScryfallURI: "https://scryfall.com/card/test/delver",
		ImageURIs:   imageURIs{PNG: "https://example.com/delver.png"},
		Faces: []cardFace{
			{
				cardProps: cardProps{
					Name:       "Delver of Secrets",
					ManaCost:   "{U}",
					TypeLine:   "Creature — Human Wizard",
					Power:      "1",
					Toughness:  "1",
					OracleText: "At the beginning of your upkeep...",
				},
			},
			{
				cardProps: cardProps{
					Name:       "Insectile Aberration",
					ManaCost:   "",
					TypeLine:   "Creature — Human Insect",
					Power:      "3",
					Toughness:  "2",
					OracleText: "Flying",
				},
			},
		},
	}

	if err := d.parseCard(ctx, rawCard); err != nil {
		t.Errorf("failed to parse double-faced card: %v", err)
	}

	// Verify card was written
	bkey := d.cardKey(rawCard.Name)
	data, err := b.Read(ctx, bkey)
	if err != nil {
		t.Fatalf("failed to read written card: %v", err)
	}

	var parsedCard game.Card
	if err := json.Unmarshal(data, &parsedCard); err != nil {
		t.Fatalf("failed to unmarshal card: %v", err)
	}

	if len(parsedCard.Faces) != 2 {
		t.Errorf("expected 2 faces, got %d", len(parsedCard.Faces))
	}

	if parsedCard.Faces[0].Name != "Delver of Secrets" {
		t.Errorf("front face name: got %s", parsedCard.Faces[0].Name)
	}
	if parsedCard.Faces[1].Name != "Insectile Aberration" {
		t.Errorf("back face name: got %s", parsedCard.Faces[1].Name)
	}
}

func TestParseSetPage(t *testing.T) {
	// Load fixture if it exists, otherwise skip
	fixturePath := filepath.Join("..", "testdata", "scryfall", "set_page.html")
	html, err := os.ReadFile(fixturePath)
	if err != nil {
		t.Skipf("Fixture not found: %s (run 'go run ./cmd/testdata refresh' to create)", fixturePath)
		return
	}

	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(html))
	if err != nil {
		t.Fatalf("failed to parse HTML: %v", err)
	}

	// Test set name extraction
	setNameRaw := doc.FindMatcher(goquery.Single(".set-header-title-h1")).Text()
	if setNameRaw == "" {
		t.Error("failed to extract set name")
	}

	setNameMatches := reSetName.FindStringSubmatch(setNameRaw)
	if len(setNameMatches) >= 3 {
		t.Logf("Set name: %s, Code: %s", setNameMatches[1], setNameMatches[2])
	}

	// Test release date extraction
	setReleasedRaw := doc.FindMatcher(goquery.Single(".set-header-title-words")).Text()
	if setReleasedRaw == "" {
		t.Error("failed to extract release date section")
	}

	releaseDateMatches := reSetReleased.FindStringSubmatch(setReleasedRaw)
	if len(releaseDateMatches) >= 2 {
		t.Logf("Release date: %s", releaseDateMatches[1])
	}

	// Test card grid parsing
	cardCount := 0
	doc.Find(".card-grid-item-invisible-label").Each(func(i int, sel *goquery.Selection) {
		cardCount++
	})

	if cardCount > 0 {
		t.Logf("Found %d cards in set", cardCount)
	}
}

func TestSetNameRegex(t *testing.T) {
	tests := []struct {
		input       string
		wantName    string
		wantCode    string
		shouldMatch bool
	}{
		{
			input:       "Dominaria United (DMU)",
			wantName:    "Dominaria United",
			wantCode:    "DMU",
			shouldMatch: true,
		},
		{
			input:       "The Brothers' War (BRO)",
			wantName:    "The Brothers' War",
			wantCode:    "BRO",
			shouldMatch: true,
		},
		{
			input:       "Invalid Format",
			shouldMatch: false,
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.input, func(t *testing.T) {
			t.Parallel()
			matches := reSetName.FindStringSubmatch(tt.input)
			if tt.shouldMatch {
				if matches == nil {
					t.Errorf("expected match, got nil")
					return
				}
				if len(matches) < 3 {
					t.Errorf("expected 3 matches, got %d", len(matches))
					return
				}
				if matches[1] != tt.wantName {
					t.Errorf("name: got %s, want %s", matches[1], tt.wantName)
				}
				if matches[2] != tt.wantCode {
					t.Errorf("code: got %s, want %s", matches[2], tt.wantCode)
				}
			} else {
				if matches != nil {
					t.Errorf("expected no match, got %v", matches)
				}
			}
		})
	}
}
