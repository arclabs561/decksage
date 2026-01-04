# Docker Build Cache Strategy

This document details the aggressive caching strategy used in the Dockerfile for maximum build performance.

## Cache Mounts Used

### 1. UV Package Manager Cache

```dockerfile
--mount=type=cache,target=/root/.cache/uv,id=uv-cache
```

**Purpose:** Caches uv's package downloads and metadata
**Location:** `/root/.cache/uv`
**Benefits:**
- Packages downloaded once, reused across builds
- Metadata cached for faster dependency resolution
- Dramatically faster rebuilds when dependencies haven't changed

### 2. Pip Cache (General)

```dockerfile
--mount=type=cache,target=/root/.cache/pip,id=pip-cache
```

**Purpose:** General pip cache directory
**Location:** `/root/.cache/pip`
**Benefits:**
- Fallback cache for pip operations
- Shared with other pip caches

### 3. Pip Wheels Cache

```dockerfile
--mount=type=cache,target=/root/.cache/pip/wheels,id=pip-wheels
```

**Purpose:** Caches built wheel files
**Location:** `/root/.cache/pip/wheels`
**Benefits:**
- Pre-built wheels reused across builds
- Avoids rebuilding wheels from source
- Faster installs for packages that need compilation

### 4. Pip HTTP Cache

```dockerfile
--mount=type=cache,target=/root/.cache/pip/http,id=pip-http
```

**Purpose:** Caches HTTP responses from PyPI
**Location:** `/root/.cache/pip/http`
**Benefits:**
- Caches package index responses
- Reduces network requests
- Faster dependency resolution

### 5. UV Data Directory

```dockerfile
--mount=type=cache,target=/root/.local/share/uv,id=uv-data
```

**Purpose:** Caches uv's internal data (Python versions, toolchains, etc.)
**Location:** `/root/.local/share/uv`
**Benefits:**
- Caches Python version downloads
- Caches toolchain data
- Faster Python environment setup

## Cache ID Strategy

Each cache mount has a unique `id` parameter:
- `uv-cache` - UV package cache
- `pip-cache` - General pip cache
- `pip-wheels` - Pip wheels cache
- `pip-http` - Pip HTTP cache
- `uv-data` - UV data directory

**Benefits of unique IDs:**
- Caches are isolated and don't interfere
- Can be cleared individually if needed
- Better cache hit rates
- Easier debugging

## Cache Persistence

All caches persist across builds:
- **Same builder:** Caches shared between builds
- **Different builders:** Caches isolated per builder
- **Cache lifetime:** Until builder is destroyed or cache is cleared

## Cache Invalidation

Caches are invalidated when:
1. **Builder is destroyed:** All caches cleared
2. **Manual cache clear:** `fly builder destroy` or cache clear command
3. **Cache size limit:** Old entries evicted (automatic)

## Performance Impact

### First Build
- No cache hits
- All packages downloaded
- Build time: ~5 minutes (baseline)

### Subsequent Builds (No Changes)
- All caches hit
- Minimal network activity
- Build time: ~30 seconds (90% faster)

### Code Changes Only
- Dependency caches hit
- Only source code copied
- Build time: ~1 minute (80% faster)

### Dependency Changes
- Partial cache hits (unchanged packages)
- Only new/changed packages downloaded
- Build time: ~2 minutes (60% faster)

## Cache Size Management

Caches grow over time but are automatically managed:
- **Old entries evicted:** LRU (Least Recently Used) eviction
- **Size limits:** Per-cache size limits prevent unbounded growth
- **Manual cleanup:** Can clear caches if needed

## Monitoring Cache Performance

### Check Cache Usage

```bash
# Deploy and watch for cache hits
fly deploy -a decksage --verbose

# Look for these indicators:
# - "CACHED" in build logs
# - Fast dependency installation
# - Minimal network activity
```

### Verify Cache Mounts

```bash
# Check build logs for cache mount usage
fly logs -a decksage | grep -i cache

# Look for:
# - Cache mount targets
# - Cache hit/miss indicators
# - Download speeds
```

## Troubleshooting

### Cache Not Working

1. **Check BuildKit is enabled:**
   ```bash
   DOCKER_BUILDKIT=1 docker build .
   ```

2. **Verify cache mounts in Dockerfile:**
   - Look for `--mount=type=cache` entries
   - Check cache IDs are unique
   - Verify cache targets are correct

3. **Check builder status:**
   ```bash
   fly builder status
   ```

### Cache Too Large

1. **Clear specific cache:**
   ```bash
   # Destroy builder (clears all caches)
   fly builder destroy
   ```

2. **Rebuild with fresh cache:**
   ```bash
   fly deploy -a decksage --no-cache
   ```

### Slow Builds Despite Cache

1. **Check network speed:**
   - Slow network = slow downloads even with cache
   - Cache helps but network still matters

2. **Verify cache hits:**
   - Check build logs for cache usage
   - Verify cache mounts are working

3. **Check dependency changes:**
   - Large dependency changes = more downloads
   - Cache helps but can't eliminate all downloads

## Best Practices

1. ✅ **Use unique cache IDs** - Prevents cache conflicts
2. ✅ **Cache at multiple levels** - Package cache + wheel cache + HTTP cache
3. ✅ **Order layers correctly** - Dependencies before source code
4. ✅ **Monitor cache performance** - Track cache hit rates
5. ✅ **Clear caches when needed** - Don't let caches grow unbounded

## References

- [Docker Cache Mounts](https://docs.docker.com/reference/dockerfile/#run---mounttypecache)
- [UV Documentation](https://docs.astral.sh/uv/)
- [Pip Cache Documentation](https://pip.pypa.io/en/stable/topics/caching/)
