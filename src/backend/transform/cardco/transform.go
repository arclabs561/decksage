package cardco

import (
	"context"
	"fmt"
	"os"
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

func (t *Transform) Transform(
	ctx context.Context,
	datasets []dataset.Dataset,
	options ...transform.TransformOption,
) (*transform.TransformOutput, error) {
	// defer func() {
	// 	if err := t.close(); err != nil {
	// 		t.log.Errorf(ctx, "failed to close: %v", err)
	// 	}
	// }()

	// d := datasets[0]

	// limit := mo.None[int]()
	// parallel := 1024
	// for _, opt := range options {
	// 	switch opt := opt.(type) {
	// 	case *transform.OptTransformLimit:
	// 		if opt.Limit > 0 {
	// 			limit = mo.Some(opt.Limit)
	// 		}
	// 	case *transform.OptTransformParallel:
	// 		parallel = opt.Parallel
	// 	default:
	// 		panic(fmt.Sprintf("invalid option type %T", opt))
	// 	}
	// }

	// f, err := os.Create("pairs.csv")
	// if err != nil {
	// 	return nil, err
	// }
	// defer f.Close()

	// wg := new(sync.WaitGroup)
	// items := make(chan dataset.Item)
	// errs := make(chan error, 1)
	// for i := 0; i < parallel; i++ {
	// 	wg.Add(1)
	// 	go func() {
	// 		defer wg.Done()
	// 		for it := range items {
	// 			if err := t.worker(it); err != nil {
	// 				errs <- err
	// 				return
	// 			}
	// 		}
	// 	}()
	// }

	// total := 0
	// it := d.IterItems(ctx)
	// err = nil
	// checkpoint := 100
	// ITEMS:
	// for it.Next(ctx) {
	// 	select {
	// 	case err = <-errs:
	// 		break ITEMS
	// 	default:
	// 	}
	// 	item, err := it.Item(ctx)
	// 	if err != nil {
	// 		t.log.Errorf(ctx, "failed to get item: %v", err)
	// 		continue
	// 	}
	// 	switch item := item.(type) {
	// 	case *dataset.CollectionItem:
	// 		_ = item
	// 		// fmt.Println(total, item.Collection.URL)
	// 	}
	// 	items <- item
	// 	total++
	// 	if total > 0 && total%checkpoint == 0 {
	// 		t.log.Debugf(ctx, "iterated through %d items", total)
	// 	}
	// 	if n, ok := limit.Get(); ok && total >= n {
	// 		break
	// 	}
	// }
	// close(items)
	// if err != nil {
	// 	return nil, err
	// }
	// if err := it.Err(); err != nil {
	// 	return nil, fmt.Errorf("failed to iterate items: %w", err)
	// }
	// wg.Wait()
	// w := csv.NewWriter(f)
	// defer w.Flush()
	// w.Write([]string{"NAME_1", "NAME_2", "COUNT_SET", "COUNT_MULTISET"})
	// stream := t.db.NewStream()
	// stream.Send = func(buf *z.Buffer) error {
	// 	list, err := badger.BufferToKVList(buf)
	// 	if err != nil {
	// 		return nil
	// 	}
	// 	for _, kv := range list.GetKv() {
	// 		var k tkey
	// 		if err := msgpack.Unmarshal(kv.Key, &k); err != nil {
	// 			return err
	// 		}
	// 		var v tval
	// 		if err := msgpack.Unmarshal(kv.Value, &v); err != nil {
	// 			return err
	// 		}
	// 		err = w.Write([]string{
	// 			k.Name1,
	// 			k.Name2,
	// 			fmt.Sprintf("%d", v.Set),
	// 			fmt.Sprintf("%d", v.Multiset),
	// 		})
	// 		if err != nil {
	// 			return err
	// 		}
	// 	}
	// 	return nil
	// }
	// if err := stream.Orchestrate(ctx); err != nil {
	// 	return nil, err
	// }
	// // err = t.db.View(func(txn *badger.Txn) error {
	// // 	it := txn.NewIterator(badger.DefaultIteratorOptions)
	// // 	defer it.Close()
	// // 	for it.Rewind(); it.Valid(); it.Next() {
	// // 		item := it.Item()
	// // 		kb := item.Key()
	// // 		var k tkey
	// // 		if err := msgpack.Unmarshal(kb, &k); err != nil {
	// // 			return err
	// // 		}
	// // 		vb, err := item.ValueCopy(nil)
	// // 		if err != nil {
	// // 			return err
	// // 		}
	// // 		var v tval
	// // 		if err := msgpack.Unmarshal(vb, &v); err != nil {
	// // 			return err
	// // 		}
	// // 		w.Write([]string{
	// // 			k.Name1,
	// // 			k.Name2,
	// // 			fmt.Sprintf("%d", v.Set),
	// // 			fmt.Sprintf("%d", v.Multiset),
	// // 		})

	// // 	}
	// // 	return nil
	// // })
	// // for pair, count := range t.counts {
	// // 	w.Write([]string{
	// // 		pair.name1,
	// // 		pair.name2,
	// // 		fmt.Sprintf("%d", count.set),
	// // 		fmt.Sprintf("%d", count.multiset),
	// // 	})
	// // }
	// if err != nil {
	// 	return nil, err
	// }
	// w.Flush()
	return nil, nil
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
