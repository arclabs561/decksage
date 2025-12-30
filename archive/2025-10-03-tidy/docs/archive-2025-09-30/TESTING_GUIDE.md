# DeckSage Testing Guide

## Overview

DeckSage uses a **multi-tier testing strategy** to balance speed, reliability, and real-world validation:

1. **Fast unit tests** - Test parsing logic with saved fixtures (default)
2. **Integration tests** - Test against live sources with build tags (opt-in)
3. **Fixture refresh tools** - Keep test data up-to-date

## Running Tests

### Quick Unit Tests (Fast)

Run all tests except slow integration tests:

```bash
cd src/backend
go test ./...
```

**Runs in ~1-2 seconds** ✅

### Specific Package Tests

```bash
# Test game models
go test ./games/magic/game/...

# Test dataset infrastructure
go test ./games/magic/dataset/...

# Test specific dataset parser
go test ./games/magic/dataset/scryfall/...
```

### Integration Tests (Slow, Live HTTP)

Run tests that hit real external sources:

```bash
# Run ALL tests including integration
go test -tags=integration ./...

# Run only integration tests
go test -tags=integration ./games/magic/dataset/ -run TestIntegration

# Run with short mode (skips slow tests)
go test -short ./...
```

**Warning**: Integration tests take 5-10+ minutes and make real HTTP requests.

### Coverage Reports

```bash
# Generate coverage
go test -cover ./...

# Detailed HTML coverage report
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out -o coverage.html
open coverage.html
```

## Test Architecture

### Unit Tests

**Purpose**: Fast validation of parsing and business logic

**Location**: `*_test.go` files alongside implementation

**Characteristics**:
- Use saved HTML/JSON fixtures from `testdata/`
- Run in milliseconds
- No network calls
- Isolated from external services

**Example**:
```go
func TestParseDeckPage(t *testing.T) {
    html, err := os.ReadFile("testdata/mtgtop8/deck_page.html")
    // ... test parsing logic
}
```

### Integration Tests

**Purpose**: Validate end-to-end functionality with real sources

**Location**: Files with `//go:build integration` tag

**Characteristics**:
- Marked with build tag: `//go:build integration`
- Make real HTTP requests
- Slow (minutes)
- Can fail due to network/site changes

**Example**:
```go
//go:build integration
// +build integration

func TestIntegrationAll(t *testing.T) {
    // ... scrape real websites
}
```

## Test Fixtures

### What Are Fixtures?

Saved HTML/JSON responses from external sources used for fast, reliable unit tests.

### Location

```
src/backend/games/magic/dataset/testdata/
├── scryfall/
│   ├── bulk_data.json
│   ├── cards_sample.json
│   └── set_page.html
├── deckbox/
│   └── deck_page.html
├── goldfish/
│   └── deck_page.html
└── mtgtop8/
    ├── deck_page.html
    └── search_page.html
```

### Refreshing Fixtures

Fixtures can become stale as websites change. Refresh them periodically:

```bash
cd src/backend

# Refresh all fixtures
go run ./cmd/testdata refresh

# Refresh specific dataset
go run ./cmd/testdata refresh --dataset=scryfall
go run ./cmd/testdata refresh --dataset=mtgtop8

# Save a specific URL
go run ./cmd/testdata save \
  --url="https://mtgtop8.com/event?e=12345&d=67890" \
  --output=mtgtop8/example_deck.html
```

### When to Refresh

- Before major releases
- When tests start failing
- After website redesigns
- Quarterly maintenance

## Test Organization

### Current Test Coverage

| Component | Tests | Status |
|-----------|-------|--------|
| `games/magic/game/` | ✅ Comprehensive | 11 tests, validation, JSON marshaling |
| `games/magic/dataset/` | ✅ Basic | Dataset creation, blob operations |
| `dataset/scryfall/` | ✅ Good | Card parsing, set parsing, regex validation |
| `dataset/deckbox/` | ⚠️ Basic | Needs expansion |
| `dataset/goldfish/` | ✅ Good | Deck parsing, URL handling |
| `dataset/mtgtop8/` | ✅ Good | Deck parsing, ID extraction |
| `scraper/` | ❌ None | Needs tests for retry, rate limiting |
| `blob/` | ⚠️ Basic | Covered in dataset tests |
| `transform/` | ❌ None | Needs tests |

### Test Types by Package

