# Architecture Review - Data Storage & ML/Backend Split

## Current State Analysis

### ✅ What's Actually Working

**Badger is ALREADY in use** (dgraph/dgo is NOT used):
1. **`blob/blob.go`** (438 lines) - Blob storage cache using Badger
2. **`transform/cardco/transform.go`** (300 lines) - Card co-occurrence using Badger

**`magic/store/store.go`** (44 lines) - Dgraph wrapper that's DISABLED:
- Contains `// TODO: Re-enable when dgraph is configured`
- Returns `nil` immediately, never actually uses dgraph
- **Should be removed or properly implemented**

### 🏗️ Current Architecture

```
Data Flow:
┌─────────────────────────────────────────────────────────────┐
│                    GO BACKEND                               │
│  1. Scrape data from sources (Scryfall, MTGTop8, etc.)    │
│  2. Store in blob storage (file:// or s3://)              │
│  3. Cache with Badger (local KV store)                     │
│  4. Transform to card co-occurrence graph                  │
│  5. Export to CSV (pairs.csv)                              │
│                                                             │
│  Storage:                                                   │
│  - Badger: Cache & temporary transforms (745MB)            │
│  - Blob: Persistent scraped data (file:// URLs)            │
│  - CSV export: Bridge to Python                            │
└─────────────────────────────────────────────────────────────┘
                          ↓ pairs.csv
┌─────────────────────────────────────────────────────────────┐
│                    PYTHON ML                                │
│  1. Load pairs.csv                                          │
│  2. Build graph edgelist                                    │
│  3. Train Node2Vec embeddings (PecanPy)                    │
│  4. Evaluate with metrics                                   │
│  5. Serve via FastAPI                                       │
│                                                             │
│  Storage:                                                   │
│  - CSV input (from Go)                                      │
│  - .wv embeddings (Gensim KeyedVectors)                    │
│  - Experiments (JSONL, YAML)                                │
└─────────────────────────────────────────────────────────────┘
```

### 📊 Dependency Analysis

**go.mod shows:**
- ✅ `badger/v3` - ACTIVELY USED (cache + transforms)
- ❌ `dgo/v210` (dgraph client) - NOT USED (commented out)
- ✅ `meilisearch-go` - Listed but usage unclear
- ✅ `gocloud.dev` - Blob abstraction (file:// + s3://)

### 🎯 ML/Backend Responsibility Split

**Current split is GOOD:**

| Component | Language | Responsibility | Why |
|-----------|----------|----------------|-----|
| **Scraping** | Go | HTTP, rate limiting, caching | Concurrency, performance |
| **Storage** | Go | Blob abstraction, zstd compression | Type safety, S3 integration |
| **Transforms** | Go | Collection → Graph edges | Streaming, memory efficiency |
| **Graph ML** | Python | Node2Vec, embeddings | ML ecosystem (Gensim, sklearn) |
| **Evaluation** | Python | Metrics, baselines | NumPy, Pandas, visualization |
| **API** | Python | Similarity search | FastAPI, easy integration |

**Boundary:** CSV files (clean, simple, universal)

### 🚨 Issues Found

1. **Unused dgraph code** - 44 lines doing nothing
2. **Import errors** - `api` package imported but not used
3. **Lock copying** - `ResolvedUpdateOptions` passed by value (has mutex)
4. **745MB cache** - Badger cache in src/backend/ (should be in data/)

### 💡 Recommendations

## Option 1: Keep Current (Recommended)

**Do:**
- ✅ Remove dgraph/dgo dependency entirely
- ✅ Keep Badger for cache + transforms
- ✅ Keep CSV as ML/backend boundary
- ✅ Move cache to `data/cache/`
- ✅ Add cache cleanup command

**Rationale:**
- Badger works well for temporary KV storage
- No need for graph database (CSV → Python handles graph)
- Simpler dependency chain
- Current split is well-designed

## Option 2: Add SQLite (If needed)

**Only add IF you need:**
- Persistent queryable storage
- Relational queries on cards/collections
- Complex joins

**Use cases:**
- Card database with full-text search
- Deck archetype classification
- Tournament result tracking

**Don't use SQLite for:**
- Cache (Badger is faster)
- Scraping results (Blob is better)
- Graph data (CSV → Python is cleaner)

## Option 3: Meilisearch (Already present)

**Purpose:** Full-text search on cards
- Already in dependencies
- Check if actually used (`meilisearch.go` files?)
- If unused, consider removing

## 🔧 Action Items

### High Priority

1. **Fix linter errors:**
   ```go
   // Change ResolvedUpdateOptions to pointer
   func Do(ctx, sc, opts *ResolvedUpdateOptions, req) 
   ```

2. **Remove unused dgraph code:**
   ```bash
   # Option A: Delete store.go entirely
   rm src/backend/games/magic/store/store.go
   
   # Option B: Remove dgraph, keep Store skeleton for future
   # (Keep the file but remove dgraph imports)
   ```

3. **Clean up go.mod:**
   ```bash
   cd src/backend
   go mod tidy  # Remove unused dgraph dependency
   ```

4. **Move cache:**
   ```bash
   # Already in .gitignore, just document it
   echo "Cache location: data/cache/ or src/backend/cache/"
   ```

### Medium Priority

5. **Add cache management:**
   ```go
   // cmd/cache-clean/main.go
   // Clear old Badger cache
   ```

6. **Document data flow:**
   ```
   README.md: Add "Data Flow" section
   ```

7. **Check Meilisearch usage:**
   ```bash
   grep -r "meilisearch" src/backend/
   # If unused, remove from go.mod
   ```

### Low Priority

8. **Consider SQLite IF:**
   - You want persistent card database
   - Need complex queries
   - Want local development DB

## ✅ Quality Validation Results

### Go Backend
- ✅ All tests passing
- ⚠️ 4 linter warnings (mutex copying)
- ⚠️ 1 unused import (dgraph api)
- ⚠️ 1 unreachable code (store.go)

### Python ML
- ✅ Scripts follow clean architecture
- ✅ Proper separation (train/eval/serve)
- ✅ FastAPI for production

### Data Flow
- ✅ CSV boundary is clean
- ✅ Badger for ephemeral storage
- ✅ Blob for persistent storage
- ✅ Python owns embeddings

## 🎯 Summary

**The current architecture is GOOD:**
1. Go handles system programming (HTTP, concurrency, storage)
2. Python handles ML (graph algorithms, embeddings, evaluation)
3. CSV is a clean, universal boundary
4. Badger serves its purpose (cache + transforms)

**Don't add SQLite unless you have a clear use case** for relational queries. The current setup works well.

**Do clean up:**
- Remove dgraph code (not used)
- Fix mutex copying
- Run `go mod tidy`

**Grade:** B+ (8/10)
- Architecture: A (9/10) - Well designed split
- Implementation: B (7.5/10) - Some unused code, minor issues
- Testing: A- (8.5/10) - Tests pass, good coverage

