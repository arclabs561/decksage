package goldfish

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"collections/blob"
	"collections/games"
	"collections/games/magic/dataset"
	"collections/games/magic/game"
	"collections/logger"
	"collections/scraper"

	"github.com/PuerkitoBio/goquery"
	"go.uber.org/ratelimit"
)

var base *url.URL

func init() {
	u, err := url.Parse("https://www.mtggoldfish.com/")
	if err != nil {
		panic(err)
	}
	base = u
}

type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

func NewDataset(
	log *logger.Logger,
	blob *blob.Bucket,
) dataset.Dataset {
	return &Dataset{
		log:  log,
		blob: blob,
	}
}

func (d *Dataset) Description() dataset.Description {
	return dataset.Description{
		Name: "goldfish",
	}
}

var reCollectionURL = regexp.MustCompile(`^https://www.mtggoldfish.com/deck/`)

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...dataset.UpdateOption,
) error {
	opts, err := dataset.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}
	for _, u := range opts.ItemOnlyURLs {
		if !reCollectionURL.MatchString(u) {
			return fmt.Errorf("invalid only url: %s", u)
		}
	}

	urls := make(chan string)
	wg := new(sync.WaitGroup)
	for i := 0; i < opts.Parallel; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				select {
				case <-ctx.Done():
					return
				case u, ok := <-urls:
					if !ok {
						return
					}
					if err := d.parseCollection(ctx, sc, u, opts); err != nil {
						d.log.Field("url", u).Errorf(ctx, "failed to parse collection: %v", err)
						// Record error in statistics if available
						if stats := games.ExtractStatsFromContext(ctx); stats != nil {
							stats.RecordCategorizedError(ctx, u, "goldfish", err)
						}
						continue
					}
				}
			}
		}()
	}

	if len(opts.ItemOnlyURLs) > 0 {
		for _, u := range opts.ItemOnlyURLs {
				// Check context cancellation before sending
				select {
				case <-ctx.Done():
					return ctx.Err()
				default:
				}
			urls <- u
		}
	} else {
		if err := d.parseRoot(ctx, sc, urls, opts); err != nil {
			return err
		}
	}
	close(urls)
	wg.Wait()
	return nil
}

func (d *Dataset) parseRoot(
	ctx context.Context,
	sc *scraper.Scraper,
	urls chan<- string,
	opts dataset.ResolvedUpdateOptions,
) error {
	page, err := d.fetch(ctx, sc, "https://www.mtggoldfish.com/deck/custom", opts)
	if err != nil {
		return err
	}
	r := bytes.NewReader(page.Response.Body)
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return err
	}

	var sectionURLs []string
	doc.Find(".subNav-menu-desktop a").
		EachWithBreak(func(i int, sel *goquery.Selection) bool {
			href, ok := sel.Attr("href")
			if !ok {
				html, _ := sel.Html()
				err = fmt.Errorf("missing href: %s", html)
				return false
			}
			var u string
			u, err = d.resolveRef(href)
			if err != nil {
				return false
			}
			sectionURLs = append(sectionURLs, u)
			return true
		})
	if err != nil {
		return fmt.Errorf("failed to find deck type pages: %w", err)
	}

	var total int
SECTIONS:
	for _, sectionURL := range sectionURLs {
		curr := sectionURL
		page := 0
		totalSection := 0
		for {
			parsed, err := d.scrollSection(ctx, sc, urls, curr, opts)
			if err != nil {
				return fmt.Errorf("failed to scroll section: %w", err)
			}
			shouldStop := func() bool {
				limit, ok := opts.ScrollLimit.Get()
				return ok && total > limit
			}
			added := 0
			for _, u := range parsed.CollectionURLs {
				if shouldStop() {
					break
				}
				// Check context cancellation before sending
				select {
				case <-ctx.Done():
					return ctx.Err()
				default:
				}
				total++
				added++
				urls <- u
			}
			totalSection += added
			d.log.Fieldf("page", "%d", page+1).
				Field("url", curr).
				Fieldf("newSection", "%d", added).
				Fieldf("totalSection", "%d", totalSection).
				Fieldf("totalAll", "%d", total).
				Infof(ctx, "parsed section page")
			if shouldStop() {
				break SECTIONS
			}
			if !parsed.Next() {
				break
			}
			page++
			curr = parsed.NextSectionURL
		}
	}

	return nil
}

