package cardco

import (
	"bytes"
	"context"
	"encoding/csv"
	"fmt"
	"os"
	"strconv"
	"sync"

	"github.com/dgraph-io/badger/v3"
	"github.com/vmihailenco/msgpack"

	"collections/games/magic/dataset"
	"collections/logger"
	"collections/transform"
)

type Transform struct {
	log *logger.Logger
	dir string
	db  *badger.DB
	mu  *sync.Mutex
}

func NewTransform(
	ctx context.Context,
	log *logger.Logger,
) (*Transform, error) {
	dir, err := os.MkdirTemp("", "transform")
	if err != nil {
		return nil, err
	}
	log.Debugf(ctx, "using db file %s", dir)
	opts := badger.DefaultOptions(dir)
	opts.Logger = &badgerLogger{
		ctx: ctx,
		log: log,
	}
	db, err := badger.Open(opts)
	if err != nil {
		return nil, err
	}
	return &Transform{
		log: log,
		dir: dir,
		db:  db,
		mu:  new(sync.Mutex),
	}, nil
}

func (t *Transform) close() error {
	if err := t.db.Close(); err != nil {
		return err
	}
	if err := os.RemoveAll(t.dir); err != nil {
		return err
	}
	return nil
}

type tkey struct {
	Name1 string
	Name2 string
}

func newKey(name1, name2 string) tkey {
	if name1 > name2 {
		name1, name2 = name2, name1
	}
	return tkey{
		Name1: name1,
		Name2: name2,
	}
}

type tval struct {
	// Unique set cooccurrences.
	Set int
	// Multiset cooccurrences. Within each collection, multiple repeats of
	// a card are counted separately. This includes self-edges.
	Multiset int
}

// Attribute storage for cards encountered via CardItem (from Scryfall dataset)
type cattr struct {
	CMC      float64
	TypeLine string
}

var (
	attrPrefix = []byte("ATTR:")
)

