package games

import (
	"context"
	"encoding/json"
	"fmt"
	"path/filepath"
	"sync"
	"time"

	"collections/blob"
	"collections/logger"
)

// ExportTracker tracks what has been exported to enable incremental exports
type ExportTracker struct {
	blob     *blob.Bucket
	log      *logger.Logger
	prefix   string
	exported map[string]time.Time // blob key -> last export time
	mu       sync.RWMutex          // Protects exported map for concurrent access
}

// NewExportTracker creates a new export tracker
func NewExportTracker(log *logger.Logger, blob *blob.Bucket, prefix string) *ExportTracker {
	return &ExportTracker{
		blob:     blob,
		log:      log,
		prefix:   prefix,
		exported: make(map[string]time.Time),
	}
}

// Load loads the tracking data from blob storage
func (et *ExportTracker) Load(ctx context.Context) error {
	key := et.trackingKey()
	exists, err := et.blob.Exists(ctx, key)
	if err != nil {
		return fmt.Errorf("failed to check tracking data: %w", err)
	}
	if !exists {
		et.log.Debugf(ctx, "No existing export tracking data found, starting fresh")
		return nil
	}

	data, err := et.blob.Read(ctx, key)
	if err != nil {
		return fmt.Errorf("failed to read tracking data: %w", err)
	}

	var trackingData struct {
		Exported map[string]string `json:"exported"` // blob key -> ISO timestamp
	}
	if err := json.Unmarshal(data, &trackingData); err != nil {
		return fmt.Errorf("failed to parse tracking data: %w", err)
	}

	// Parse timestamps
	exported := make(map[string]time.Time, len(trackingData.Exported))
	for blobKey, tsStr := range trackingData.Exported {
		if ts, err := time.Parse(time.RFC3339, tsStr); err == nil {
			exported[blobKey] = ts
		}
	}

	et.mu.Lock()
	et.exported = exported
	et.mu.Unlock()

	et.log.Infof(ctx, "Loaded export tracking data: %d items already exported", len(exported))
	return nil
}

// Save saves the tracking data to blob storage
func (et *ExportTracker) Save(ctx context.Context) error {
	et.mu.RLock()
	exported := make(map[string]time.Time, len(et.exported))
	for k, v := range et.exported {
		exported[k] = v
	}
	et.mu.RUnlock()

	trackingData := struct {
		Exported map[string]string `json:"exported"`
	}{
		Exported: make(map[string]string, len(exported)),
	}

	// Convert timestamps to ISO strings
	for blobKey, ts := range exported {
		trackingData.Exported[blobKey] = ts.Format(time.RFC3339)
	}

	data, err := json.Marshal(trackingData)
	if err != nil {
		return fmt.Errorf("failed to marshal tracking data: %w", err)
	}

	key := et.trackingKey()
	if err := et.blob.Write(ctx, key, data); err != nil {
		return fmt.Errorf("failed to write tracking data: %w", err)
	}

	return nil
}

// ShouldExport checks if a blob should be exported (not exported or modified since last export)
// Uses Collection metadata (UpdatedAt/Version) if available, falls back to file mtime
// Thread-safe: uses read lock for concurrent access
func (et *ExportTracker) ShouldExport(ctx context.Context, blobKey string, blobModifiedTime time.Time, collectionUpdatedAt time.Time, collectionVersion int) bool {
	et.mu.RLock()
	lastExported, exists := et.exported[blobKey]
	et.mu.RUnlock()
	
	if !exists {
		return true // Never exported
	}

	// Prefer Collection metadata over file mtime (more reliable for cloud storage)
	if !collectionUpdatedAt.IsZero() {
		return collectionUpdatedAt.After(lastExported)
	}

	// Fallback to file modification time
	return blobModifiedTime.After(lastExported)
}

// MarkExported marks a blob as exported
// Thread-safe: uses write lock for concurrent access
func (et *ExportTracker) MarkExported(blobKey string) {
	et.mu.Lock()
	et.exported[blobKey] = time.Now()
	et.mu.Unlock()
}

// GetStats returns statistics about exported items
// Thread-safe: uses read lock for concurrent access
func (et *ExportTracker) GetStats() (total, recent int) {
	et.mu.RLock()
	exported := make(map[string]time.Time, len(et.exported))
	for k, v := range et.exported {
		exported[k] = v
	}
	et.mu.RUnlock()

	total = len(exported)
	cutoff := time.Now().Add(-24 * time.Hour)
	for _, ts := range exported {
		if ts.After(cutoff) {
			recent++
		}
	}
	return total, recent
}

func (et *ExportTracker) trackingKey() string {
	return filepath.Join(et.prefix, ".export_tracker.json")
}

