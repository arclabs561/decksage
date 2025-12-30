package games

import (
	"errors"
	"testing"
)

func TestCategorizeError(t *testing.T) {
	tests := []struct {
		name     string
		err      error
		expected ErrorCategory
	}{
		{
			name:     "network error",
			err:      errors.New("connection refused"),
			expected: ErrorCategoryNetwork,
		},
		{
			name:     "rate limit error",
			err:      errors.New("rate limit exceeded"),
			expected: ErrorCategoryRateLimit,
		},
		{
			name:     "parsing error",
			err:      errors.New("failed to parse JSON"),
			expected: ErrorCategoryParsing,
		},
		{
			name:     "validation error",
			err:      errors.New("invalid card name"),
			expected: ErrorCategoryValidation,
		},
		{
			name:     "unknown error",
			err:      errors.New("something went wrong"),
			expected: ErrorCategoryUnknown,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := CategorizeError(tt.err)
			if result != tt.expected {
				t.Errorf("CategorizeError(%q) = %v, want %v", tt.err.Error(), result, tt.expected)
			}
		})
	}
}

