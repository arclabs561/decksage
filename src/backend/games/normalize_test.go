package games

import (
	"testing"
)

func TestNormalizeCardName(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "trim whitespace",
			input:    "  Lightning Bolt  ",
			expected: "Lightning Bolt",
		},
		{
			name:     "html entities",
			input:    "Fire &amp; Ice",
			expected: "Fire & Ice",
		},
		{
			name:     "multiple spaces",
			input:    "Lightning   Bolt",
			expected: "Lightning Bolt",
		},
		{
			name:     "unicode normalization",
			input:    "José",
			expected: "José",
		},
		{
			name:     "mixed case with spaces",
			input:    "  LIGHTNING   bolt  ",
			expected: "LIGHTNING bolt",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := NormalizeCardName(tt.input)
			if result != tt.expected {
				t.Errorf("NormalizeCardName(%q) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}

func TestNormalizeFormatName(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "standard lowercase",
			input:    "std",
			expected: "standard",
		},
		{
			name:     "modern uppercase",
			input:    "MOD",
			expected: "modern",
		},
		{
			name:     "commander variation",
			input:    "edh",
			expected: "commander",
		},
		{
			name:     "unknown format",
			input:    "custom format",
			expected: "Custom Format",
		},
		{
			name:     "with whitespace",
			input:    "  modern  ",
			expected: "modern",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := NormalizeFormatName(tt.input)
			if result != tt.expected {
				t.Errorf("NormalizeFormatName(%q) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}

func TestIsValidCardName(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected bool
	}{
		{
			name:     "valid name",
			input:    "Lightning Bolt",
			expected: true,
		},
		{
			name:     "empty after normalization",
			input:    "   ",
			expected: false,
		},
		{
			name:     "with control character",
			input:    "Lightning\x00Bolt",
			expected: false,
		},
		{
			name:     "with html entities",
			input:    "Fire &amp; Ice",
			expected: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := IsValidCardName(tt.input)
			if result != tt.expected {
				t.Errorf("IsValidCardName(%q) = %v, want %v", tt.input, result, tt.expected)
			}
		})
	}
}
