package deckbox

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/PuerkitoBio/goquery"

	"collections/blob"
	"collections/games/magic/dataset"
	"collections/games/magic/game"
	"collections/logger"
	"collections/scraper"
)

var base *url.URL

func init() {
	u, err := url.Parse("https://deckbox.org")
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

func (d Dataset) Description() dataset.Description {
	return dataset.Description{
		Name: "deckbox",
	}
}

var reCollectionURL = regexp.MustCompile(`^https://deckbox.org/sets/\d+`)

type task struct {
	CollectionURL string
	ReleaseDate   time.Time
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
	for _, u := range opts.ItemOnlyURLs {
		if !reCollectionURL.MatchString(u) {
			return fmt.Errorf("invalid only url: %s", u)
		}
	}

	tasks := make(chan task)
	wg := new(sync.WaitGroup)
	for i := 0; i < opts.Parallel; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for task := range tasks {
				if err := d.parseCollection(ctx, sc, task, opts); err != nil {
					d.log.Field("url", task.CollectionURL).Errorf(ctx, "failed to parse collection: %v", err)
					continue
				}
			}
		}()
	}

	if len(opts.ItemOnlyURLs) > 0 {
		for _, u := range opts.ItemOnlyURLs {
			tasks <- task{
				CollectionURL: u,
				ReleaseDate:   time.Now(),
			}
		}
	} else {
		if err := d.scrollPages(ctx, sc, tasks, opts); err != nil {
			return err
		}
	}
	close(tasks)
	wg.Wait()
	return nil
}

func (d *Dataset) scrollPages(
	ctx context.Context,
	sc *scraper.Scraper,
	tasks chan task,
	opts dataset.ResolvedUpdateOptions,
) error {
	page := opts.ScrollStart.OrElse(1)
	collections := 0
	nextPageRef := fmt.Sprintf("/decks/mtg?p=%d", page)
PAGES:
	for {
		p, err := d.parsePage(ctx, sc, nextPageRef)
		if err != nil {
			return err
		}
		if !p.Next() {
			break
		}
		for i, collectionURL := range p.CollectionURLs {
			tasks <- task{
				CollectionURL: collectionURL,
				ReleaseDate:   p.CollectionReleaseDates[i],
			}
			collections++
			if limit, ok := opts.ItemLimit.Get(); ok && collections >= limit {
				break PAGES
			}
		}
		firstURL := ""
		if len(p.CollectionURLs) > 0 {
			firstURL = p.CollectionURLs[0]
		}
		var firstReleaseDate *time.Time
		if n := len(p.CollectionReleaseDates); n > 0 {
			firstReleaseDate = &p.CollectionReleaseDates[0]
		}
		d.log.Fieldf("page", "%d", page).
			Field("pageUrl", p.CurrURL).
			Fieldf("total", "%d", collections).
			Fieldf("new", "%d", len(p.CollectionURLs)).
			Field("firstUrl", firstURL).
			Fieldf("firstReleaseDate", "%v", firstReleaseDate).
			Infof(ctx, "scrolled page")
		page++
		if limit, ok := opts.ScrollLimit.Get(); ok && page >= limit {
			break PAGES
		}
		nextPageRef = p.NextURL
	}
	return nil
}

type parsedPage struct {
	CurrURL                string
	NextURL                string
	CollectionURLs         []string
	CollectionReleaseDates []time.Time
}

func (p parsedPage) Next() bool {
	return p.NextURL != ""
}

func (d *Dataset) parsePage(
	ctx context.Context,
	sc *scraper.Scraper,
	ref string,
) (*parsedPage, error) {
	u, err := d.resolveRef(ref)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequest("GET", u, nil)
	if err != nil {
		return nil, err
	}
	page, err := sc.Do(ctx, req)
	if err != nil {
		return nil, err
	}

	r := bytes.NewReader(page.Response.Body)
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return nil, err
	}
	sel := doc.Find("#users_list_container tr")
	var collectionURLs []string
	var collectionReleaseDates []time.Time
	sel.EachWithBreak(func(i int, sel *goquery.Selection) bool {
		if i == 0 {
			// skip header
			return true
		}
		val, ok := sel.Find("td:first-of-type a").Attr("href")
		if !ok {
			s, _ := sel.Html()
			err = fmt.Errorf("failed to find href in sel: %s", s)
			return false
		}
		var cu string
		cu, err = d.resolveRef(val)
		if err != nil {
			return false
		}
		collectionURLs = append(collectionURLs, cu)
		t := strings.TrimSpace(sel.Find("td:last-of-type span[id^='time']").Text())
		var releaseDate time.Time
		releaseDate, err = time.Parse("02-Jan-2006 15:04", t)
		if err != nil {
			return false
		}
		collectionReleaseDates = append(collectionReleaseDates, releaseDate)
		return true
	})
	if err != nil {
		return nil, err
	}

	sel = doc.Find(".controls:first-of-type a:last-of-type")
	nextPageURL, ok := sel.Attr("href")
	if !ok {
		return nil, fmt.Errorf("failed to find next page href")
	}

	return &parsedPage{
		CurrURL:                u,
		NextURL:                nextPageURL,
		CollectionURLs:         collectionURLs,
		CollectionReleaseDates: collectionReleaseDates,
	}, nil
}

