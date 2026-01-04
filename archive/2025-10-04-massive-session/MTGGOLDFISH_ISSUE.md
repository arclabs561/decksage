# MTGGoldfish Scraper Issue - October 4, 2025

## Problem

MTGGoldfish parser extracting 0 cards from all decks (100% failure rate during expansion attempt).

## Root Cause

**MTGGoldfish uses client-side JavaScript rendering** - the deck table HTML is not present in the initial HTTP response. It's loaded via AJAX after page load.

### Evidence

```bash
# Debug output shows:
Found 0 deck-view-deck-table elements
Parsed 0 cards from deck
```

The `<table class="deck-view-deck-table">` element exists in the fully rendered page (seen via Firecrawl) but is absent in the raw HTTP response that our HTTP-only scraper receives.

## Solutions

### Option 1: Browser Automation (Recommended Long-term)
Implement Playwright/Puppeteer to render JavaScript before scraping:

```go
// Pseudocode
import "github.com/playwright-community/playwright-go"

func (d *Dataset) fetch(ctx context.Context, url string) (*goquery.Document, error) {
    pw, _ := playwright.Run()
    browser, _ := pw.Chromium.Launch()
    page, _ := browser.NewPage()
    page.Goto(url)
    page.WaitForSelector(".deck-view-deck-table")
    content, _ := page.Content()
    return goquery.NewDocumentFromReader(strings.NewReader(content))
}
```

**Pros**: Would work for all JS-rendered sites
**Cons**: Adds complexity, slower, resource-intensive
**Effort**: 2-3 days development + testing

### Option 2: Find AJAX Endpoint
Reverse-engineer the AJAX call that loads deck data:

1. Open browser DevTools Network tab
2. Load MTGGoldfish deck page
3. Find XHR request that returns deck data
4. Scrape that endpoint directly

**Pros**: Faster than browser automation, works with current HTTP scraper
**Cons**: Brittle (endpoint may change), may have rate limiting
**Effort**: 1-2 hours investigation + implementation

### Option 3: Skip MTGGoldfish (Recommended Short-term)
Focus on sources that work:
- MTGTop8: ✅ Working (55,293 decks)
- Other sources: Implement Pokemon/YGO tournament scrapers

**Pros**: Unblocks other work, MTGTop8 already has good coverage
**Cons**: Lose meta percentage data from Goldfish
**Effort**: 0 hours

## Recommendation

**Short-term**: Option 3 (Skip for now)
**Medium-term**: Option 2 (Find AJAX endpoint) - if meta % data becomes important
**Long-term**: Option 1 (Browser automation) - if we need to scrape many JS-heavy sites

## Current Status

- Parser code updated but won't work without JS rendering
- MTGGoldfish scraping **disabled** in expansion scripts
- Documented in `DATASET_EXPANSION_PLAN.md`

## Data Impact

**Minimal** - we already have 55,293 decks from MTGTop8, which is sufficient for:
- Co-occurrence analysis
- Card similarity
- Format/archetype analysis

MTGGoldfish would add:
- Meta percentage data (nice-to-have, not critical)
- +2,000-5,000 more decks (incremental value)

## Next Steps

1. ✅ Document issue (this file)
2. Move forward with Pokemon/YGO tournament scrapers (higher priority for cross-game parity)
3. Revisit MTGGoldfish when:
   - We need meta percentage data, OR
   - We implement browser automation for other sites, OR
   - We have spare capacity after completing Pokemon/YGO work

## Test Case for Future Fixes

```bash
# Should parse 60+ cards from this deck
cd src/backend
go run cmd/dataset/main.go --bucket file://./data-full extract goldfish \
  --limit 1 \
  --only https://www.mtggoldfish.com/deck/7248896

# Success criteria: log shows "Parsed 60 cards from deck"
```

## Related Files

- `src/backend/games/magic/dataset/goldfish/dataset.go` - Parser code
- `DATA_QUALITY_REVIEW_2025_10_04.md` - Initial problem discovery
- `EXPANSION_RESULTS_OCT_4.md` - Impact on expansion attempt
