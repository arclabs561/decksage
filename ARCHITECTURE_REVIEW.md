# DeckSage Architecture Review

**Date**: 2025-01-XX  
**Reviewer**: AI Assistant  
**Scope**: Overall system architecture, component interactions, data flow, and design decisions

---

## Executive Summary

DeckSage is a multi-modal card similarity system with a well-structured data lineage system and sophisticated fusion architecture. The system demonstrates strong separation of concerns but has several integration points that lack formal contracts, and the fusion system's complexity may be premature given current performance constraints.

**Overall Assessment**: Solid foundation with clear architectural vision, but integration boundaries need strengthening and some complexity should be deferred until core metrics improve.

---

## Architecture Overview

### System Components

```
┌─────────────────┐
│  Go Backend     │  Data extraction, scraping, export
│  (src/backend)  │  → Exports JSONL/CSV files
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Python ML      │  Training, embeddings, fusion
│  (src/ml)       │  → Generates embeddings, models
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FastAPI Server │  Similarity search, deck completion
│  (src/ml/api)   │  → Serves queries
└─────────────────┘
```

### Data Flow (7-Order Lineage)

```
Order 0: Raw data (immutable, S3/local)
  ↓ [Go export tools]
Order 1: Exported decks (JSONL)
  ↓ [Python pair generation]
Order 2: Co-occurrence pairs (CSV)
  ↓ [Graph construction]
Order 3: Incremental graph (SQLite/JSON)
  ↓ [Training]
Order 4: Embeddings (.wv, .json)
  ↓ [Evaluation/Annotation]
Order 5: Test sets (JSON)
Order 6: Annotations (JSONL)
```

---

## Strengths

### 1. Data Lineage System

**Excellent design**: The 7-order hierarchy with explicit dependencies and immutability rules for Order 0 is well-conceived.

- Clear dependency chain (each order depends only on previous)
- Order 0 immutability prevents accidental corruption
- Validation script exists (`validate_lineage.py`)
- Documentation is clear (`docs/DATA_LINEAGE_FLOW.txt`)

**Implementation**: `src/ml/utils/lineage.py` provides validation utilities, though enforcement is advisory rather than mandatory.

### 2. Path Centralization

**Good practice**: `PATHS` utility (`src/ml/utils/paths.py`) centralizes all file paths, preventing hardcoded paths throughout codebase.

- Single source of truth for data locations
- Environment variable override support (`DECKSAGE_ROOT`)
- Works with runctl execution context

**Issue**: Not all code uses `PATHS` yet (see "Hardcoded Paths" below).

### 3. Multi-Modal Fusion Architecture

**Sophisticated**: `WeightedLateFusion` combines 6+ signals with configurable weights:

- GNN embeddings (30%)
- Instruction-tuned embeddings (25%)
- Co-occurrence embeddings (20%)
- Visual embeddings (20%)
- Jaccard similarity (15%)
- Functional tags (10%)

**Design**: Supports multiple aggregation methods (weighted, RRF, CombMNZ, MMR), task-specific weights, and adaptive visual weight adjustment.

**Concern**: Complexity may be premature given P@10 = 0.08 plateau (see "Premature Complexity" below).

### 4. Separation of Concerns

**Clear boundaries**: Go backend handles data extraction, Python ML handles training/inference, FastAPI serves queries.

- Go backend: Fast, concurrent data processing
- Python ML: Rich ML ecosystem, experimentation
- API layer: Clean REST interface

---

## Critical Issues

### 1. Go/Python Integration Contract

**Problem**: No formal schema or versioning between Go exports and Python consumption.

**Current State** (from code inspection):
- Go exports JSONL with structure: `DeckRecord` with `cards[]`, `format`, `archetype`, etc. (see `src/backend/cmd/export-hetero/main.go:17-35`)
- Python reads with `json.loads(line)` and assumes fields exist (see `src/ml/utils/data_loading.py:272`)
- Python code uses defensive `.get()` calls but no schema validation
- No versioning metadata in exported JSONL files
- Go export structure has evolved (comments show "FIXED" for structure changes)

**Evidence from Code**:
```go
// src/backend/cmd/export-hetero/main.go:17-35
type DeckRecord struct {
    DeckID     string       `json:"deck_id"`
    Cards      []CardInDeck `json:"cards"`
    Format     string       `json:"format"`
    // ... more fields
}
```

```python
# src/ml/utils/data_loading.py:272-286
deck = json.loads(line)  # No validation
deck.get("source")  # Assumes structure
deck.get("format")  # No schema check
```

**Actual Risk**: 
- Go code has "FIXED" comments indicating structure changes (line 93, 107)
- Python code assumes `cards` array exists but doesn't validate
- If Go changes field names or structure, Python will fail silently or with cryptic errors

