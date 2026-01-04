package scryfall

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/samber/mo"

	"collections/blob"
	"collections/games"
	"collections/games/magic/dataset"
	"collections/games/magic/game"
	"collections/logger"
	"collections/scraper"
)

var base *url.URL

func init() {
	u, err := url.Parse("https://scryfall.com")
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
		Name: "scryfall",
	}
}

var reCollectionRef = regexp.MustCompile(`^https://scryfall.com/sets/.+$`)

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
		if !reCollectionRef.MatchString(u) {
			return fmt.Errorf("invalid only url: %s", u)
		}
	}
	someSection := false
	if opts.Section(`cards?`) {
		someSection = true
		if err := d.extractCards(ctx, sc, opts); err != nil {
			return fmt.Errorf("failed to extract cards: %w", err)
		}
	}
	if opts.Section(`collections?`) {
		someSection = true
		if err := d.extractCollections(ctx, sc, opts); err != nil {
			return fmt.Errorf("failed to extract collections: %w", err)
		}
	}
	if !someSection {
		return fmt.Errorf("no sections matched options")
	}
	return nil
}

type respBulkData struct {
	Data []bulkDataItem `json:"data"`
}

type bulkDataItem struct {
	Type        string `json:"type"`
	DownloadURI string `json:"download_uri"`
}

// https://scryfall.com/docs/api/cards
type card struct {
	cardProps
	ScryfallURI     string     `json:"scryfall_uri"`
	ImageURIs       imageURIs  `json:"image_uris"`
	Rarity          string     `json:"rarity"`
	Artist          string     `json:"artist"`
	Set             string     `json:"set"`
	CollectorNumber string     `json:"collector_number"`
	Faces           []cardFace `json:"card_faces"`
}

type imageURIs struct {
	PNG string `json:"png"`
}

type cardProps struct {
	Name       string `json:"name"`
	ManaCost   string `json:"mana_cost"`
	Power      string `json:"power"`
	Toughness  string `json:"toughness"`
	TypeLine   string `json:"type_line"`
	OracleText string `json:"oracle_text"`
	FlavorText string `json:"flavor_text"`
}

type cardFace struct {
	cardProps
}

func (d *Dataset) extractCards(
	ctx context.Context,
	sc *scraper.Scraper,
	opts dataset.ResolvedUpdateOptions,
) error {
	start := time.Now()
	req, err := http.NewRequest("GET", "https://api.scryfall.com/bulk-data", nil)
	if err != nil {
		return err
	}
	page, err := sc.Do(ctx, req)
	if err != nil {
		return err
	}
	var resp respBulkData
	if err := json.Unmarshal(page.Response.Body, &resp); err != nil {
		return err
	}
	uri := mo.None[string]()
	var types []string
	for _, data := range resp.Data {
		if data.Type == "default_cards" {
			uri = mo.Some(data.DownloadURI)
			break
		}
		types = append(types, data.Type)
	}
	if uri.IsAbsent() {
		return fmt.Errorf("failed to find default_cards type, but found: %v", types)
	}
	req, err = http.NewRequest("GET", uri.MustGet(), nil)
	if err != nil {
		return err
	}
	page, err = sc.Do(ctx, req)
	if err != nil {
		return err
	}
	var rawCards []card
	if err := json.Unmarshal(page.Response.Body, &rawCards); err != nil {
		return err
	}
	d.log.Fieldf("dur", "%v", time.Since(start).Round(time.Millisecond)).
		Infof(ctx, "extracted %d raw cards", len(rawCards))

	start = time.Now()
	wg := new(sync.WaitGroup)
	queue := make(chan card)
	var nok, nerr uint32 = 0, 0
	for i := 0; i < opts.Parallel; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				select {
				case <-ctx.Done():
					return
				case rawCard, ok := <-queue:
					if !ok {
						return
					}
						if err := d.parseCard(ctx, rawCard); err != nil {
							d.log.Errorf(ctx, "failed to parse card %q: %v", rawCard.Name, err)
							atomic.AddUint32(&nerr, 1)
							// Record error in statistics if available
							if stats := games.ExtractStatsFromContext(ctx); stats != nil {
								stats.RecordCategorizedError(ctx, rawCard.ScryfallURI, "scryfall", err)
							}
							continue
						}
					atomic.AddUint32(&nok, 1)
				}
			}
		}()
	}
	for i, rawCard := range rawCards {
		// Check context cancellation
		select {
		case <-ctx.Done():
			close(queue)
			wg.Wait()
			return ctx.Err()
		default:
		}

		// Check item limit
		if n, ok := opts.ItemLimit.Get(); ok && i >= n {
			break
		}
		bkey := d.cardKey(rawCard.Name)
		if !opts.Reparse {
			exists, err := d.blob.Exists(ctx, bkey)
			if err != nil {
				return fmt.Errorf("failed to check if card already exists: %w", err)
			}
			if exists {
				d.log.Field("name", rawCard.Name).Debugf(ctx, "parsed card already exists")
				continue
			}
		}
		if i > 0 && i%1000 == 0 {
			d.log.Debugf(ctx, "enqueued %d cards for parsing", i)
		}
		queue <- rawCard
	}
	close(queue)
	wg.Wait()
	d.log.Fieldf("dur", "%v", time.Since(start).Round(time.Millisecond)).
		Infof(ctx, "parsed %d cards, with %d errors", nok, nerr)
	return nil
}

