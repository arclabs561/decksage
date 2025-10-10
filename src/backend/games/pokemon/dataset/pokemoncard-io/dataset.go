package pokemoncardio

import (
	"bytes"
	"collections/blob"
	"collections/games"
	pgame "collections/games/pokemon/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"go.uber.org/ratelimit"
)

// Dataset scrapes user-submitted Pokemon decks from pokemoncard.io
type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

func NewDataset(log *logger.Logger, blob *blob.Bucket) *Dataset {
	return &Dataset{log: log, blob: blob}
}

func (d *Dataset) Description() games.Description {
	return games.Description{Game: "pokemon", Name: "pokemoncard-io"}
}

var (
	baseURL, _ = url.Parse("https://pokemoncard.io/")
	reDeckID   = regexp.MustCompile(`-(\d+)$`)
)

var (
	// Be polite; Cloudflare often challenges rapid requests
	requestLimiter = ratelimit.New(60, ratelimit.Per(time.Minute)) // 1 rps
)

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	opts, err := games.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	var deckURLs []string
	if len(opts.ItemOnlyURLs) > 0 {
		deckURLs = append(deckURLs, opts.ItemOnlyURLs...)
	} else {
		urls, err := d.scrapeDeckListingPages(ctx, sc, opts)
		if err != nil {
			return err
		}
		deckURLs = urls
	}

	total := 0
	for i, u := range deckURLs {
		if limit, ok := opts.ItemLimit.Get(); ok && total >= limit {
			d.log.Infof(ctx, "Reached item limit of %d", limit)
			break
		}
		if (i+1)%10 == 0 {
			d.log.Infof(ctx, "Processing deck %d/%d...", i+1, len(deckURLs))
		}
		if err := d.parseDeck(ctx, sc, u, opts); err != nil {
			d.log.Field("url", u).Warnf(ctx, "failed to parse deck: %v", err)
			continue
		}
		total++
	}
	d.log.Infof(ctx, "✅ Extracted %d PokemonCard.io decks", total)
	return nil
}

func (d *Dataset) scrapeDeckListingPages(
	ctx context.Context,
	sc *scraper.Scraper,
	opts games.ResolvedUpdateOptions,
) ([]string, error) {
	// Basic pagination over deck search
	// Try page parameter; stop when no new links found or pages limit reached
	startPage := opts.ScrollStart.OrElse(0)
	maxPages := opts.ScrollLimit.OrElse(0)

	found := make(map[string]struct{})
	urls := []string{}

	for pageNum := startPage; ; pageNum++ {
		if maxPages > 0 && pageNum >= startPage+maxPages {
			break
		}

		candidateURLs := []string{
			"https://pokemoncard.io/deck-search/",
			fmt.Sprintf("https://pokemoncard.io/deck-search/?page=%d", pageNum+1),
			fmt.Sprintf("https://pokemoncard.io/deck-search/page/%d/", pageNum+1),
			fmt.Sprintf("https://pokemoncard.io/deck-search/?view=grid&page=%d", pageNum+1),
		}

		newCount := 0
		for _, listURL := range candidateURLs {
			req, err := http.NewRequest("GET", listURL, nil)
			if err != nil {
				continue
			}
			// Headers to reduce 403s
			req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
			req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
			req.Header.Set("Accept-Language", "en-US,en;q=0.5")

			requestLimiter.Take()
			page, err := games.Do(ctx, sc, &opts, req)
			if err != nil || len(page.Response.Body) == 0 {
				continue
			}

			doc, err := goquery.NewDocumentFromReader(bytes.NewReader(page.Response.Body))
			if err != nil {
				continue
			}

			doc.Find("a[href*='/deck/']").Each(func(i int, s *goquery.Selection) {
			href, ok := s.Attr("href")
			if !ok {
				return
			}
			href = strings.TrimSpace(href)
			if !strings.Contains(href, "/deck/") {
				return
			}
			// Normalize absolute URL
			u, err := url.Parse(href)
			if err != nil {
				return
			}
			if !u.IsAbs() {
				u = baseURL.ResolveReference(u)
			}
			segs := strings.Split(strings.TrimSuffix(u.Path, "/"), "/")
			if len(segs) == 0 {
				return
			}
			slug := segs[len(segs)-1]
			if !reDeckID.MatchString(slug) {
				return
			}
			full := u.String()
			if _, exists := found[full]; exists {
				return
			}
			found[full] = struct{}{}
			urls = append(urls, full)
			newCount++
			})
			// If we found any on this candidate, no need to try others for this page number
			if newCount > 0 {
				break
			}
		}

		d.log.Field("page", fmt.Sprintf("%d", pageNum+1)).Field("found", fmt.Sprintf("%d", newCount)).Infof(ctx, "pokemoncard.io listing")
		if newCount == 0 {
			break
		}
		// Gentle crawl
		time.Sleep(500 * time.Millisecond)
	}

	return urls, nil
}

