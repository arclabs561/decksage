package scraper

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/playwright-community/playwright-go"
	"go.uber.org/ratelimit"
	"collections/logger"
)

// BrowserScraper handles JavaScript-rendered pages using Playwright
type BrowserScraper struct {
	log      *logger.Logger
	pw       *playwright.Playwright
	browser  playwright.Browser
	pagePool chan playwright.Page
	limiter  ratelimit.Limiter
	mu       sync.Mutex
	closed   bool
}

// BrowserScraperOptions configures browser scraper behavior
type BrowserScraperOptions struct {
	PagePoolSize int           // Number of pages to pool (default: 3)
	RateLimit    int           // Requests per minute (default: 30)
	Headless     bool           // Run in headless mode (default: true)
	Timeout      time.Duration // Default timeout (default: 30s)
}

// DefaultBrowserScraperOptions returns sensible defaults
func DefaultBrowserScraperOptions() BrowserScraperOptions {
	return BrowserScraperOptions{
		PagePoolSize: 3,
		RateLimit:    30, // 30 requests per minute
		Headless:     true,
		Timeout:      30 * time.Second,
	}
}

// NewBrowserScraper creates a new browser scraper for JS-rendered content
func NewBrowserScraper(log *logger.Logger) (*BrowserScraper, error) {
	return NewBrowserScraperWithOptions(log, DefaultBrowserScraperOptions())
}

// InstallPlaywrightDrivers installs Playwright browsers if needed
func InstallPlaywrightDrivers(log *logger.Logger) error {
	log.Infof(context.Background(), "Installing Playwright drivers (this may take a minute, ~50MB download)...")
	if err := playwright.Install(); err != nil {
		return fmt.Errorf("failed to install Playwright drivers: %w", err)
	}
	log.Infof(context.Background(), "✅ Playwright drivers installed successfully")
	return nil
}

// NewBrowserScraperWithOptions creates a browser scraper with custom options
func NewBrowserScraperWithOptions(log *logger.Logger, opts BrowserScraperOptions) (*BrowserScraper, error) {
	pw, err := playwright.Run()
	if err != nil {
		// Try to install drivers if they're missing
		if strings.Contains(err.Error(), "please install") || strings.Contains(err.Error(), "driver") {
			log.Infof(context.Background(), "Playwright drivers not found, installing...")
			if installErr := InstallPlaywrightDrivers(log); installErr != nil {
				return nil, fmt.Errorf("failed to install Playwright drivers: %w (original error: %v)", installErr, err)
			}
			// Retry after installation
			pw, err = playwright.Run()
			if err != nil {
				return nil, fmt.Errorf("failed to start Playwright after driver installation: %w", err)
			}
		} else {
			return nil, fmt.Errorf("failed to start Playwright: %w", err)
		}
	}

	browser, err := pw.Chromium.Launch(playwright.BrowserTypeLaunchOptions{
		Headless: playwright.Bool(opts.Headless),
	})
	if err != nil {
		pw.Stop()
		return nil, fmt.Errorf("failed to launch browser: %w", err)
	}

	// Create page pool
	pagePoolSize := opts.PagePoolSize
	if pagePoolSize < 1 {
		pagePoolSize = 3
	}
	pagePool := make(chan playwright.Page, pagePoolSize)
	for i := 0; i < pagePoolSize; i++ {
		page, err := browser.NewPage()
		if err != nil {
			// Close already created pages
			close(pagePool)
			for p := range pagePool {
				p.Close()
			}
			browser.Close()
			pw.Stop()
			return nil, fmt.Errorf("failed to create page %d: %w", i, err)
		}
		pagePool <- page
	}

	// Create rate limiter
	rateLimit := opts.RateLimit
	if rateLimit < 1 {
		rateLimit = 30
	}
	limiter := ratelimit.New(rateLimit, ratelimit.Per(time.Minute))

	return &BrowserScraper{
		log:      log,
		pw:       pw,
		browser:  browser,
		pagePool: pagePool,
		limiter:  limiter,
	}, nil
}

// Close shuts down the browser and Playwright
func (bs *BrowserScraper) Close() error {
	bs.mu.Lock()
	if bs.closed {
		bs.mu.Unlock()
		return nil
	}
	bs.closed = true
	bs.mu.Unlock()

	// Close all pages in pool
	close(bs.pagePool)
	for page := range bs.pagePool {
		if err := page.Close(); err != nil {
			bs.log.Warnf(context.Background(), "Failed to close page: %v", err)
		}
	}

	var errs []error
	if bs.browser != nil {
		if err := bs.browser.Close(); err != nil {
			errs = append(errs, fmt.Errorf("failed to close browser: %w", err))
		}
	}

	if bs.pw != nil {
		bs.pw.Stop()
	}

	if len(errs) > 0 {
		return fmt.Errorf("errors during close: %v", errs)
	}

	return nil
}

