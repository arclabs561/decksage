package pokemontcg

import (
	"testing"
)

func TestDescription(t *testing.T) {
	d := &Dataset{}
	desc := d.Description()

	if desc.Game != "pokemon" {
		t.Errorf("Expected game=pokemon, got %s", desc.Game)
	}

	if desc.Name != "pokemontcg" {
		t.Errorf("Expected name=pokemontcg, got %s", desc.Name)
	}
}

func TestConvertToCard(t *testing.T) {
	apiCard := apiCard{
		ID:                     "base1-4",
		Name:                   "Charizard",
		Supertype:              "Pokémon",
		Subtypes:               []string{"Stage 2"},
		HP:                     "120",
		Types:                  []string{"Fire"},
		EvolvesFrom:            "Charmeleon",
		Rarity:                 "Rare Holo",
		Artist:                 "Mitsuhiro Arita",
		NationalPokedexNumbers: []int{6},
	}

	apiCard.Attacks = []struct {
		Name                string   `json:"name"`
		Cost                []string `json:"cost"`
		ConvertedEnergyCost int      `json:"convertedEnergyCost"`
		Damage              string   `json:"damage"`
		Text                string   `json:"text"`
	}{
		{
			Name:                "Fire Spin",
			Cost:                []string{"Fire", "Fire", "Fire", "Fire"},
			ConvertedEnergyCost: 4,
			Damage:              "100",
			Text:                "Discard 2 Energy.",
		},
	}

	apiCard.Weaknesses = []struct {
		Type  string `json:"type"`
		Value string `json:"value"`
	}{
		{Type: "Water", Value: "×2"},
	}

	card := convertToCard(apiCard)

	if card.Name != "Charizard" {
		t.Errorf("Expected name=Charizard, got %s", card.Name)
	}

	if card.SuperType != "Pokémon" {
		t.Errorf("Expected supertype=Pokémon, got %s", card.SuperType)
	}

	if len(card.Attacks) != 1 {
		t.Errorf("Expected 1 attack, got %d", len(card.Attacks))
	}

	if card.Attacks[0].Name != "Fire Spin" {
		t.Errorf("Expected attack name=Fire Spin, got %s", card.Attacks[0].Name)
	}

	if len(card.Weaknesses) != 1 {
		t.Errorf("Expected 1 weakness, got %d", len(card.Weaknesses))
	}

	if len(card.NationalDex) != 1 || card.NationalDex[0] != 6 {
		t.Errorf("Expected national dex=[6], got %v", card.NationalDex)
	}
}

func TestConvertToCard_RegulationAndLegalities(t *testing.T) {
	apiCard := apiCard{
		ID:             "sv1-1",
		Name:           "Sprigatito",
		Supertype:      "Pokémon",
		Subtypes:       []string{"Basic"},
		HP:             "70",
		Types:          []string{"Grass"},
		RegulationMark: "G",
		Legalities:     map[string]string{"standard": "Legal", "expanded": "Legal", "unlimited": "Legal"},
	}

	card := convertToCard(apiCard)

	if card.Regulation != "G" {
		t.Errorf("Regulation: got %q, want %q", card.Regulation, "G")
	}
	if card.Legalities["standard"] != "Legal" {
		t.Errorf("Legalities[standard]: got %q, want %q", card.Legalities["standard"], "Legal")
	}
}
