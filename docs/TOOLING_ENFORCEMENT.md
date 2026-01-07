# Tooling Enforcement for Architecture Improvements

This document describes the tooling we've added to enforce the architectural improvements we've implemented.

## Overview

We've added multiple layers of enforcement:

1. **Pre-commit hooks** - Fast checks on every commit
2. **Custom validation scripts** - Detect unsafe patterns
3. **Unit tests** - Verify functionality works correctly
4. **Type checking** - Catch schema issues at development time

## Pre-commit Hooks

### Hardcoded Paths Check (Blocking)

**Hook**: `check-hardcoded-paths`
**Status**: Blocking (fails commit)
**Location**: `.pre-commit-config.yaml`

Checks for hardcoded paths like `Path("data/")` that should use `PATHS` utility.

```bash
# Runs automatically on commit
# Or manually: pre-commit run check-hardcoded-paths
```

### Lineage Usage Check (Non-blocking)

**Hook**: `check-lineage-usage`
**Status**: Non-blocking (warns only)
**Location**: `.pre-commit-config.yaml`

Detects direct writes to data directories that should use `safe_write` context manager.

```bash
# Runs automatically on commit
# Or manually: pre-commit run check-lineage-usage
```

**What it checks**:
- `open(..., "w")` to data directories
- `.to_csv()` to data directories
- `json.dump()` to data directories
- Direct `Path.write_text()` to data directories

**Exclusions**:
- Test files
- Validation scripts themselves
- The lineage module itself

### Schema Validation Check (Non-blocking)

**Hook**: `check-schema-validation`
**Status**: Non-blocking (warns only)
**Location**: `.pre-commit-config.yaml`

Detects deck loading without schema validation.

```bash
# Runs automatically on commit
# Or manually: pre-commit run check-schema-validation
```

**What it checks**:
- `json.loads()` / `json.load()` of deck-like data
- Missing `validate_deck_record` or `DeckExport` imports

## Custom Validation Scripts

### `scripts/validation/check_lineage_usage.py`

Scans Python files for unsafe data writes. Can be run standalone:

```bash
python3 scripts/validation/check_lineage_usage.py <file1> [file2] ...
```

**Usage in CI**:
```yaml
# .github/workflows/ci.yml (if using GitHub Actions)
- name: Check lineage usage
  run: |
    python3 scripts/validation/check_lineage_usage.py $(git diff --name-only HEAD origin/main | grep '\.py$')
```

### `scripts/validation/check_schema_validation.py`

Scans Python files for unvalidated deck loads. Can be run standalone:

```bash
python3 scripts/validation/check_schema_validation.py <file1> [file2] ...
```

## Unit Tests

### `tests/test_lineage_validation.py`

Tests for lineage validation functionality:

- `test_validate_write_path_order_0()` - Rejects Order 0 writes
- `test_validate_write_path_order_1()` - Allows Order 1 writes
- `test_safe_write_success()` - Successful safe_write
- `test_safe_write_strict_mode()` - Strict mode raises on violation
- `test_get_order_for_path()` - Order inference

**Run tests**:
```bash
pytest tests/test_lineage_validation.py -v
```

### `tests/test_schema_validation.py`

Tests for schema validation functionality:

- `test_valid_deck_record()` - Valid deck passes
- `test_invalid_deck_empty_cards()` - Empty cards rejected
- `test_backward_compatibility_aliases()` - Timestamp aliases work
- `test_export_version_default()` - Default version handling

**Run tests**:
```bash
pytest tests/test_schema_validation.py -v
```

## Type Checking

### Pydantic Models

The `DeckExport` model provides type safety:

```python
from src.ml.data.export_schema import DeckExport

# Type-checked at runtime
deck = DeckExport(**data)  # Validates structure
```

### Future: Static Type Checking

Consider adding `mypy` or `pyright` for static type checking:

```toml
# pyproject.toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
```

## CI Integration

### Recommended CI Checks

1. **Pre-commit hooks** (fast, runs on every commit)
2. **Unit tests** (runs on push/PR)
3. **Lineage validation** (runs on PR)
4. **Schema validation** (runs on PR)

### Example GitHub Actions Workflow

```yaml
name: CI

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install pre-commit
      - run: pre-commit run --all-files

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: pytest tests/test_lineage_validation.py tests/test_schema_validation.py -v
```

## Gradual Enforcement Strategy

### Phase 1: Non-blocking (Current)

- Lineage usage check: Warns only
- Schema validation check: Warns only
- Hardcoded paths: Blocks (already fixed)

**Rationale**: Many existing files don't use new patterns yet. Non-blocking allows gradual migration.

### Phase 2: Blocking (Future)

Once most files are migrated:

1. Make lineage check blocking
2. Make schema validation check blocking
3. Add to CI as required checks

**Migration path**:
- Fix files as you touch them
- Run checks manually: `pre-commit run --all-files`
- Track progress with grep: `rg "safe_write" --type py | wc -l`

## Usage Examples

### Using safe_write

```python
from ml.utils.lineage import safe_write

# Before (unsafe):
with open("data/processed/decks.jsonl", "w") as f:
    json.dump(decks, f)

# After (safe):
with safe_write(Path("data/processed/decks.jsonl"), order=1, strict=False) as path:
    with open(path, "w") as f:
        json.dump(decks, f)
```

### Using schema validation

```python
from ml.data.export_schema import validate_deck_record

# Before (unvalidated):
deck = json.loads(line)

# After (validated):
deck = json.loads(line)
is_valid, error, validated = validate_deck_record(deck, strict=False)
if not is_valid:
    logger.warning(f"Invalid deck: {error}")
    continue
deck = validated  # Use validated version
```

## Monitoring

### Check Coverage

```bash
# Count files using safe_write
rg "safe_write" --type py | wc -l

# Count files using schema validation
rg "validate_deck_record" --type py | wc -l

# Count unsafe writes (should decrease over time)
python3 scripts/validation/check_lineage_usage.py $(fd -e py) | wc -l
```

### Pre-commit Statistics

```bash
# Run all checks
pre-commit run --all-files

# See what would fail
pre-commit run --all-files --hook-stage commit
```

## Future Enhancements

1. **Ruff custom rules** - Add AST-based checks for safe_write usage
2. **Type stubs** - Generate mypy stubs from Pydantic models
3. **CI dashboard** - Track adoption metrics over time
4. **Auto-fix** - Scripts to automatically migrate code

## Summary

We now have:

✅ **Pre-commit hooks** - Fast feedback on every commit
✅ **Custom validators** - Detect unsafe patterns
✅ **Unit tests** - Verify functionality
✅ **Type safety** - Pydantic models for schema validation
⏳ **CI integration** - Ready to add to CI/CD pipeline

The tooling is designed to be:
- **Non-intrusive** - Non-blocking for existing code
- **Gradual** - Can migrate files over time
- **Actionable** - Clear error messages with fixes
- **Fast** - Only checks changed files by default
