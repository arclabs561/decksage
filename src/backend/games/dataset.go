package games

import (
	"collections/blob"
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

// Dataset is the core interface that all data sources must implement.
// Game-agnostic: works for MTG, Yu-Gi-Oh!, Pokemon, etc.
type Dataset interface {
	// Description returns metadata about this dataset
	Description() Description

	// Extract scrapes data from the source and stores in blob storage
	Extract(
		ctx context.Context,
		scraper *scraper.Scraper,
		options ...UpdateOption,
	) error

	// IterItems iterates over stored items (cards or collections)
	IterItems(
		ctx context.Context,
		fn func(item Item) error,
		options ...IterItemsOption,
	) error
}

// Description provides dataset metadata
type Description struct {
	Game string // "magic", "yugioh", "pokemon"
	Name string // "scryfall", "mtgtop8", "ygoprodeck"
}

// --- Update Options (for Extract) ---

var ErrIterItemsStop = errors.New("stop iter items")

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

// ResolvedUpdateOptions are the normalized extraction options
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
	// Cached compiled regexes for Section() to avoid recompilation
	sectionRegexCache map[string]*regexp.Regexp
	sectionRegexMu    sync.RWMutex
}

// Section checks if a pattern matches any of the SectionOnly filters.
// Uses cached compiled regexes for performance.
func (ro *ResolvedUpdateOptions) Section(pat string) bool {
	if len(ro.SectionOnly) == 0 {
		return true
	}

	// Get or compile regex (with caching)
	ro.sectionRegexMu.RLock()
	re, exists := ro.sectionRegexCache[pat]
	ro.sectionRegexMu.RUnlock()

	if !exists {
		// Compile and cache
		ro.sectionRegexMu.Lock()
		// Double-check after acquiring write lock
		if re, exists = ro.sectionRegexCache[pat]; !exists {
			var err error
			re, err = regexp.Compile(fmt.Sprintf("(?i)%s", pat))
			if err != nil {
				ro.sectionRegexMu.Unlock()
				return false // Invalid pattern doesn't match
			}
			if ro.sectionRegexCache == nil {
				ro.sectionRegexCache = make(map[string]*regexp.Regexp)
			}
			ro.sectionRegexCache[pat] = re
		}
		ro.sectionRegexMu.Unlock()
	}

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
				return ResolvedUpdateOptions{}, fmt.Errorf("start page must be non-negative: %d", opt.Start)
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

// Do performs an HTTP request with appropriate scraper options
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

// --- Item Types (Cards and Collections) ---

type Item interface {
	Kind() string
	item()
}

type ItemWrapper struct {
	Kind string `json:"kind"`
	Item Item
}

// CollectionItem wraps a Collection
type CollectionItem struct {
	Collection *Collection `json:"collection"`
}

func (i *CollectionItem) Kind() string { return "Collection" }
func (i *CollectionItem) item()        {}

// CardItem should be implemented per-game with game-specific Card types
// See games/magic/dataset/item.go for example

// --- Iteration Options ---

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

// --- Helper Functions ---

// ItemDeserializer converts stored bytes into an Item
type ItemDeserializer func(key string, data []byte) (Item, error)

// DeserializeAsCollection is a universal deserializer for collections
func DeserializeAsCollection(_ string, data []byte) (Item, error) {
	var col Collection
	if err := json.Unmarshal(data, &col); err != nil {
		return nil, err
	}
	return &CollectionItem{
		Collection: &col,
	}, nil
}

// IterItemsBlobPrefix iterates over items in blob storage with a given prefix.
// Processes items in parallel up to the specified parallelism level.
// Respects context cancellation and returns the first error encountered.
func IterItemsBlobPrefix(
	ctx context.Context,
	b *blob.Bucket,
	prefix string,
	de ItemDeserializer,
	fn func(Item) error,
	options ...IterItemsOption,
) error {
	parallel := 64 // Lowered from 512 for safety
	for _, opt := range options {
		switch opt := opt.(type) {
		case *OptIterItemsParallel:
			if opt.Parallel < 1 || opt.Parallel > 1024 {
				return fmt.Errorf("parallel must be 1-1024, got %d", opt.Parallel)
			}
			parallel = opt.Parallel
		}
	}

	it := b.List(ctx, &blob.OptListPrefix{
		Prefix: prefix,
	})

	// Buffered error channel
	errChan := make(chan error, parallel)
	wg := new(sync.WaitGroup)
	sem := make(chan struct{}, parallel)

	// Track first error
	var firstErr error
	errOnce := new(sync.Once)

	// Main loop
	for it.Next(ctx) {
		// Check context cancellation
		select {
		case <-ctx.Done():
			wg.Wait()
			return ctx.Err()
		default:
		}

		// Check for errors (non-blocking)
		select {
		case err := <-errChan:
			errOnce.Do(func() { firstErr = err })
		default:
		}

		// If we have any error (including ErrIterItemsStop), stop starting new goroutines
		if firstErr != nil {
			break
		}

		key := it.Key()
		wg.Add(1)
		sem <- struct{}{}

		// Capture key in goroutine scope
		go func(k string) {
			defer wg.Done()
			defer func() { <-sem }()

			// Panic recovery
			defer func() {
				if r := recover(); r != nil {
					// Non-blocking error send
					select {
					case errChan <- fmt.Errorf("panic in worker processing %s: %v", k, r):
					default:
					}
				}
			}()

			// Read data
			data, err := b.Read(ctx, k)
			if err != nil {
				select {
				case errChan <- fmt.Errorf("failed to read %s: %w", k, err):
				default:
				}
				return
			}

			// Deserialize
			item, err := de(k, data)
			if err != nil {
				select {
				case errChan <- fmt.Errorf("failed to deserialize %s: %w", k, err):
				default:
				}
				return
			}

			// Process
			if err := fn(item); err != nil {
				select {
				case errChan <- err:
				default:
				}
				return
			}
		}(key)
	}

	// Wait for ALL goroutines to finish
	wg.Wait()

	// Now check all error sources
	if firstErr != nil {
		if errors.Is(firstErr, ErrIterItemsStop) {
			return nil
		}
		return firstErr
	}

	// Check iterator error
	if err := it.Err(); err != nil {
		return err
	}

	// Check for any remaining errors in channel
	select {
	case err := <-errChan:
		if !errors.Is(err, ErrIterItemsStop) {
			return err
		}
	default:
	}

	return nil
}
