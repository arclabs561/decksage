package scryfall

import (
	"bytes"
	"testing"

	"github.com/PuerkitoBio/goquery"
)

// FuzzSetPageParsing fuzzes minimal variations of set page HTML to ensure parser doesn't panic.
func FuzzSetPageParsing(f *testing.F) {
	f.Add("<html><body><h1 class=\"set-header-title-h1\">Dominaria United (DMU)</h1><div class=\"set-header-title-words\">Released Sep 9, 2022</div><div class=\"card-grid-item-invisible-label\">Card</div></body></html>")
	f.Add("<html><body><h1>Missing classes</h1></body></html>")
	f.Add("")
	f.Fuzz(func(t *testing.T, html string) {
		r := bytes.NewReader([]byte(html))
		_, _ = goquery.NewDocumentFromReader(r)
		// The dataset tests that use goquery selectors should handle absence gracefully; this ensures no panics here.
	})
}
