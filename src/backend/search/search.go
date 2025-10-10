package search

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/meilisearch/meilisearch-go"
	"github.com/samber/mo"

	"collections/games/magic/dataset"
	"collections/games/magic/game"
	"collections/logger"
)

const indexUid = "magic_cards"

type Index struct {
	log    *logger.Logger
	client *meilisearch.Client
}

func NewIndex(
	log *logger.Logger,
	options ...IndexOption,
) (*Index, error) {
	opts := newResolvedOptions(options...)
	config := meilisearch.ClientConfig{
		Host: opts.URL,
	}
	if key, ok := opts.Key.Get(); ok {
		config.APIKey = key
	}
	client := meilisearch.NewClient(config)
	x := &Index{
		log:    log,
		client: client,
	}
	if err := x.init(); err != nil {
		return nil, err
	}
	return x, nil

}

func (x *Index) init() error {
	taskInfo, err := x.client.CreateIndex(&meilisearch.IndexConfig{
		Uid:        indexUid,
		PrimaryKey: "id",
	})
	if err != nil {
		// Tolerate already existing index by probing its presence
		if _, fetchErr := x.client.Index(indexUid).FetchInfo(); fetchErr == nil {
			// Index exists; proceed
		} else {
			return fmt.Errorf("failed to create index: %w", err)
		}
	} else {
		if err := x.waitForTask(taskInfo); err != nil {
			e := new(apiError)
			if errors.As(err, &e) && e.Code != "index_already_exists" {
				return err
			}
		}
	}

	taskInfo, err = x.client.Index(indexUid).UpdateSearchableAttributes(&[]string{
		"name",
	})
	if err != nil {
		return fmt.Errorf("failed to update displayed attributes: %w", err)
	}
	if err := x.waitForTask(taskInfo); err != nil {
		return err
	}

	return nil
}

type apiError struct {
	Message string
	Code    string
	Type    string
	Link    string
}

func (e *apiError) Error() string {
	return fmt.Sprintf("%s (%s): %s", e.Type, e.Code, e.Message)
}

func (x *Index) waitForTask(taskInfo *meilisearch.TaskInfo) error {
	task, err := x.client.Index(indexUid).WaitForTask(taskInfo.TaskUID)
	if err != nil {
		return fmt.Errorf(
			"failed to wait for task %q (%d): %w",
			task.Type,
			taskInfo.TaskUID,
			err,
		)
	}
	if task.Status != meilisearch.TaskStatusSucceeded {
		err := &apiError{
			task.Error.Message,
			task.Error.Code,
			task.Error.Type,
			task.Error.Link,
		}
		return fmt.Errorf(
			"task %q (%d) did not succeed (%v): %w",
			task.Type,
			task.UID,
			task.Status,
			err,
		)
	}
	return nil
}

type IndexOption interface {
	indexOption()
}

type OptClientURL struct {
	URL string
}

type OptClientKey struct {
	Key string
}

type OptLimit struct {
	Limit int
}

func (o OptClientURL) indexOption() {}
func (o OptClientKey) indexOption() {}
func (o OptLimit) indexOption()     {}

type resolvedOptions struct {
	URL string
	Key mo.Option[string]
}

func newResolvedOptions(options ...IndexOption) resolvedOptions {
	var url mo.Option[string]
	var key mo.Option[string]
	return resolvedOptions{
		URL: url.OrElse("http://localhost:7700"),
		Key: key,
	}
}

func (x *Index) PutItems(
	ctx context.Context,
	d dataset.Dataset,
	options ...IndexOption,
) error {
	limit := mo.None[int]()
	for _, opt := range options {
		switch opt := opt.(type) {
		case *OptLimit:
			limit = mo.Some(opt.Limit)
		}
	}

	index := x.client.Index("magic_cards")
	var batch []*dataset.CardItem
	wg := new(sync.WaitGroup)

	flush := func() {
		defer func() { batch = nil }()
		var docs []map[string]interface{}
		for _, card := range batch {
			var imageURL string
			if len(card.Card.Images) > 0 {
				imageURL = card.Card.Images[0].URL
			}
			var refURL string
			if len(card.Card.References) > 0 {
				refURL = card.Card.References[0].URL
			}
			docs = append(docs, map[string]interface{}{
				"id":        cardPrimaryKey(card.Card),
				"name":      card.Card.Name,
				"image_url": imageURL,
				"ref_url":   refURL,
			})
		}
		start := time.Now()
		taskInfo, err := index.AddDocuments(docs)
		if err != nil {
			x.log.Errorf(ctx, "failed to add documents: %v", err)
			return
		}
		wg.Add(1)
		go func() {
			defer wg.Done()
			task, err := index.WaitForTask(taskInfo.TaskUID)
			if err != nil {
				x.log.Errorf(ctx, "failed to wait for task: %v", err)
				return
			}
			if task.Status != meilisearch.TaskStatusSucceeded {
				x.log.Errorf(ctx, "task failed: %+v", task.Error)
				return
			}
			x.log.Fieldf("dur", "%v", time.Since(start).Round(time.Millisecond)).
				Fieldf("status", "%v", task.Status).
				Fieldf("docs", "%d", len(docs)).
				Debugf(ctx, "finished task")
		}()
	}

	batchSize := 100
	cards := make(chan *dataset.CardItem, batchSize)
	wg.Add(1)
	go func() {
		defer wg.Done()
		for card := range cards {
			batch = append(batch, card)
			if len(batch) >= batchSize {
				flush()
			}
		}
		if len(batch) > 0 {
			flush()
		}
	}()

	mu := new(sync.Mutex)
	total := 0
	fn := func(item dataset.Item) error {
		card, ok := item.(*dataset.CardItem)
		if !ok {
			return nil
		}
		mu.Lock()
		defer mu.Unlock()
		if n, ok := limit.Get(); ok && total >= n {
			return dataset.ErrIterItemsStop
		}
		cards <- card
		total++
		return nil
	}
	opts := []dataset.IterItemsOption{
		&dataset.OptIterItemsFilterType{
			Only: &dataset.CardItem{},
		},
		&dataset.OptIterItemsParallel{
			Parallel: 2,
		},
	}
	err := d.IterItems(ctx, fn, opts...)
	close(cards)
	if err != nil {
		return fmt.Errorf("failed to iterate over dataset items: %w", err)
	}
	wg.Wait()
	x.log.Infof(ctx, "successfully indexed %d items", total)
	return nil
}

func cardPrimaryKey(card *game.Card) string {
	b := sha256.Sum256([]byte(card.Name))
	return fmt.Sprintf("card-%x", b)
}
