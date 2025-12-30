# BadgerDB Cache Critical Issues - October 4, 2025

## 🔴 CRITICAL FINDINGS

### Issue #1: **5.5GB Stale Cache from March 2023**

**Evidence:**
```bash
$ du -sh src/backend/cache/
5.5G	cache/

$ stat cache/000276.vlog
Size: 432247381 bytes (413 MB)
Modify: 2023-03-18 21:15:22
Birth: 2023-03-18 21:12:32
```

**Analysis:**
- Cache has data from **March 18, 2023** (almost 2 years ago!)
- **5.5GB** of stale data accumulating
- **457 files** in cache directory
- Largest file: 413MB value log

**Impact:**
- Wasted disk space (5.5GB)
- Potential I/O overhead (scanning old files)
- Stale data never cleaned up
- Cache effectiveness unknown

---

### Issue #2: **No Garbage Collection**

**Code Review:**
```bash
$ grep -r "RunValueLogGC\|GC\|garbage" src/backend/blob/
# NO RESULTS
```

**Problem:** BadgerDB requires manual GC to reclaim space

**From BadgerDB docs:**
```go
// Recommended pattern:
ticker := time.NewTicker(5 * time.Minute)
defer ticker.Stop()
for range ticker.C {
again:
    err := db.RunValueLogGC(0.7)
    if err == nil {
        goto again  // Run GC until no more work
    }
}
```

**Our Code:** ❌ **NONE OF THIS EXISTS**

**Impact:**
- Deleted/updated data not reclaimed
- Value logs grow indefinitely
- Disk space wasted on garbage

---

### Issue #3: **No TTL (Time To Live)**

**Configuration:**
```go
// src/backend/blob/blob.go:54
cacheOpts := badger.DefaultOptions(opt.Dir)
// NO TTL CONFIGURATION
```

**Problem:** Data never expires automatically

**Should Have:**
```go
cacheOpts := badger.DefaultOptions(opt.Dir)
cacheOpts.WithTTL = 24 * time.Hour  // Or appropriate duration
```

**Impact:**
- March 2023 data still in cache
- No automatic cleanup
- Cache grows monotonically

---

### Issue #4: **No Size Limits**

**Configuration:**
```go
cacheOpts := badger.DefaultOptions(opt.Dir)
// NO SIZE LIMITS
```

**Problem:** BadgerDB has no built-in size limits

**Impact:**
- Cache can grow to fill entire disk
- No protection against runaway growth
- Manual monitoring required

---

### Issue #5: **Cache Not Used in Normal Operations**

**Evidence:**
```bash
$ grep "cache" scripts/expand_scraping.sh
# NO RESULTS

$ grep "\-\-cache" scripts/expand_scraping.sh  
# NO RESULTS
```

**Commands that support --cache:**
- `extract` ✅ (but never used)
- `index` ✅
- `transform` ✅

**Commands that don't:**
- Most others

**Analysis:** Cache flag exists but is **optional and rarely used**

**Current Usage:** Effectively **ZERO** (not passed in scripts)

---

### Issue #6: **Double Caching Architecture**

**Discovered Pattern:**

```
Request Flow:
1. Check Badger cache        ← Layer 2 (memory-backed)
   ↓ miss
2. Check Blob storage        ← Layer 1 (file:// or s3://)
   (which IS the cache for HTTP!)
   ↓ miss
3. HTTP request
   ↓
4. Store in Blob             ← Persistent cache
   ↓
5. Store in Badger           ← Ephemeral cache
```

**Analysis:**
- Badger caches **what's already cached** in blob storage
- Blob storage is already SHA256-keyed persistent cache
- Badger adds memory-backed layer for **local file read optimization**

**When Useful:**
- Reading from S3 repeatedly (network → cache → memory)
- Large datasets with frequent access

**When Useless:**
- file:// blob storage (disk → cache → disk?)
- Infrequent access patterns
- One-time processing

**Current Setup:**
```bash
--bucket file://./data-full  # Local filesystem
# NO --cache flag              # Badger not used
```

**Verdict:** Badger cache is **redundant** for file:// buckets!

---

### Issue #7: **No Cache Invalidation Strategy**

**Scenarios:**
1. Scraper code updated (e.g., MTGGoldfish parser fixed)
2. Old cache has wrong data (sideboard bug)
3. Schema changes (new fields added)

