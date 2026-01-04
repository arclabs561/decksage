package games

import (
	"fmt"
	"strings"
	"time"
)

// Common date formats used across different sources
var dateFormats = []string{
	"2006-01-02",                    // ISO format
	"Jan 2, 2006",                   // MTG Goldfish
	"02-Jan-2006 15:04",             // Deckbox
	"2006-01-02 15:04:05",           // With time
	"January 2, 2006",               // Full month name
	"Jan _2, 2006",                  // With space padding
	"02/01/2006",                    // DD/MM/YYYY
	"01/02/2006",                    // MM/DD/YYYY
	"2006-01-02T15:04:05Z07:00",     // RFC3339
	"Mon, 02 Jan 2006 15:04:05 MST", // RFC1123
}

// ParseDateWithValidation attempts to parse a date string using common formats
// and validates the result is within a reasonable range (1990-2100)
func ParseDateWithValidation(dateStr string) (time.Time, error) {
	if dateStr == "" {
		return time.Time{}, fmt.Errorf("empty date string")
	}

	dateStr = strings.TrimSpace(dateStr)

	// Try each format
	for _, format := range dateFormats {
		if t, err := time.Parse(format, dateStr); err == nil {
			// Validate reasonable range
			year := t.Year()
			if year >= 1990 && year <= 2100 {
				return t, nil
			}
			return time.Time{}, fmt.Errorf("date %q has invalid year %d (expected 1990-2100)", dateStr, year)
		}
	}

	return time.Time{}, fmt.Errorf("could not parse date %q with any known format", dateStr)
}

// ParseDateWithFallback attempts to parse a date, falling back to a default if parsing fails
func ParseDateWithFallback(dateStr string, fallback time.Time) time.Time {
	if t, err := ParseDateWithValidation(dateStr); err == nil {
		return t
	}
	return fallback
}
