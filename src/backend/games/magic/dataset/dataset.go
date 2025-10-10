package dataset

import (
	"collections/blob"
	"collections/games/magic/game"
	"collections/scraper"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"sync"

	"github.com/samber/lo"
	"github.com/samber/mo"
)

type Dataset interface {
	Description() Description
	Extract(
		ctx context.Context,
		scraper *scraper.Scraper,
		options ...UpdateOption,
	) error
	IterItems(
		ctx context.Context,
		fn func(item Item) error,
		options ...IterItemsOption,
	) error
}

var ErrIterItemsStop = errors.New("stop iter items")

type IterItemsOption interface {
	iterItemsOption()
}

type OptIterItemsFilterType struct {
	Only Item
}

type OptIterItemsParallel struct {
	Parallel int
}

func (o *OptIterItemsFilterType) iterItemsOption() {}
func (o *OptIterItemsParallel) iterItemsOption()   {}

type Description struct {
	Name string
}

type UpdateOption interface {
	updateOption()
}

type OptExtractReparse struct{}

type OptExtractScraperReplaceAll struct{}

type OptExtractScraperSkipMissing struct{}

type OptExtractScraperCache struct{}

type OptExtractParallel struct{ Parallel int }

type OptExtractSectionOnly struct{ Section string }

type OptExtractScrollLimit struct{ Limit int }

type OptExtractScrollStart struct{ Start int }

type OptExtractItemLimit struct{ Limit int }

type OptExtractItemOnlyURL struct{ URL string }

type OptExtractItemCat struct{}

func (o *OptExtractReparse) updateOption()            {}
func (o *OptExtractScraperReplaceAll) updateOption()  {}
func (o *OptExtractScraperSkipMissing) updateOption() {}
func (o *OptExtractScraperCache) updateOption()       {}
func (o *OptExtractParallel) updateOption()           {}
func (o *OptExtractSectionOnly) updateOption()        {}
func (o *OptExtractScrollLimit) updateOption()        {}
func (o *OptExtractScrollStart) updateOption()        {}
func (o *OptExtractItemLimit) updateOption()          {}
func (o *OptExtractItemOnlyURL) updateOption()        {}
func (o *OptExtractItemCat) updateOption()            {}

type ResolvedUpdateOptions struct {
	Reparse         bool
	FetchReplaceAll bool
	Parallel        int
	SectionOnly     []string
	ScrollLimit     mo.Option[int]
	ScrollStart     mo.Option[int]
	ItemLimit       mo.Option[int]
	ItemOnlyURLs    []string
	Cat             bool
}

func (ro *ResolvedUpdateOptions) Section(pat string) bool {
	if len(ro.SectionOnly) == 0 {
		return true
	}
	re := regexp.MustCompile(fmt.Sprintf("(?i)%s", pat))
	return lo.ContainsBy(ro.SectionOnly, func(s string) bool {
		return re.MatchString(s)
	})
}

