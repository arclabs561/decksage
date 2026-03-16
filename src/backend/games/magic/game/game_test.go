package game

import (
	"testing"
)

func TestParseTypeLine(t *testing.T) {
	tests := []struct {
		name       string
		typeLine   string
		wantSuper  []string
		wantTypes  []string
		wantSub    []string
	}{
		{
			name:      "legendary creature with subtypes",
			typeLine:  "Legendary Creature \u2014 Human Wizard",
			wantSuper: []string{"Legendary"},
			wantTypes: []string{"Creature"},
			wantSub:   []string{"Human", "Wizard"},
		},
		{
			name:      "instant",
			typeLine:  "Instant",
			wantSuper: nil,
			wantTypes: []string{"Instant"},
			wantSub:   nil,
		},
		{
			name:      "basic land",
			typeLine:  "Basic Land \u2014 Mountain",
			wantSuper: []string{"Basic"},
			wantTypes: []string{"Land"},
			wantSub:   []string{"Mountain"},
		},
		{
			name:      "legendary planeswalker",
			typeLine:  "Legendary Planeswalker \u2014 Jace",
			wantSuper: []string{"Legendary"},
			wantTypes: []string{"Planeswalker"},
			wantSub:   []string{"Jace"},
		},
		{
			name:      "snow artifact creature",
			typeLine:  "Snow Artifact Creature \u2014 Construct",
			wantSuper: []string{"Snow"},
			wantTypes: []string{"Artifact", "Creature"},
			wantSub:   []string{"Construct"},
		},
		{
			name:      "enchantment creature",
			typeLine:  "Enchantment Creature \u2014 God",
			wantSuper: nil,
			wantTypes: []string{"Enchantment", "Creature"},
			wantSub:   []string{"God"},
		},
		{
			name:      "artifact no subtypes",
			typeLine:  "Artifact",
			wantSuper: nil,
			wantTypes: []string{"Artifact"},
			wantSub:   nil,
		},
		{
			name:      "legendary snow creature",
			typeLine:  "Legendary Snow Creature \u2014 Dragon",
			wantSuper: []string{"Legendary", "Snow"},
			wantTypes: []string{"Creature"},
			wantSub:   []string{"Dragon"},
		},
		{
			name:      "kindred sorcery",
			typeLine:  "Kindred Sorcery \u2014 Elemental",
			wantSuper: nil,
			wantTypes: []string{"Kindred", "Sorcery"},
			wantSub:   []string{"Elemental"},
		},
		{
			name:      "empty",
			typeLine:  "",
			wantSuper: nil,
			wantTypes: nil,
			wantSub:   nil,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			supers, types, subs := ParseTypeLine(tt.typeLine)
			if !sliceEq(supers, tt.wantSuper) {
				t.Errorf("supertypes: got %v, want %v", supers, tt.wantSuper)
			}
			if !sliceEq(types, tt.wantTypes) {
				t.Errorf("types: got %v, want %v", types, tt.wantTypes)
			}
			if !sliceEq(subs, tt.wantSub) {
				t.Errorf("subtypes: got %v, want %v", subs, tt.wantSub)
			}
		})
	}
}

func TestParseManaCost(t *testing.T) {
	tests := []struct {
		name       string
		manaCost   string
		wantCMC    int
		wantColors []string
	}{
		{
			name:       "empty",
			manaCost:   "",
			wantCMC:    0,
			wantColors: nil,
		},
		{
			name:       "generic only",
			manaCost:   "{3}",
			wantCMC:    3,
			wantColors: nil,
		},
		{
			name:       "single color",
			manaCost:   "{U}",
			wantCMC:    1,
			wantColors: []string{"Blue"},
		},
		{
			name:       "generic plus colors",
			manaCost:   "{2}{U}{B}",
			wantCMC:    4,
			wantColors: []string{"Blue", "Black"},
		},
		{
			name:       "all five colors",
			manaCost:   "{W}{U}{B}{R}{G}",
			wantCMC:    5,
			wantColors: []string{"White", "Blue", "Black", "Red", "Green"},
		},
		{
			name:       "variable X",
			manaCost:   "{X}{R}{R}",
			wantCMC:    2,
			wantColors: []string{"Red"},
		},
		{
			name:       "colorless",
			manaCost:   "{C}{C}",
			wantCMC:    2,
			wantColors: nil,
		},
		{
			name:       "snow",
			manaCost:   "{S}{S}{S}",
			wantCMC:    3,
			wantColors: nil,
		},
		{
			name:       "hybrid",
			manaCost:   "{W/U}{B}",
			wantCMC:    2,
			wantColors: []string{"White", "Blue", "Black"},
		},
		{
			name:       "hybrid with generic",
			manaCost:   "{2/W}",
			wantCMC:    1,
			wantColors: []string{"White"},
		},
		{
			name:       "duplicate color symbols",
			manaCost:   "{R}{R}{R}",
			wantCMC:    3,
			wantColors: []string{"Red"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cmc, colors := ParseManaCost(tt.manaCost)
			if cmc != tt.wantCMC {
				t.Errorf("cmc: got %d, want %d", cmc, tt.wantCMC)
			}
			if !sliceEq(colors, tt.wantColors) {
				t.Errorf("colors: got %v, want %v", colors, tt.wantColors)
			}
		})
	}
}

func sliceEq(a, b []string) bool {
	if len(a) == 0 && len(b) == 0 {
		return true
	}
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
