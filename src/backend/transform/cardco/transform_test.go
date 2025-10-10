package cardco

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	mdataset "collections/games/magic/dataset"
	mgame "collections/games/magic/game"
	"collections/logger"
)

func TestExportAttributesCSV_WritesCardAttrs(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	tr, err := NewTransform(ctx, log)
	if err != nil {
		t.Fatalf("new transform: %v", err)
	}
	defer tr.Close()

	// Feed a CardItem (as produced by Scryfall dataset)
	card := &mgame.Card{
		Name: "Lightning Bolt",
		CMC:  1.0,
		Faces: []mgame.CardFace{{
			TypeLine: "Instant",
		}},
	}
	if err := tr.worker(&mdataset.CardItem{Card: card}); err != nil {
		t.Fatalf("worker(card): %v", err)
	}

	out := filepath.Join(t.TempDir(), "attrs.csv")
	if err := tr.ExportAttributesCSV(ctx, out); err != nil {
		t.Fatalf("export attrs: %v", err)
	}
	b, err := os.ReadFile(out)
	if err != nil {
		t.Fatalf("read attrs: %v", err)
	}
	s := string(b)
	if !strings.Contains(s, "Lightning Bolt") || !strings.Contains(s, "Instant") {
		t.Fatalf("missing expected row: %s", s)
	}
}
