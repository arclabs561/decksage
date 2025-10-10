# Test Fixtures

This directory contains saved HTML/JSON responses from external sources for unit testing.

## Structure

```
testdata/
├── scryfall/
│   ├── bulk_data.json          # Response from /bulk-data API
│   ├── cards_sample.json       # Sample of card data
│   └── set_page.html           # Sample set page
├── deckbox/
│   ├── deck_page.html          # Sample deck page
│   └── collection_list.html    # Sample collection listing
├── goldfish/
│   ├── deck_page.html          # Sample deck page
│   └── section_page.html       # Sample section listing
└── mtgtop8/
    ├── deck_page.html          # Sample deck page
    └── search_results.html     # Sample search results
```

## Refreshing Fixtures

To update test fixtures with fresh data from live sources:

```bash
# Refresh all fixtures
go run ./cmd/testdata refresh

# Refresh specific dataset
go run ./cmd/testdata refresh --dataset=scryfall

# Save a specific URL as a fixture
go run ./cmd/testdata save --url="https://mtgtop8.com/event?e=12345&d=67890" --output=mtgtop8/sample_deck.html
```

## Using Fixtures in Tests

```go
func TestParser(t *testing.T) {
    html, err := os.ReadFile("testdata/mtgtop8/deck_page.html")
    if err != nil {
        t.Fatal(err)
    }
    
    doc, err := goquery.NewDocumentFromReader(bytes.NewReader(html))
    // ... test parsing logic
}
```

## Integration Tests

To run tests against live sources instead of fixtures, use the `integration` build tag:

```bash
go test -tags=integration ./...
```
