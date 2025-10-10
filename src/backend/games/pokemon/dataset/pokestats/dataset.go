package pokestats

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
)

// Dataset scrapes minimal deck info from PokéStats posts that embed deck exports
// Site is Blogger-style; many posts link to Limitless for full lists. We best-effort
// parse any inline export blocks.
type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

func NewDataset(log *logger.Logger, blob *blob.Bucket) *Dataset {
	return &Dataset{log: log, blob: blob}
}

func (d *Dataset) Description() games.Description {
	return games.Description{Game: "pokemon", Name: "pokestats"}
}

var (
	reDeck = regexp.MustCompile(`(?i)^\s*(\d+)\s+(.+)$`)
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

	var postURLs []string
	if len(opts.ItemOnlyURLs) > 0 {
		postURLs = append(postURLs, opts.ItemOnlyURLs...)
	} else {
		urls, err := d.scrapeIndex(ctx, sc, opts)
		if err != nil {
			return err
		}
		postURLs = urls
	}

	total := 0
	for i, u := range postURLs {
		if limit, ok := opts.ItemLimit.Get(); ok && total >= limit {
			d.log.Infof(ctx, "Reached item limit of %d", limit)
			break
		}
		if (i+1)%10 == 0 {
			d.log.Infof(ctx, "Processing post %d/%d...", i+1, len(postURLs))
		}
		if err := d.parsePost(ctx, sc, u, opts); err != nil {
			d.log.Field("url", u).Warnf(ctx, "failed to parse post: %v", err)
			continue
		}
		total++
	}
	d.log.Infof(ctx, "✅ Extracted %d PokéStats deck posts", total)
	return nil
}

func (d *Dataset) scrapeIndex(
	ctx context.Context,
	sc *scraper.Scraper,
	opts games.ResolvedUpdateOptions,
) ([]string, error) {
	index := "http://www.ptcgstats.com/"
	req, err := http.NewRequest("GET", index, nil)
	if err != nil {
		return nil, err
	}
	page, err := games.Do(ctx, sc, &opts, req)
	if err != nil {
		return nil, err
	}
	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(page.Response.Body))
	if err != nil {
		return nil, err
	}

	found := make(map[string]struct{})
	var urls []string
	doc.Find("a").Each(func(i int, s *goquery.Selection) {
		href, ok := s.Attr("href")
		if !ok {
			return
		}
		h := strings.TrimSpace(href)
		if !strings.Contains(h, "/p/") && !strings.Contains(h, "/20") { // basic filter for posts/pages
			return
		}
		u, err := url.Parse(h)
		if err != nil || u.Host == "limitlesstcg.com" {
			return
		}
		if _, exists := found[u.String()]; exists {
			return
		}
		found[u.String()] = struct{}{}
		urls = append(urls, u.String())
	})
	return urls, nil
}

func (d *Dataset) parsePost(
	ctx context.Context,
	sc *scraper.Scraper,
	postURL string,
	opts games.ResolvedUpdateOptions,
) error {
	// Use URL path as ID
	u, err := url.Parse(postURL)
	if err != nil {
		return err
	}
	id := strings.Trim(strings.ReplaceAll(u.Path, "/", "-"), "-")
	if id == "" {
		id = "index"
	}
	key := filepath.Join("pokemon", "pokestats", id+".json")
	if !opts.Reparse && !opts.FetchReplaceAll {
		if exists, _ := d.blob.Exists(ctx, key); exists {
			return nil
		}
	}

	req, err := http.NewRequest("GET", postURL, nil)
	if err != nil {
		return err
	}
	page, err := games.Do(ctx, sc, &opts, req)
	if err != nil {
		return err
	}
	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(page.Response.Body))
	if err != nil {
		return err
	}

	// Try to find export blocks (pre/code or textarea)
	exportText := strings.TrimSpace(doc.Find("pre, code, textarea").First().Text())
	if exportText == "" {
		return fmt.Errorf("no export found in post")
	}

	cardMap := map[string]int{}
	for _, line := range strings.Split(exportText, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		m := reDeck.FindStringSubmatch(line)
		if len(m) != 3 {
			continue
		}
		count := 0
		fmt.Sscanf(m[1], "%d", &count)
		name := strings.TrimSpace(m[2])
		if count <= 0 || name == "" {
			continue
		}
		cardMap[name] += count
	}
	if len(cardMap) == 0 {
		return fmt.Errorf("no cards parsed from export")
	}

	cards := make([]pgame.CardDesc, 0, len(cardMap))
	for nm, cnt := range cardMap {
		cards = append(cards, pgame.CardDesc{Name: nm, Count: cnt})
	}
	part := pgame.Partition{Name: pgame.PartitionDeck, Cards: cards}
	deckType := &pgame.CollectionTypeDeck{
		Name:      doc.Find("h1, h2, .post-title").First().Text(),
		Format:    "Unknown",
		Archetype: doc.Find("h1, h2, .post-title").First().Text(),
	}
	tw := pgame.CollectionTypeWrapper{Type: deckType.Type(), Inner: deckType}
	col := pgame.Collection{
		ID:          id,
		URL:         postURL,
		Type:        tw,
		ReleaseDate: time.Now(),
		Partitions:  []pgame.Partition{part},
		Source:      "pokestats",
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