func (t *Transform) add(k tkey, v tval) error {
	kb, err := msgpack.Marshal(k)
	if err != nil {
		return err
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	err = t.db.Update(func(txn *badger.Txn) error {
		item, err := txn.Get(kb)
		if err == badger.ErrKeyNotFound {
			vb, err := msgpack.Marshal(v)
			if err != nil {
				return err
			}
			if err := txn.Set(kb, vb); err != nil {
				return fmt.Errorf("failed to set value: %w", err)
			}
			return nil
		}
		if err != nil {
			return fmt.Errorf("failed to get value: %w", err)
		}
		err = item.Value(func(wb []byte) error {
			var w tval
			if err := msgpack.Unmarshal(wb, &w); err != nil {
				return err
			}
			w.Set += v.Set
			w.Multiset += v.Multiset
			wb, err = msgpack.Marshal(w)
			if err != nil {
				return err
			}
			if err := txn.Set(kb, wb); err != nil {
				return fmt.Errorf("failed to update value: %w", err)
			}
			return nil
		})
		if err != nil {
			return fmt.Errorf("failed to read item value: %w", err)
		}
		return nil
	})
	if err != nil {
		return fmt.Errorf("failed to update: %w", err)
	}
	return nil
	// valuePut := new(bytes.Buffer)
	// c, ok := t.counts[pair]
	// if !ok {
	// 	t.counts[pair] = &count{
	// 		set:      d.set,
	// 		multiset: d.multiset,
	// 	}
	// 	return
	// }
	// c.add(d)
}

func (t *Transform) setAttr(name string, attr cattr) error {
	kb := append([]byte{}, attrPrefix...)
	kb = append(kb, []byte(name)...)
	vb, err := msgpack.Marshal(attr)
	if err != nil {
		return err
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.db.Update(func(txn *badger.Txn) error {
		if err := txn.Set(kb, vb); err != nil {
			return fmt.Errorf("failed to set attr: %w", err)
		}
		return nil
	})
}

func (t *Transform) Transform(
	ctx context.Context,
	datasets []dataset.Dataset,
	options ...transform.TransformOption,
) (*transform.TransformOutput, error) {
	t.log.Infof(ctx, "Starting card co-occurrence transform...")

	// Parse options
	limit := -1
	iterParallel := 0
	for _, opt := range options {
		switch opt := opt.(type) {
		case *transform.OptTransformLimit:
			if opt.Limit > 0 {
				limit = opt.Limit
			}
		case *transform.OptTransformParallel:
			// Pass through to dataset iteration
			if opt.Parallel > 0 {
				iterParallel = opt.Parallel
			}
		default:
			panic(fmt.Sprintf("invalid option type %T", opt))
		}
	}

	// Process items from all datasets
	total := 0
	for _, d := range datasets {
		t.log.Infof(ctx, "Processing dataset: %s", d.Description().Name)

		var iterOpts []dataset.IterItemsOption
		if iterParallel > 0 {
			iterOpts = append(iterOpts, &dataset.OptIterItemsParallel{Parallel: iterParallel})
		}

		err := d.IterItems(ctx, func(item dataset.Item) error {
			if err := t.worker(item); err != nil {
				return fmt.Errorf("worker failed: %w", err)
			}
			total++
			if total%100 == 0 {
				t.log.Debugf(ctx, "Processed %d collections", total)
			}
			if limit > 0 && total >= limit {
				return dataset.ErrIterItemsStop
			}
			return nil
		}, iterOpts...)

		if err != nil && err != dataset.ErrIterItemsStop {
			return nil, fmt.Errorf("failed to iterate items: %w", err)
		}

		if limit > 0 && total >= limit {
			break
		}
	}

	t.log.Infof(ctx, "Transform complete! Processed %d collections", total)
	return &transform.TransformOutput{}, nil
}

// ExportCSV exports the co-occurrence matrix to CSV
func (t *Transform) ExportCSV(ctx context.Context, filename string) error {
	f, err := os.Create(filename)
	if err != nil {
		return err
	}
	defer f.Close()

	w := csv.NewWriter(f)
	defer w.Flush()

	return t.db.View(func(txn *badger.Txn) error {
		it := txn.NewIterator(badger.DefaultIteratorOptions)
		defer it.Close()

		// Write header
		if err := w.Write([]string{"NAME_1", "NAME_2", "COUNT_SET", "COUNT_MULTISET"}); err != nil {
			return err
		}

		count := 0
		for it.Rewind(); it.Valid(); it.Next() {
			item := it.Item()

			var k tkey
			if err := msgpack.Unmarshal(item.Key(), &k); err != nil {
				return err
			}

			vb, err := item.ValueCopy(nil)
			if err != nil {
				return err
			}

			var v tval
			if err := msgpack.Unmarshal(vb, &v); err != nil {
				return err
			}

			if err := w.Write([]string{k.Name1, k.Name2, strconv.Itoa(v.Set), strconv.Itoa(v.Multiset)}); err != nil {
				return err
			}
			count++
		}

		w.Flush()
		if err := w.Error(); err != nil {
			return err
		}

		t.log.Infof(ctx, "Exported %d card pairs to %s", count, filename)
		return nil
	})
}

// ExportAttributesCSV exports card attributes captured from CardItem entries.
func (t *Transform) ExportAttributesCSV(ctx context.Context, filename string) error {
	f, err := os.Create(filename)
	if err != nil {
		return err
	}
	defer f.Close()

	w := csv.NewWriter(f)
	defer w.Flush()

	if err := w.Write([]string{"NAME", "CMC", "TYPE_LINE"}); err != nil {
		return err
	}

	return t.db.View(func(txn *badger.Txn) error {
		it := txn.NewIterator(badger.DefaultIteratorOptions)
		defer it.Close()

		count := 0
		for it.Rewind(); it.Valid(); it.Next() {
			item := it.Item()
			key := item.Key()
			if !bytes.HasPrefix(key, attrPrefix) {
				continue
			}
			name := string(key[len(attrPrefix):])
			vb, err := item.ValueCopy(nil)
			if err != nil {
				return err
			}
			var attr cattr
			if err := msgpack.Unmarshal(vb, &attr); err != nil {
				return err
			}
			if err := w.Write([]string{name, strconv.FormatFloat(attr.CMC, 'f', -1, 64), attr.TypeLine}); err != nil {
				return err
			}
			count++
		}
		w.Flush()
		if err := w.Error(); err != nil {
			return err
		}
		t.log.Infof(ctx, "Exported %d card attributes to %s", count, filename)
		return nil
	})
}

// Close closes the transform and cleans up temp files
func (t *Transform) Close() error {
	return t.close()
}

func (t *Transform) worker(item dataset.Item) error {
	switch item := item.(type) {
	case *dataset.CollectionItem:
		for _, partition := range item.Collection.Partitions {
			n := len(partition.Cards)
			for i := 0; i < n; i++ {
				c := partition.Cards[i]
				if c.Count > 1 {
					k := newKey(c.Name, c.Name)
					err := t.add(k, tval{
						Set:      0,
						Multiset: c.Count - 1,
					})
					if err != nil {
						return err
					}
				}
				for j := i + 1; j < n; j++ {
					d := partition.Cards[j]
					k := newKey(c.Name, d.Name)
					err := t.add(k, tval{
						Set:      1,
						Multiset: c.Count * d.Count,
					})
					if err != nil {
						return err
					}
				}
			}
		}
	case *dataset.CardItem:
		if item.Card != nil {
			var cmc float64
			cmc = item.Card.CMC
			typeLine := ""
			if len(item.Card.Faces) > 0 {
				typeLine = item.Card.Faces[0].TypeLine
			}
			if err := t.setAttr(item.Card.Name, cattr{CMC: cmc, TypeLine: typeLine}); err != nil {
				return err
			}
		}
	default:
		panic(fmt.Sprintf("unhandled item type: %T", item))
	}
	return nil
}

var _ badger.Logger = (*badgerLogger)(nil)

type badgerLogger struct {
	ctx context.Context
	log *logger.Logger
}

func (l *badgerLogger) Errorf(format string, args ...any) {
	l.log.Errorf(l.ctx, format, args...)
}
func (l *badgerLogger) Warningf(format string, args ...any) {
	l.log.Warnf(l.ctx, format, args...)
}
func (l *badgerLogger) Infof(format string, args ...any) {
	l.log.Debugf(l.ctx, format, args...)
}
func (l *badgerLogger) Debugf(format string, args ...any) {
	l.log.Tracef(l.ctx, format, args...)
}