**Current Approach:**
```go
if !replace {
    // Check cache first
    b, err := s.blob.Read(ctx, bkey)
    // Return cached data even if parser changed!
}
```

**Problem:** Cache invalidation requires manual intervention

**Options:**
- Pass `--rescrape` flag (invalidates HTTP cache)
- Pass `--reparse` flag (re-parses cached HTTP)
- Delete cache directory manually
- No automatic versioning

**Impact:** Bug fixes require manual cache busting

---

## 🔍 DETAILED ANALYSIS

### BadgerDB Configuration Review

**Current:**
```go
cacheOpts := badger.DefaultOptions(opt.Dir)
cacheOpts.Logger = &badgerLogger{ctx, log}
cache, err = badger.Open(cacheOpts)
```

**What's Missing:**
```go
// Size management
cacheOpts.ValueLogFileSize = 128 << 20  // 128MB per file (default: 1GB)
cacheOpts.MemTableSize = 32 << 20        // 32MB mem tables (default: 64MB)

// Compression
cacheOpts.Compression = options.Snappy   // Compress value logs

// GC
cacheOpts.ValueLogMaxEntries = 1000000  // Trigger GC more often

// TTL (would need code changes)
// Badger v3 supports TTL but needs explicit setting on each key
```

### Error Handling Review

**Cache errors are logged but ignored:**

```go
if err != nil {
    b.log.Errorf(ctx, "failed to set cache: %v", err)
    // Continues anyway - cache is optional
}
```

**Analysis:** ✅ **CORRECT BEHAVIOR**
- Cache is optimization, not requirement
- Degraded gracefully when cache fails
- Operations continue without cache

### Transaction Usage Review

**Pattern:**
```go
b.cache.View(func(txn *badger.Txn) error {
    item, err := txn.Get(key)
    if err == nil {
        data, err = item.ValueCopy(nil)  // ✅ Copies data
    }
    return err
})
```

**Analysis:** ✅ **CORRECT**
- Uses `ValueCopy()` to avoid holding transaction
- Proper error handling
- No transaction leaks

### Consistency Review

**Write Path:**
```go
// 1. Write to blob first
err := b.bucket.NewWriter(...)

// 2. Then update cache
if b.cache != nil {
    b.cache.Update(...)  // ← Error is logged but ignored
}
```

**Problem:** ⚠️ **INCONSISTENCY POSSIBLE**
- Blob write succeeds
- Cache update fails (disk full, corruption)
- → Cache becomes stale/inconsistent
- → Future reads get outdated data

**Severity:** LOW (cache is optional)

---

## 📊 CACHE EFFECTIVENESS ANALYSIS

### Question: Is the cache actually helping?

**Cache Purpose:** Speed up reads from blob storage

**Measurement Needed:**
```go
// Add metrics:
cacheHits := 0
cacheMisses := 0
readLatencyWithCache := []time.Duration{}
readLatencyWithoutCache := []time.Duration{}
```

**Current Metrics:** ❌ **NONE**

**We Don't Know:**
- Cache hit rate
- Read latency improvement
- Whether cache is worth 5.5GB

---

## 🎯 CRITICAL PROBLEMS SUMMARY

| # | Issue | Severity | Impact |
|---|-------|----------|--------|
| 1 | 5.5GB stale cache (March 2023) | HIGH | Disk waste |
| 2 | No garbage collection | HIGH | Unbounded growth |
| 3 | No TTL | MEDIUM | Stale data accumulates |
| 4 | No size limits | MEDIUM | Can fill disk |
| 5 | Double caching redundancy | LOW | Complexity |
| 6 | No invalidation strategy | MEDIUM | Bug fixes need manual intervention |
| 7 | No metrics/monitoring | LOW | Can't assess value |
| 8 | Inconsistency possible | LOW | Cache can become stale |

---

## 🔧 RECOMMENDED FIXES

### Fix #1: Clean Up Stale Cache (Immediate)
```bash
# Option A: Delete stale cache
rm -rf src/backend/cache/
# Cache will be recreated on next use

# Option B: Archive it
mv src/backend/cache/ src/backend/cache-2023-03-archived/
```

**Effort:** 1 minute  
**Impact:** Frees 5.5GB  
**Risk:** None (cache is optional)

