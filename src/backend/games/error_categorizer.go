package games

import (
	"context"
	"errors"
	"strings"
)

// ErrorCategory represents the type of error encountered
type ErrorCategory string

const (
	ErrorCategoryNetwork    ErrorCategory = "network"     // HTTP, connection errors
	ErrorCategoryParsing   ErrorCategory = "parsing"     // HTML/JSON parsing errors
	ErrorCategoryValidation ErrorCategory = "validation"  // Data validation errors
	ErrorCategoryRateLimit  ErrorCategory = "rate_limit" // Rate limiting/throttling
	ErrorCategoryUnknown    ErrorCategory = "unknown"    // Unclassified errors
)

// CategorizeError determines the category of an error
func CategorizeError(err error) ErrorCategory {
	if err == nil {
		return ErrorCategoryUnknown
	}

	errStr := strings.ToLower(err.Error())

	// Network errors
	if strings.Contains(errStr, "connection") ||
		strings.Contains(errStr, "timeout") ||
		strings.Contains(errStr, "network") ||
		strings.Contains(errStr, "dial") ||
		strings.Contains(errStr, "refused") ||
		strings.Contains(errStr, "no such host") {
		return ErrorCategoryNetwork
	}

	// Rate limiting
	if strings.Contains(errStr, "rate limit") ||
		strings.Contains(errStr, "throttle") ||
		strings.Contains(errStr, "too many requests") ||
		strings.Contains(errStr, "429") {
		return ErrorCategoryRateLimit
	}

	// Parsing errors
	if strings.Contains(errStr, "parse") ||
		strings.Contains(errStr, "unmarshal") ||
		strings.Contains(errStr, "invalid json") ||
		strings.Contains(errStr, "syntax error") ||
		strings.Contains(errStr, "malformed") {
		return ErrorCategoryParsing
	}

	// Validation errors
	if strings.Contains(errStr, "invalid") ||
		strings.Contains(errStr, "validation") ||
		strings.Contains(errStr, "empty") ||
		strings.Contains(errStr, "missing") ||
		strings.Contains(errStr, "required") {
		return ErrorCategoryValidation
	}

	return ErrorCategoryUnknown
}

// RecordCategorizedError records an error with automatic categorization
func (s *ExtractStats) RecordCategorizedError(ctx context.Context, url, dataset string, err error) {
	category := CategorizeError(err)
	s.RecordError(ctx, url, dataset, err)
	s.RecordValidationFailure("error_" + string(category))
}

// GetErrorSummary returns a summary of errors by category
func (s *ExtractStats) GetErrorSummary() map[ErrorCategory]int {
	s.mu.Lock()
	defer s.mu.Unlock()

	summary := make(map[ErrorCategory]int)
	for _, extractErr := range s.Errors {
		category := CategorizeError(errors.New(extractErr.Error))
		summary[category]++
	}
	return summary
}
