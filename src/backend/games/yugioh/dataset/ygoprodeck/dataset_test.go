package ygoprodeck

import (
	"collections/games/yugioh/game"
	"testing"
)

// TestContainsFunction tests the critical contains() function
// This function was found to be broken during code review - it only checked
// prefix/suffix, not middle of string.
func TestContainsFunction(t *testing.T) {
	tests := []struct {
		name   string
		s      string
		substr string
		want   bool
	}{
		// Prefix matches
		{"prefix_match", "Effect Monster", "Effect", true},
		{"prefix_match_2", "Fusion Monster", "Fusion", true},

		// Suffix matches
		{"suffix_match", "Link Monster", "Monster", true},

		// Middle matches (CRITICAL - this was failing before fix)
		{"middle_match_tuner", "Synchro Tuner Effect Monster", "Tuner", true},
		{"middle_match_effect", "Synchro Tuner Effect Monster", "Effect", true},
		{"middle_match_xyz", "Rank 4 XYZ Monster", "XYZ", true},

		// No match
		{"no_match", "Normal Monster", "Effect", false},
		{"no_match_2", "Spell Card", "Monster", false},

		// Edge cases
		{"exact_match", "Effect", "Effect", true},
		{"empty_substr", "Effect Monster", "", true}, // Empty string is always contained
		{"empty_both", "", "", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := contains(tt.s, tt.substr)
			if got != tt.want {
				t.Errorf("contains(%q, %q) = %v, want %v", tt.s, tt.substr, got, tt.want)
			}
		})
	}
}

// TestParseMonsterType tests monster type parsing with real YGO examples
func TestParseMonsterType(t *testing.T) {
	tests := []struct {
		name    string
		typeStr string
		checks  map[string]bool
	}{
		{
			name:    "simple_effect",
			typeStr: "Effect Monster",
			checks: map[string]bool{
				"IsEffect":  true,
				"IsFusion":  false,
				"IsSynchro": false,
			},
		},
		{
			name:    "synchro_tuner_effect",
			typeStr: "Synchro Tuner Effect Monster",
			checks: map[string]bool{
				"IsEffect":  true,
				"IsSynchro": true,
				// Note: Tuner would be in subtypes, not a bool flag
			},
		},
		{
			name:    "xyz_effect",
			typeStr: "XYZ Effect Monster",
			checks: map[string]bool{
				"IsEffect": true,
				"IsXyz":    true,
			},
		},
		{
			name:    "link_effect",
			typeStr: "Link Effect Monster",
			checks: map[string]bool{
				"IsEffect": true,
				"IsLink":   true,
			},
		},
		{
			name:    "fusion_effect",
			typeStr: "Fusion Effect Monster",
			checks: map[string]bool{
				"IsEffect": true,
				"IsFusion": true,
			},
		},
		{
			name:    "pendulum_effect",
			typeStr: "Pendulum Effect Monster",
			checks: map[string]bool{
				"IsEffect":   true,
				"IsPendulum": true,
			},
		},
		{
			name:    "normal_monster",
			typeStr: "Normal Monster",
			checks: map[string]bool{
				"IsEffect": false,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mt := parseMonsterType(tt.typeStr)

			for field, expected := range tt.checks {
				var got bool
				switch field {
				case "IsEffect":
					got = mt.IsEffect
				case "IsFusion":
					got = mt.IsFusion
				case "IsSynchro":
					got = mt.IsSynchro
				case "IsXyz":
					got = mt.IsXyz
				case "IsLink":
					got = mt.IsLink
				case "IsRitual":
					got = mt.IsRitual
				case "IsPendulum":
					got = mt.IsPendulum
				default:
					t.Errorf("unknown field: %s", field)
					continue
				}

				if got != expected {
					t.Errorf("%s: got %v, want %v (typeStr: %q)", field, got, expected, tt.typeStr)
				}
			}
		})
	}
}

// TestConvertToCard tests full card conversion from API
func TestConvertToCard(t *testing.T) {
	// Test a complex monster
	atk := 2500
	def := 2000
	level := 7

	apiCard := apiCard{
		Name:      "Blue-Eyes White Dragon",
		Type:      "Normal Monster",
		Desc:      "This legendary dragon is a powerful engine of destruction.",
		ATK:       &atk,
		DEF:       &def,
		Level:     &level,
		Race:      "Dragon",
		Attribute: "LIGHT",
		CardImages: []struct {
			ImageURL      string `json:"image_url"`
			ImageURLSmall string `json:"image_url_small"`
		}{
			{ImageURL: "https://example.com/blue-eyes.jpg"},
		},
	}

	card := convertToCard(apiCard)

	if card.Name != "Blue-Eyes White Dragon" {
		t.Errorf("Name: got %q, want %q", card.Name, "Blue-Eyes White Dragon")
	}

	if card.Type != game.TypeMonster {
		t.Errorf("Type: got %v, want %v", card.Type, game.TypeMonster)
	}

	if card.ATK != 2500 {
		t.Errorf("ATK: got %d, want 2500", card.ATK)
	}

	if card.DEF != 2000 {
		t.Errorf("DEF: got %d, want 2000", card.DEF)
	}

	if card.Level != 7 {
		t.Errorf("Level: got %d, want 7", card.Level)
	}

	if len(card.Images) != 1 {
		t.Errorf("Images: got %d, want 1", len(card.Images))
	}
}

// TestCardTypeDetection tests Spell/Trap detection
func TestCardTypeDetection(t *testing.T) {
	tests := []struct {
		typeStr  string
		wantType game.CardType
	}{
		{"Effect Monster", game.TypeMonster},
		{"Normal Spell Card", game.TypeSpell},
		{"Quick-Play Spell Card", game.TypeSpell},
		{"Counter Trap Card", game.TypeTrap},
		{"Continuous Trap Card", game.TypeTrap},
	}

	for _, tt := range tests {
		t.Run(tt.typeStr, func(t *testing.T) {
			apiCard := apiCard{
				Name: "Test",
				Type: tt.typeStr,
				Desc: "Test card",
			}

			card := convertToCard(apiCard)

			if card.Type != tt.wantType {
				t.Errorf("got %v, want %v for type %q", card.Type, tt.wantType, tt.typeStr)
			}
		})
	}
}
