package scraper

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"collections/blob"
	"collections/logger"
)

func TestScraper_CacheHit(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer b.Close(ctx)

	scraper := NewScraper(log, b)

	// Create test server
	requestCount := 0
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++
		w.Header().Set("Content-Type", "text/html")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("<html><body>Test Page</body></html>"))
	}))
	defer ts.Close()

	// First request - should hit server
	req1, _ := http.NewRequest("GET", ts.URL, nil)
	page1, err := scraper.Do(ctx, req1)
	if err != nil {
		t.Fatalf("first request failed: %v", err)
	}
	if page1 == nil {
		t.Fatal("expected page, got nil")
	}
	if requestCount != 1 {
		t.Errorf("expected 1 request to server, got %d", requestCount)
	}

	// Second request - should hit cache
	req2, _ := http.NewRequest("GET", ts.URL, nil)
	page2, err := scraper.Do(ctx, req2)
	if err != nil {
		t.Fatalf("second request failed: %v", err)
	}
	if page2 == nil {
		t.Fatal("expected page, got nil")
	}
	if requestCount != 1 {
		t.Errorf("expected cache hit (1 total request), got %d requests", requestCount)
	}

	// Verify cached content matches
	if string(page1.Response.Body) != string(page2.Response.Body) {
		t.Error("cached content doesn't match original")
	}
}

func TestScraper_ReplaceOption(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer b.Close(ctx)

	scraper := NewScraper(log, b)

	// Create test server with version counter
	version := 1
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("<html><body>Version " + string(rune('0'+version)) + "</body></html>"))
		version++
	}))
	defer ts.Close()

	// First request - cache version 1
	req1, _ := http.NewRequest("GET", ts.URL, nil)
	page1, err := scraper.Do(ctx, req1)
	if err != nil {
		t.Fatalf("first request failed: %v", err)
	}
	if !contains(string(page1.Response.Body), "Version 1") {
		t.Error("expected version 1")
	}

	// Second request with replace - should get version 2
	req2, _ := http.NewRequest("GET", ts.URL, nil)
	page2, err := scraper.Do(ctx, req2, &OptDoReplace{})
	if err != nil {
		t.Fatalf("second request failed: %v", err)
	}
	if !contains(string(page2.Response.Body), "Version 2") {
		t.Error("expected version 2 after replace")
	}
}

func TestScraper_ErrorHandling(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer b.Close(ctx)

	scraper := NewScraper(log, b)

	// Test 404 error
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte("Not Found"))
	}))
	defer ts.Close()

	req, _ := http.NewRequest("GET", ts.URL, nil)
	_, err = scraper.Do(ctx, req)
	if err == nil {
		t.Error("expected error for 404 response")
	}

	// Verify error is ErrStatusNotOK
	if !contains(err.Error(), "status") {
		t.Errorf("expected status error, got: %v", err)
	}
}

func TestScraper_Retry(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping retry test in short mode")
	}

	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer b.Close(ctx)

	scraper := NewScraper(log, b)

	// Server that fails first 2 times, then succeeds
	attempts := 0
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		if attempts < 3 {
			// Close connection without response
			hj, ok := w.(http.Hijacker)
			if !ok {
				t.Fatal("server doesn't support hijacking")
			}
			conn, _, err := hj.Hijack()
			if err != nil {
				t.Fatal(err)
			}
			conn.Close()
			return
		}
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("Success"))
	}))
	defer ts.Close()

	req, _ := http.NewRequest("GET", ts.URL, nil)
	page, err := scraper.Do(ctx, req)
	if err != nil {
		t.Fatalf("request failed after retries: %v", err)
	}
	if !contains(string(page.Response.Body), "Success") {
		t.Error("expected success after retries")
	}
	if attempts < 3 {
		t.Errorf("expected at least 3 attempts, got %d", attempts)
	}
}

