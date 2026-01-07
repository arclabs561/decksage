package games

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"path/filepath"
	"sort"
	"strings"
	"sync"

	"collections/blob"
	"collections/logger"
)

// DeckSignature represents a normalized deck signature for deduplication
type DeckSignature struct {
	CardSignature string   `json:"card_signature"` // Hash of sorted card names and counts
	Sources       []string `json:"sources"`        // All sources this deck appears in
	CanonicalID   string   `json:"canonical_id"`   // ID of the canonical version
	CanonicalURL  string   `json:"canonical_url"`  // URL of the canonical version
}

// ComputeDeckSignature computes a signature for a collection based on its cards
func ComputeDeckSignature(c *Collection) string {
	// Create a normalized representation: sorted partition names, sorted cards within each
	var parts []string
	for _, p := range c.Partitions {
		partSig := p.Name + ":"
		var cards []string
		for _, card := range p.Cards {
			cards = append(cards, fmt.Sprintf("%s:%d", card.Name, card.Count))
		}
		sort.Strings(cards)
		partSig += strings.Join(cards, ",")
		parts = append(parts, partSig)
	}
	sort.Strings(parts)

	// Hash the normalized signature
	h := sha256.New()
	h.Write([]byte(strings.Join(parts, "|")))
	return hex.EncodeToString(h.Sum(nil))
}

// DeduplicationTracker tracks deck signatures to identify duplicates across sources
type DeduplicationTracker struct {
	blob       *blob.Bucket
	log        *logger.Logger
	prefix     string
	signatures map[string]*DeckSignature // card signature -> deck signature
	mu         sync.RWMutex               // Protects signatures map for concurrent access
}

// NewDeduplicationTracker creates a new deduplication tracker
func NewDeduplicationTracker(log *logger.Logger, blob *blob.Bucket, prefix string) *DeduplicationTracker {
	return &DeduplicationTracker{
		blob:       blob,
		log:        log,
		prefix:     prefix,
		signatures: make(map[string]*DeckSignature),
	}
}

// Load loads deduplication data from blob storage
func (dt *DeduplicationTracker) Load(ctx context.Context) error {
	key := dt.trackingKey()
	exists, err := dt.blob.Exists(ctx, key)
	if err != nil {
		return fmt.Errorf("failed to check deduplication data: %w", err)
	}
	if !exists {
		dt.log.Debugf(ctx, "No existing deduplication data found, starting fresh")
		return nil
	}

	data, err := dt.blob.Read(ctx, key)
	if err != nil {
		return fmt.Errorf("failed to read deduplication data: %w", err)
	}

	var signatures map[string]*DeckSignature
	if err := json.Unmarshal(data, &signatures); err != nil {
		return fmt.Errorf("failed to parse deduplication data: %w", err)
	}

	dt.mu.Lock()
	dt.signatures = signatures
	dt.mu.Unlock()

	dt.log.Infof(ctx, "Loaded deduplication data: %d signatures", len(signatures))
	return nil
}

// Save saves deduplication data to blob storage
func (dt *DeduplicationTracker) Save(ctx context.Context) error {
	dt.mu.RLock()
	signatures := make(map[string]*DeckSignature, len(dt.signatures))
	for k, v := range dt.signatures {
		// Deep copy to avoid race conditions during save
		sigCopy := &DeckSignature{
			CardSignature: v.CardSignature,
			Sources:       make([]string, len(v.Sources)),
			CanonicalID:   v.CanonicalID,
			CanonicalURL:  v.CanonicalURL,
		}
		copy(sigCopy.Sources, v.Sources)
		signatures[k] = sigCopy
	}
	dt.mu.RUnlock()

	data, err := json.Marshal(signatures)
	if err != nil {
		return fmt.Errorf("failed to marshal deduplication data: %w", err)
	}

	key := dt.trackingKey()
	if err := dt.blob.Write(ctx, key, data); err != nil {
		return fmt.Errorf("failed to write deduplication data: %w", err)
	}

	return nil
}

// FindDuplicate checks if a collection is a duplicate and returns canonical info
// Thread-safe: uses read-write lock for concurrent access
func (dt *DeduplicationTracker) FindDuplicate(c *Collection) (isDuplicate bool, canonicalID, canonicalURL string) {
	sig := ComputeDeckSignature(c)
	
	dt.mu.RLock()
	existing, exists := dt.signatures[sig]
	dt.mu.RUnlock()
	
	if exists {
		// Check if this is a different source
		isNewSource := true
		for _, src := range existing.Sources {
			if src == c.Source {
				isNewSource = false
				break
			}
		}

		if isNewSource {
			// Add this source to the list (need write lock)
			dt.mu.Lock()
			// Re-check after acquiring lock (double-check pattern)
			existing, exists = dt.signatures[sig]
			if exists {
				// Check again if source was added by another goroutine
				isNewSource = true
				for _, src := range existing.Sources {
					if src == c.Source {
						isNewSource = false
						break
					}
				}
				if isNewSource {
					existing.Sources = append(existing.Sources, c.Source)
				}
			}
			dt.mu.Unlock()
		}

		return true, existing.CanonicalID, existing.CanonicalURL
	}

	// New deck, register it as canonical
	dt.mu.Lock()
	// Double-check: another goroutine might have added it
	if existing, exists := dt.signatures[sig]; exists {
		dt.mu.Unlock()
		return true, existing.CanonicalID, existing.CanonicalURL
	}
	dt.signatures[sig] = &DeckSignature{
		CardSignature: sig,
		Sources:       []string{c.Source},
		CanonicalID:   c.ID,
		CanonicalURL:  c.URL,
	}
	dt.mu.Unlock()

	return false, c.ID, c.URL
}

// GetCanonicalSource returns the preferred source for a deck signature
// Priority: scryfall > mtgtop8 > goldfish > deckbox > others
func (dt *DeduplicationTracker) GetCanonicalSource(sig string) string {
	sigData, exists := dt.signatures[sig]
	if !exists {
		return ""
	}

	sourcePriority := map[string]int{
		"scryfall":          10,
		"mtgtop8":           9,
		"goldfish":          8,
		"deckbox":           7,
		"ygoprodeck":        6,
		"limitless-web":     5,
		"pokemoncard-io":    4,
	}

	bestSource := ""
	bestPriority := -1

	for _, src := range sigData.Sources {
		priority := sourcePriority[src]
		if priority == 0 {
			priority = 1 // Default for unknown sources
		}
		if priority > bestPriority {
			bestPriority = priority
			bestSource = src
		}
	}

	return bestSource
}

func (dt *DeduplicationTracker) trackingKey() string {
	return filepath.Join(dt.prefix, ".deduplication.json")
}