type parsedSection struct {
	CollectionURLs []string
	CurrSectionURL string
	NextSectionURL string
}

func (p parsedSection) Next() bool {
	return p.NextSectionURL != ""
}

func (d *Dataset) scrollSection(
	ctx context.Context,
	sc *scraper.Scraper,
	urls chan<- string,
	sectionURL string,
	opts dataset.ResolvedUpdateOptions,
) (*parsedSection, error) {
	page, err := d.fetch(ctx, sc, sectionURL, opts)
	if err != nil {
		return nil, err
	}
	r := bytes.NewReader(page.Response.Body)
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return nil, err
	}
	var collectionURLs []string
	doc.Find(".archetype-tile .card-image-tile-link-overlay").
		EachWithBreak(func(i int, sel *goquery.Selection) bool {
			href, ok := sel.Attr("href")
			if !ok {
				html, _ := sel.Html()
				err = fmt.Errorf("missing href: %s", html)
				return false
			}
			var u string
			u, err = d.resolveRef(href)
			if err != nil {
				return false
			}
			collectionURLs = append(collectionURLs, u)
			return true
		})
	if err != nil {
		return nil, err
	}

	nextPageHref, ok := doc.Find(".page-item.active").Next().Find("a").Attr("href")
	nextPageURL := ""
	if ok {
		nextPageURL, err = d.resolveRef(nextPageHref)
		if err != nil {
			return nil, err
		}
	}

	return &parsedSection{
		CollectionURLs: collectionURLs,
		CurrSectionURL: sectionURL,
		NextSectionURL: nextPageURL,
	}, nil
}

var reFormat = regexp.MustCompile(`Format:\s+(.*)`)
var reDate = regexp.MustCompile(`Deck Date:\s+(.*)`)

var reDeckID = regexp.MustCompile(`^https://www.mtggoldfish.com/([^#]+)`)