func (d *Dataset) parseDeck(
	ctx context.Context,
	sc *scraper.Scraper,
	deckURL string,
	opts games.ResolvedUpdateOptions,
) error {
	// Derive ID from slug suffix
	id := ""
	if u, err := url.Parse(deckURL); err == nil {
		segs := strings.Split(strings.TrimSuffix(u.Path, "/"), "/")
		if len(segs) > 0 {
			slug := segs[len(segs)-1]
			if m := reDeckID.FindStringSubmatch(slug); len(m) == 2 {
				id = m[1]
			}
		}
	}
	if id == "" {
		return fmt.Errorf("failed to extract deck id from url")
	}

	key := d.collectionKey(id)
	if !opts.Reparse && !opts.FetchReplaceAll {
		if exists, _ := d.blob.Exists(ctx, key); exists {
			d.log.Field("deck_id", id).Debugf(ctx, "deck already exists")
			return nil
		}
	}

	req, err := http.NewRequest("GET", deckURL, nil)
	if err != nil {
		return err
	}
	// Add headers to reduce 403s
	req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
	req.Header.Set("Accept-Language", "en-US,en;q=0.5")
	requestLimiter.Take()
	page, err := games.Do(ctx, sc, &opts, req)
	if err != nil {
		return err
	}

	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(page.Response.Body))
	if err != nil {
		return err
	}

	// Name
	name := strings.TrimSpace(doc.Find(".deck-metadata-container h1").First().Text())
	if name == "" {
		name = "PokemonCard.io Deck"
	}

	// Format
	format := strings.TrimSpace(doc.Find(".deck-metadata-container a[href*='/category/format/']").First().Text())
	if format == "" {
		format = "Unknown"
	}

	// Cards: use visual deck output entries
	cardNameToCount := map[string]int{}
	doc.Find("#full-deck .deck-output a.ygodeckcard").Each(func(i int, s *goquery.Selection) {
		img := s.Find("img").First()
		cardName := strings.TrimSpace(img.AttrOr("data-cardname", ""))
		if cardName == "" {
			return
		}
		countText := strings.TrimSpace(s.Find(".card-count").First().Text())
		n := 1
		if strings.HasPrefix(countText, "x") {
			fmt.Sscanf(countText, "x%d", &n)
		}
		cardNameToCount[cardName] += n
	})

	if len(cardNameToCount) == 0 {
		// Fallback: parse export textarea if present
		exportText := strings.TrimSpace(doc.Find("#export0").Text())
		for _, line := range strings.Split(exportText, "\n") {
			line = strings.TrimSpace(line)
			if line == "" || strings.Contains(line, " - ") { // section headers like "Pokemon - 18"
				continue
			}
			// Format: "2 Card Name SET 123" -> take leading count and card name
			parts := strings.Fields(line)
			if len(parts) < 2 {
				continue
			}
			cnt := 1
			fmt.Sscanf(parts[0], "%d", &cnt)
			// Card name is everything except trailing set code and number; best effort: drop last 2 tokens
			nameParts := parts[1:]
			if len(nameParts) >= 2 {
				nameParts = nameParts[:len(nameParts)-2]
			}
			nm := strings.TrimSpace(strings.Join(nameParts, " "))
			if nm == "" {
				continue
			}
			cardNameToCount[nm] += cnt
		}
	}

	if len(cardNameToCount) == 0 {
		return fmt.Errorf("no cards found on page")
	}

	cards := make([]pgame.CardDesc, 0, len(cardNameToCount))
	for nm, cnt := range cardNameToCount {
		cards = append(cards, pgame.CardDesc{Name: nm, Count: cnt})
	}

	part := pgame.Partition{Name: pgame.PartitionDeck, Cards: cards}
	deckType := &pgame.CollectionTypeDeck{
		Name:      name,
		Format:    format,
		Archetype: name,
	}
	tw := pgame.CollectionTypeWrapper{Type: deckType.Type(), Inner: deckType}
	col := pgame.Collection{
		ID:          id,
		URL:         deckURL,
		Type:        tw,
		ReleaseDate: time.Now(),
		Partitions:  []pgame.Partition{part},
		Source:      "pokemoncard-io",
	}
	if err := col.Canonicalize(); err != nil {
		return err
	}

	b, err := json.Marshal(col)
	if err != nil {
		return err
	}
	return d.blob.Write(ctx, key, b)
}

func (d *Dataset) collectionKey(id string) string {
	return filepath.Join("pokemon", "pokemoncard-io", id+".json")
}
