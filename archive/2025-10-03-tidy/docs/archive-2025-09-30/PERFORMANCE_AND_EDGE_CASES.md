# ⚡ Performance Analysis & Edge Case Handling

**Date**: October 1, 2025  
**Focus**: Concurrency, error handling, edge cases, failure modes

---

## 1. Concurrency Analysis - 31 Synchronization Points

### 1.1 Primitive Usage

```
sync.Mutex:     3 instances   (Transform, ?)
sync.WaitGroup: 15+ instances (Every worker pool)
Channels:       20+ instances (Task queues, semaphores)
atomic.*:       5+ instances  (Request counters, metrics)
```

### 1.2 Concurrency Patterns Identified

**Pattern 1: Worker Pool with Buffered Channel**
```go
// Used in: MTGTop8, MTGGoldfish, Deckbox, Scryfall
tasks := make(chan task, 25*10)  // Buffer size: 250
wg := new(sync.WaitGroup)

for i := 0; i < opts.Parallel; i++ {  // Default: 128 workers
    wg.Add(1)
    go func() {
        defer wg.Done()
        for t := range tasks {
            process(t)
        }
    }()
}
```

**Characteristics**:
- ✅ **Fixed worker count**: Prevents goroutine explosion
- ✅ **Buffered channel**: Decouples producer from consumers
- ✅ **Clean shutdown**: close(tasks) + wg.Wait()
- 🔍 **No error aggregation**: Each worker logs errors independently

**Pattern 2: Semaphore with Dynamic Goroutines**
```go
// Used in: games/dataset.go - IterItemsBlobPrefix
sem := make(chan struct{}, parallel)  // 512 by default!
errs := make(chan error, parallel)
wg := new(sync.WaitGroup)

LOOP:
for it.Next(ctx) {
    select {
    case err := <-errs:  // Check for errors
        if errors.Is(err, ErrIterItemsStop) {
            errLoop = nil
        }
        break LOOP
    default:
    }
    
    wg.Add(1)
    sem <- struct{}{}  // Acquire
    go func() {
        defer wg.Done()
        defer func() { <-sem }()  // Release
        
        // Work here
        if err := fn(item); err != nil {
            errs <- err
        }
    }()
}
```

**Characteristics**:
- ✅ **Error propagation**: First error stops iteration
- ✅ **Bounded concurrency**: Semaphore limits active goroutines
- ✅ **Early exit**: select{} checks errors before spawning new work
- 🔍 **512 default**: Much higher than worker pool (512 vs 128)

**Pattern 3: Scoped Mutex (Transform)**
```go
func (t *Transform) add(k tkey, v tval) error {
    t.mu.Lock()
    defer t.mu.Unlock()
    
    // Critical section: badger read-modify-write
    err = t.db.Update(func(txn *badger.Txn) error {
        // Get existing value
        // Add to it
        // Write back
    })
}
```

**Characteristics**:
- ⚠️ **Global serialization**: All workers contend on single lock
- ✅ **Safe**: Prevents race conditions in badger
- ⚠️ **Performance**: Bottleneck for high-throughput scenarios
- 🔍 **Design tradeoff**: Simplicity vs performance

---

## 2. Error Handling Philosophy

### 2.1 Error Propagation Hierarchy

```
Level 1: Library Errors (goquery, http, badger)
         ↓ wrapped with context
Level 2: Dataset Errors (parsing, validation)
         ↓ wrapped with details
Level 3: CLI Errors (user-facing)
         ↓ logged and returned

Pattern: fmt.Errorf("failed to X: %w", err)
```

**Example Chain**:
```go
// Level 1: HTTP error
err := http.Get(url)

// Level 2: Wrap with context
err = fmt.Errorf("failed to fetch cards: %w", err)

// Level 3: Wrap with more context
err = fmt.Errorf("failed to update dataset %s: %w", name, err)

// Final error message:
// "failed to update dataset scryfall: failed to fetch cards: connection refused"
```

### 2.2 Panic vs Error - Decision Points