```
games/magic/
├── game/
│   └── game_test.go              # Model validation, JSON marshaling
├── dataset/
│   ├── dataset_test.go           # Integration tests (build tag)
│   ├── dataset_unit_test.go      # Fast unit tests
│   ├── scryfall/
│   │   └── dataset_test.go       # Card parsing, set parsing
│   ├── deckbox/
│   │   └── (needs tests)
│   ├── goldfish/
│   │   └── dataset_test.go       # Deck parsing
│   └── mtgtop8/
│       └── dataset_test.go       # Deck parsing
```

## Writing New Tests

### Unit Test Template

```go
package mypackage

import (
    "testing"
)

func TestMyFunction(t *testing.T) {
    tests := []struct {
        name    string
        input   string
        want    string
        wantErr bool
    }{
        {
            name:  "valid input",
            input: "test",
            want:  "expected",
        },
        {
            name:    "invalid input",
            input:   "bad",
            wantErr: true,
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got, err := MyFunction(tt.input)
            if tt.wantErr {
                if err == nil {
                    t.Error("expected error, got nil")
                }
                return
            }
            if err != nil {
                t.Fatalf("unexpected error: %v", err)
            }
            if got != tt.want {
                t.Errorf("got %s, want %s", got, tt.want)
            }
        })
    }
}
```

### Parser Test with Fixtures

```go
func TestParseHTML(t *testing.T) {
    fixturePath := filepath.Join("testdata", "example.html")
    html, err := os.ReadFile(fixturePath)
    if err != nil {
        t.Skipf("Fixture not found: %s", fixturePath)
        return
    }

    doc, err := goquery.NewDocumentFromReader(bytes.NewReader(html))
    if err != nil {
        t.Fatalf("failed to parse HTML: %v", err)
    }

    // Test parsing logic
    result := parseDocument(doc)
    if result.Name == "" {
        t.Error("failed to extract name")
    }
}
```

### Integration Test Template

```go
//go:build integration
// +build integration

package mypackage_test

func TestIntegrationRealAPI(t *testing.T) {
    if testing.Short() {
        t.Skip("skipping integration test in short mode")
    }

    // Test against real API
    result, err := FetchFromAPI()
    if err != nil {
        t.Fatalf("API call failed: %v", err)
    }
    
    // Validate result
}
```

## Continuous Integration

### GitHub Actions (Future)

```yaml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-go@v4
        with:
          go-version: '1.23'
      - run: go test ./...

  integration-tests:
    runs-on: ubuntu-latest
    # Only on main branch
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-go@v4
      - run: go test -tags=integration ./...
```

## Debugging Failed Tests

### Verbose Output

```bash
go test -v ./games/magic/dataset/scryfall/...
```

### Run Single Test

```bash
go test ./games/magic/game/ -run TestCollectionCanonicalize
```

### Enable Debug Logging

```go
log := logger.NewLogger(ctx)
log.SetLevel("DEBUG")  // Change from ERROR/INFO
```

### Save Test Output

```bash
go test -v ./... 2>&1 | tee test_output.log
```

## Best Practices

### ✅ Do

- Write unit tests first with fixtures
- Test edge cases and error conditions
- Use table-driven tests for multiple scenarios
- Refresh fixtures regularly
- Keep integration tests behind build tags
- Clean up temporary resources (use `t.TempDir()`)

### ❌ Don't

- Make network calls in unit tests
- Hard-code test data in tests (use fixtures)
- Test implementation details (test behavior)
- Commit large fixture files (keep them minimal)
- Leave broken tests in the codebase

## Troubleshooting

### Test Hangs

**Cause**: Integration test making slow HTTP requests

**Solution**: 
```bash
# Kill the test
Ctrl+C

# Run without integration tests
go test ./... -short
```

### Fixture Not Found

**Cause**: Fixtures haven't been created yet

**Solution**:
```bash
go run ./cmd/testdata refresh
```

### Test Fails After Website Change

**Cause**: Website HTML structure changed

**Solution**:
1. Refresh fixtures: `go run ./cmd/testdata refresh --dataset=mtgtop8`
2. Update parser if structure changed significantly
3. Update expected test values

### Race Conditions

**Cause**: Concurrent access to shared resources

**Solution**:
```bash
# Run with race detector
go test -race ./...
```

## Performance Benchmarks

```bash
# Run benchmarks
go test -bench=. ./...

# With memory profiling
go test -bench=. -benchmem ./...

# CPU profiling
go test -cpuprofile=cpu.prof -bench=.
go tool pprof cpu.prof
```

## Summary

- **Default**: Fast unit tests (~1-2s)
- **Integration**: Add `-tags=integration` flag (~5-10min)
- **Fixtures**: Refresh with `go run ./cmd/testdata refresh`
- **Debug**: Use `-v` flag and adjust log levels

The goal is **fast feedback** during development with **confidence** from integration tests before release.