func TestScraper_StatusCodes(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer b.Close(ctx)

	scraper := NewScraper(log, b)

	tests := []struct {
		name       string
		statusCode int
		wantErr    bool
	}{
		{"200 OK", http.StatusOK, false},
		{"404 Not Found", http.StatusNotFound, true},
		{"500 Internal Server Error", http.StatusInternalServerError, true},
		{"403 Forbidden", http.StatusForbidden, true},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tt.statusCode)
				w.Write([]byte("Test"))
			}))
			defer ts.Close()

			req, _ := http.NewRequest("GET", ts.URL, nil)
			_, err := scraper.Do(ctx, req)

			if tt.wantErr && err == nil {
				t.Errorf("expected error for status %d", tt.statusCode)
			}
			if !tt.wantErr && err != nil {
				t.Errorf("unexpected error for status %d: %v", tt.statusCode, err)
			}
		})
	}
}

func TestScraper_RedirectTracking(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer b.Close(ctx)

	scraper := NewScraper(log, b)

	// Create server with redirect
	final := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("Final destination"))
	}))
	defer final.Close()

	redirect := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, final.URL, http.StatusFound)
	}))
	defer redirect.Close()

	req, _ := http.NewRequest("GET", redirect.URL, nil)
	page, err := scraper.Do(ctx, req)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}

	// Check that redirect was tracked
	if page.Request.RedirectedURL == "" {
		t.Error("expected redirect URL to be tracked")
	}
	if page.Request.RedirectedURL != final.URL {
		t.Errorf("expected redirect to %s, got %s", final.URL, page.Request.RedirectedURL)
	}
}

func TestScraper_Timestamp(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer b.Close(ctx)

	scraper := NewScraper(log, b)

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("Test"))
	}))
	defer ts.Close()

	before := time.Now()
	req, _ := http.NewRequest("GET", ts.URL, nil)
	page, err := scraper.Do(ctx, req)
	after := time.Now()

	if err != nil {
		t.Fatalf("request failed: %v", err)
	}

	if page.ScrapedAt.Before(before) || page.ScrapedAt.After(after) {
		t.Errorf("ScrapedAt timestamp %v not within expected range [%v, %v]",
			page.ScrapedAt, before, after)
	}
}

func TestScraper_Timeout(t *testing.T) {
	// Deterministic timeout using request context cancellation rather than long sleeps.
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer b.Close(ctx)

	scraper := NewScraper(log, b)

	// Server that sleeps longer than our request context deadline (2s sleep).
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(2 * time.Second)
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("Too late"))
	}))
	defer ts.Close()

	// Use a short context deadline to enforce a fast, deterministic timeout.
	reqCtx, cancel := context.WithTimeout(ctx, 200*time.Millisecond)
	defer cancel()

	start := time.Now()
	req, _ := http.NewRequestWithContext(reqCtx, "GET", ts.URL, nil)
	_, err = scraper.Do(ctx, req)
	elapsed := time.Since(start)

	if err == nil {
		t.Error("expected timeout/cancellation error, got nil")
	}

	// Should fail quickly (well under 1s), not wait for server sleep.
	if elapsed > 1*time.Second {
		t.Errorf("deadline exceeded too slowly: %v (expected <1s)", elapsed)
	}

	if !contains(err.Error(), "timeout") && !contains(err.Error(), "deadline") && !contains(err.Error(), "context") {
		t.Logf("Warning: error message doesn't mention timeout: %v", err)
	}
}

func TestScraper_CardCountValidation(t *testing.T) {
	// This tests that the scraper itself works correctly
	// Actual validation happens in dataset-specific parsers
	// This test just ensures the scraper doesn't interfere with validation

	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("ERROR")

	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	b, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer b.Close(ctx)

	scraper := NewScraper(log, b)

	// Server returns malformed data
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("<html><body>0 Invalid Card</body></html>"))
	}))
	defer ts.Close()

	req, _ := http.NewRequest("GET", ts.URL, nil)
	page, err := scraper.Do(ctx, req)

	// Scraper should succeed - validation happens at parse layer
	if err != nil {
		t.Fatalf("scraper should not fail on malformed data: %v", err)
	}
	if page == nil {
		t.Fatal("expected page, got nil")
	}
	if page.Response.StatusCode != 200 {
		t.Errorf("expected status 200, got %d", page.Response.StatusCode)
	}
}

// Helper functions
// contains is a simple wrapper to avoid importing strings in older tests.
func contains(s, substr string) bool {
	// minimal safe implementation
	if len(substr) == 0 {
		return true
	}
	if len(substr) > len(s) {
		return false
	}
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
