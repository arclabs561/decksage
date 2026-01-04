package games

import (
	"context"
	"sync/atomic"
	"time"

	"collections/logger"
)

// ProgressReporter provides periodic progress updates during long extractions
type ProgressReporter struct {
	log          *logger.Logger
	interval     time.Duration
	lastReport   atomic.Int64
	total        atomic.Int64
	successful   atomic.Int64
	failed       atomic.Int64
	datasetName  string
	startTime    time.Time
}

// NewProgressReporter creates a new progress reporter
func NewProgressReporter(log *logger.Logger, datasetName string, interval time.Duration) *ProgressReporter {
	if interval == 0 {
		interval = 30 * time.Second // Default: report every 30 seconds
	}
	return &ProgressReporter{
		log:         log,
		interval:    interval,
		datasetName: datasetName,
		startTime:   time.Now(),
	}
}

// IncrementTotal increments the total count
func (pr *ProgressReporter) IncrementTotal() {
	pr.total.Add(1)
	pr.maybeReport()
}

// IncrementSuccess increments the successful count
func (pr *ProgressReporter) IncrementSuccess() {
	pr.successful.Add(1)
	pr.maybeReport()
}

// IncrementFailed increments the failed count
func (pr *ProgressReporter) IncrementFailed() {
	pr.failed.Add(1)
	pr.maybeReport()
}

// maybeReport checks if enough time has passed and reports progress
func (pr *ProgressReporter) maybeReport() {
	now := time.Now().Unix()
	lastReport := pr.lastReport.Load()

	if now-lastReport < int64(pr.interval.Seconds()) {
		return
	}

	if pr.lastReport.CompareAndSwap(lastReport, now) {
		pr.report()
	}
}

// report outputs the current progress
func (pr *ProgressReporter) report() {
	total := pr.total.Load()
	successful := pr.successful.Load()
	failed := pr.failed.Load()
	duration := time.Since(pr.startTime)

	rate := 0.0
	if duration.Seconds() > 0 {
		rate = float64(total) / duration.Minutes()
	}

	successRate := 0.0
	if total > 0 {
		successRate = float64(successful) / float64(total) * 100
	}

	pr.log.Infof(context.Background(),
		"📊 Progress [%s]: %d total (%d successful, %d failed, %.1f%% success) - %.1f/min - elapsed: %v",
		pr.datasetName, total, successful, failed, successRate, rate, duration.Round(time.Second),
	)
}

// FinalReport outputs a final summary
func (pr *ProgressReporter) FinalReport() {
	total := pr.total.Load()
	successful := pr.successful.Load()
	failed := pr.failed.Load()
	duration := time.Since(pr.startTime)

	rate := 0.0
	if duration.Seconds() > 0 {
		rate = float64(total) / duration.Minutes()
	}

	successRate := 0.0
	if total > 0 {
		successRate = float64(successful) / float64(total) * 100
	}

	pr.log.Infof(context.Background(),
		"✅ Final [%s]: %d total (%d successful, %d failed, %.1f%% success) in %v (%.1f/min)",
		pr.datasetName, total, successful, failed, successRate, duration.Round(time.Second), rate,
	)
}