func (d *Dataset) parseCollection(
	ctx context.Context,
	sc *scraper.Scraper,
	u string,
	opts dataset.ResolvedUpdateOptions,
) error {
	idSubmatches := reDeckID.FindStringSubmatch(u)
	if idSubmatches == nil {
		return fmt.Errorf("failed to extract deck id")
	}
	id := strings.ReplaceAll(idSubmatches[1], "/", ":")
	bkey := d.collectionKey(id)

	if !opts.Reparse && !opts.FetchReplaceAll {
		exists, err := d.blob.Exists(ctx, bkey)
		if err != nil {
			return fmt.Errorf("failed to check if already parsed collection exists: %w", err)
		}
		if exists {
			d.log.Field("url", u).Debugf(ctx, "parsed collection already exists")
			return nil
		}
	}

	// Append #paper to URL to ensure paper tab is active
	deckURL := u
	if !strings.Contains(deckURL, "#") {
		deckURL = deckURL + "#paper"
	}
	page, err := d.fetch(ctx, sc, deckURL, opts)
	if err != nil {
		return err
	}
	r := bytes.NewReader(page.Response.Body)
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return err
	}

	header := doc.Find(".header-container .title")
	header.Find(".author").Remove()
	deckName := strings.TrimSpace(header.Text())

	infoStr := doc.Find(".deck-container-information").Text()
	formatSubmatches := reFormat.FindStringSubmatch(infoStr)
	if formatSubmatches == nil {
		return fmt.Errorf("failed to extract deck format")
	}
	format := formatSubmatches[1]
	dateSubmatches := reDate.FindStringSubmatch(infoStr)
	if dateSubmatches == nil {
		return fmt.Errorf("failed to extract deck date")
	}
	// Use centralized date parsing with validation
	date, err := games.ParseDateWithValidation(dateSubmatches[1])
	if err != nil {
		// Try fallback format specific to Goldfish
		if fallbackDate, fallbackErr := time.Parse("Jan _2, 2006", dateSubmatches[1]); fallbackErr == nil {
			// Validate the fallback date is in reasonable range
			year := fallbackDate.Year()
			if year >= 1990 && year <= 2100 {
				date = fallbackDate
			} else {
				return fmt.Errorf("fallback date %q has invalid year %d (expected 1990-2100)", dateSubmatches[1], year)
			}
		} else {
			return fmt.Errorf("failed to parse deck date %q: %w (fallback also failed: %v)", dateSubmatches[1], err, fallbackErr)
		}
	}

	// Extract deck ID from URL for download endpoint
	deckID := strings.TrimPrefix(u, "https://www.mtggoldfish.com/deck/")
	deckID = strings.TrimSuffix(deckID, "#paper")
	deckID = strings.TrimSuffix(deckID, "#")

	// Fetch deck in plain text format (much more reliable than HTML parsing)
	downloadURL := fmt.Sprintf("https://www.mtggoldfish.com/deck/download/%s", deckID)
	downloadPage, err := d.fetch(ctx, sc, downloadURL, opts)
	if err != nil {
		return fmt.Errorf("failed to fetch deck download: %w", err)
	}

	// Parse plain text deck format:
	// "3 Card Name\n4 Another Card\n\n1 Sideboard Card\n..."
	// Blank line separates main deck from sideboard
	deckText := string(downloadPage.Response.Body)
	lines := strings.Split(deckText, "\n")

	var mainCards []game.CardDesc
	var sideboardCards []game.CardDesc
	inSideboard := false

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			inSideboard = true
			continue
		}

		// Parse format: "3 Card Name" or "4 Card Name"
		parts := strings.SplitN(line, " ", 2)
		if len(parts) != 2 {
			continue // Skip invalid lines
		}

		countStr := parts[0]
		cardName := parts[1]

		count, parseErr := strconv.ParseInt(countStr, 10, 0)
		if parseErr != nil {
			continue // Skip lines that don't start with a number
		}

		// Normalize card name for consistency
		normalizedName := games.NormalizeCardName(cardName)
		if normalizedName == "" || count <= 0 {
			continue
		}

		card := game.CardDesc{
			Name:  normalizedName,
			Count: int(count),
		}

		if inSideboard {
			sideboardCards = append(sideboardCards, card)
		} else {
			mainCards = append(mainCards, card)
		}
	}

	if len(mainCards) == 0 {
		return fmt.Errorf("failed to parse cards: no cards found in deck download")
	}

	partitions := []game.Partition{{
		Name:  "Main",
		Cards: mainCards,
	}}
	if len(sideboardCards) > 0 {
		partitions = append(partitions, game.Partition{
			Name:  "Sideboard",
			Cards: sideboardCards,
		})
	}

	// Extract tournament type and location from deck name or URL
	tournamentType := extractMTGTournamentType(deckName)
	location := extractMTGLocation(deckName)

	t := &game.CollectionTypeDeck{
		Name:           deckName,
		Format:         format,
		TournamentType: tournamentType,
		Location:       location,
	}
	tw := game.CollectionTypeWrapper{
		Type:  t.Type(),
		Inner: t,
	}
	collection := game.Collection{
		Type:        tw,
		ID:          id,
		URL:         u,
		ReleaseDate: date,
		Partitions:  partitions,
	}
	if err := collection.Canonicalize(); err != nil {
		return fmt.Errorf("collection is invalid: %w", err)
	}

	b, err := json.Marshal(collection)
	if err != nil {
		return err
	}
	if err := d.blob.Write(ctx, bkey, b); err != nil {
		return err
	}

	// Record success in statistics if available
	if stats := games.ExtractStatsFromContext(ctx); stats != nil {
		stats.RecordSuccess()
	}

	return nil
}

var prefix = filepath.Join("magic", "goldfish")