var reDeckID = regexp.MustCompile(`/sets/(\d+)`)

func (d *Dataset) parseCollection(
	ctx context.Context,
	sc *scraper.Scraper,
	task task,
	opts dataset.ResolvedUpdateOptions,
) error {
	matches := reDeckID.FindStringSubmatch(task.CollectionURL)
	if len(matches) != 2 {
		return fmt.Errorf("failed to create deck id from url %s", task.CollectionURL)
	}
	id := matches[1]
	bkey := d.collectionKey(id)

	if !opts.Reparse {
		exists, err := d.blob.Exists(ctx, bkey)
		if err != nil {
			return fmt.Errorf("failed to check if already parsed collection exists: %w", err)
		}
		if exists {
			d.log.Field("url", task.CollectionURL).Debugf(ctx, "parsed collection already is exists")
			return nil
		}
	}

	req, err := http.NewRequest("GET", task.CollectionURL, nil)
	if err != nil {
		return err
	}
	page, err := sc.Do(ctx, req)
	if err != nil {
		return fmt.Errorf("failed to fetch: %w", err)
	}
	if page.Request.URL != task.CollectionURL {
		if page.Request.URL == "https://deckbox.org/" || strings.HasPrefix(page.Request.URL, "https://deckbox.org/users/") {
			return errors.New("not found")
		}
	}

	r := bytes.NewReader(page.Response.Body)
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return err
	}

	collectionName := strings.TrimSpace(doc.Find(".page_header .section_title span").Text())

	var t game.CollectionType
	doc.Find("#validity span.dt.note").EachWithBreak(func(i int, sel *goquery.Selection) bool {
		if strings.TrimSpace(sel.Text()) != "Format:" {
			return true
		}
		format := sel.NextFilteredUntil("span.variant", "span.dt.note").Text()
		format = strings.TrimSpace(format)
		switch format {
		case "cub":
			t = &game.CollectionTypeCube{
				Name: collectionName,
			}
		default:
			t = &game.CollectionTypeDeck{
				Name:   collectionName,
				Format: format,
			}
		}
		return false
	})
	if err != nil {
		return err
	}
	if t == nil {
		// No format found - might be inventory/wishlist/collection
		// Default to Cube type for general collections
		t = &game.CollectionTypeCube{
			Name: collectionName,
		}
	}

	var partitions []game.Partition
	sel := doc.Find("#show_simple_contents .section_header")
	sel.EachWithBreak(func(i int, sel *goquery.Selection) bool {
		title := strings.TrimSpace(sel.Find(".section_title").Text())
		var partitionName string
		switch {
		case strings.HasPrefix(title, "Main Deck"):
			partitionName = "Main"
		case strings.HasPrefix(title, "Sideboard"):
			partitionName = "Sideboard"
		case strings.HasPrefix(title, "Scratchpad"):
			partitionName = "Scratchpad"
		default:
			err = fmt.Errorf("unknown section title: %q", title)
			return false
		}
		var cards []game.CardDesc
		sel.NextUntil(".section_title").
			Find(".set_cards .card_name a").
			Each(func(i int, sel *goquery.Selection) {
				cardName := strings.TrimSpace(sel.Text())
				cardCountStr := strings.TrimSpace(sel.SiblingsFiltered(".card_count").First().Text())
				cardCount, err := strconv.ParseInt(cardCountStr, 10, 0)
				if err != nil {
					cardCount = 1
				}
				cards = append(cards, game.CardDesc{
					Name:  cardName,
					Count: int(cardCount),
				})
			})
		if len(cards) == 0 {
			return true
		}
		partitions = append(partitions, game.Partition{
			Name:  partitionName,
			Cards: cards,
		})
		return true
	})
	if err != nil {
		return err
	}

	tw := game.CollectionTypeWrapper{
		Type:  t.Type(),
		Inner: t,
	}
	collection := &game.Collection{
		ID:          id,
		URL:         task.CollectionURL,
		Type:        tw,
		ReleaseDate: task.ReleaseDate,
		Partitions:  partitions,
		Source:      "deckbox", // Source tracking
	}
	if err := collection.Canonicalize(); err != nil {
		return fmt.Errorf("collection is invalid: %w", err)
	}

	b, err := json.Marshal(collection)
	if err != nil {
		return err
	}
	return d.blob.Write(ctx, bkey, b)
}

var prefix = filepath.Join("magic", "deckbox")

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
