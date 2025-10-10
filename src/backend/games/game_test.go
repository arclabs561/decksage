package games

import (
	"testing"
	"time"
)

func TestCardDesc(t *testing.T) {
	cd := CardDesc{
		Name:  "Lightning Bolt",
		Count: 4,
	}

	if cd.Name != "Lightning Bolt" {
		t.Errorf("Expected name=Lightning Bolt, got %s", cd.Name)
	}

	if cd.Count != 4 {
		t.Errorf("Expected count=4, got %d", cd.Count)
	}
}

func TestPartition(t *testing.T) {
	p := Partition{
		Name: "Main Deck",
		Cards: []CardDesc{
			{Name: "Card A", Count: 2},
			{Name: "Card B", Count: 3},
		},
	}

	if p.Name != "Main Deck" {
		t.Errorf("Expected name=Main Deck, got %s", p.Name)
	}

	if len(p.Cards) != 2 {
		t.Errorf("Expected 2 cards, got %d", len(p.Cards))
	}
}

func TestTypeRegistry(t *testing.T) {
	// First register a unique type
	uniqueTypeName := "UniqueTestType12345"
	RegisterCollectionType(uniqueTypeName, func() CollectionType {
		return &testCollectionType{}
	})

	// Test that registering the same type twice panics
	defer func() {
		if r := recover(); r == nil {
			t.Error("Expected panic when registering duplicate type")
		}
	}()

	// This should panic
	RegisterCollectionType(uniqueTypeName, func() CollectionType {
		return nil
	})
}

// Mock collection type for testing
type testCollectionType struct{}

func (tct *testCollectionType) Type() string      { return "TestType" }
func (tct *testCollectionType) IsCollectionType() {}

func TestCanonicalizeValidCollection(t *testing.T) {
	ct := &testCollectionType{}

	c := Collection{
		ID:  "test-123",
		URL: "https://example.com/test",
		Type: CollectionTypeWrapper{
			Type:  "TestType",
			Inner: ct,
		},
		ReleaseDate: time.Now(),
		Partitions: []Partition{
			{
				Name: "Main",
				Cards: []CardDesc{
					{Name: "Card A", Count: 2},
					{Name: "Card B", Count: 1},
				},
			},
		},
	}

	if err := c.Canonicalize(); err != nil {
		t.Errorf("Expected valid collection to pass canonicalization, got error: %v", err)
	}

	// Verify sorting
	if c.Partitions[0].Cards[0].Name != "Card A" {
		t.Error("Expected cards to be sorted by name")
	}
}

func TestCanonicalizeInvalidCollection(t *testing.T) {
	ct := &testCollectionType{}

	tests := []struct {
		name       string
		collection Collection
		expectErr  bool
	}{
		{
			name: "empty ID",
			collection: Collection{
				ID: "",
			},
			expectErr: true,
		},
		{
			name: "empty URL",
			collection: Collection{
				ID:  "test",
				URL: "",
			},
			expectErr: true,
		},
		{
			name: "zero release date",
			collection: Collection{
				ID:  "test",
				URL: "https://example.com",
				Type: CollectionTypeWrapper{
					Type:  "TestType",
					Inner: ct,
				},
				ReleaseDate: time.Time{},
			},
			expectErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.collection.Canonicalize()
			if (err != nil) != tt.expectErr {
				t.Errorf("Expected error=%v, got error=%v", tt.expectErr, err)
			}
		})
	}
}
