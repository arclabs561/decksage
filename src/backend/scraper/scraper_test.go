package scraper

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"collections/blob"
	"collections/logger"
)

func TestResponseSizeLimit(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic")
	
	// Create test blob storage
	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	blob, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer blob.Close(ctx)
	
	// Create a test server that returns large response
	largeBody := make([]byte, 11*1024*1024) // 11MB, exceeds 10MB limit
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write(largeBody)
	}))
	defer server.Close()
	
	sc := NewScraper(log, blob)
	
	req, err := http.NewRequest("GET", server.URL, nil)
	if err != nil {
		t.Fatalf("failed to create request: %v", err)
	}
	
	_, err = sc.Do(ctx, req)
	if err == nil {
		t.Error("Expected error for response exceeding size limit, got nil")
	}
	if err != nil && err.Error() == "" {
		t.Error("Error message should not be empty")
	}
}

func TestResponseSizeWithinLimit(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic")
	
	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	blob, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer blob.Close(ctx)
	
	// Create a test server that returns small response
	smallBody := []byte("test response")
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write(smallBody)
	}))
	defer server.Close()
	
	sc := NewScraper(log, blob)
	
	req, err := http.NewRequest("GET", server.URL, nil)
	if err != nil {
		t.Fatalf("failed to create request: %v", err)
	}
	
	page, err := sc.Do(ctx, req)
	if err != nil {
		t.Fatalf("Unexpected error for response within size limit: %v", err)
	}
	if page == nil {
		t.Fatal("Expected page, got nil")
	}
	if len(page.Response.Body) != len(smallBody) {
		t.Errorf("Response body length = %d, want %d", len(page.Response.Body), len(smallBody))
	}
}

func TestCaching(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("panic")
	
	tmpDir := t.TempDir()
	bucketURL := "file://" + tmpDir
	blob, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		t.Fatalf("failed to create blob: %v", err)
	}
	defer blob.Close(ctx)
	
	requestCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("cached response"))
	}))
	defer server.Close()
	
	sc := NewScraper(log, blob)
	
	req, err := http.NewRequest("GET", server.URL, nil)
	if err != nil {
		t.Fatalf("failed to create request: %v", err)
	}
	
	// First request should hit server
	page1, err := sc.Do(ctx, req)
	if err != nil {
		t.Fatalf("First request failed: %v", err)
	}
	if requestCount != 1 {
		t.Errorf("First request: requestCount = %d, want 1", requestCount)
	}
	
	// Second request should use cache
	req2, err := http.NewRequest("GET", server.URL, nil)
	if err != nil {
		t.Fatalf("failed to create second request: %v", err)
	}
	page2, err := sc.Do(ctx, req2)
	if err != nil {
		t.Fatalf("Second request failed: %v", err)
	}
	if requestCount != 1 {
		t.Errorf("Second request should use cache: requestCount = %d, want 1", requestCount)
	}
	if string(page1.Response.Body) != string(page2.Response.Body) {
		t.Error("Cached response should match original")
	}
}

