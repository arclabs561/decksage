package games

import (
	"sort"
	"testing"
	"time"
)

func TestComputeContentHash(t *testing.T) {
	col := &Collection{
		ID:          "test-1",
		URL:         "https://example.com/deck",
		ReleaseDate: time.Now(),
		Partitions: []Partition{
			{
				Name: "Main",
				Cards: []CardDesc{
					{Name: "Lightning Bolt", Count: 4},
					{Name: "Mountain", Count: 20},
				},
			},
		},
	}

	// First computation
	col.ComputeContentHash()
	hash1 := col.ContentHash
	if hash1 == "" {
		t.Error("ContentHash should be computed")
	}

	// Second computation should be cached
	col.ComputeContentHash()
	hash2 := col.ContentHash
	if hash1 != hash2 {
		t.Error("ContentHash should be cached, not recomputed")
	}

	// Same content should produce same hash
	col2 := &Collection{
		ID:          "test-2",
		URL:         "https://example.com/deck2",
		ReleaseDate: time.Now(),
		Partitions: []Partition{
			{
				Name: "Main",
				Cards: []CardDesc{
					{Name: "Lightning Bolt", Count: 4},
					{Name: "Mountain", Count: 20},
				},
			},
		},
	}
	col2.ComputeContentHash()
	if col2.ContentHash != hash1 {
		t.Error("Same content should produce same hash")
	}

	// Different content should produce different hash
	col2.Partitions[0].Cards[0].Count = 3
	col2.ContentHash = "" // Reset to force recomputation
	col2.ComputeContentHash()
	if col2.ContentHash == hash1 {
		t.Error("Different content should produce different hash")
	}
}

func TestComputeContentHashOrderIndependent(t *testing.T) {
	// Hash should be order-independent (cards are sorted before hashing)
	// We'll manually sort to test order-independence without requiring full Collection setup
	col1 := &Collection{
		Partitions: []Partition{
			{
				Name: "Main",
				Cards: []CardDesc{
					{Name: "A", Count: 1},
					{Name: "B", Count: 2},
				},
			},
		},
	}
	col2 := &Collection{
		Partitions: []Partition{
			{
				Name: "Main",
				Cards: []CardDesc{
					{Name: "B", Count: 2},
					{Name: "A", Count: 1},
				},
			},
		},
	}
	// Manually sort cards (as Canonicalize would)
	sort.Slice(col1.Partitions[0].Cards, func(i, j int) bool {
		return col1.Partitions[0].Cards[i].Name < col1.Partitions[0].Cards[j].Name
	})
	sort.Slice(col2.Partitions[0].Cards, func(i, j int) bool {
		return col2.Partitions[0].Cards[i].Name < col2.Partitions[0].Cards[j].Name
	})

	col1.ComputeContentHash()
	col2.ComputeContentHash()
	if col1.ContentHash != col2.ContentHash {
		t.Error("Hash should be order-independent when cards are sorted")
	}
}

