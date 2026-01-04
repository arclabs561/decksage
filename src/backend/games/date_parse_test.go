package games

import (
	"testing"
	"time"
)

func TestParseDateWithValidation(t *testing.T) {
	tests := []struct {
		name      string
		input     string
		wantErr   bool
		checkYear func(time.Time) bool
	}{
		{
			name:    "ISO format",
			input:   "2024-01-15",
			wantErr: false,
			checkYear: func(t time.Time) bool {
				return t.Year() == 2024 && t.Month() == time.January && t.Day() == 15
			},
		},
		{
			name:    "MTG Goldfish format",
			input:   "Jan 15, 2024",
			wantErr: false,
			checkYear: func(t time.Time) bool {
				return t.Year() == 2024 && t.Month() == time.January && t.Day() == 15
			},
		},
		{
			name:    "Deckbox format",
			input:   "15-Jan-2024 14:30",
			wantErr: false,
			checkYear: func(t time.Time) bool {
				return t.Year() == 2024 && t.Month() == time.January && t.Day() == 15
			},
		},
		{
			name:    "year too old",
			input:   "1980-01-15",
			wantErr: true,
		},
		{
			name:    "year too far future",
			input:   "2200-01-15",
			wantErr: true,
		},
		{
			name:    "invalid format",
			input:   "not a date",
			wantErr: true,
		},
		{
			name:    "empty string",
			input:   "",
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := ParseDateWithValidation(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseDateWithValidation(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
				return
			}
			if !tt.wantErr && tt.checkYear != nil {
				if !tt.checkYear(result) {
					t.Errorf("ParseDateWithValidation(%q) = %v, date validation failed", tt.input, result)
				}
			}
		})
	}
}

func TestParseDateWithFallback(t *testing.T) {
	fallback := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	tests := []struct {
		name     string
		input    string
		expected time.Time
	}{
		{
			name:     "valid date",
			input:    "2024-06-15",
			expected: time.Date(2024, 6, 15, 0, 0, 0, 0, time.UTC),
		},
		{
			name:     "invalid date uses fallback",
			input:    "not a date",
			expected: fallback,
		},
		{
			name:     "empty string uses fallback",
			input:    "",
			expected: fallback,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := ParseDateWithFallback(tt.input, fallback)
			if !result.Equal(tt.expected) {
				t.Errorf("ParseDateWithFallback(%q, %v) = %v, want %v", tt.input, fallback, result, tt.expected)
			}
		})
	}
}
