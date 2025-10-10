package game

import (
	"encoding/json"
	"testing"
)

func TestCollectionTypeMarshal(t *testing.T) {
	tests := []struct {
		name string
		ct   CollectionType
		want string
	}{
		{
			name: "YGODeck",
			ct: &CollectionTypeDeck{
				Name:   "Blue-Eyes Deck",
				Format: "TCG",
			},
			want: `{"name":"Blue-Eyes Deck","format":"TCG"}`,
		},
		{
			name: "YGOCollection",
			ct: &CollectionTypeCollection{
				Name:        "My Binder",
				Description: "Rare cards",
			},
			want: `{"name":"My Binder","description":"Rare cards"}`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := json.Marshal(tt.ct)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			if string(got) != tt.want {
				t.Errorf("Marshal() = %v, want %v", string(got), tt.want)
			}
		})
	}
}

func TestCardMarshal(t *testing.T) {
	card := Card{
		Name: "Blue-Eyes White Dragon",
		Type: TypeMonster,
		MonsterType: &MonsterType{
			MainType: "Normal",
			IsEffect: false,
		},
		Attribute:   "LIGHT",
		Level:       8,
		ATK:         3000,
		DEF:         2500,
		Race:        "Dragon",
		Description: "This legendary dragon is a powerful engine of destruction.",
	}

	data, err := json.Marshal(card)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}

	var decoded Card
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal() error = %v", err)
	}

	if decoded.Name != card.Name {
		t.Errorf("Name = %v, want %v", decoded.Name, card.Name)
	}
	if decoded.ATK != card.ATK {
		t.Errorf("ATK = %v, want %v", decoded.ATK, card.ATK)
	}
}
