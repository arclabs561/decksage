package game_test

import (
	"encoding/json"
	"testing"
	"time"

	"collections/games/magic/game"
)

func TestCollectionCanonicalize(t *testing.T) {
	tests := []struct {
		name        string
		collection  game.Collection
		expectError bool
		errorMsg    string
	}{
		{
			name: "valid deck",
			collection: game.Collection{
				ID:  "test-1",
				URL: "https://example.com/deck/1",
				Type: game.CollectionTypeWrapper{
					Type: "Deck",
					Inner: &game.CollectionTypeDeck{
						Name:   "Test Deck",
						Format: "Standard",
					},
				},
				ReleaseDate: time.Now(),
				Partitions: []game.Partition{
					{
						Name: "Main",
						Cards: []game.CardDesc{
							{Name: "Lightning Bolt", Count: 4},
							{Name: "Mountain", Count: 20},
						},
					},
				},
			},
			expectError: false,
		},
		{
			name: "empty ID",
			collection: game.Collection{
				URL: "https://example.com/deck/1",
				Type: game.CollectionTypeWrapper{
					Type: "Deck",
					Inner: &game.CollectionTypeDeck{
						Name:   "Test Deck",
						Format: "Standard",
					},
				},
				ReleaseDate: time.Now(),
				Partitions: []game.Partition{
					{
						Name:  "Main",
						Cards: []game.CardDesc{{Name: "Test", Count: 1}},
					},
				},
			},
			expectError: true,
			errorMsg:    "empty id",
		},
		{
			name: "empty URL",
			collection: game.Collection{
				ID: "test-1",
				Type: game.CollectionTypeWrapper{
					Type: "Deck",
					Inner: &game.CollectionTypeDeck{
						Name:   "Test Deck",
						Format: "Standard",
					},
				},
				ReleaseDate: time.Now(),
				Partitions: []game.Partition{
					{
						Name:  "Main",
						Cards: []game.CardDesc{{Name: "Test", Count: 1}},
					},
				},
			},
			expectError: true,
			errorMsg:    "url is empty",
		},
		{
			name: "invalid URL",
			collection: game.Collection{
				ID:  "test-1",
				URL: "://invalid-url",
				Type: game.CollectionTypeWrapper{
					Type: "Deck",
					Inner: &game.CollectionTypeDeck{
						Name:   "Test Deck",
						Format: "Standard",
					},
				},
				ReleaseDate: time.Now(),
				Partitions: []game.Partition{
					{
						Name:  "Main",
						Cards: []game.CardDesc{{Name: "Test", Count: 1}},
					},
				},
			},
			expectError: true,
			errorMsg:    "failed to parse url",
		},
		{
			name: "zero release date",
			collection: game.Collection{
				ID:  "test-1",
				URL: "https://example.com/deck/1",
				Type: game.CollectionTypeWrapper{
					Type: "Deck",
					Inner: &game.CollectionTypeDeck{
						Name:   "Test Deck",
						Format: "Standard",
					},
				},
				ReleaseDate: time.Time{},
				Partitions: []game.Partition{
					{
						Name:  "Main",
						Cards: []game.CardDesc{{Name: "Test", Count: 1}},
					},
				},
			},
			expectError: true,
			errorMsg:    "release date is zero time",
		},
		{
			name: "no partitions",
			collection: game.Collection{
				ID:          "test-1",
				URL:         "https://example.com/deck/1",
				Type:        game.CollectionTypeWrapper{Type: "Deck", Inner: &game.CollectionTypeDeck{Name: "Test"}},
				ReleaseDate: time.Now(),
				Partitions:  []game.Partition{},
			},
			expectError: true,
			errorMsg:    "collection has no partitions",
		},
		{
			name: "partition with zero count card",
			collection: game.Collection{
				ID:          "test-1",
				URL:         "https://example.com/deck/1",
				Type:        game.CollectionTypeWrapper{Type: "Deck", Inner: &game.CollectionTypeDeck{Name: "Test"}},
				ReleaseDate: time.Now(),
				Partitions: []game.Partition{
					{
						Name: "Main",
						Cards: []game.CardDesc{
							{Name: "Lightning Bolt", Count: 0},
						},
					},
				},
			},
			expectError: true,
			errorMsg:    "invalid count",
		},
		{
			name: "partition with bad card name",
			collection: game.Collection{
				ID:          "test-1",
				URL:         "https://example.com/deck/1",
				Type:        game.CollectionTypeWrapper{Type: "Deck", Inner: &game.CollectionTypeDeck{Name: "Test"}},
				ReleaseDate: time.Now(),
				Partitions: []game.Partition{
					{
						Name: "Main",
						Cards: []game.CardDesc{
							{Name: "   ", Count: 1},
						},
					},
				},
			},
			expectError: true,
			errorMsg:    "bad card name",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.collection.Canonicalize()
			if tt.expectError {
				if err == nil {
					t.Errorf("expected error containing %q, got nil", tt.errorMsg)
				} else if tt.errorMsg != "" && !contains(err.Error(), tt.errorMsg) {
					t.Errorf("expected error containing %q, got %q", tt.errorMsg, err.Error())
				}
			} else {
				if err != nil {
					t.Errorf("unexpected error: %v", err)
				}
			}
		})
	}
}

