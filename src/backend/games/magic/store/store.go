package store

import (
	"context"
)

// Store is a placeholder for future graph database integration.
// Currently unused - the system uses Badger for caching and CSV for ML data flow.
//
// Potential use cases:
// - Persistent card database with complex queries
// - Deck archetype classification
// - Tournament result tracking
//
// Consider SQLite or keep Badger + CSV → Python for graph operations.
type Store struct {
	// Future: database connection
}

func NewStore(ctx context.Context) (*Store, error) {
	return &Store{}, nil
}