**Panics** (fail-fast, programming errors):
```go
// Type registry conflict
if _, exists := TypeRegistry[typeName]; exists {
    panic(fmt.Sprintf("collection type %q already registered", typeName))
}

// Invalid option type
default:
    panic(fmt.Sprintf("invalid option: %T", opt))

// URL parse failure at init()
func init() {
    u, err := url.Parse("https://scryfall.com")
    if err != nil {
        panic(err)  // Can't proceed without base URL
    }
}
```

**Errors** (recoverable, runtime issues):
```go
// Network failures
page, err := sc.Do(ctx, req)
if err != nil {
    return fmt.Errorf("failed to fetch: %w", err)
}

// Parse failures
if err := json.Unmarshal(data, &result); err != nil {
    return fmt.Errorf("failed to parse: %w", err)
}
```

**Philosophy**:
- ✅ **Panic for invariant violations**: Programming errors that shouldn't happen
- ✅ **Error for external failures**: Network, disk, parsing issues
- ✅ **Early panic**: Fail-fast at init() for configuration issues
- 🔍 **No panic recovery**: Let the program crash on programmer errors

### 2.3 Logging Levels - Structured Logging

```go
type Logger struct {
    inner  *logrus.Entry  // Wraps logrus
    prefix string
}

// Method chaining for fields
log.Field("url", url).
    Field("status", fmt.Sprintf("%d", status)).
    Fieldf("dur", "%v", duration).
    Debugf(ctx, "fetched page")
```

**Level Usage**:
```
FATAL: Configuration errors (env var parsing)
ERROR: Failed operations (parse errors, network failures)
WARN:  Recoverable issues (throttling, retries)
INFO:  Progress updates (page counts, extraction stats)
DEBUG: Detailed operations (cache hits, individual fetches)
TRACE: Library internals (retryablehttp callbacks)
```

**Insights**:
- ✅ **Structured logging**: Fields are first-class, not string interpolation
- ✅ **Context passed**: All log calls take context (future tracing support)
- ✅ **Method chaining**: Fluent API for field accumulation
- 🔍 **Level mapping**: Maps retryablehttp levels to lower levels (Info→Trace)

---

## 3. Edge Cases - How They're Handled

### 3.1 Empty Collections

```go
// In Canonicalize()
if len(c.Partitions) == 0 {
    return errors.New("collection has no partitions")
}

for i, p := range c.Partitions {
    if len(p.Cards) == 0 {
        return fmt.Errorf("partition %s has no cards", p.Name)
    }
}
```

**Handling**: **Reject** empty collections/partitions
**Rationale**: Empty decks are invalid domain objects
**Impact**: Prevents garbage data from entering system

### 3.2 Redirect Handling

```go
// In scraper.go
redirect := ""
if resp.Request.URL.String() != req.URL.String() {
    redirect = resp.Request.URL.String()
}

page = &Page{
    Request: PageRequest{
        URL:           req.URL.String(),      // Original
        RedirectedURL: redirect,               // Final (if different)
    },
}
```

**Example** (Deckbox):
```go
if page.Request.URL != task.CollectionURL {
    if page.Request.URL == "https://deckbox.org/" {
        return errors.New("not found")  // Redirect to home = 404
    }
}
```

**Handling**: **Track** redirects, interpret as errors when appropriate
**Insight**: Deckbox redirects to home on 404 (no HTTP 404 status)

### 3.3 Multi-Faced Card Handling (MTG Only)

```go
if len(rawCard.Faces) == 0 {
    // Single-faced card: use top-level fields
    faces = append(faces, game.CardFace{
        Name:       rawCard.Name,
        ManaCost:   rawCard.ManaCost,
        // ...
    })
} else {
    // Multi-faced card: use face-specific fields
    for _, rawFace := range rawCard.Faces {
        faces = append(faces, game.CardFace{
            Name:       rawFace.Name,
            ManaCost:   rawFace.ManaCost,
            // ...
        })
    }
}
```

**Card Types**:
- Double-Faced Cards (DFC): Werewolves, transform cards
- Split Cards: Two spells on one card
- Flip Cards: Flip upside down
- Meld Cards: Two cards combine into one

**Insight**: Only MTG has this complexity - architecture handled it elegantly

### 3.4 Nullable Fields (YGO)