### Fix #2: Add GC Routine (High Priority)
```go
// In blob/blob.go - Add method:
func (b *Bucket) RunGC(ctx context.Context) error {
    if b.cache == nil {
        return nil
    }
    
    ticker := time.NewTicker(5 * time.Minute)
    defer ticker.Stop()
    
    for {
        select {
        case <-ctx.Done():
            return ctx.Err()
        case <-ticker.C:
        again:
            err := b.cache.RunValueLogGC(0.7)
            if err == nil {
                goto again
            }
        }
    }
}
```

**Effort:** 30 minutes  
**Impact:** Prevents unbounded growth

### Fix #3: Configure Size Limits (Medium Priority)
```go
cacheOpts := badger.DefaultOptions(opt.Dir)
cacheOpts.ValueLogFileSize = 128 << 20  // 128MB per file (not 1GB)
cacheOpts.MemTableSize = 32 << 20        // 32MB (not 64MB)
cacheOpts.NumMemtables = 2               // Limit memory usage
cacheOpts.NumLevelZeroTables = 2         // Compact more aggressively
```

**Effort:** 10 minutes  
**Impact:** Reduces cache footprint

### Fix #4: Add TTL Support (Optional)
```go
// Set TTL on cache entries
err := b.cache.Update(func(txn *badger.Txn) error {
    entry := badger.NewEntry(key, data).WithTTL(24 * time.Hour)
    return txn.SetEntry(entry)
})
```

**Effort:** 15 minutes  
**Impact:** Automatic cleanup of old data

### Fix #5: Document When to Use Cache (Immediate)
```markdown
## When to Use --cache Flag

**Use when:**
- Reading from S3 repeatedly
- Running multiple analysis passes
- Large dataset with frequent access

**Don't use when:**
- Using file:// blob storage (redundant)
- One-time extraction
- Low disk space
- First time setup

**Default:** NO CACHE (let blob storage handle caching)
```

**Effort:** 5 minutes  
**Impact:** Prevents misuse

---

## 🤔 ARCHITECTURAL QUESTIONS

### Question 1: Should Cache Exist At All?

**For file:// buckets:**
- Blob storage: `data-full/` on disk
- Cache: Badger DB on disk
- **Net effect:** Disk → Disk → Memory
- **Value:** Minimal (both are disk I/O)

**For s3:// buckets:**
- Blob storage: S3 over network
- Cache: Badger DB on disk  
- **Net effect:** Network → Disk → Memory
- **Value:** HIGH (avoids network calls)

**Conclusion:** Cache valuable for S3, redundant for file://

### Question 2: Why Not Use Badger Directly?

**Current:** gocloud.dev/blob + optional Badger cache

**Alternative:** Badger for everything

**Why Current Approach:**
- Blob abstraction supports S3/GCS/Azure
- Cache is optional optimization
- Separation of concerns

**Verdict:** ✅ Current approach is sound (when cache is used properly)

### Question 3: Is 5.5GB Normal?

**Math Check:**
- 55,000 decks × ~2KB each ≈ 110MB of deck data
- 5.5GB cache = **50x larger than data**
- Something is very wrong

**Hypothesis:**
- Caching HTTP responses (large HTML pages)
- Caching parsed data
- Caching intermediate transforms
- Old data from experiments

**Needs Investigation:** What's actually in the cache?

---

## 🚨 IMMEDIATE ACTIONS REQUIRED

### Priority 0 (Do Now)
1. **Delete stale cache** - Free 5.5GB
   ```bash
   rm -rf src/backend/cache/
   ```

2. **Document cache usage** - Prevent misuse
   ```markdown
   # README: --cache flag is for S3 buckets, not file://
   ```

### Priority 1 (This Week)
3. **Add GC routine** - Prevent future unbounded growth
4. **Configure size limits** - Reduce memory footprint  
5. **Add metrics** - Measure cache effectiveness

### Priority 2 (Future)
6. **Add TTL support** - Automatic cleanup
7. **Add cache stats command** - Monitor cache health
8. **Consider removing cache** - If file:// only, might not need it

---

## 📊 CACHE LAYER ANALYSIS

### Two-Layer Caching Architecture

**Layer 1: HTTP Response Cache (Scraper → Blob)**
```
Location: data-full/scraper/
Format: {hostname}/{sha256}.json.zst
Size: 1.9GB
Purpose: Avoid re-fetching same HTTP response
Persistence: Permanent (until explicitly deleted)
```

**Layer 2: Blob Read Cache (Blob → BadgerDB)**
```
Location: cache/
Format: BadgerDB KV store
Size: 5.5GB (!!!)
Purpose: Speed up blob reads (S3 → local)
Persistence: Ephemeral (should be temporary)
```

