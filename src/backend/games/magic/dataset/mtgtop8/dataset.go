package mtgtop8

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
)

var base *url.URL

func init() {
	u, err := url.Parse("https://mtgtop8.com/")
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
) *Dataset {
	return &Dataset{
		log:  log,
		blob: blob,
	}
}

func (d Dataset) Description() dataset.Description {
	return dataset.Description{
		Name: "mtgtop8",
	}
}

type task struct {
	ItemURL string
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...dataset.UpdateOption,
) error {
	opts, err := dataset.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	tasks := make(chan task, 25*10)
	wg := new(sync.WaitGroup)
	for i := 0; i < opts.Parallel; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				select {
				case <-ctx.Done():
					return
				case t, ok := <-tasks:
					if !ok {
						return
					}
					if err := d.parseItem(ctx, opts, sc, t.ItemURL); err != nil {
						d.log.Errorf(ctx, "failed to parse item: %v", err)
						// Record error in statistics if available
						if stats := games.ExtractStatsFromContext(ctx); stats != nil {
							stats.RecordCategorizedError(ctx, t.ItemURL, "mtgtop8", err)
						}
					}
				}
			}
		}()
	}

	done := func(err error) error {
		close(tasks)
		wg.Wait()
		return err
	}

	if len(opts.ItemOnlyURLs) > 0 {
		for _, u := range opts.ItemOnlyURLs {
			// Check context cancellation before sending
			select {
			case <-ctx.Done():
				close(tasks)
				wg.Wait()
				return ctx.Err()
			default:
			}
			tasks <- task{ItemURL: u}
		}
		return done(nil)
	}

	if err := d.scrollPages(ctx, opts, sc, tasks); err != nil {
		return done(err)
	}

	return done(nil)
}

func (d *Dataset) scrollPages(
	ctx context.Context,
	opts dataset.ResolvedUpdateOptions,
	sc *scraper.Scraper,
	tasks chan task,
) error {
	startPage := opts.ScrollStart.OrElse(1)
	if startPage < 1 {
		startPage = 1
	}
	currPage := startPage
	totalPages := 0
	totalItems := 0
	checkpoint := 10
	start := time.Now()
scroll:
	for {
		if currPage-startPage > 0 && currPage%checkpoint == 0 {
			dur := time.Since(start)
			pageRate := float64(currPage-startPage) / float64(dur.Seconds())
			d.log.Fieldf("total_items", "%d", totalItems).
				Fieldf("page_rate", fmt.Sprintf("%0.2f/s", pageRate)).
				Infof(ctx, "parsing page %d", currPage)
		}
		urls, err := d.parsePage(ctx, opts, sc, currPage)
		if err != nil {
			return err
		}
		if len(urls) == 0 {
			d.log.Infof(ctx, "last page %d, stopping scrolling", currPage)
			return nil
		}
		for _, u := range urls {
			// Check context cancellation before sending
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
			}
			tasks <- task{ItemURL: u}
			totalItems++
			if n, ok := opts.ItemLimit.Get(); ok && totalItems >= n {
				break scroll
			}
		}
		currPage++
		totalPages++
		if n, ok := opts.ScrollLimit.Get(); ok && totalPages >= n {
			break scroll
		}
	}
	return nil
}

func (d *Dataset) parsePage(
	ctx context.Context,
	opts dataset.ResolvedUpdateOptions,
	sc *scraper.Scraper,
	currPage int,
) ([]string, error) {
	u := base.JoinPath("/search").String()
	formData := make(url.Values)
	formData.Set("current_page", fmt.Sprintf("%d", currPage))
	body := strings.NewReader(formData.Encode())
	req, err := http.NewRequest("POST", u, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	page, err := dataset.Do(ctx, sc, opts, req)
	if err != nil {
		return nil, err
	}
	r := bytes.NewReader(page.Response.Body)
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return nil, err
	}
	var urls []string
	// Try multiple selectors as page structure may have changed
	selectors := []string{
		"tr.hover_tr td.S12 a",
		"table tr td a[href*='event']",
		"tr td a[href*='event?e=']",
		"a[href*='event?e=']",
	}
	
	for _, selector := range selectors {
		doc.Find(selector).EachWithBreak(func(i int, sel *goquery.Selection) bool {
			href, ok := sel.Attr("href")
			if !ok {
				return true // Skip if no href
			}
			// Only process event URLs
			if !strings.Contains(href, "event?e=") {
				return true
			}
			uref, parseErr := url.Parse(href)
			if parseErr != nil {
				return true // Skip invalid URLs, don't break
			}
			u := base.ResolveReference(uref)
			urlStr := u.String()
			// Deduplicate URLs
			for _, existing := range urls {
				if existing == urlStr {
					return true
				}
			}
			urls = append(urls, urlStr)
			return true
		})
		if len(urls) > 0 {
			break // Found URLs with this selector
		}
	}
	if err != nil {
		return nil, err
	}
	return urls, nil
}

