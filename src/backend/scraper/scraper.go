package scraper

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"math"
	"math/rand"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/hashicorp/go-cleanhttp"
	"github.com/hashicorp/go-retryablehttp"
	"go.uber.org/ratelimit"

	"collections/blob"
	"collections/logger"
)

var veryStart = time.Now()
var requests atomic.Uint64

var envRateLimit = "SCRAPER_RATE_LIMIT"
var rateLimitOverride ratelimit.Limiter

var reNumbericPrefix = regexp.MustCompile(`^\d+`)

func init() {
	rateLimitRaw, ok := os.LookupEnv(envRateLimit)
	if !ok {
		return
	}
	switch strings.ToLower(rateLimitRaw) {
	case "none", "unlimited", "disabled", "off":
		rateLimitOverride = ratelimit.NewUnlimited()
		return
	}

	parts := strings.SplitN(rateLimitRaw, "/", 2)
	rate, err := strconv.ParseInt(parts[0], 10, 0)
	if err != nil {
		log.Fatalf("failed to parse %s=%q: %v", envRateLimit, rateLimitRaw, err)
	}
	var opts []ratelimit.Option
	if len(parts) == 2 {
		per := parts[1]
		if !reNumbericPrefix.MatchString(per) {
			per = fmt.Sprintf("1%s", per)
		}
		dur, err := time.ParseDuration(per)
		if err != nil {
			log.Fatalf("failed to parse %s=%q: %v", envRateLimit, rateLimitRaw, err)
		}
		opts = append(opts, ratelimit.Per(dur))
	}
	rateLimitOverride = ratelimit.New(int(rate), opts...)
}

type Scraper struct {
	log        *logger.Logger
	httpClient *retryablehttp.Client
	blob       *blob.Bucket
}

func NewScraper(
	log *logger.Logger,
	blob *blob.Bucket,
) *Scraper {
	httpClient := retryablehttp.NewClient()

	// Configure HTTP client with timeout to prevent indefinite hangs
	client := cleanhttp.DefaultClient() // not pooled
	client.Timeout = 30 * time.Second
	httpClient.HTTPClient = client

	httpClient.Logger = newLeveledLogger(log)
	httpClient.RequestLogHook = func(_ retryablehttp.Logger, req *http.Request, i int) {
		if rateLimitOverride != nil {
			rateLimitOverride.Take()
		} else {
			val, ok := req.Context().Value(ctxKeyLimiter{}).(ctxValLimiter)
			if ok {
				val.Limiter.Take()
			}
		}
		requests.Add(1)
	}
	return &Scraper{
		log:        log,
		httpClient: httpClient,
		blob:       blob,
	}
}

type ErrFetchStatusNotOK struct {
	Page *Page
}

func (e *ErrFetchStatusNotOK) Error() string {
	return fmt.Sprintf("bad fetch status: %d", e.Page.Response.StatusCode)
}

func errPageStatusNotOK(page *Page) error {
	if page.Response.StatusCode != 200 {
		return &ErrFetchStatusNotOK{
			Page: page,
		}
	}
	return nil
}

type ErrFetchThrottled struct{}

func (e *ErrFetchThrottled) Error() string {
	return "fetch throtted"
}