### Cache Coherence Issues

**Scenario 1: Parser Bug Fixed**
```
1. Old cache has bad parse results
2. Fix parser code
3. Run with --reparse
4. Blob layer re-parses HTTP (good)
5. Badger cache still has old parse? (depends on key)
```

**Verdict:** ✅ Probably OK - cache keys include content hash

**Scenario 2: Cache Corruption**
```
1. Badger cache becomes corrupted
2. Reads fail
3. Falls back to blob storage
4. Operations continue
```

**Verdict:** ✅ Graceful degradation

---

## 💡 DESIGN QUESTIONS

### Is Double Caching a Problem?

**Intentional Design (Per User Principles):**
> "Caching pushed lower in stack"

**Architecture:**
```
HTTP → Scraper Cache (SHA256-keyed) → Badger Cache (optional)
       ↑ Persistent              ↑ Ephemeral
       Required                  Optional optimization
```

**Analysis:**
- ✅ Layered caching is intentional
- ✅ Each layer serves different purpose:
  - Scraper cache: HTTP deduplication (required)
  - Badger cache: I/O optimization (optional)
- ⚠️ But: Not configured properly (no GC, no TTL, stale)

### Should We Keep It?

**Arguments FOR:**
- Speeds up S3 reads significantly
- Reduces S3 API costs
- Optional (can disable)
- Clean abstraction