```go
type apiCard struct {
    ATK     *int `json:"atk"`      // Pointer = nullable
    DEF     *int `json:"def"`
    Level   *int `json:"level"`
    Rank    *int `json:"rank"`
    LinkVal *int `json:"linkval"`
}

// Conditional assignment
if apiCard.ATK != nil {
    card.ATK = *apiCard.ATK
}
```

**Reason**: Not all cards have these fields
- Spell/Trap cards: No ATK/DEF
- Normal monsters: Have Level but not Rank
- Xyz monsters: Have Rank but not Level  
- Link monsters: Have LinkRating but not Level/Rank

**Insight**: API design reflects game rules correctly

### 3.5 Pagination Edge Cases

**Pokemon TCG** - End Detection:
```go
if page * apiResp.PageSize >= apiResp.TotalCount {
    d.log.Infof(ctx, "Reached end of results")
    break
}
```

**MTGTop8** - Empty Page Detection:
```go
if len(urls) == 0 {
    d.log.Infof(ctx, "last page %d, stopping scrolling", currPage)
    return nil
}
```

**Deckbox** - Next Link Detection:
```go
nextPageURL, ok := sel.Attr("href")
if !ok {
    return fmt.Errorf("failed to find next page href")
}

func (p parsedPage) Next() bool {
    return p.NextURL != ""  // Empty string = no next page
}
```

**Insight**: Different pagination strategies require different end conditions

---

## 4. Performance Characteristics

### 4.1 Throughput Benchmarks (Observed)

**YGOPRODeck**:
```
13,930 cards in 8 seconds
= 1,741 cards/second
= Single API call + parallel storage
```

**Pokemon TCG**:
```
250 cards/page, 50 cards extracted in ~55 seconds
= ~1 card/second (API rate limited?)
```

**MTGTop8** (Historical):
```
~100 decks with 100/min rate limit
= 1 deck/minute minimum
= Dominated by rate limiting, not processing
```

**Scryfall Cards**:
```
20,000+ cards parsed with 128 workers
= ~200 cards/second (CPU-bound parsing)
```

### 4.2 Bottleneck Analysis

**Network-bound scenarios**:
- MTGTop8: Rate limited at 100 req/min (if enabled)
- MTGGoldfish: Throttle detection + 100 req/min
- Pokemon: API pagination latency

**CPU-bound scenarios**:
- Scryfall card parsing: 128 parallel workers
- Transform co-occurrence: Bottlenecked by global mutex

**I/O-bound scenarios**:
- Blob storage reads: 512 parallel (semaphore)
- Blob storage writes: Async, compressed

**Insight**: Different datasets have different bottlenecks

### 4.3 Memory Characteristics

**Large Allocations**:
```go
// Scryfall: Load entire bulk JSON into memory
var rawCards []card
json.Unmarshal(page.Response.Body, &rawCards)  // ~50MB in memory

// YGOPRODeck: Similar
var apiResp apiResponse  // ~13,930 cards in slice

// Pokemon: Paginated (250 at a time)
var apiResp apiResponse  // Only current page in memory
```

**Memory Patterns**:
- ✅ **Streaming where possible**: Pokemon uses pagination
- ⚠️ **Bulk loading**: Scryfall, YGO load entire dataset
- ✅ **Worker pools**: Fixed goroutines prevent memory explosion
- 🔍 **Trade-off**: Bulk = faster but more memory

---

## 5. HTTP Client Configuration - Devils in Details

### 5.1 cleanhttp.DefaultClient()

```go
httpClient.HTTPClient = cleanhttp.DefaultClient() // not pooled
```

**Comment says "not pooled"** - what does this mean?

From cleanhttp docs:
```go
// DefaultPooledClient returns HTTP client with:
// - Connection pooling (reuses TCP connections)
// - Timeouts configured

// DefaultClient returns HTTP client with:
// - NO connection pooling (new connection each request)
// - Same timeouts
```

**Why not pooled?**
- 🔍 **Cache layer**: HTTP responses cached in blob, so same URL rarely hit twice
- 🔍 **Different hosts**: Scraper hits multiple domains (scryfall, mtgtop8, etc.)
- 🔍 **Simplicity**: No connection pool management needed
- ⚠️ **Trade-off**: Slower for repeated requests to same host (but cache handles this)

### 5.2 retryablehttp Configuration