func (d *Dataset) parseCard(
	ctx context.Context,
	rawCard card,
) error {
	var faces []game.CardFace
	if len(rawCard.Faces) == 0 {
		faces = append(faces, game.CardFace{
			Name:       rawCard.Name,
			ManaCost:   rawCard.ManaCost,
			TypeLine:   rawCard.TypeLine,
			OracleText: rawCard.OracleText,
			FlavorText: rawCard.FlavorText,
			Power:      rawCard.Power,
			Toughness:  rawCard.Toughness,
		})
	} else {
		for _, rawFace := range rawCard.Faces {
			faces = append(faces, game.CardFace{
				Name:       rawFace.Name,
				ManaCost:   rawFace.ManaCost,
				TypeLine:   rawFace.TypeLine,
				OracleText: rawFace.OracleText,
				FlavorText: rawFace.FlavorText,
				Power:      rawFace.Power,
				Toughness:  rawFace.Toughness,
			})
		}
	}
	ref, err := url.Parse(rawCard.ScryfallURI)
	if err != nil {
		return fmt.Errorf("failed to parse scryfall uri %s: %w", rawCard.ScryfallURI, err)
	}
	qvals := ref.Query()
	for key := range qvals {
		if strings.HasPrefix(key, "utm") {
			qvals.Del(key)
		}
	}
	ref.RawQuery = qvals.Encode()
	card := &game.Card{
		Name:  rawCard.Name,
		Faces: faces,
		Images: []game.CardImage{
			{URL: rawCard.ImageURIs.PNG},
		},
		References: []game.CardReference{
			{URL: ref.String()},
		},
	}

	bkey := d.cardKey(card.Name)
	b, err := json.Marshal(card)
	if err != nil {
		return fmt.Errorf("failed to marshal card %q: %w", card.Name, err)
	}
	if err := d.blob.Write(ctx, bkey, b); err != nil {
		return fmt.Errorf("failed to write card %q: %w", card.Name, err)
	}

	// Record success in statistics if available
	if stats := games.ExtractStatsFromContext(ctx); stats != nil {
		stats.RecordSuccess()
	}

	return nil
}

func (d *Dataset) extractCollections(
	ctx context.Context,
	sc *scraper.Scraper,
	opts dataset.ResolvedUpdateOptions,
) error {
	urls := make(chan string)
	wg := new(sync.WaitGroup)
	for i := 0; i < opts.Parallel; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for u := range urls {
				if err := d.parseCollection(ctx, sc, u, opts); err != nil {
					d.log.Field("url", u).Errorf(ctx, "failed to parse collection: %v", err)
					// Record error in statistics if available
					if stats := games.ExtractStatsFromContext(ctx); stats != nil {
						stats.RecordCategorizedError(ctx, u, "scryfall", err)
					}
					continue
				}
			}
		}()
	}

	if len(opts.ItemOnlyURLs) > 0 {
		for _, u := range opts.ItemOnlyURLs {
			// Check context cancellation before sending
			select {
			case <-ctx.Done():
				close(urls)
				wg.Wait()
				return ctx.Err()
			default:
			}
			urls <- u
		}
	} else {
		parsedURLs, err := d.parsePage(ctx, sc, "/sets")
		if err != nil {
			close(urls)
			wg.Wait()
			return err
		}
		collections := 0
		for _, u := range parsedURLs {
			// Check context cancellation before sending
			select {
			case <-ctx.Done():
				close(urls)
				wg.Wait()
				return ctx.Err()
			default:
			}
			urls <- u
			collections++
			if limit, ok := opts.ItemLimit.Get(); ok && collections >= limit {
				break
			}
		}
	}
	close(urls)

	wg.Wait()
	return nil
}

