package scryfall

import "testing"

// FuzzSetNameRegex fuzzes reSetName to ensure it never panics and only matches valid patterns.
func FuzzSetNameRegex(f *testing.F) {
	// Seed with known-good and bad inputs
	f.Add("Dominaria United (DMU)")
	f.Add("The Brothers' War (BRO)")
	f.Add("Invalid Format")
	f.Add("")
	f.Add("()")
	f.Add("((((((((((((((((((((((((((((((")

	f.Fuzz(func(t *testing.T, s string) {
		m := reSetName.FindStringSubmatch(s)
		if m != nil {
			// If matched, ensure captures exist
			if len(m) < 3 {
				t.Fatalf("expected >=3 captures, got %d for %q", len(m), s)
			}
			// Code should be 2-5 uppercase letters typically; be lenient but non-empty
			if len(m[2]) == 0 {
				t.Fatalf("empty code capture for %q", s)
			}
		}
	})
}