```go
httpClient := retryablehttp.NewClient()
httpClient.RequestLogHook = func(_ retryablehttp.Logger, req *http.Request, i int) {
    // Rate limiting here (before request)
    if rateLimitOverride != nil {
        rateLimitOverride.Take()
    }
    requests.Add(1)
}
```

**Default Behavior** (from library):
- Retries on: 5xx errors, network failures
- Backoff: Exponential (but we override this)
- Max retries: 4 (but we override with our own loop)

**Our Overrides**:
- Custom retry loop: 7 attempts (not library's 4)
- Custom backoff: 1s → 64s (not library's default)
- Throttle detection: Check response body (not just status code)

**Insight**: We use retryablehttp mainly for its client wrapper, but implement custom retry logic for more control

### 5.3 Request Lifecycle

```
1. Client builds HTTP request
2. Scraper.Do() called
   ├─ Check blob cache (SHA256 key)
   │  └─ Cache hit? Return immediately
   ├─ Add rate limiter to context
   ├─ Convert to retryablehttp.Request
   ├─ RequestLogHook fires → Take() from rate limiter
   ├─ HTTP request sent
   ├─ Read response body
   ├─ Check for silent throttle pattern
   │  └─ If throttled: sleep 10s + exponential backoff, retry
   ├─ Store Page in blob
   └─ Return Page

Total: Up to 7 attempts, up to 130 seconds
```

---

## 6. Edge Cases in Parsing

### 6.1 Card Count Parsing

**Goldfish** - Default to 1:
```go
count, err := strconv.ParseInt(countStr, 10, 0)
if err != nil {
    return false  // Error stops iteration
}
```

**Deckbox** - Graceful fallback:
```go
cardCount, err := strconv.ParseInt(cardCountStr, 10, 0)
if err != nil {
    cardCount = 1  // Default to 1 on parse error
}
```

**Insight**: Different error tolerance strategies
- Goldfish: Fail if can't parse count (strict)
- Deckbox: Assume 1 if missing (lenient)

### 6.2 Section Detection (MTGTop8)

```go
doc.Find("div.O14").EachWithBreak(func(i int, s *goquery.Selection) bool {
    switch s.Text() {
    case "COMMANDER":
        section = "Commander"
    case "SIDEBOARD":
        section = "Sideboard"
    default:
        section = "Main"  // Unknown sections go to Main
    }
    return true
})
```

**Edge case**: What if there are custom section names?
**Handling**: Default to "Main" (reasonable fallback)
**Impact**: Might misclassify novel formats

### 6.3 Date Parsing Variations

**Three different formats** across datasets:

```go
// Scryfall: ISO format
time.Parse("2006-01-02", "2025-11-21")

// Goldfish: Month Day, Year
time.Parse("Jan _2, 2006", "Nov 23, 2022")

// Deckbox: Day-Month-Year Hour:Minute
time.Parse("02-Jan-2006 15:04", "23-Nov-2022 14:30")
```

**Insight**: No abstraction - each dataset handles its own format

### 6.4 URL Validation

**Pattern**: Pre-validate URLs with regex before processing

```go
// Scryfall
var reCollectionRef = regexp.MustCompile(`^https://scryfall.com/sets/.+$`)
for _, u := range opts.ItemOnlyURLs {
    if !reCollectionRef.MatchString(u) {
        return fmt.Errorf("invalid only url: %s", u)
    }
}

// Goldfish
var reCollectionURL = regexp.MustCompile(`^https://www.mtggoldfish.com/deck/`)

// Deckbox
var reCollectionURL = regexp.MustCompile(`^https://deckbox.org/sets/\d+`)
```

**Benefits**:
- ✅ **Fail fast**: Invalid URLs rejected before scraping
- ✅ **Security**: Prevents scraping arbitrary domains
- ✅ **User feedback**: Clear error messages

---

## 7. Subtle Patterns & Idioms

### 7.1 done() Function Pattern

```go
// In MTGTop8
done := func(err error) error {
    close(tasks)
    wg.Wait()
    return err
}

if len(opts.ItemOnlyURLs) > 0 {
    for _, u := range opts.ItemOnlyURLs {
        tasks <- task{ItemURL: u}
    }
    return done(nil)
}

if err := d.scrollPages(...); err != nil {
    return done(err)
}

return done(nil)
```

**Benefits**:
- ✅ **DRY**: Single cleanup path
- ✅ **Ensures cleanup**: Can't forget to close(tasks) + wg.Wait()
- ✅ **Error threading**: Pass through error while cleaning up

### 7.2 Error Variable in Closure Pattern

```go
var err error  // Outer scope
doc.Find(selector).EachWithBreak(func(i int, sel *goquery.Selection) bool {
    value, ok := sel.Attr("href")
    if !ok {
        err = fmt.Errorf("missing href")  // Assign to outer err
        return false  // Stop iteration
    }
    return true
})
if err != nil {
    return err  // Check and propagate
}
```

**Necessity**: goquery's Each() doesn't return errors
**Trade-off**: Closure can't return errors directly, so use outer variable
**Risk**: Variable shadowing (if `err :=` used inside closure)

### 7.3 Key Normalization (Symmetric Pairs)

```go
func newKey(name1, name2 string) tkey {
    if name1 > name2 {
        name1, name2 = name2, name1  // Swap to ensure order
    }
    return tkey{
        Name1: name1,
        Name2: name2,
    }
}
```

**Purpose**: (Lightning Bolt, Lava Spike) == (Lava Spike, Lightning Bolt)
**Benefits**:
- ✅ **Deduplication**: Only one key for each pair
- ✅ **Graph symmetry**: Undirected edge representation
- ✅ **Deterministic**: Same pair always produces same key

### 7.4 Progress Logging Pattern

```go
for i, item := range items {
    process(item)
    
    if (i+1) % 1000 == 0 {
        log.Infof(ctx, "Processed %d/%d items...", i+1, total)
    }
}
```

**Used everywhere**: Scryfall (1000), YGO (1000), Pokemon (100)
**Benefits**:
- ✅ **User feedback**: Shows progress on long operations
- ✅ **Debug info**: Can estimate completion time
- 🔍 **Threshold varies**: Adjusted based on expected item count

---

## 8. Library Choices - Why These?

### 8.1 Dependencies Analysis

```go
// HTTP & Retry
"github.com/hashicorp/go-cleanhttp"      // Clean HTTP client
"github.com/hashicorp/go-retryablehttp"  // Retry logic
"go.uber.org/ratelimit"                  // Rate limiting

// HTML Parsing
"github.com/PuerkitoBio/goquery"         // jQuery-like API

// Storage
"gocloud.dev/blob"                       // Multi-backend (S3, file, GCS)
"github.com/dgraph-io/badger/v3"         // Embedded KV store
"github.com/DataDog/zstd"                // Compression

// Utilities
"github.com/samber/mo"                   // Option type (Maybe monad)
"github.com/samber/lo"                   // Functional utilities
"github.com/vmihailenco/msgpack"         // Binary serialization
"github.com/sirupsen/logrus"             // Structured logging
```

**Why gocloud.dev/blob?**
- ✅ **Multi-backend**: Same code for file://, s3://, gcs://
- ✅ **Industry standard**: Google's cloud abstraction
- ✅ **Easy migration**: Change URL, code stays same

**Why badger?**
- ✅ **Embedded**: No external database needed
- ✅ **Fast**: Written in Go, LSM-tree design
- ✅ **Transactions**: ACID guarantees for co-occurrence updates

**Why zstd?**
- ✅ **Best ratio**: Better than gzip/lz4 for JSON
- ✅ **Fast**: Compression speed vs ratio sweet spot
- ✅ **Streaming**: Can compress/decompress on-the-fly

**Why mo.Option?**
- ✅ **Type-safe**: No nil pointer bugs
- ✅ **Explicit**: `Get()` returns (value, bool)
- ✅ **Ergonomic**: `OrElse()` for defaults

---

## 9. Surprising Discoveries

### 9.1 Badger Cache is 556MB! 

**For only ~198 MTG collections**:
```
cache/000276.vlog: 432 MB (value log)
cache/*.sst:       ~100 MB (sorted string tables)
```

**Analysis**: Caching is aggressive
**Contents**: Likely caching both HTTP responses AND parsed data
**Question**: Is this intentional or accidental growth?

**Recommendation**: Add cache size limits or TTL cleanup

### 9.2 Two Caching Layers

**Layer 1: Scraper Blob Cache** (HTTP level)
```go
// In scraper.go
bkey := sha256(url + method + headers + body)
blob.Write("scraper/{hostname}/{hash}.json", page)
```

**Layer 2: Badger Cache** (Blob level)
```go
// In blob.go
if b.cache != nil {
    b.cache.Update(func(txn *badger.Txn) error {
        return txn.Set(b.cacheKey(key), data)
    })
}
```

**Effect**: **Double caching!**
```
HTTP Request → Check badger cache
              ↓ miss
              Check blob (file:// or s3://)
              ↓ miss
              Fetch from network
              ↓
              Store in blob
              ↓
              Store in badger cache
```

**Insight**: Caching pushed lower in the stack (per user principles!)
- Blob cache: Network → local file
- Badger cache: Local file → memory

### 9.3 Content-Type Header Logging

```go
s.log.Field("content_type", req.Header.Get("Content-Type")).
    Debugf(ctx, "fetched http page")
```

**But looking at request, not response!**
**Bug?**: Should be `resp.Header.Get("Content-Type")`
**Impact**: Logs request Content-Type instead of response
**Severity**: Low - just logging, doesn't affect functionality

### 9.4 Silent Error Swallowing

```go
// In blob.go cache handling
if err := b.cache.Update(func(txn *badger.Txn) error {
    return txn.Set(b.cacheKey(key), data)
}); err != nil {
    b.log.Errorf(ctx, "failed to set cache: %v", err)
    // NO RETURN! Continues despite cache failure
}
```

**Philosophy**: **Cache failures are non-fatal**
- ✅ **Robustness**: System works even if cache broken
- ✅ **Graceful degradation**: Falls back to blob storage
- 🔍 **Silent failures**: Logged but not surfaced to user

---

## 10. Code Quality Observations

### 10.1 Defer Usage (17 files)

**Cleanup patterns**:
```go
defer wg.Done()           // Goroutine cleanup
defer func() { <-sem }()  // Semaphore release
defer zw.Close()          // zstd writer cleanup
defer r.Close()           // Reader cleanup
defer f.Close()           // File handle cleanup
```

**Grade**: ✅ Excellent - consistent use of defer for cleanup

### 10.2 Error Wrapping

**Almost every error is wrapped with context**:
```go
return fmt.Errorf("failed to parse %s: %w", itemURL, err)
return fmt.Errorf("failed to marshal card %q: %w", card.Name, err)
return fmt.Errorf("collection is invalid: %w", err)
```

**Benefits**:
- ✅ **Error chains**: Full context from error origin to user
- ✅ **Debug-friendly**: Clear what operation failed
- ✅ **errors.Is/As**: %w preserves error type for inspection

**Grade**: ✅ Excellent - follows Go best practices

### 10.3 Regex Compilation

**All patterns compiled at package level**:
```go
var reSetName = regexp.MustCompile(`(.*)\s+\((.*)\)$`)
var reDeckID = regexp.MustCompile(`^https://mtgtop8\.com/event\?e=(\d+)&d=(\d+)`)
var reBadCardName = regexp.MustCompile(`(^\s*$)|(\p{Cc})`)
```

**Benefits**:
- ✅ **Performance**: Compile once, use many times
- ✅ **Validation**: Panics on invalid regex at startup
- ✅ **Readability**: Named variables document purpose

**Grade**: ✅ Excellent - best practice

---

## 11. Missing Pieces Discovered

### 11.1 No Metrics/Monitoring

**Current**: Only logs
**Missing**:
- Success/failure rates per dataset
- Average fetch times
- Cache hit rates
- Error type distribution

**Impact**: Hard to diagnose performance issues
**Fix**: Add Prometheus metrics or structured telemetry

### 11.2 No Request Timeouts

```go
httpClient := retryablehttp.NewClient()
// Uses library defaults, but not explicitly configured
```

**Risk**: Hanging requests could block workers
**Mitigation**: Retry logic provides implicit timeout (7 attempts × ~130s max)
**Recommendation**: Set explicit timeout (e.g., 30s per attempt)

### 11.3 No Circuit Breaker

**Current**: Retries indefinitely if source is down
**Missing**: Circuit breaker to stop retrying after N failures

**Impact**: Wastes time retrying unavailable sources
**Fix**: Add circuit breaker pattern (fail-fast after threshold)

---

## 12. Performance Optimization Opportunities

### 12.1 Transform Mutex Sharding

**Current**:
```go
t.mu.Lock()  // Global lock
defer t.mu.Unlock()
```

**Proposed**:
```go
type Transform struct {
    shards [256]struct {
        mu sync.Mutex
        // ...
    }
}

func (t *Transform) add(k tkey, v tval) error {
    shard := hash(k.Name1) % 256
    t.shards[shard].mu.Lock()
    defer t.shards[shard].mu.Unlock()
    // ...
}
```

**Expected improvement**: ~256x parallelism on updates

### 12.2 Batch Blob Writes

**Current**: Write each card individually
```go
for _, card := range cards {
    blob.Write(ctx, key, data)  // Network round-trip each time
}
```

**Proposed**: Batch writes
```go
batch := []BlobItem{}
for _, card := range cards {
    batch = append(batch, BlobItem{key, data})
}
blob.WriteBatch(ctx, batch)  // Single operation
```

**Expected improvement**: ~10x faster for bulk operations

### 12.3 Parallel Blob Iteration

**Current**: 512 goroutines by default
```go
sem := make(chan struct{}, 512)
```

**Observation**: Very high for I/O-bound tasks
**Measurement needed**: Profile to see if this helps or hurts

---

## 13. Robustness Analysis

### 13.1 Failure Modes

| Failure | Detection | Recovery | Impact |
|---------|-----------|----------|--------|
| Network down | HTTP error | Retry 7x, exponential backoff | Delays, eventual failure |
| API rate limit | Status code | Retry with backoff | Automatic recovery |
| Silent throttle | Regex pattern | Extra delay + retry | Automatic recovery |
| Parse error | Unmarshal fails | Log + continue | Skip bad data |
| Invalid collection | Canonicalize fails | Log + continue | Skip invalid |
| Badger cache full | Update error | Log + continue (silent) | Degraded performance |
| Disk full | Write error | Return error | Operation fails |

**Grade**: ✅ Good - handles transient failures gracefully

### 13.2 Data Consistency

**Atomicity**: Per-blob writes are atomic
**Durability**: zstd flush ensures data written
**Isolation**: Each worker writes independent keys
**Consistency**: Canonicalize() enforces invariants

**Missing**: **No transactions across multiple blobs**
- If scraper crashes mid-extraction, partial data remains
- No rollback mechanism
- Not a critical issue (re-run fixes it)

---

## 14. Final Insights

### 14.1 What Makes This Code Good

1. **Separation of concerns**: Scraper, blob, dataset, transform are independent
2. **Composable options**: UpdateOption, DoOption, BucketOption patterns
3. **Fail-fast on config**: init() panics prevent bad runtime state
4. **Graceful degradation**: Cache failures don't stop operation
5. **Comprehensive logging**: Every operation has context
6. **Error wrapping**: Full error chains for debugging
7. **Consistent patterns**: Worker pools, error handling, regex validation

### 14.2 What Could Be Better

1. **Metrics/monitoring**: Add telemetry for production
2. **Timeout configuration**: Explicit HTTP timeouts
3. **Circuit breakers**: Fail-fast on unavailable sources
4. **Transform performance**: Shard locks for co-occurrence
5. **Cache management**: Size limits, TTL cleanup
6. **Transaction support**: Multi-blob consistency (if needed)

### 14.3 Grade by Category

| Category | Grade | Rationale |
|----------|-------|-----------|
| Architecture | A+ | Universal abstractions proven across 3 games |
| Concurrency | A | Good patterns, but mutex bottleneck in transform |
| Error Handling | A | Comprehensive, well-wrapped, contextual |
| Caching | A- | Excellent strategy, but growth management needed |
| Logging | A | Structured, leveled, contextual |
| Testing | B+ | Good coverage, missing integration tests |
| Documentation | B | Inline docs sparse, but external docs good |
| Performance | B+ | Good for most cases, known bottlenecks |

**Overall**: **A** - Production-quality with room for optimization