func TestCollectionTypeWrapperMarshalJSON(t *testing.T) {
	tests := []struct {
		name     string
		wrapper  game.CollectionTypeWrapper
		validate func(t *testing.T, data []byte)
	}{
		{
			name: "deck type",
			wrapper: game.CollectionTypeWrapper{
				Type: "Deck",
				Inner: &game.CollectionTypeDeck{
					Name:      "Modern Burn",
					Format:    "Modern",
					Archetype: "Aggro",
				},
			},
			validate: func(t *testing.T, data []byte) {
				var result map[string]interface{}
				if err := json.Unmarshal(data, &result); err != nil {
					t.Fatalf("failed to unmarshal: %v", err)
				}
				if result["type"] != "Deck" {
					t.Errorf("expected type=Deck, got %v", result["type"])
				}
			},
		},
		{
			name: "set type",
			wrapper: game.CollectionTypeWrapper{
				Type: "Set",
				Inner: &game.CollectionTypeSet{
					Name: "Dominaria United",
					Code: "DMU",
				},
			},
			validate: func(t *testing.T, data []byte) {
				var result map[string]interface{}
				if err := json.Unmarshal(data, &result); err != nil {
					t.Fatalf("failed to unmarshal: %v", err)
				}
				if result["type"] != "Set" {
					t.Errorf("expected type=Set, got %v", result["type"])
				}
			},
		},
		{
			name: "cube type",
			wrapper: game.CollectionTypeWrapper{
				Type: "Cube",
				Inner: &game.CollectionTypeCube{
					Name: "Vintage Cube",
				},
			},
			validate: func(t *testing.T, data []byte) {
				var result map[string]interface{}
				if err := json.Unmarshal(data, &result); err != nil {
					t.Fatalf("failed to unmarshal: %v", err)
				}
				if result["type"] != "Cube" {
					t.Errorf("expected type=Cube, got %v", result["type"])
				}
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.wrapper)
			if err != nil {
				t.Fatalf("failed to marshal: %v", err)
			}

			// Unmarshal and validate
			var decoded game.CollectionTypeWrapper
			if err := json.Unmarshal(data, &decoded); err != nil {
				t.Fatalf("failed to unmarshal: %v", err)
			}

			if decoded.Type != tt.wrapper.Type {
				t.Errorf("expected type %q, got %q", tt.wrapper.Type, decoded.Type)
			}

			tt.validate(t, data)
		})
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(substr) == 0 ||
		(len(s) > 0 && len(substr) > 0 && stringContains(s, substr)))
}

func stringContains(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
