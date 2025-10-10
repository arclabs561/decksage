package mtgtop8

import "testing"

// FuzzDeckIDRegex ensures reDeckID never panics and captures expected groups when matching.
func FuzzDeckIDRegex(f *testing.F) {
	f.Add("https://mtgtop8.com/event?e=123&d=456")
	f.Add("https://example.com/deck")
	f.Add("")
	f.Add("event?e=&d=")
	f.Fuzz(func(t *testing.T, s string) {
		m := reDeckID.FindStringSubmatch(s)
		if m != nil {
			if len(m) < 3 {
				t.Fatalf("expected >=3 captures, got %d for %q", len(m), s)
			}
		}
	})
}