func (s *Scraper) Do(
	ctx context.Context,
	req *http.Request,
	options ...DoOption,
) (page *Page, err error) {
	start := time.Now()

	replace := false
	var reSilentThrottle *regexp.Regexp
	var limiter Limiter
	for _, opt := range options {
		switch opt := opt.(type) {
		case *OptDoReplace:
			replace = true
		case *OptDoSilentThrottle:
			reSilentThrottle = opt.PageBytesRegexp
		case *OptDoLimiter:
			limiter = opt.Limiter
		default:
			panic(fmt.Sprintf("invalid fetch option: %T", opt))
		}
	}

	bkey, reqBody, err := s.blobKey(req)
	if err != nil {
		return nil, fmt.Errorf("failed to create blob key: %w", err)
	}

	if !replace {
		b, err := s.blob.Read(ctx, bkey)
		errNoExist := &blob.ErrNotFound{}
		if !errors.As(err, &errNoExist) {
			if err != nil {
				return nil, fmt.Errorf("failed to read from blob: %w", err)
			}
			page := new(Page)
			if err := json.Unmarshal(b, page); err != nil {
				return nil, fmt.Errorf("failed to unmarshal page: %w", err)
			}
			if err := errPageStatusNotOK(page); err != nil {
				return nil, err
			}
			return page, nil
		}
	}

	if limiter != nil {
		rctx := req.Context()
		rctx = context.WithValue(rctx, ctxKeyLimiter{}, ctxValLimiter{limiter})
		req = req.WithContext(rctx)
	}
	rreq, err := retryablehttp.FromRequest(req)
	if err != nil {
		return nil, err
	}
	// Retry, as reading the body can fail outside the purview of the
	// retryablehttp api. Or, the read body could indicate that the request
	// should be retried. Adding it to the CheckRetry func would be awkward
	// as it would involve conditionally forwarding an already read body.
	var resp *http.Response
	var body []byte
	attemptsMax := 7
	waitMin := 1 * time.Second
	waitMax := 4 * time.Minute
	waitJitter := 1 * time.Second
	wait := func(attempt int) {
		d := time.Duration(math.Pow(2, float64(attempt))) * waitMin
		d += time.Duration(rand.Intn(int(waitJitter)))
		if d > waitMax {
			d = waitMax
		}
		time.Sleep(d)
	}
	for i := 0; i < attemptsMax; i++ {
		resp, err = s.httpClient.Do(rreq)
		if err != nil {
			return nil, fmt.Errorf("failed to perform http get: %w", err)
		}
		body, err = io.ReadAll(resp.Body)
		resp.Body.Close()
		lastAttempt := i >= attemptsMax-1
		if err != nil {
			if lastAttempt {
				return nil, fmt.Errorf("failed to read http resp body: %w", err)
			}
			s.log.Fieldf("attempt", "%d", i).Warnf(ctx, "failed to read http resp body, retrying: %v", err)
			wait(i)
			continue
		}
		if reSilentThrottle != nil && reSilentThrottle.Match(body) {
			n := requests.Load()
			rate := float64(n) / (float64(time.Since(veryStart).Minutes()))
			s.log.Fieldf("rate", "%0.3f/m", rate).Warnf(ctx, "silently throttled")
			if lastAttempt {
				return nil, &ErrFetchThrottled{}
			}
			s.log.Fieldf("attempt", "%d", i).Warnf(ctx, "response is silently throttled, retrying")
			time.Sleep(10 * time.Second)
			wait(i)
			continue
		}
		break
	}

	redirect := ""
	if resp.Request.URL.String() != req.URL.String() {
		redirect = resp.Request.URL.String()
	}
	page = &Page{
		ScrapedAt: time.Now(),
		Request: PageRequest{
			URL:           req.URL.String(),
			RedirectedURL: redirect,
			Method:        req.Method,
			Header:        resp.Request.Header,
			Body:          reqBody,
		},
		Response: PageResponse{
			StatusCode: resp.StatusCode,
			Header:     resp.Header,
			Body:       body,
		},
	}
	b, err := json.Marshal(page)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal page: %w", err)
	}
	if err := s.blob.Write(ctx, bkey, b); err != nil {
		return nil, fmt.Errorf("failed to write page: %w", err)
	}
	if err := errPageStatusNotOK(page); err != nil {
		return nil, err
	}
	s.log.Field("url", rreq.URL.String()).
		Field("status", fmt.Sprintf("%d", page.Response.StatusCode)).
		Field("resp_bytes", fmt.Sprintf("%d", len(page.Response.Body))).
		Field("dur", fmt.Sprintf("%v", time.Since(start).Round(time.Millisecond))).
		Field("content_type", req.Header.Get("Content-Type")).
		Field("req_body", string(reqBody)).
		Debugf(ctx, "fetched http page")
	return page, nil
}

