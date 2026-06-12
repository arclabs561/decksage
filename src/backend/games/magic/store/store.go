package store

import (
	"context"
	"embed"

	"github.com/dgraph-io/dgo/v210"
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

func (s *Store) init(_ context.Context) error {
	// Dgraph schema setup was stubbed out in the 2025-12-30 cleanup
	// (deprecated backend); callers only need the no-op. The previous body
	// read assets/schema.graphql and ran s.dgraph.Alter.
	return nil
}
