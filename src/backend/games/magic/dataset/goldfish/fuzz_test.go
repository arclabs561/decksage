package goldfish

import "testing"

// FuzzDeckIDRegex fuzzes the deck/archetype ID regex and ensures safe captures.
func FuzzDeckIDRegex(f *testing.F) {
	f.Add("https://www.mtggoldfish.com/deck/5678901#paper")
	f.Add("https://www.mtggoldfish.com/archetype/modern-burn")
	f.Add("")
	f.Add("/deck/")
	f.Fuzz(func(t *testing.T, s string) {
		m := reDeckID.FindStringSubmatch(s)
		if m != nil && len(m) < 2 {
			t.Fatalf("expected >=2 captures, got %d for %q", len(m), s)
		}
	})
}