func (s *Scraper) blobKey(req *http.Request) (string, []byte, error) {
	buf := new(bytes.Buffer)

	if _, err := buf.WriteString(req.URL.String()); err != nil {
		return "", nil, err
	}
	if _, err := buf.WriteString("."); err != nil {
		return "", nil, err
	}

	if _, err := buf.WriteString(req.Method); err != nil {
		return "", nil, err
	}
	if _, err := buf.WriteString("."); err != nil {
		return "", nil, err
	}

	if err := req.Header.WriteSubset(buf, nil); err != nil {
		return "", nil, err
	}
	if _, err := buf.WriteString("."); err != nil {
		return "", nil, err
	}

	var body []byte
	if req.Body != nil {
		var err error
		body, err = io.ReadAll(req.Body)
		if err != nil {
			return "", nil, err
		}
	}
	if _, err := buf.Write(body); err != nil {
		return "", nil, err
	}
	if _, err := buf.WriteString("."); err != nil {
		return "", nil, err
	}
	req.Body = io.NopCloser(bytes.NewBuffer(body))

	h := sha256.Sum256(buf.Bytes())
	henc := base64.RawURLEncoding.EncodeToString(h[:])
	bkey := filepath.Join(req.URL.Hostname(), henc) + ".json"
	return bkey, body, nil
}

type DoOption interface {
	doOption()
}

type OptDoReplace struct{}

type OptDoSilentThrottle struct {
	PageBytesRegexp *regexp.Regexp
}

type ctxKeyLimiter struct{}
type ctxValLimiter struct {
	Limiter Limiter
}

type OptDoLimiter struct {
	Limiter Limiter
}

type Limiter interface {
	Take() time.Time
}

func (o *OptDoReplace) doOption()        {}
func (o *OptDoSilentThrottle) doOption() {}
func (o *OptDoLimiter) doOption()        {}

var _ retryablehttp.LeveledLogger = (*leveledLogger)(nil)

type leveledLogger struct {
	ctx context.Context
	log *logger.Logger
}

func newLeveledLogger(log *logger.Logger) *leveledLogger {
	return &leveledLogger{
		ctx: context.Background(),
		log: log,
	}
}

func (l leveledLogger) fields(keysAndValues []any) *logger.Logger {
	log := l.log
	for i := 0; i < len(keysAndValues); i += 2 {
		key := fmt.Sprintf("%v", keysAndValues[i])
		val := fmt.Sprintf("%v", keysAndValues[i+1])
		log = log.Field(key, val)
	}
	return log
}

func (l leveledLogger) Error(msg string, keysAndValues ...any) {
	l.fields(keysAndValues).Errorf(l.ctx, msg)
}

func (l leveledLogger) Warn(msg string, keysAndValues ...any) {
	l.fields(keysAndValues).Warnf(l.ctx, msg)
}

func (l leveledLogger) Info(msg string, keysAndValues ...any) {
	l.fields(keysAndValues).Tracef(l.ctx, msg)
}

func (l leveledLogger) Debug(msg string, keysAndValues ...any) {
	l.fields(keysAndValues).Tracef(l.ctx, msg)
}

type Page struct {
	ScrapedAt time.Time    `json:"scraped_at"`
	Request   PageRequest  `json:"request"`
	Response  PageResponse `json:"response"`
}

type PageRequest struct {
	URL           string      `json:"url"`
	RedirectedURL string      `json:"redirected_url,omitempty"`
	Method        string      `json:"method"`
	Header        http.Header `json:"header,omitempty"`
	Body          []byte      `json:"body,omitempty"`
}

type PageResponse struct {
	StatusCode int         `json:"status_code"`
	Header     http.Header `json:"header,omitempty"`
	Body       []byte      `json:"body,omitempty"`
}