var reDeckID = regexp.MustCompile(`^https://mtgtop8\.com/event\?e=(\d+)&d=(\d+)`)

func (d *Dataset) parseItem(
	ctx context.Context,
	opts dataset.ResolvedUpdateOptions,
	sc *scraper.Scraper,
	itemURL string,
) error {
	idSubmatches := reDeckID.FindStringSubmatch(itemURL)
	if idSubmatches == nil {
		return fmt.Errorf("failed to extract deck id from url: %s", itemURL)
	}
	eID, dID := idSubmatches[1], idSubmatches[2]
	id := fmt.Sprintf("%s.%s", eID, dID)
	bkey := d.collectionKey(id)

	if !opts.Reparse && !opts.FetchReplaceAll {
		exists, err := d.blob.Exists(ctx, bkey)
		if err != nil {
			return fmt.Errorf("failed to check if already parsed collection exists: %w", err)
		}
		if opts.Cat {
			b, err := d.blob.Read(ctx, bkey)
			if err != nil {
				d.log.Errorf(ctx, "failed to read item blob: %v", err)
			} else {
				fmt.Println(string(b))
			}
		}
		if exists {
			d.log.Field("url", itemURL).Debugf(ctx, "parsed collection already exists")
			return nil
		}
	}

	req, err := http.NewRequest("GET", itemURL, nil)
	if err != nil {
		return nil
	}
	page, err := dataset.Do(ctx, sc, opts, req)
	if err != nil {
		return err
	}
	r := bytes.NewReader(page.Response.Body)
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return err
	}

	deckName := doc.Find("head title").Text()

	var archetype string
	doc.Find("div.S14 a").EachWithBreak(func(i int, sel *goquery.Selection) bool {
		href, ok := sel.Attr("href")
		if !ok {
			return true
		}
		if strings.HasPrefix(href, "archetype") {
			archetype = strings.TrimSpace(strings.TrimSuffix(sel.Text(), "decks"))
			return false
		}
		return true
	})

	format := doc.Find(".S14 .meta_arch").Text()
	format = strings.TrimSpace(format)

	// Extract tournament metadata: player, event, placement, record
	var player, event, placement, record string
	var wins, losses, ties int
	
	// Try to extract from page structure - MTGTop8 shows this in various places
	// Look for event name in page title or headers
	titleText := doc.Find("head title").Text()
	if strings.Contains(titleText, " - ") {
		parts := strings.Split(titleText, " - ")
		if len(parts) > 1 {
			event = strings.TrimSpace(parts[0])
		}
	}
	
	// Look for player name in various selectors
	doc.Find(".S14, .meta_arch, div[class*='player'], span[class*='player']").Each(func(i int, sel *goquery.Selection) {
		text := strings.TrimSpace(sel.Text())
		if text != "" && !strings.Contains(text, "Format:") && !strings.Contains(text, "Archetype:") {
			// Heuristic: if it looks like a name and we don't have one yet
			if player == "" && len(text) > 2 && len(text) < 50 && !strings.Contains(text, "http") {
				player = text
			}
		}
	})
	
	// Try to extract placement from result/rank indicators
	doc.Find(".S14, .meta_arch, div[class*='result'], span[class*='result'], div[class*='rank'], span[class*='rank']").Each(func(i int, sel *goquery.Selection) {
		text := strings.TrimSpace(sel.Text())
		if strings.Contains(text, "st") || strings.Contains(text, "nd") || strings.Contains(text, "rd") || strings.Contains(text, "th") || 
		   strings.Contains(text, "Top") || strings.Contains(text, "Winner") || strings.Contains(text, "Finalist") {
			placement = text
		}
	})
	
	// Try to extract record (W-L-T format)
	doc.Find(".S14, .meta_arch, div[class*='record'], span[class*='record']").Each(func(i int, sel *goquery.Selection) {
		text := strings.TrimSpace(sel.Text())
		// Look for patterns like "5-2-1" or "5-2" or "5W-2L"
		if matched, _ := regexp.MatchString(`\d+[\s-]+\d+`, text); matched {
			record = text
			// Parse wins/losses/ties from record
			reRecord := regexp.MustCompile(`(\d+)[\s-]+(\d+)(?:[\s-]+(\d+))?`)
			if matches := reRecord.FindStringSubmatch(text); len(matches) >= 3 {
				if w, err := strconv.Atoi(matches[1]); err == nil {
					wins = w
				}
				if l, err := strconv.Atoi(matches[2]); err == nil {
					losses = l
				}
				if len(matches) >= 4 && matches[3] != "" {
					if t, err := strconv.Atoi(matches[3]); err == nil {
						ties = t
					}
				}
			}
		}
	})

	// Try to extract date from page, fallback to current time
	date := time.Now()
	// Look for date in various formats on the page
	doc.Find(".S14, .meta_arch, div[class*='date'], span[class*='date']").Each(func(i int, sel *goquery.Selection) {
		text := strings.TrimSpace(sel.Text())
		parsedDate := games.ParseDateWithFallback(text, date)
		if !parsedDate.Equal(date) || parsedDate.After(time.Date(1990, 1, 1, 0, 0, 0, 0, time.UTC)) {
			date = parsedDate
		}
	})

	section := "Unknown"
	parts := make(map[string][]game.CardDesc)
	doc.Find(`div[style*="display:flex"] > div[align=left]`).EachWithBreak(func(i int, s *goquery.Selection) bool {
		s.Find("div.deck_line, div.O14").EachWithBreak(func(i int, s *goquery.Selection) bool {
			if s.HasClass("O14") {
				switch s.Text() {
				case "COMMANDER":
					section = "Commander"
				case "SIDEBOARD":
					section = "Sideboard"
				default:
					section = "Main"
				}
				return true
			}
			var cardName string
			s.Find("span").Each(func(i int, sel *goquery.Selection) {
				cardName = sel.Text()
				sel.Remove()
			})
			countStr := strings.TrimSpace(s.Text())
			var count int64
			count, err = strconv.ParseInt(countStr, 10, 0)
			if err != nil {
				err = fmt.Errorf("failed to parse count: %q", countStr)
				return false
			}
			// Normalize card name for consistency
			normalizedName := games.NormalizeCardName(cardName)
			if normalizedName == "" {
				// Skip empty card names (after normalization)
				return true
			}
			parts[section] = append(parts[section], game.CardDesc{
				Name:  normalizedName,
				Count: int(count),
			})
			return true
		})
		return true
	})
	if err != nil {
		return fmt.Errorf("failed to parse cards: %w", err)
	}

	t := &game.CollectionTypeDeck{
		Name:      deckName,
		Format:    format,
		Archetype: archetype,
		Player:    player,
		Event:     event,
		Placement: placement,
		Record:    record,
		Wins:      wins,
		Losses:    losses,
		Ties:      ties,
		EventDate: date.Format("2006-01-02"),
	}
	tw := game.CollectionTypeWrapper{
		Type:  t.Type(),
		Inner: t,
	}
	var partitions []game.Partition
	for section, cards := range parts {
		// Only add partition if it has cards (validation requires non-empty partitions)
		if len(cards) == 0 {
			continue
		}
		partitions = append(partitions, game.Partition{
			Name:  section,
			Cards: cards,
		})
	}
	collection := game.Collection{
		Type:        tw,
		ID:          id,
		URL:         itemURL,
		ReleaseDate: date,
		Partitions:  partitions,
	}
	if err := collection.Canonicalize(); err != nil {
		if opts.Cat {
			b, _ := json.Marshal(collection)
			fmt.Println(string(b))
		}
		return fmt.Errorf("collection is invalid: %w", err)
	}
	b, err := json.Marshal(collection)
	if err != nil {
		return err
	}
	if opts.Cat {
		fmt.Println(string(b))
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

var basePrefix = filepath.Join("magic", "mtgtop8")
var collectionsPrefix = filepath.Join(basePrefix, "collections")

func (d *Dataset) collectionKey(collectionID string) string {
	return filepath.Join(collectionsPrefix, collectionID+".json")
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(dataset.Item) error,
	options ...dataset.IterItemsOption,
) error {
	prefix := collectionsPrefix
	de := dataset.DeserializeAsCollection
	return dataset.IterItemsBlobPrefix(ctx, d.blob, prefix, de, fn, options...)
}