func (d *Dataset) parsePage(
	ctx context.Context,
	sc *scraper.Scraper,
	ref string,
) ([]string, error) {
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
	var urls []string
	sel := doc.Find("table.checklist tbody tr td:first-of-type a")
	sel.EachWithBreak(func(i int, sel *goquery.Selection) bool {
		href, ok := sel.Attr("href")
		if !ok {
			err = fmt.Errorf("failed to find set href")
			return false
		}
		if strings.HasPrefix(href, "/cubes") {
			return true // skip
		}
		urls = append(urls, href)
		return true
	})
	return urls, nil
}

var reSetName = regexp.MustCompile(`(.*)\s+\((.*)\)$`)
var reSetReleased = regexp.MustCompile(`Released[\p{Zs}\s]+(\d+-\d+-\d+)`)

func (d *Dataset) parseCollection(
	ctx context.Context,
	sc *scraper.Scraper,
	u string,
	opts dataset.ResolvedUpdateOptions,
) error {
	parts := strings.Split(u, "/")
	setID := parts[len(parts)-1]
	bkey := d.collectionKey(setID)

	if !opts.Reparse {
		exists, err := d.blob.Exists(ctx, bkey)
		if err != nil {
			return fmt.Errorf("failed to check if already parsed collection exists: %w", err)
		}
		if exists {
			d.log.Field("url", u).Debugf(ctx, "parsed collection already exists")
			return nil
		}
	}

	req, err := http.NewRequest("GET", u, nil)
	if err != nil {
		return err
	}
	page, err := sc.Do(ctx, req)
	if err != nil {
		return err
	}
	r := bytes.NewReader(page.Response.Body)
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return err
	}

	setNameRaw := strings.TrimSpace(doc.FindMatcher(goquery.Single(".set-header-title-h1")).Text())
	setNameSubmatches := reSetName.FindStringSubmatch(setNameRaw)
	if setNameSubmatches == nil {
		return fmt.Errorf("failed to extract set name: %q", setNameRaw)
	}
	setName := setNameSubmatches[1]
	setCode := setNameSubmatches[2]

	setReleasedRaw := strings.TrimSpace(doc.FindMatcher(goquery.Single(".set-header-title-words")).Text())
	setReleasedSubmatches := reSetReleased.FindStringSubmatch(setReleasedRaw)
	if setReleasedSubmatches == nil {
		return fmt.Errorf("failed to extract set release date: %q", setReleasedRaw)
	}
		// Use centralized date parsing with validation
		setReleaseDate, err := games.ParseDateWithValidation(setReleasedSubmatches[1])
		if err != nil {
			// Try fallback format
			if fallbackDate, fallbackErr := time.Parse("2006-01-02", setReleasedSubmatches[1]); fallbackErr == nil {
				year := fallbackDate.Year()
				if year >= 1990 && year <= 2100 {
					setReleaseDate = fallbackDate
					err = nil
				} else {
					err = fmt.Errorf("fallback date has invalid year %d", year)
				}
			}
		}
	if err != nil {
		return fmt.Errorf("failed to parse set release date %q: %w", setReleasedSubmatches[1], err)
	}

	sel := doc.Find(".card-grid-header-content")
	var partitions []game.Partition
	sel.EachWithBreak(func(i int, headerSel *goquery.Selection) bool {
		// Try to get partition name from id attribute on anchor (legacy format)
		anchorSel := headerSel.Find("a:first-of-type")
		partitionName, hasID := anchorSel.Attr("id")

		// If no id attribute, extract from text content
		if !hasID {
			// Clone the header selection and remove child elements to get just the text
			textSel := headerSel.Clone()
			textSel.Find("a").Remove()
			textSel.Find(".card-grid-header-dot").Remove()
			textSel.Find("span").Remove()
			partitionName = strings.TrimSpace(textSel.Text())

			// Clean up the partition name
			partitionName = strings.TrimSpace(partitionName)
			partitionName = strings.TrimPrefix(partitionName, "•")
			partitionName = strings.TrimSpace(partitionName)

			// If still empty, try extracting from the raw text content
			if partitionName == "" {
				// Get all text and split by newlines
				allText := headerSel.Text()
				lines := strings.Split(allText, "\n")
				for _, line := range lines {
					line = strings.TrimSpace(line)
					// Skip lines with "cards", bullet points, or empty
					if line != "" &&
					   !strings.Contains(strings.ToLower(line), "cards") &&
					   !strings.Contains(line, "•") &&
					   !strings.HasPrefix(line, "<") {
						partitionName = line
						break
					}
				}
			}

			// Final cleanup: remove any HTML entities or special characters
			partitionName = strings.TrimSpace(partitionName)
			// Remove common prefixes/suffixes
			partitionName = strings.TrimPrefix(partitionName, "•")
			partitionName = strings.TrimSuffix(partitionName, "•")
			partitionName = strings.TrimSpace(partitionName)
		}

		// If we still don't have a partition name, skip this partition with a warning
		if partitionName == "" {
			html, _ := headerSel.Html()
			d.log.Field("html", html).Warnf(ctx, "skipping partition with no name")
			return true // Continue to next partition instead of failing
		}

		var cards []game.CardDesc
		seen := make(map[string]int) // Key: normalized card name (lowercase), Value: index in cards slice
		headerSel.ParentsMatcher(goquery.Single(".card-grid-header")).
			NextFilteredUntil(".card-grid", ".card-grid-header").
			Find(".card-grid-item-invisible-label").
			Each(func(i int, sel *goquery.Selection) {
				t := sel.Text()
				if strings.HasPrefix(t, "|") && strings.HasSuffix(t, ".") {
					return
				}
				// Normalize card name first, then check for duplicates
				normalizedName := games.NormalizeCardName(t)
				if normalizedName == "" {
					return // Skip empty card names
				}
				// Use normalized lowercase name for duplicate detection
				normalizedLower := strings.ToLower(normalizedName)
				if j, ok := seen[normalizedLower]; ok {
					cards[j].Count++
					return
				}
				seen[normalizedLower] = len(cards)
				cards = append(cards, game.CardDesc{
					Name:  normalizedName,
					Count: 1,
				})
			})

		// Only add partition if it has cards (validation requires non-empty partitions)
		if len(cards) == 0 {
			d.log.Field("partition", partitionName).Warnf(ctx, "skipping partition with no cards")
			return true // Continue to next partition
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

	// Check if we have any partitions with cards
	if len(partitions) == 0 {
		return fmt.Errorf("collection has no partitions with cards")
	}

	ty := &game.CollectionTypeSet{
		Name: setName,
		Code: setCode,
	}
	set := game.Collection{
		Type: game.CollectionTypeWrapper{
			Type:  ty.Type(),
			Inner: ty,
		},
		ID:          setID,
		URL:         u,
		ReleaseDate: setReleaseDate,
		Partitions:  partitions,
	}

	// Validate and normalize the collection before writing
	if err := set.Canonicalize(); err != nil {
		return fmt.Errorf("collection is invalid: %w", err)
	}

	b, err := json.Marshal(set)
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

func (d *Dataset) resolveRef(ref string) (string, error) {
	u, err := url.Parse(ref)
	if err != nil {
		return "", err
	}
	u = base.ResolveReference(u)
	return u.String(), nil
}

var basePrefix = filepath.Join("magic", "scryfall")
var cardsPrefix = filepath.Join(basePrefix, "cards")
var collectionsPrefix = filepath.Join(basePrefix, "collections")

func (d *Dataset) cardKey(cardName string) string {
	return filepath.Join(cardsPrefix, cardName+".json")
}

func (d *Dataset) collectionKey(collectionID string) string {
	return filepath.Join(collectionsPrefix, collectionID+".json")
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(dataset.Item) error,
	options ...dataset.IterItemsOption,
) error {
	var de dataset.ItemDeserializer
	prefix := basePrefix
	for _, opt := range options {
		switch opt := opt.(type) {
		case *dataset.OptIterItemsFilterType:
			switch opt.Only.(type) {
			case *dataset.CardItem:
				prefix = cardsPrefix
				de = dataset.DeserializeAsCard
			case *dataset.CollectionItem:
				prefix = collectionsPrefix
				de = dataset.DeserializeAsCollection
			}
		}
	}
	if prefix == basePrefix {
		de = func(key string, data []byte) (dataset.Item, error) {
			switch {
			case strings.HasPrefix(key, cardsPrefix):
				return dataset.DeserializeAsCard(key, data)
			case strings.HasPrefix(key, collectionsPrefix):
				return dataset.DeserializeAsCard(key, data)
			default:
				return nil, fmt.Errorf("unsupported key: %q", key)
			}
		}
	}
	return dataset.IterItemsBlobPrefix(ctx, d.blob, prefix, de, fn, options...)
}