**Recommendation**:
1. **Immediate**: Add JSON Schema validation in Python before processing (validate first 10 lines on load)
2. **Short-term**: Include export version in Go output (add `"export_version": "1.0"` to each record)
3. **Medium-term**: Shared schema definition (JSON Schema file, validate in both Go and Python)
4. **Long-term**: Consider Protobuf or similar for type-safe contracts

### 2. Fusion System Complexity vs. Performance

**Problem**: Sophisticated fusion system (6+ signals, multiple aggregation methods) while core performance is P@10 = 0.08.

**Current State** (from code inspection):
- `WeightedLateFusion` supports 10+ signals (see `src/ml/similarity/fusion.py:45-67`)
- Signals loaded in API: embeddings, graph, text_embedder, visual_embedder, gnn_embedder, sideboard, temporal, archetype, format (see `src/ml/api/api.py:602-621`)
- **All signals are optional** - graceful degradation (returns 0.0 if None)
- Many signals may be None at runtime if files don't exist

**Evidence from Code**:
```python
# src/ml/api/load_signals.py:100-112
if sideboard_path.exists():
    state.sideboard_cooccurrence = json.load(f)
else:
    state.sideboard_cooccurrence = None  # Graceful degradation
```

```python
# src/ml/similarity/fusion.py:234-242
def _get_jaccard_similarity(self, query: str, candidate: str) -> float:
    if not self.adj or query not in self.adj:
        return 0.0  # Returns 0 if missing
```

**Actual Assessment**: 
- Architecture is sound - optional signals with graceful degradation
- But complexity may be premature if signals aren't actually loaded/used
- Need to verify which signals are actually available at runtime

**Reality** (from `experimental/REALITY_FINDINGS.md`):
- Co-occurrence alone maxes at P@10 ≈ 0.08
- Format-specific filtering makes it worse (P@10 = 0.0045 for Modern-only)
- Papers achieve 0.42 with multi-modal features (text, images, meta stats)

**Recommendation**:
1. **Immediate**: Add logging to show which signals are actually loaded at API startup
2. **Short-term**: Measure individual signal contributions (which signals are non-zero?)
3. **Focus**: Add text embeddings (biggest performance lever) - code supports it but may not be enabled
4. **Revisit**: Advanced fusion methods when P@10 > 0.15 and signals are proven

### 3. Hardcoded Paths Still Exist

**Problem**: Despite `PATHS` utility, some code still uses hardcoded paths.

**Evidence from Code**:
```python
# src/ml/scripts/evaluate_downstream_complete.py:231, 277
pairs_path = Path("src/backend/pairs.csv")  # Hardcoded!
```

**Actual Impact**: 
- Found 2 instances in `evaluate_downstream_complete.py`
- Most code correctly uses `PATHS` utility
- These are in evaluation scripts (lower risk but still violates rules)

**Recommendation**:
1. **Immediate**: Fix the 2 instances found: use `PATHS.backend / "pairs.csv"` or better, `PATHS.pairs_large`
2. **Short-term**: Add ruff rule to detect `Path("data/")`, `Path("experiments/")`, `Path("src/")` patterns
3. **Medium-term**: Pre-commit hook to block hardcoded paths

### 4. Data Lineage Enforcement is Advisory

**Problem**: Lineage rules are documented and validated, but not enforced at runtime.

**Current State** (from code inspection):
- `src/ml/utils/lineage.py` provides `validate_write_path()` function
- `scripts/data_processing/validate_lineage.py` exists but is separate script
- **No actual calls to `validate_write_path()` found in data processing code**
- Scripts can write anywhere without validation

**Evidence**:
```python
# src/ml/utils/lineage.py:65-88
def validate_write_path(path: str | Path, order: int) -> tuple[bool, str | None]:
    # Function exists but...
```

**Grep results**: No files call `validate_write_path()` except the lineage.py file itself.

**Actual Risk**: Scripts could accidentally write to Order 0 locations (immutable data).

**Recommendation**:
1. **Immediate**: Add `validate_write_path()` calls in key data processing scripts:
   - `scripts/data_processing/unified_export_pipeline.py` (Order 1 writes)
   - `scripts/data_processing/generate_pairs_for_games.py` (Order 2 writes)
   - Graph update scripts (Order 3 writes)
2. **Short-term**: Create context manager for safe writes:
   ```python
   with safe_write(path, order=2):
       # write operations
   ```
3. **Medium-term**: CI check that runs `validate_lineage.py` before merges

### 5. Test Set Size Insufficient

**Problem**: Small test sets (38 MTG, 10 Pokemon, 13 Yu-Gi-Oh) limit evaluation confidence.

