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
			for t := range tasks {
				if err := d.parseItem(ctx, opts, sc, t.ItemURL); err != nil {
					d.log.Errorf(ctx, "failed to parse item: %v", err)
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
	page, err := dataset.Do(ctx, sc, &opts, req)
	if err != nil {
		return nil, err
	}
	r := bytes.NewReader(page.Response.Body)
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return nil, err
	}
	var urls []string
	doc.Find("tr.hover_tr td.S12 a").EachWithBreak(func(i int, sel *goquery.Selection) bool {
		href, ok := sel.Attr("href")
		if !ok {
			html, _ := sel.Parent().Html()
			err = fmt.Errorf("failed to find href in: %s", html)
			return false
		}
		uref, parseErr := url.Parse(href)
		if parseErr != nil {
			err = fmt.Errorf("failed to parse href %q: %w", href, parseErr)
			return false
		}
		u := base.ResolveReference(uref)
		urls = append(urls, u.String())
		return true
	})
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
			d.log.Field("url", itemURL).Debugf(ctx, "parsed collection already is exists")
			return nil
		}
	}

	req, err := http.NewRequest("GET", itemURL, nil)
	if err != nil {
		return err
	}
	page, err := dataset.Do(ctx, sc, &opts, req)
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

	// Extract event name, player, and placement
	var event, player string
	var placement int

	// Event name is in first div.event_title
	event = strings.TrimSpace(doc.Find("div.event_title").First().Text())

	// Player is in <a class=player_big>
	player = strings.TrimSpace(doc.Find("a.player_big").Text())

	// Placement is in second div.event_title as "#N " prefix
	placementText := doc.Find("div.event_title").Eq(1).Text()
	if strings.HasPrefix(placementText, "#") {
		// Extract number after #
		parts := strings.SplitN(placementText, " ", 2)
		if len(parts) > 0 {
			numStr := strings.TrimPrefix(parts[0], "#")
			if num, err := strconv.Atoi(numStr); err == nil {
				placement = num
			}
		}
	}

	date := time.Now()

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
			// Validate card count is reasonable
			if count <= 0 || count > 100 {
				d.log.Field("url", itemURL).Warnf(ctx, "invalid card count %d for %s, skipping", count, cardName)
				return true // Continue to next card
			}
			parts[section] = append(parts[section], game.CardDesc{
				Name:  cardName,
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
	}
	tw := game.CollectionTypeWrapper{
		Type:  t.Type(),
		Inner: t,
	}
	var partitions []game.Partition
	for section, cards := range parts {
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
		Source:      "mtgtop8", // Source tracking
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
	return d.blob.Write(ctx, bkey, b)

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
