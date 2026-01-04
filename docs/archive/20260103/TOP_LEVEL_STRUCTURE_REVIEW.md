# Top-Level Structure Review - January 2025

## Summary

After cleanup: **7 files, 6 directories** at top level.

## Completed Cleanup

1. ✅ Moved `packages/decksage-ts/` to archive (was marked archived but still at top level)
2. ✅ Added `bin/` (38MB) and `archive/` (1.7GB) to `.gitignore`
3. ✅ Moved `assets/` → `docs/assets/` (1.8MB, only used in HTML generation)
4. ✅ Moved `deploy/` → `docs/deploy/` (18MB deployment docs)
5. ✅ Made `runctl.toml` visible (was `.runctl.toml`, updated runctl to support both)
6. ✅ Removed 9 unnecessary items (games/, tests/, Makefile, api.py, etc.)

## Final Structure

### Files (7)
- `Dockerfile.api`, `README.md`, `fly.toml`, `justfile`, `pyproject.toml`, `runctl.toml`, `uv.lock`

### Directories (6)
- `annotations/` (1.6MB) - Annotation data
- `data/` (11GB) - Primary data
- `docs/` (21MB) - Documentation (includes assets, deploy)
- `experiments/` (5.5MB) - Evaluation artifacts
- `scripts/` (804KB) - Utility scripts
- `src/` (9.9GB) - Source code

## Research: Monorepo Best Practices

Research suggests nesting `data/`, `experiments/`, `annotations/` under services/libs, but:
- **164 files** use top-level paths via `PATHS` abstraction
- Heavy cross-component usage (Go backend + Python ML)
- Operational simplicity for scripts/runctl
- Migration would be complex (8-16 hours)

## Recommendation

**Keep current structure** - The operational benefits outweigh theoretical nesting benefits. Heavy usage justifies top-level placement.

## Path Usage

- 304 matches across 119 files use `PATHS` from `src/ml/utils/paths.py`
- Centralized path management is good practice
- Some hardcoded paths remain (migrate gradually to `PATHS`)