**Current State**:
- Test sets in `experiments/test_set_unified_*.json`
- Evaluation uses these for P@K, MRR, NDCG
- But sample sizes too small for statistical significance

**Impact**: Can't confidently measure improvements (e.g., is 0.08 vs 0.09 statistically significant?).

**Recommendation** (from priority matrix):
1. Expand test set to 100+ queries per game
2. Use confidence intervals in evaluation reports
3. Consider bootstrap resampling for small samples

---

## Design Concerns

### 1. API State Management

**Observation**: `src/ml/api/api.py` uses FastAPI's `app.state` pattern for state management.

**Actual Implementation** (from code):
```python
# src/ml/api/api.py:215-220
def get_state() -> ApiState:
    state = getattr(app.state, "api", None)
    if state is None:
        state = ApiState()
        app.state.api = state
    return state
```

**State Loading** (from code):
```python
# src/ml/api/api.py:338-380
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load on startup
    load_embeddings_to_state(emb_path, pairs_path)
    load_signals_to_state(...)
    yield
    # Cleanup on shutdown
```

**Actual Assessment**:
- Uses FastAPI's recommended `app.state` pattern (not global variables)
- State loaded in lifespan handler (proper async pattern)
- **Issue**: With multiple uvicorn workers, each worker loads state independently (memory duplication)
- **Issue**: No easy way to test with different state configurations

**Recommendation**:
1. **Document**: Add note about worker configuration (single worker recommended, or shared memory)
2. **Testing**: Add fixture to inject test state for unit tests
3. **Optional**: Consider dependency injection with `Depends()` for testability (lower priority)

### 2. Experimental Code Organization

**Observation**: `src/ml/experimental/` contains sophisticated techniques (A-Mem, meta-learning) that are "premature" per README.

**Assessment**: Good self-awareness. The code is archived rather than deleted, which is appropriate.

**Recommendation**: Continue this pattern—archive rather than delete, but don't activate until foundation is solid.

### 3. Multiple Similarity Method Implementations

**Observation**: Multiple similarity implementations exist:
- `src/ml/similarity/similarity_methods.py`
- `src/ml/similarity/fusion.py`
- `src/ml/similarity/fusion_integration.py`
- Various signal-specific files (archetype_signal.py, format_signal.py, etc.)

**Assessment**: Some duplication, but mostly appropriate separation of concerns (each signal in its own file).

**Recommendation**: Document the relationship between these files clearly. Consider a similarity method registry pattern if more methods are added.

### 4. Go Backend Structure

**Observation**: Go backend has many small command tools (`cmd/export-*`, `cmd/analyze-*`).

**Assessment**: Good Unix philosophy (small, focused tools), but:
- No shared library for common operations
- Each tool reimplements similar logic
- Hard to maintain consistency

**Recommendation** (lower priority):
1. Extract common operations to shared package
2. Use shared validation/error handling
3. Consider single tool with subcommands (cobra CLI framework)

---

## Recommendations by Priority

### High Priority (Address Soon)

1. **Add schema validation to Go/Python boundary**
   - **Immediate**: Validate JSONL structure in Python before processing (check first 10 lines)
   - **Short-term**: Add export version to Go output (`"export_version": "1.0"`)
   - **Medium-term**: JSON Schema definition, validate in both languages
   - **Effort**: 4-6 hours

2. **Fix hardcoded paths**
   - **Immediate**: Fix 2 instances in `evaluate_downstream_complete.py`
   - **Short-term**: Add ruff rule to detect hardcoded paths
   - **Effort**: 1-2 hours

3. **Add lineage enforcement to data processing scripts**
   - **Immediate**: Add `validate_write_path()` calls in key scripts
   - **Short-term**: Create `safe_write()` context manager
   - **Effort**: 2-3 hours

4. **Expand test sets to 100+ queries per game**
   - Critical for evaluation confidence
   - Enables statistical significance testing
   - **Effort**: 6-10 hours (annotation time)

5. **Add text embeddings signal**
   - Biggest performance lever (per priority matrix)
   - Code supports it but may not be enabled/loaded
   - Should improve P@10 from 0.08 to 0.15-0.20
   - **Effort**: 13-19 hours

### Medium Priority (Address When Stable)

6. **Improve API state management**
   - Document worker configuration requirements
   - Add test fixtures for state injection
   - **Effort**: 2-3 hours

7. **Add signal availability logging**
   - Log which signals are loaded at API startup
   - Help diagnose why fusion may not be using all signals
   - **Effort**: 1 hour

8. **Measure individual signal contributions**
   - Which signals are actually non-zero at runtime?
   - Which signals contribute to final similarity scores?
   - **Effort**: 3-4 hours

### Low Priority (Nice to Have)

