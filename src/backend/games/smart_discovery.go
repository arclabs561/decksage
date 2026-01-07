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

// DiscoveryState tracks the state of discovery for a dataset
type DiscoveryState struct {
	LastPageSeen    int       `json:"last_page_seen"`     // Last page number we've seen
	LastItemSeen    string    `json:"last_item_seen"`    // Last item URL we've seen
	LastItemDate    time.Time `json:"last_item_date"`    // Date of last item seen
	LastDiscovery   time.Time `json:"last_discovery"`    // When we last ran discovery
	ItemsSinceStart int       `json:"items_since_start"` // Items found since last start page
}

// SmartDiscoveryTracker enables smarter discovery by tracking where we left off
type SmartDiscoveryTracker struct {
	blob   *blob.Bucket
	log    *logger.Logger
	prefix string
	state  map[string]*DiscoveryState // dataset name -> state
	mu     sync.RWMutex                // Protects state map for concurrent access
}

// NewSmartDiscoveryTracker creates a new smart discovery tracker
func NewSmartDiscoveryTracker(log *logger.Logger, blob *blob.Bucket, prefix string) *SmartDiscoveryTracker {
	return &SmartDiscoveryTracker{
		blob:   blob,
		log:    log,
		prefix: prefix,
		state:  make(map[string]*DiscoveryState),
	}
}

// Load loads discovery state from blob storage
func (sdt *SmartDiscoveryTracker) Load(ctx context.Context, datasetName string) (*DiscoveryState, error) {
	key := sdt.stateKey(datasetName)
	exists, err := sdt.blob.Exists(ctx, key)
	if err != nil {
		return nil, fmt.Errorf("failed to check discovery state: %w", err)
	}
	if !exists {
		sdt.log.Debugf(ctx, "No existing discovery state for %s, starting fresh", datasetName)
		return &DiscoveryState{
			LastPageSeen: 1,
			LastDiscovery: time.Now(),
		}, nil
	}

	data, err := sdt.blob.Read(ctx, key)
	if err != nil {
		return nil, fmt.Errorf("failed to read discovery state: %w", err)
	}

	var state DiscoveryState
	if err := json.Unmarshal(data, &state); err != nil {
		return nil, fmt.Errorf("failed to parse discovery state: %w", err)
	}

	sdt.mu.Lock()
	sdt.state[datasetName] = &state
	sdt.mu.Unlock()
	
	return &state, nil
}

// Save saves discovery state to blob storage
func (sdt *SmartDiscoveryTracker) Save(ctx context.Context, datasetName string, state *DiscoveryState) error {
	data, err := json.Marshal(state)
	if err != nil {
		return fmt.Errorf("failed to marshal discovery state: %w", err)
	}

	key := sdt.stateKey(datasetName)
	if err := sdt.blob.Write(ctx, key, data); err != nil {
		return fmt.Errorf("failed to write discovery state: %w", err)
	}

	sdt.mu.Lock()
	sdt.state[datasetName] = state
	sdt.mu.Unlock()
	
	return nil
}

// UpdateLastSeen updates the last seen item/page
func (sdt *SmartDiscoveryTracker) UpdateLastSeen(ctx context.Context, datasetName string, page int, itemURL string, itemDate time.Time) error {
	state, err := sdt.Load(ctx, datasetName)
	if err != nil {
		return err
	}

	state.LastPageSeen = page
	state.LastItemSeen = itemURL
	if !itemDate.IsZero() {
		state.LastItemDate = itemDate
	}
	state.LastDiscovery = time.Now()

	return sdt.Save(ctx, datasetName, state)
}

// GetStartPage returns the page to start from for incremental discovery
// Returns 1 if we should start from beginning, or a higher page if we can resume
// Thread-safe: Load is already thread-safe
func (sdt *SmartDiscoveryTracker) GetStartPage(ctx context.Context, datasetName string, maxPagesToSkip int) int {
	state, err := sdt.Load(ctx, datasetName)
	if err != nil {
		return 1
	}

	// If last discovery was recent (within 1 hour), we can try to resume
	if time.Since(state.LastDiscovery) < time.Hour {
		// Start a few pages before last seen to catch any we might have missed
		startPage := state.LastPageSeen - maxPagesToSkip
		if startPage < 1 {
			startPage = 1
		}
		sdt.log.Infof(ctx, "Resuming discovery for %s from page %d (last seen: %d)", datasetName, startPage, state.LastPageSeen)
		return startPage
	}

	// Too much time has passed, start from beginning
	return 1
}

// ShouldStopDiscovery checks if we should stop discovery based on finding known items
// Returns true if we should stop, and updates the consecutive count
func (sdt *SmartDiscoveryTracker) ShouldStopDiscovery(ctx context.Context, datasetName string, itemURL string, currentConsecutive int, maxConsecutiveKnown int) (shouldStop bool, newConsecutive int) {
	state, err := sdt.Load(ctx, datasetName)
	if err != nil {
		return false, currentConsecutive
	}

	// If we've seen this item before, increment counter
	if itemURL == state.LastItemSeen {
		newConsecutive = currentConsecutive + 1
		if newConsecutive >= maxConsecutiveKnown {
			sdt.log.Infof(ctx, "Found %d consecutive known items, stopping discovery", newConsecutive)
			return true, newConsecutive
		}
		return false, newConsecutive
	}

	// New item, reset counter
	return false, 0
}

func (sdt *SmartDiscoveryTracker) stateKey(datasetName string) string {
	return filepath.Join(sdt.prefix, fmt.Sprintf(".discovery_%s.json", datasetName))
}

