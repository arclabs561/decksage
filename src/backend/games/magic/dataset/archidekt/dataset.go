package archidekt

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"strconv"
	"time"

	"collections/blob"
	"collections/games"
	"collections/games/magic/dataset"
	"collections/games/magic/game"
	"collections/logger"
	limpet "github.com/arclabs561/limpet"
)

var base *url.URL

const prefix = "magic/archidekt/"

func init() {
	u, err := url.Parse("https://archidekt.com/")
	if err != nil {
		panic(err)
	}
	base = u
}

// Dataset extracts Commander decks from Archidekt's public API via limpet.
// Limpet caches raw HTTP responses so extraction logic can be iterated
// without re-fetching. Rate limit: ~40 req/min per Archidekt staff.
type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

func NewDataset(log *logger.Logger, blob *blob.Bucket) dataset.Dataset {
	return &Dataset{log: log, blob: blob}
}

func (d *Dataset) Description() dataset.Description {
	return dataset.Description{Name: "archidekt"}
}

type searchResponse struct {
	Count   int           `json:"count"`
	Next    *string       `json:"next"`
	Results []deckSummary `json:"results"`
}

type deckSummary struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

type deckDetail struct {
	ID        int    `json:"id"`
	Name      string `json:"name"`
	ViewCount int    `json:"viewCount"`
	Owner     struct {
		Username string `json:"username"`
	} `json:"owner"`
	CreatedAt string `json:"createdAt"`
	Cards     []struct {
		Quantity   int      `json:"quantity"`
		Categories []string `json:"categories"`
		Card       struct {
			OracleCard struct {
				Name string `json:"name"`
			} `json:"oracleCard"`
		} `json:"card"`
	} `json:"cards"`
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *limpet.Client,
	options ...dataset.UpdateOption,
) error {
	opts, err := dataset.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}
	_ = opts // used for ItemOnlyURLs if needed

	maxDecks := 5000
	formatCode := 3 // Commander

	d.log.Infof(ctx, "archidekt: starting (max %d, format %d)", maxDecks, formatCode)

	saved := 0
	for page := 1; saved < maxDecks; page++ {
		searchURL := base.JoinPath("api/decks/v3/")
		q := searchURL.Query()
		q.Set("deckFormat", strconv.Itoa(formatCode))
		q.Set("orderBy", "-createdAt")
		q.Set("page", strconv.Itoa(page))
		q.Set("pageSize", "50")
		searchURL.RawQuery = q.Encode()

		searchPage, err := sc.Get(ctx, searchURL.String())
		if err != nil {
			d.log.Warnf(ctx, "archidekt: search page %d: %v", page, err)
			break
		}

		var sr searchResponse
		if err := json.Unmarshal(searchPage.Response.Body, &sr); err != nil {
			d.log.Warnf(ctx, "archidekt: decode page %d: %v", page, err)
			break
		}
		if len(sr.Results) == 0 {
			break
		}

		for _, summary := range sr.Results {
			if saved >= maxDecks || ctx.Err() != nil {
				break
			}

			deckURL := base.JoinPath(fmt.Sprintf("api/decks/%d/", summary.ID))
			deckPage, err := sc.Get(ctx, deckURL.String())
			if err != nil {
				continue
			}

			var dd deckDetail
			if err := json.Unmarshal(deckPage.Response.Body, &dd); err != nil {
				continue
			}

			col := toCollection(dd)
			if col == nil {
				continue
			}
			if err := col.Canonicalize(); err != nil {
				continue
			}

			data, _ := json.Marshal(col)
			key := fmt.Sprintf("%s%d.json", prefix, dd.ID)
			if err := d.blob.Write(ctx, key, data); err != nil {
				continue
			}

			saved++
			if saved%100 == 0 {
				d.log.Infof(ctx, "archidekt: %d saved (page %d)", saved, page)
				if stats := games.ExtractStatsFromContext(ctx); stats != nil {
					stats.RecordSuccess()
				}
			}
		}

		time.Sleep(1500 * time.Millisecond)
	}

	d.log.Infof(ctx, "archidekt: done (%d decks)", saved)
	return nil
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

func toCollection(dd deckDetail) *game.Collection {
	if len(dd.Cards) < 20 {
		return nil
	}

	partitions := make(map[string][]game.CardDesc)
	for _, entry := range dd.Cards {
		name := entry.Card.OracleCard.Name
		if name == "" {
			continue
		}
		partition := "Main"
		for _, cat := range entry.Categories {
			if cat == "Sideboard" {
				partition = "Sideboard"
			} else if cat == "Commander" || cat == "Companion" {
				partition = "Commander"
			}
		}
		partitions[partition] = append(partitions[partition], game.CardDesc{
			Name:  name,
			Count: entry.Quantity,
		})
	}

	var parts []game.Partition
	for name, cards := range partitions {
		parts = append(parts, game.Partition{
			Name:  name,
			Cards: cards,
		})
	}

	if len(parts) == 0 {
		return nil
	}

	deckType := &game.CollectionTypeDeck{
		Name:   dd.Name,
		Format: "commander",
		Player: dd.Owner.Username,
	}

	createdAt, _ := time.Parse(time.RFC3339, dd.CreatedAt)
	if createdAt.IsZero() {
		createdAt = time.Now().UTC()
	}

	return &game.Collection{
		ID:          fmt.Sprintf("archidekt:%d", dd.ID),
		URL:         fmt.Sprintf("https://archidekt.com/decks/%d", dd.ID),
		Type:        game.CollectionTypeWrapper{Type: deckType.Type(), Inner: deckType},
		ReleaseDate: createdAt,
		Partitions:  parts,
	}
}
