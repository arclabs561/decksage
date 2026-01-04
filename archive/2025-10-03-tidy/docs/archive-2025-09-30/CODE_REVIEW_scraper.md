# Code Review: scraper/scraper.go

**File**: `src/backend/scraper/scraper.go`
**Lines Reviewed**: 1-402
**Severity**: Found 1 critical bug, 3 minor issues

---

## 🔴 CRITICAL BUG: Dead Code in init()

**Lines 63-67**:
```go
dur, err := time.ParseDuration(per)
if err != nil {
    if err != nil {  // ← DUPLICATE CHECK! Inner check is dead code
        log.Fatalf("failed to parse %s=%q: %v", envRateLimit, rateLimitRaw, err)
    }
}
```

**Issue**: Duplicate `if err != nil` - inner block never reached

**Should be**:
```go
dur, err := time.ParseDuration(per)
if err != nil {
    log.Fatalf("failed to parse %s=%q: %v", envRateLimit, rateLimitRaw, err)
}
```

**Impact**: If rate limit parsing fails, program doesn't crash (silently continues with broken rate limit)

**Severity**: HIGH - Silent failure mode

---

### 🟡 TYPO: "throtted" → "throttled"

**Line 124**:
```go
return "fetch throtted"  // ← Missing 'l'
```

**Fix**:
```go
return "fetch throttled"
```

**Severity**: Very low (typo in error message)

---

### 🟡 WARNING: Panic on Unknown Option

**Line 146**:
```go
default:
    panic(fmt.Sprintf("invalid fetch option: %T", opt))
```

**Issue**: Same as dataset.go - panics instead of returning error

**Better**: Return error from Do()

**Severity**: Medium (API usability)

---

### 🟢 OBSERVATION: Global State for Metrics

**Lines 32-33**:
```go
var veryStart = time.Now()
var requests atomic.Uint64
```

**Issue**: Package-level globals make testing harder

**Better**: Encapsulate in Scraper struct:
```go
type Scraper struct {
    log        *logger.Logger
    httpClient *retryablehttp.Client
    blob       *blob.Bucket
    startTime  time.Time       // ← Instance variable
    requests   atomic.Uint64   // ← Instance variable
}
```

**Severity**: Low (works fine, just not ideal for testing)

---

## Other Observations

### ✅ Good Practices

1. **Rate limiting** - Properly implemented with configurable override
2. **Atomic operations** - Uses atomic.Uint64 for request counter
3. **Context propagation** - req.Context() used properly
4. **Retry logic** - Uses retryablehttp.Client
5. **Blob caching** - Smart caching with blob storage

### ⚠️ Potential Issues

1. **init() can panic** - If env var malformed, crashes at startup
2. **No request timeout configuration** - Uses defaults
3. **Cache key collision risk** - SHA256 should be fine, but no explicit handling

---

## Recommended Fixes

### Must Fix

1. **Remove duplicate `if err != nil`** (lines 63-67)
2. **Add test for rate limit parsing edge cases**

### Should Fix

3. **Fix typo**: "throtted" → "throttled"
4. **Return error instead of panic** for unknown options

### Nice to Have

5. **Encapsulate globals** in Scraper struct
6. **Add configurable timeouts**
7. **Validate rate limit at parse time** (e.g., reject 0/m)

---

##Grade

**Code Quality**: B+ (8/10)
**Bug Severity**: Medium (dead code, but low impact)
**Robustness**: B (7.5/10)

**Overall**: **B+ (8/10)** - Solid implementation, one dead code bug
