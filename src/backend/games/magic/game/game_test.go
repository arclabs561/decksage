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
