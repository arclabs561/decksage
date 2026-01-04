package games

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"collections/blob"
	"collections/logger"
)

// IncrementalTracker tracks what has already been extracted to enable incremental updates
type IncrementalTracker struct {
	blob    *blob.Bucket
	log     *logger.Logger
	seen    map[string]time.Time // URL -> last extracted time
	prefix  string
}

// NewIncrementalTracker creates a new incremental tracker
func NewIncrementalTracker(log *logger.Logger, blob *blob.Bucket, prefix string) *IncrementalTracker {
	return &IncrementalTracker{
		blob:   blob,
		log:    log,
		seen:   make(map[string]time.Time),
		prefix: prefix,
	}
}

// Load loads the tracking data from blob storage
func (it *IncrementalTracker) Load(ctx context.Context) error {
	key := it.trackingKey()
	exists, err := it.blob.Exists(ctx, key)
	if err != nil {
		return fmt.Errorf("failed to check tracking data: %w", err)
	}
	if !exists {
		it.log.Debugf(ctx, "No existing tracking data found, starting fresh")
		return nil
	}

	data, err := it.blob.Read(ctx, key)
	if err != nil {
		return fmt.Errorf("failed to read tracking data: %w", err)
	}

	var trackingData struct {
		Seen map[string]string `json:"seen"` // URL -> ISO timestamp
	}
	if err := json.Unmarshal(data, &trackingData); err != nil {
		return fmt.Errorf("failed to parse tracking data: %w", err)
	}

	// Parse timestamps
	for url, tsStr := range trackingData.Seen {
		if ts, err := time.Parse(time.RFC3339, tsStr); err == nil {
			it.seen[url] = ts
		}
	}

	it.log.Infof(ctx, "Loaded tracking data: %d URLs already seen", len(it.seen))
	return nil
}

// Save saves the tracking data to blob storage
func (it *IncrementalTracker) Save(ctx context.Context) error {
	trackingData := struct {
		Seen map[string]string `json:"seen"`
	}{
		Seen: make(map[string]string),
	}

	// Convert timestamps to ISO strings
	for url, ts := range it.seen {
		trackingData.Seen[url] = ts.Format(time.RFC3339)
	}

	data, err := json.Marshal(trackingData)
	if err != nil {
		return fmt.Errorf("failed to marshal tracking data: %w", err)
	}

	key := it.trackingKey()
	if err := it.blob.Write(ctx, key, data); err != nil {
		return fmt.Errorf("failed to write tracking data: %w", err)
	}

	return nil
}

// ShouldExtract checks if a URL should be extracted (not seen or seen too long ago)
func (it *IncrementalTracker) ShouldExtract(url string, maxAge time.Duration) bool {
	lastSeen, exists := it.seen[url]
	if !exists {
		return true // Never seen, should extract
	}

	if maxAge > 0 && time.Since(lastSeen) > maxAge {
		return true // Too old, should re-extract
	}

	return false // Recently seen, skip
}

// MarkExtracted marks a URL as extracted
func (it *IncrementalTracker) MarkExtracted(url string) {
	it.seen[url] = time.Now()
}

// GetStats returns statistics about tracked URLs
func (it *IncrementalTracker) GetStats() (total, recent int) {
	total = len(it.seen)
	cutoff := time.Now().Add(-24 * time.Hour) // Last 24 hours
	for _, ts := range it.seen {
		if ts.After(cutoff) {
			recent++
		}
	}
	return total, recent
}

func (it *IncrementalTracker) trackingKey() string {
	return fmt.Sprintf("%s/.incremental_tracker.json", it.prefix)
}