// RenderPage renders a JavaScript page and returns the HTML
// waitFor can be a selector, text, or "networkidle" to wait for network to be idle
func (bs *BrowserScraper) RenderPage(ctx context.Context, url string, waitFor string, timeout time.Duration) ([]byte, error) {
	bs.mu.Lock()
	if bs.closed {
		bs.mu.Unlock()
		return nil, fmt.Errorf("browser scraper is closed")
	}
	bs.mu.Unlock()

	// Rate limit
	bs.limiter.Take()

	// Check context cancellation
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}

	// Get a page from pool (or create new one if pool is empty)
	var page playwright.Page
	select {
	case page = <-bs.pagePool:
		// Got page from pool
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
		// Pool empty, create new page
		var err error
		page, err = bs.browser.NewPage()
		if err != nil {
			return nil, fmt.Errorf("failed to create page: %w", err)
		}
		defer func() {
			if err := page.Close(); err != nil {
				bs.log.Warnf(ctx, "Failed to close temporary page: %v", err)
			}
		}()
	}

	// Return page to pool when done (unless it was a temporary page)
	returnToPool := true
	defer func() {
		if returnToPool {
			select {
			case bs.pagePool <- page:
				// Returned to pool
			default:
				// Pool full, close page
				if err := page.Close(); err != nil {
					bs.log.Warnf(ctx, "Failed to close page when pool full: %v", err)
				}
			}
		}
	}()

	// Set timeout
	if timeout == 0 {
		timeout = 30 * time.Second
	}
	page.SetDefaultTimeout(float64(timeout.Milliseconds()))

	// Navigate to URL with retry
	var err error
	maxRetries := 3
	for attempt := 0; attempt < maxRetries; attempt++ {
		if attempt > 0 {
			// Wait before retry
			waitTime := time.Duration(attempt) * time.Second
			bs.log.Debugf(ctx, "Retrying navigation to %s (attempt %d/%d) after %v", url, attempt+1, maxRetries, waitTime)
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(waitTime):
			}
		}

		_, err = page.Goto(url, playwright.PageGotoOptions{
			WaitUntil: playwright.WaitUntilStateNetworkidle,
			Timeout:   playwright.Float(timeout.Seconds() * 1000),
		})
		if err == nil {
			break
		}

		bs.log.Warnf(ctx, "Navigation attempt %d/%d failed for %s: %v", attempt+1, maxRetries, url, err)
	}

	// Even if navigation failed, try to get content (might have partial page)
	if err != nil && !strings.Contains(err.Error(), "timeout") {
		return nil, fmt.Errorf("failed to navigate to %s after %d attempts: %w", url, maxRetries, err)
	}
	// If timeout, log but continue - might have partial content
	if err != nil {
		bs.log.Debugf(ctx, "Navigation had timeout issues for %s, but attempting to get content: %v", url, err)
	}

	// Wait for specific element if provided
	// If waitFor is "body", just wait a bit for page to settle
	if waitFor != "" && waitFor != "networkidle" {
		if waitFor == "body" {
			// Just wait a short time for page to settle after network idle
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(2 * time.Second):
			}
		} else {
			waitTimeout := timeout
			if waitTimeout > 10*time.Second {
				waitTimeout = 10 * time.Second // Cap wait time for selector
			}
			if _, err := page.WaitForSelector(waitFor, playwright.PageWaitForSelectorOptions{
				Timeout: playwright.Float(waitTimeout.Seconds() * 1000),
			}); err != nil {
				// Log warning but continue - element might not exist or page might be valid without it
				bs.log.Debugf(ctx, "WaitFor selector %q not found (continuing anyway): %v", waitFor, err)
			}
		}
	}

	// Get rendered HTML
	content, err := page.Content()
	if err != nil {
		// If we had navigation errors but got this far, log and return error
		return nil, fmt.Errorf("failed to get page content: %w", err)
	}

	// If content is very short, might be an error page
	if len(content) < 100 {
		bs.log.Warnf(ctx, "Page content is very short (%d bytes) for %s, might be incomplete", len(content), url)
	}

	return []byte(content), nil
}