**Arguments AGAINST:**
- Not used in practice (file:// buckets)
- Adds complexity
- Requires maintenance (GC, TTL, monitoring)
- Current implementation broken (5.5GB stale data)

**Recommendation:** 
- **Keep the feature** (useful for S3)
- **Fix the implementation** (GC, TTL, size limits)
- **Document usage** (when to use --cache)
- **Clean up stale data** (delete March 2023 cache)

---

## 🧪 TESTING GAPS

### BadgerDB Cache Tests: ❌ **ZERO**

**Should Test:**
1. Cache hit/miss behavior
2. Write-through consistency
3. Graceful degradation on cache failure
4. GC behavior (after implementing)
5. TTL expiration (if implemented)
6. Size limits (if implemented)
7. Concurrent access

**Current:** ❌ None of this tested

**Risk:** Medium - cache is optional but could cause issues

---

## 📋 COMPREHENSIVE FIX PLAN

### Step 1: Clean Up (5 minutes)
```bash
# Delete stale cache
rm -rf src/backend/cache/

# Add to .gitignore if not already there
echo "cache/" >> src/backend/.gitignore
```

### Step 2: Configure Properly (15 minutes)
```go
// In blob.go:54
cacheOpts := badger.DefaultOptions(opt.Dir)

// Add size constraints
cacheOpts.ValueLogFileSize = 128 << 20      // 128MB per file
cacheOpts.MemTableSize = 32 << 20            // 32MB memory
cacheOpts.NumMemtables = 2                   // Limit concurrent tables
cacheOpts.NumLevelZeroTables = 2             // Compact more often
cacheOpts.ValueLogMaxEntries = 500000        // Limit value log size

// Add logger
cacheOpts.Logger = &badgerLogger{ctx, log}
```

### Step 3: Add GC (30 minutes)
```go
// Add method to Bucket
func (b *Bucket) StartGC(ctx context.Context) {
    if b.cache == nil {
        return
    }
    
    go func() {
        ticker := time.NewTicker(5 * time.Minute)
        defer ticker.Stop()
        
        for {
            select {
            case <-ctx.Done():
                return
            case <-ticker.C:
                // Run GC until no more work
                for {
                    err := b.cache.RunValueLogGC(0.7)
                    if err != nil {
                        break  // No more work or error
                    }
                }
            }
        }
    }()
}

// Call in NewBucket after opening cache
if cache != nil {
    bucket := &Bucket{...}
    bucket.StartGC(ctx)  // Start background GC
    return bucket, nil
}
```

### Step 4: Add Monitoring (20 minutes)
```go
// Add stats method
func (b *Bucket) CacheStats(ctx context.Context) map[string]interface{} {
    if b.cache == nil {
        return nil
    }
    
    lsmSize, vlogSize := b.cache.Size()
    
    return map[string]interface{}{
        "lsm_size_mb":  float64(lsmSize) / (1024 * 1024),
        "vlog_size_mb": float64(vlogSize) / (1024 * 1024),
        "total_mb":     float64(lsmSize+vlogSize) / (1024 * 1024),
    }
}
```

### Step 5: Document Usage (10 minutes)
- When to use --cache
- How cache works
- How to clean it up
- Performance impact

### Step 6: Add Tests (1 hour)
- Cache hit/miss
- Write-through behavior
- Graceful degradation
- GC behavior

**Total Effort:** 2-3 hours for complete fix

---

## 🎯 PRIORITY MATRIX

### P0 (Do Now) - 5 minutes
- [ ] Delete stale 5.5GB cache
- [ ] Add cache/ to .gitignore
- [ ] Document not to use --cache with file:// buckets

### P1 (This Week) - 2 hours
- [ ] Configure size limits
- [ ] Implement GC routine
- [ ] Add monitoring/stats
- [ ] Test cache behavior

### P2 (Future) - 2 hours
- [ ] Add TTL support
- [ ] Add cache admin commands
- [ ] Performance benchmarks
- [ ] Consider removing if file:// only

---

## 🔬 DEEPER ISSUES DISCOVERED

### Issue #8: Cache Key Design

**Current:**
```go
func (b *Bucket) cacheKey(key string) []byte {
    return []byte(b.prefix + key)
}
```

**Analysis:**
- Keys include prefix (games/, scraper/, etc.)
- Keys include .zst extension
- No versioning in keys
- No TTL metadata

**Potential Problem:**
- Parser version changes don't invalidate cache
- Would need to delete entire cache or use --reparse

**Severity:** LOW (reparse flag handles this)

### Issue #9: No Cache Warmup

**Observation:** Cache starts cold

**Impact:** First access always misses

**Opportunity:** Could pre-warm cache for common operations

**Priority:** LOW (not critical)

### Issue #10: Transaction Retries

**Code:**
```go
err := b.cache.Update(func(txn *badger.Txn) error {
    return txn.Set(key, data)
})
```

**Problem:** No retry on `ErrConflict`

**BadgerDB Recommendation:**
```go
for {
    err := db.Update(func(txn *badger.Txn) error { ... })
    if err != badger.ErrConflict {
        return err
    }
    // Retry on conflict
}
```

**Current:** ❌ No retries

**Impact:** LOW (writes are mostly independent)

---

## 📝 HARMONIZATION IMPLICATIONS

**From HARMONIZATION_COMPLETE.md:**
> "Successfully harmonized... all export tools, analysis tools, and ML utilities updated"

**Cache Harmonization Status:** ❌ **NOT ADDRESSED**

**Questions:**
1. Is cache being used for new source tracking?
2. Do cached entries have old schema?
3. Does cache need invalidation for harmonization?

**Answer:** Cache is **optional** and **not used** in current operations, so harmonization wasn't affected.

**But:** If cache were enabled, old cached data would lack new fields!

---

## ✅ FINAL RECOMMENDATIONS

### Immediate (5 min)
1. ✅ **Delete stale cache** - rm -rf cache/
2. ✅ **Document cache flag** - When to use, when not to

### Short-term (2-3 hours)
3. ⚠️ **Add GC routine** - Prevent unbounded growth
4. ⚠️ **Configure size limits** - Reduce memory footprint
5. ⚠️ **Add cache stats** - Monitor effectiveness
6. ⚠️ **Add tests** - Verify cache behavior

### Long-term (Future)
7. 💡 **Add TTL** - Automatic cleanup
8. 💡 **Add metrics** - Measure hit rate
9. 💡 **Consider removal** - If file:// only, might not need it
10. 💡 **Add admin commands** - Cache management tools

---

## 🎓 LESSONS LEARNED

1. **Optional features still need maintenance** - Cache has been rotting for 2 years
2. **Defaults aren't always safe** - BadgerDB DefaultOptions has no limits
3. **Measure effectiveness** - Don't know if cache helps without metrics
4. **Documentation matters** - Users don't know when to use --cache
5. **Double caching needs justification** - Each layer should have clear value

---

**Analysis Date:** October 4, 2025  
**Cache Age:** March 18, 2023 (19+ months old!)  
**Cache Size:** 5.5GB  
**Issues Found:** 10  
**Critical Issues:** 4  
**Recommended Action:** Clean up immediately, fix implementation before re-enabling

**Status:** ⚠️ **BROKEN** (stale, unbounded, unmaintained)  
**Impact:** LOW (not currently used)  
**Fix Effort:** 2-3 hours for complete solution
