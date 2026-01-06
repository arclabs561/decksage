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

// ExtractionMonitor tracks extraction health and freshness
type ExtractionMonitor struct {
	blob      *blob.Bucket
	log       *logger.Logger
	prefix    string
	mu        sync.RWMutex
	lastCheck time.Time
}

// NewExtractionMonitor creates a new extraction monitor
func NewExtractionMonitor(log *logger.Logger, blob *blob.Bucket, prefix string) *ExtractionMonitor {
	return &ExtractionMonitor{
		blob:   blob,
		log:    log,
		prefix: prefix,
	}
}

// HealthCheck performs a health check on a dataset
type HealthCheck struct {
	DatasetName      string            `json:"dataset_name"`
	LastExtraction   time.Time         `json:"last_extraction"`
	TotalItems       int               `json:"total_items"`
	ItemsLast24h     int               `json:"items_last_24h"`
	ItemsLast7d      int               `json:"items_last_7d"`
	StaleItems       int               `json:"stale_items"`       // Items not updated in 30+ days
	ErrorRate        float64           `json:"error_rate"`        // Errors per 1000 items
	AvgAge           time.Duration     `json:"avg_age"`           // Average age of items
	FreshnessScore   float64           `json:"freshness_score"`   // 0-1 score (1 = all fresh)
	Status           string            `json:"status"`            // "healthy", "degraded", "stale"
	Issues           []string          `json:"issues,omitempty"`
	Metadata         map[string]string `json:"metadata,omitempty"`
}

// CheckHealth performs a health check on a dataset
func (em *ExtractionMonitor) CheckHealth(
	ctx context.Context,
	dataset Dataset,
	maxStaleAge time.Duration,
) (*HealthCheck, error) {
	desc := dataset.Description()
	prefix := filepath.Join(desc.Game, desc.Name, "collections")

	now := time.Now()
	cutoff24h := now.Add(-24 * time.Hour)
	cutoff7d := now.Add(-7 * 24 * time.Hour)
	cutoffStale := now.Add(-maxStaleAge)

	var totalItems, items24h, items7d, staleItems int
	var totalAge time.Duration
	var errors int

	it := em.blob.List(ctx, &blob.OptListPrefix{Prefix: prefix})
	for it.Next(ctx) {
		key := it.Key()
		data, err := em.blob.Read(ctx, key)
		if err != nil {
			errors++
			continue
		}

		var col Collection
		if err := json.Unmarshal(data, &col); err != nil {
			errors++
			continue
		}

		totalItems++

		// Check freshness
		checkTime := col.UpdatedAt
		if checkTime.IsZero() {
			checkTime = col.ScrapedAt
		}
		if checkTime.IsZero() {
			checkTime = col.ReleaseDate
		}

		if !checkTime.IsZero() {
			age := now.Sub(checkTime)
			totalAge += age

			if checkTime.After(cutoff24h) {
				items24h++
			}
			if checkTime.After(cutoff7d) {
				items7d++
			}
			if checkTime.Before(cutoffStale) {
				staleItems++
			}
		}
	}

	if err := it.Err(); err != nil {
		return nil, fmt.Errorf("failed to iterate items: %w", err)
	}

	// Calculate metrics
	var avgAge time.Duration
	if totalItems > 0 {
		avgAge = totalAge / time.Duration(totalItems)
	}

	errorRate := float64(errors) / float64(totalItems) * 1000
	if totalItems == 0 {
		errorRate = 0
	}

	freshnessScore := 1.0
	if totalItems > 0 {
		freshnessScore = float64(items24h) / float64(totalItems)
	}

	// Determine status
	status := "healthy"
	var issues []string

	if totalItems == 0 {
		status = "stale"
		issues = append(issues, "no items extracted")
	} else if items24h == 0 {
		status = "stale"
		issues = append(issues, "no items updated in last 24 hours")
	} else if freshnessScore < 0.1 {
		status = "stale"
		issues = append(issues, fmt.Sprintf("only %.1f%% items fresh", freshnessScore*100))
	} else if freshnessScore < 0.5 {
		status = "degraded"
		issues = append(issues, fmt.Sprintf("only %.1f%% items fresh", freshnessScore*100))
	}

	if errorRate > 50 {
		status = "degraded"
		issues = append(issues, fmt.Sprintf("high error rate: %.1f per 1000", errorRate))
	}

	if staleItems > totalItems/2 {
		status = "stale"
		issues = append(issues, fmt.Sprintf("%d%% items are stale", staleItems*100/totalItems))
	}

	em.mu.Lock()
	em.lastCheck = now
	em.mu.Unlock()

	return &HealthCheck{
		DatasetName:    desc.Name,
		LastExtraction: now,
		TotalItems:     totalItems,
		ItemsLast24h:   items24h,
		ItemsLast7d:    items7d,
		StaleItems:     staleItems,
		ErrorRate:      errorRate,
		AvgAge:         avgAge,
		FreshnessScore: freshnessScore,
		Status:         status,
		Issues:         issues,
	}, nil
}

// SaveHealthCheck saves a health check result
func (em *ExtractionMonitor) SaveHealthCheck(ctx context.Context, check *HealthCheck) error {
	key := filepath.Join(em.prefix, fmt.Sprintf(".health_%s.json", check.DatasetName))
	data, err := json.Marshal(check)
	if err != nil {
		return fmt.Errorf("failed to marshal health check: %w", err)
	}
	return em.blob.Write(ctx, key, data)
}

// LoadHealthCheck loads the most recent health check
func (em *ExtractionMonitor) LoadHealthCheck(ctx context.Context, datasetName string) (*HealthCheck, error) {
	key := filepath.Join(em.prefix, fmt.Sprintf(".health_%s.json", datasetName))
	data, err := em.blob.Read(ctx, key)
	if err != nil {
		return nil, err
	}
	var check HealthCheck
	if err := json.Unmarshal(data, &check); err != nil {
		return nil, fmt.Errorf("failed to unmarshal health check: %w", err)
	}
	return &check, nil
}

