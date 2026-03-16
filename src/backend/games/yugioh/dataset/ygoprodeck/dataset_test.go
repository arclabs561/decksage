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
	atk := 2500
	def := 2000
	level := 7

	apiCard := apiCard{
		ID:        89631139,
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
		CardSets: []struct {
			SetName       string `json:"set_name"`
			SetCode       string `json:"set_code"`
			SetRarity     string `json:"set_rarity"`
			SetRarityCode string `json:"set_rarity_code"`
			SetPrice      string `json:"set_price"`
		}{
			{SetName: "Legend of Blue Eyes White Dragon", SetCode: "LOB-EN001", SetRarity: "Ultra Rare", SetPrice: "12.34"},
			{SetName: "Starter Deck: Kaiba", SetCode: "SDK-001", SetRarity: "Ultra Rare", SetPrice: "5.67"},
		},
	}

	card := convertToCard(apiCard)

	if card.Name != "Blue-Eyes White Dragon" {
		t.Errorf("Name: got %q, want %q", card.Name, "Blue-Eyes White Dragon")
	}
	if card.Passcode != 89631139 {
		t.Errorf("Passcode: got %d, want 89631139", card.Passcode)
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
	if len(card.Sets) != 2 {
		t.Errorf("Sets: got %d, want 2", len(card.Sets))
	} else {
		if card.Sets[0].SetCode != "LOB-EN001" {
			t.Errorf("Sets[0].SetCode: got %q, want %q", card.Sets[0].SetCode, "LOB-EN001")
		}
	}
}

// TestCardTypeDetection tests Spell/Trap detection and property extraction
func TestCardTypeDetection(t *testing.T) {
	tests := []struct {
		typeStr      string
		wantType     game.CardType
		wantProperty string
	}{
		{"Effect Monster", game.TypeMonster, ""},
		{"Normal Spell Card", game.TypeSpell, "Normal"},
		{"Quick-Play Spell Card", game.TypeSpell, "Quick-Play"},
		{"Equip Spell Card", game.TypeSpell, "Equip"},
		{"Field Spell Card", game.TypeSpell, "Field"},
		{"Continuous Spell Card", game.TypeSpell, "Continuous"},
		{"Ritual Spell Card", game.TypeSpell, "Ritual"},
		{"Counter Trap Card", game.TypeTrap, "Counter"},
		{"Continuous Trap Card", game.TypeTrap, "Continuous"},
		{"Normal Trap Card", game.TypeTrap, "Normal"},
	}

	for _, tt := range tests {
		t.Run(tt.typeStr, func(t *testing.T) {
			ac := apiCard{
				Name: "Test",
				Type: tt.typeStr,
				Desc: "Test card",
			}

			card := convertToCard(ac)

			if card.Type != tt.wantType {
				t.Errorf("Type: got %v, want %v for %q", card.Type, tt.wantType, tt.typeStr)
			}
			if card.Property != tt.wantProperty {
				t.Errorf("Property: got %q, want %q for %q", card.Property, tt.wantProperty, tt.typeStr)
			}
		})
	}
}

// TestMonsterSubTypes tests subtypes like Tuner, Spirit, etc.
func TestMonsterSubTypes(t *testing.T) {
	tests := []struct {
		typeStr     string
		wantSubs    []string
	}{
		{"Synchro Tuner Effect Monster", []string{"Tuner"}},
		{"Flip Effect Monster", []string{"Flip"}},
		{"Spirit Effect Monster", []string{"Spirit"}},
		{"Normal Monster", nil},
		{"Toon Effect Monster", []string{"Toon"}},
		{"Union Effect Monster", []string{"Union"}},
		{"Gemini Effect Monster", []string{"Gemini"}},
	}

	for _, tt := range tests {
		t.Run(tt.typeStr, func(t *testing.T) {
			mt := parseMonsterType(tt.typeStr)
			if len(mt.SubTypes) != len(tt.wantSubs) {
				t.Errorf("SubTypes: got %v, want %v", mt.SubTypes, tt.wantSubs)
				return
			}
			for i, s := range mt.SubTypes {
				if s != tt.wantSubs[i] {
					t.Errorf("SubTypes[%d]: got %q, want %q", i, s, tt.wantSubs[i])
				}
			}
		})
	}
}

// TestPendulumScale tests Pendulum scale extraction
func TestPendulumScale(t *testing.T) {
	scale := 4
	ac := apiCard{
		Name:  "Performapal Skullcrobat Joker",
		Type:  "Pendulum Effect Monster",
		Desc:  "test",
		Scale: &scale,
	}
	card := convertToCard(ac)

	if card.Scale != 4 {
		t.Errorf("Scale: got %d, want 4", card.Scale)
	}
	if card.MonsterType == nil || !card.MonsterType.IsPendulum {
		t.Error("expected IsPendulum=true")
	}
}