7. **Refactor Go backend shared code**
   - Extract common operations
   - Use cobra for CLI structure
   - **Effort**: 4-6 hours

8. **Document similarity method relationships**
   - Architecture diagram
   - Method registry pattern
   - **Effort**: 1-2 hours

---

## Architecture Patterns to Preserve

### ✅ Keep These

1. **7-order data lineage system**: Excellent design, well-documented
2. **PATHS utility**: Centralized path management (just needs full adoption)
3. **Multi-modal fusion architecture**: Sound design, just needs proven signals first
4. **Separation of concerns**: Go/Python/API boundaries are appropriate
5. **Experimental code archiving**: Good self-awareness about premature complexity

### ⚠️ Improve These

1. **Go/Python integration**: Add formal contracts (schemas, versioning)
2. **Lineage enforcement**: Make it mandatory, not advisory
3. **Test set size**: Expand for statistical confidence
4. **API state management**: Better patterns for testing/deployment

---

## Conclusion

DeckSage has a solid architectural foundation with clear separation of concerns and a well-designed data lineage system. After examining the actual code (not just documentation), the main issues are:

1. **Integration boundaries** need formal contracts (schemas, versioning) - Go exports have no versioning, Python assumes structure
2. **Enforcement** of architectural rules is advisory - `validate_write_path()` exists but isn't called, hardcoded paths still exist
3. **Fusion complexity** may be premature - many signals are optional/None, need to verify what's actually loaded

**Key Findings from Code Inspection**:
- Go export structure has evolved (comments show "FIXED" changes) but no versioning
- Python reads JSONL with `json.loads()` and defensive `.get()` but no schema validation
- Lineage enforcement utilities exist but aren't used in data processing scripts
- Fusion system gracefully handles missing signals (returns 0.0) but may be using fewer signals than expected
- API state management uses FastAPI's recommended pattern but needs worker configuration documentation

**The system is well-positioned to scale, but should focus on**:
- Adding proven signals (text embeddings) - code supports it but may not be enabled
- Strengthening integration contracts (schema validation, versioning)
- Enforcing architectural rules (lineage validation, path centralization)
- Expanding evaluation rigor (larger test sets)

**Overall Grade**: B+ (solid foundation, needs integration hardening and rule enforcement)

---

## Code-Level Findings

### Go Export Structure Assumptions

**Go exports** (`src/backend/cmd/export-hetero/main.go`):
- Structure: `DeckRecord` with `cards[]`, `format`, `archetype`, `source`, etc.
- Comments show structure evolution: "FIXED: Data is at root level, not under 'collection'" (line 93)
- No version metadata in output

**Python consumption** (`src/ml/utils/data_loading.py`):
- Reads with `json.loads(line)` - no validation
- Assumes `deck.get("cards")` exists (line 272+)
- Uses defensive `.get()` but no schema check
- Validator exists (`load_decks_lenient`) but optional

**Risk**: If Go changes field names (e.g., `cards` → `card_list`), Python will fail silently.

### Fusion Signal Loading

**Actual signal loading** (`src/ml/api/load_signals.py`):
- All signals are optional - graceful degradation
- Checks `if path.exists()` before loading
- Sets to `None` if missing (line 109, 128, 154)
- Fusion returns 0.0 for missing signals (see `fusion.py:234-242`)

**Question**: Which signals are actually loaded at runtime? Need logging to verify.

### Path Usage Patterns

**Found hardcoded paths**:
- `src/ml/scripts/evaluate_downstream_complete.py:231, 277`: `Path("src/backend/pairs.csv")`
- Most other code correctly uses `PATHS` utility

**Pattern**: Scripts in `src/ml/scripts/` are more likely to have hardcoded paths than core library code.

### Lineage Enforcement Gap

**Utilities exist** (`src/ml/utils/lineage.py`):
- `validate_write_path()` function exists (line 65-88)
- `check_dependencies()` function exists (line 104-131)

**But**: No calls to these functions found in data processing scripts. Enforcement is completely advisory.

### API State Management

**Implementation** (`src/ml/api/api.py`):
- Uses FastAPI's `app.state.api` (not global variables) - good
- Loaded in `lifespan()` handler - proper async pattern
- State is `ApiState` dataclass with many optional fields

**Issue**: With multiple uvicorn workers, each loads state independently (memory duplication, slower startup).

---

## References

- `docs/DATA_LINEAGE_FLOW.txt` - Data lineage architecture
- `docs/DEVELOPMENT_RULES.md` - Development guidelines
- `docs/PRIORITY_MATRIX.md` - Prioritized action items
- `src/ml/experimental/REALITY_FINDINGS.md` - Performance reality check
- `src/ml/utils/lineage.py` - Lineage validation utilities
- `src/ml/similarity/fusion.py` - Fusion system implementation