func ResolveUpdateOptions(options ...UpdateOption) (ResolvedUpdateOptions, error) {
	var reparse mo.Option[bool]
	var fetchReplaceAll mo.Option[bool]
	var parallel mo.Option[int]
	var sectionOnly []string
	var scrollLimit mo.Option[int]
	var scrollStart mo.Option[int]
	var collectionLimit mo.Option[int]
	var onlyCollectionURLs []string
	var cat mo.Option[bool]
	for _, opt := range options {
		switch opt := opt.(type) {
		case *OptExtractReparse:
			reparse = mo.Some(true)
		case *OptExtractScraperReplaceAll:
			fetchReplaceAll = mo.Some(true)
		case *OptExtractParallel:
			parallel = mo.Some(opt.Parallel)
		case *OptExtractSectionOnly:
			sectionOnly = append(sectionOnly, opt.Section)
		case *OptExtractScrollLimit:
			if opt.Limit > 0 {
				scrollLimit = mo.Some(opt.Limit)
			}
		case *OptExtractScrollStart:
			if opt.Start < 0 {
				return ResolvedUpdateOptions{}, fmt.Errorf("start page must be non-negatie: %d", opt.Start)
			}
			scrollStart = mo.Some(opt.Start)
		case *OptExtractItemLimit:
			if opt.Limit > 0 {
				collectionLimit = mo.Some(opt.Limit)
			}
		case *OptExtractItemOnlyURL:
			onlyCollectionURLs = append(onlyCollectionURLs, opt.URL)
		case *OptExtractItemCat:
			cat = mo.Some(true)
		default:
			panic(fmt.Sprintf("invalid option: %T", opt))
		}
	}
	return ResolvedUpdateOptions{
		Reparse:         reparse.OrElse(false),
		FetchReplaceAll: fetchReplaceAll.OrElse(false),
		Parallel:        parallel.OrElse(128),
		SectionOnly:     sectionOnly,
		ScrollLimit:     scrollLimit,
		ScrollStart:     scrollStart,
		ItemLimit:       collectionLimit,
		ItemOnlyURLs:    onlyCollectionURLs,
		Cat:             cat.OrElse(false),
	}, nil
}

func Do(
	ctx context.Context,
	sc *scraper.Scraper,
	opts *ResolvedUpdateOptions,
	req *http.Request,
) (*scraper.Page, error) {
	var doOpts []scraper.DoOption
	if opts.FetchReplaceAll {
		doOpts = append(doOpts, &scraper.OptDoReplace{})
	}
	return sc.Do(ctx, req, doOpts...)
}

type Item interface {
	Kind() string
	item()
}

// FIXME
type ItemWrapper struct {
	Kind string `json:"kind"`
	Item Item
}

type CollectionItem struct {
	Collection *game.Collection `json:"collection"`
}

type CardItem struct {
	Card *game.Card `json:"card"`
}

func (i *CollectionItem) Kind() string { return "Collection" }
func (i *CardItem) Kind() string       { return "Card" }

func (n *CollectionItem) item() {}
func (n *CardItem) item()       {}

type ItemDeserializer func(key string, data []byte) (Item, error)

func DeserializeAsCard(_ string, data []byte) (Item, error) {
	var card game.Card
	if err := json.Unmarshal(data, &card); err != nil {
		return nil, err
	}
	return &CardItem{
		Card: &card,
	}, nil
}

func DeserializeAsCollection(_ string, data []byte) (Item, error) {
	var col game.Collection
	if err := json.Unmarshal(data, &col); err != nil {
		return nil, err
	}
	return &CollectionItem{
		Collection: &col,
	}, nil
}

func IterItemsBlobPrefix(
	ctx context.Context,
	b *blob.Bucket,
	prefix string,
	de ItemDeserializer,
	fn func(Item) error,
	options ...IterItemsOption,
) error {
	parallel := 512
	for _, opt := range options {
		switch opt := opt.(type) {
		case *OptIterItemsParallel:
			parallel = opt.Parallel
		}
	}

	it := b.List(ctx, &blob.OptListPrefix{
		Prefix: prefix,
	})
	errs := make(chan error, parallel)
	var errLoop error
	wg := new(sync.WaitGroup)
	sem := make(chan struct{}, parallel)
LOOP:
	for it.Next(ctx) {
		select {
		case err := <-errs:
			if errors.Is(err, ErrIterItemsStop) {
				errLoop = nil
			}
			break LOOP
		default:
		}
		key := it.Key()
		wg.Add(1)
		sem <- struct{}{}
		go func() {
			defer wg.Done()
			defer func() { <-sem }()
			data, err := b.Read(ctx, key)
			if err != nil {
				errs <- err
				return
			}
			item, err := de(key, data)
			if err != nil {
				errs <- err
				return
			}
			if err := fn(item); err != nil {
				errs <- err
				return
			}
		}()
	}
	if errLoop != nil {
		return errLoop
	}
	if err := it.Err(); err != nil {
		return err
	}
	wg.Wait()
	return nil
}
