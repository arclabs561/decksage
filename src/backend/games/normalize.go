package games

import (
	"html"
	"strings"
	"unicode"

	"golang.org/x/text/unicode/norm"
)

// NormalizeCardName normalizes card names for consistent storage and comparison
// Handles:
// - Leading/trailing whitespace
// - HTML entity decoding
// - Unicode normalization (NFC)
// - Multiple spaces collapsed to single space
func NormalizeCardName(name string) string {
	// Trim whitespace
	name = strings.TrimSpace(name)

	// Decode HTML entities (e.g., &amp; -> &, &quot; -> ")
	name = html.UnescapeString(name)

	// Unicode normalization (NFC - Canonical Decomposition followed by Canonical Composition)
	name = norm.NFC.String(name)

	// Collapse multiple spaces to single space
	fields := strings.Fields(name)
	name = strings.Join(fields, " ")

	return name
}

// NormalizeFormatName normalizes format names to canonical form
func NormalizeFormatName(format string) string {
	format = strings.TrimSpace(format)
	format = strings.ToLower(format)

	// Map common variations to canonical names
	formatMap := map[string]string{
		"std":     "standard",
		"mod":     "modern",
		"leg":     "legacy",
		"vin":     "vintage",
		"pio":     "pioneer",
		"pau":     "pauper",
		"cedh":    "cedh",
		"commander": "commander",
		"edh":     "commander",
		"duel commander": "duel commander",
		"dc":      "duel commander",
		"premodern": "premodern",
		"pre":     "premodern",
		"highlander": "highlander",
		"peasant": "peasant",
	}

	if canonical, ok := formatMap[format]; ok {
		return canonical
	}

	// Capitalize first letter of each word for unknown formats
	words := strings.Fields(format)
	for i, word := range words {
		if len(word) > 0 {
			words[i] = strings.ToUpper(string(word[0])) + strings.ToLower(word[1:])
		}
	}
	return strings.Join(words, " ")
}

// IsValidCardName checks if a card name is valid after normalization
func IsValidCardName(name string) bool {
	normalized := NormalizeCardName(name)
	if normalized == "" {
		return false
	}
	// Check for control characters
	for _, r := range normalized {
		if unicode.IsControl(r) {
			return false
		}
	}
	return true
}