// extractMTGTournamentType extracts tournament type from event name
func extractMTGTournamentType(eventName string) string {
	if eventName == "" {
		return ""
	}

	eventLower := strings.ToLower(eventName)

	// Check for common tournament types
	if strings.Contains(eventLower, "grand prix") || strings.Contains(eventLower, "gp ") {
		return "GP"
	}
	if strings.Contains(eventLower, "pro tour") || strings.Contains(eventLower, "pt ") {
		return "Pro Tour"
	}
	if strings.Contains(eventLower, "ptq") {
		return "PTQ"
	}
	if strings.Contains(eventLower, "regional") {
		return "Regional"
	}
	if strings.Contains(eventLower, "championship") || strings.Contains(eventLower, "worlds") {
		return "Championship"
	}
	if strings.Contains(eventLower, "fnm") || strings.Contains(eventLower, "friday night magic") {
		return "FNM"
	}
	if strings.Contains(eventLower, "rcq") {
		return "RCQ"
	}
	if strings.Contains(eventLower, "rptq") {
		return "RPTQ"
	}
	if strings.Contains(eventLower, "scg") || strings.Contains(eventLower, "star city games") {
		return "SCG"
	}
	if strings.Contains(eventLower, "open") {
		return "Open"
	}
	if strings.Contains(eventLower, "invitational") {
		return "Invitational"
	}

	return ""
}

// extractMTGLocation extracts location from event name
// Examples: "GP Las Vegas", "Regional Pittsburgh, PA"
func extractMTGLocation(eventName string) string {
	if eventName == "" {
		return ""
	}

	// Try to find comma-separated location
	parts := strings.Split(eventName, ",")
	if len(parts) >= 2 {
		// Check if last part looks like a state/country (2-3 letters or full country name)
		lastPart := strings.TrimSpace(parts[len(parts)-1])
		if len(lastPart) <= 3 || strings.Contains(strings.ToLower(lastPart), "united states") {
			// Likely a location
			city := strings.TrimSpace(parts[len(parts)-2])
			// Remove tournament type prefix if present
			city = strings.TrimPrefix(city, "GP")
			city = strings.TrimPrefix(city, "Pro Tour")
			city = strings.TrimPrefix(city, "Regional")
			city = strings.TrimPrefix(city, "Championship")
			city = strings.TrimSpace(city)
			return fmt.Sprintf("%s, %s", city, lastPart)
		}
	}

	// Try to extract city from common patterns like "GP Las Vegas"
	eventLower := strings.ToLower(eventName)
	if strings.Contains(eventLower, "gp ") {
		parts := strings.Fields(eventName)
		for i, part := range parts {
			if strings.ToLower(part) == "gp" && i+1 < len(parts) {
				// Next part might be city
				city := strings.Join(parts[i+1:], " ")
				return city
			}
		}
	}

	return ""
}

func (d *Dataset) collectionKey(collectionID string) string {
	return filepath.Join(prefix, collectionID+".json")
}

func (d *Dataset) resolveRef(ref string) (string, error) {
	u, err := url.Parse(ref)
	if err != nil {
		return "", err
	}
	u = base.ResolveReference(u)
	return u.String(), nil
}

var (
	reSilentThrottle = regexp.MustCompile(`^Throttled`)
	limiter          = ratelimit.New(100, ratelimit.Per(time.Minute))
	defaultFetchOpts = []scraper.DoOption{
		&scraper.OptDoSilentThrottle{
			PageBytesRegexp: reSilentThrottle,
		},
		&scraper.OptDoLimiter{
			Limiter: limiter,
		},
	}
)

func (d *Dataset) fetch(
	ctx context.Context,
	sc *scraper.Scraper,
	u string,
	datasetOptions dataset.ResolvedUpdateOptions,
) (*scraper.Page, error) {
	opts := defaultFetchOpts
	if datasetOptions.FetchReplaceAll {
		opts = append(opts, &scraper.OptDoReplace{})
	}
	req, err := http.NewRequest("GET", u, nil)
	if err != nil {
		return nil, err
	}
	page, err := sc.Do(ctx, req, opts...)
	if err != nil {
		return nil, err
	}
	return page, nil
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(dataset.Item) error,
	options ...dataset.IterItemsOption,
) error {
	return dataset.IterItemsBlobPrefix(
		ctx,
		d.blob,
		prefix,
		dataset.DeserializeAsCollection,
		fn,
	)
}
