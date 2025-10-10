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
			name: "PokemonDeck",
			ct: &CollectionTypeDeck{
				Name:   "Charizard Deck",
				Format: "Standard",
			},
			want: `{"name":"Charizard Deck","format":"Standard"}`,
		},
		{
			name: "PokemonSet",
			ct: &CollectionTypeSet{
				Name:   "Base Set",
				Code:   "base1",
				Series: "Base",
			},
			want: `{"name":"Base Set","code":"base1","series":"Base"}`,
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
		Name:        "Charizard",
		SuperType:   "Pokémon",
		SubTypes:    []string{"Stage 2"},
		HP:          "120",
		Types:       []string{"Fire"},
		EvolvesFrom: "Charmeleon",
		Attacks: []Attack{
			{
				Name:   "Fire Spin",
				Cost:   []string{"Fire", "Fire", "Fire", "Fire"},
				Damage: "100",
				Text:   "Discard 2 Energy attached to Charizard.",
			},
		},
		RetreatCost: []string{"Colorless", "Colorless", "Colorless"},
		Rarity:      "Rare Holo",
		NationalDex: 6,
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
	if decoded.HP != card.HP {
		t.Errorf("HP = %v, want %v", decoded.HP, card.HP)
	}
	if len(decoded.Attacks) != 1 {
		t.Errorf("Attacks count = %v, want 1", len(decoded.Attacks))
	}
}
