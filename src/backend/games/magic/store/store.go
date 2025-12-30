package store

import (
	"context"
	"embed"

	"github.com/dgraph-io/dgo/v210"
	"github.com/dgraph-io/dgo/v210/protos/api"
)

//go:embed assets
var assets embed.FS

type Store struct {
	dgraph *dgo.Dgraph
}

func NewStore(
	ctx context.Context,
	dgraph *dgo.Dgraph,
) (*Store, error) {
	s := &Store{
		dgraph: dgraph,
	}
	if err := s.init(ctx); err != nil {
		return nil, err
	}
	return s, nil
}

func (s *Store) init(ctx context.Context) error {
	return nil
	schema, err := assets.ReadFile("assets/schema.graphql")
	if err != nil {
		return err
	}
	op := &api.Operation{Schema: string(schema)}
	if err := s.dgraph.Alter(ctx, op); err != nil {
		return err
	}
	return nil
}
