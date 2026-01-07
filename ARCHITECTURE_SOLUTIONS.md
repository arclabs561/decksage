# Architecture Issues - Recommended Solutions

**Date**: 2025-01-XX  
**Based on**: Code inspection and best practices research

---

## Issue 1: Go/Python Integration Contract

### Problem
Go exports JSONL with no schema validation or versioning. Python assumes structure exists.

### Recommended Solution: Pydantic + JSON Schema

**Why**: Codebase already uses Pydantic extensively. JSON Schema is language-agnostic and human-readable.

**Implementation Plan**:

#### Step 1: Create Pydantic Model for Deck Export (Python)

```python
# src/ml/data/export_schema.py
from pydantic import BaseModel, Field
from typing import Optional

class CardInDeck(BaseModel):
    """Card in deck structure."""
    name: str = Field(..., description="Card name")
    count: int = Field(..., ge=1, description="Number of copies")
    partition: str = Field(..., description="Deck partition (mainboard, sideboard, etc.)")

class DeckExport(BaseModel):
    """Deck export schema matching Go output."""
    deck_id: str = Field(..., description="Unique deck identifier")
    archetype: Optional[str] = Field(None, description="Deck archetype")
    format: Optional[str] = Field(None, description="Format name")
    url: Optional[str] = Field(None, description="Source URL")
    source: Optional[str] = Field(None, description="Data source")
    player: Optional[str] = Field(None, description="Player name")
    event: Optional[str] = Field(None, description="Event name")
    placement: Optional[int] = Field(None, ge=0, description="Tournament placement")
    event_date: Optional[str] = Field(None, description="Event date (ISO format)")
    scraped_at: str = Field(..., description="Scrape timestamp (ISO format)")
    cards: list[CardInDeck] = Field(..., min_length=1, description="Cards in deck")
    
    # Backward compatibility aliases
    timestamp: Optional[str] = Field(None, alias="scraped_at")
    created_at: Optional[str] = Field(None, alias="scraped_at")
    
    # Export version metadata
    export_version: str = Field("1.0", description="Export format version")
    
    @classmethod
    def model_json_schema(cls) -> dict:
        """Generate JSON Schema for cross-language validation."""
        return super().model_json_schema()
```

#### Step 2: Generate JSON Schema File

```python
# scripts/schema/generate_deck_schema.py
import json
from pathlib import Path
from ml.data.export_schema import DeckExport

schema = DeckExport.model_json_schema()
schema_path = Path("schemas/deck_export_v1.json")

schema_path.parent.mkdir(exist_ok=True)
with open(schema_path, "w") as f:
    json.dump(schema, f, indent=2)

print(f"Generated schema: {schema_path}")
```

#### Step 3: Validate in Python Before Processing

```python
# src/ml/utils/data_loading.py (modify load_decks_jsonl)
import jsonschema
from pathlib import Path

# Load schema once
_SCHEMA_CACHE = None

def _load_export_schema() -> dict:
    """Load deck export schema."""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        schema_path = Path("schemas/deck_export_v1.json")
        if schema_path.exists():
            with open(schema_path) as f:
                _SCHEMA_CACHE = json.load(f)
    return _SCHEMA_CACHE

def validate_deck_record(record: dict, strict: bool = False) -> tuple[bool, str | None]:
    """Validate deck record against schema."""
    schema = _load_export_schema()
    if not schema:
        return True, None  # No schema = skip validation
    
    try:
        jsonschema.validate(instance=record, schema=schema)
        return True, None
    except jsonschema.ValidationError as e:
        if strict:
            return False, f"Schema validation failed: {e.message}"
        # Non-strict: log warning but continue
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Schema validation warning: {e.message}")
        return True, None

# In load_decks_jsonl, add validation:
def load_decks_jsonl(...):
    # ... existing code ...
    for line in f:
        deck = json.loads(line)
        
        # Validate schema (non-strict by default)
        is_valid, error = validate_deck_record(deck, strict=False)
        if not is_valid and strict:
            continue  # Skip invalid records in strict mode
        
        # ... rest of processing ...
```

#### Step 4: Add Version Metadata to Go Export

```go
// src/backend/cmd/export-hetero/main.go
// Add to DeckRecord struct:
type DeckRecord struct {
    // ... existing fields ...
    ExportVersion string `json:"export_version"`  // New field
}

// In main(), set version:
deckMap := map[string]interface{}{
    // ... existing fields ...
    "export_version": "1.0",  // Add this
}
```

#### Step 5: Validate in Go (Optional but Recommended)

```go
// Use gojsonschema library
import "github.com/xeipuuv/gojsonschema"

func validateDeckRecord(record map[string]interface{}, schemaPath string) error {
    schemaLoader := gojsonschema.NewReferenceLoader("file://" + schemaPath)
    documentLoader := gojsonschema.NewGoLoader(record)
    
    result, err := gojsonschema.Validate(schemaLoader, documentLoader)
    if err != nil {
        return err
    }
    
    if !result.Valid() {
        var errors []string
        for _, err := range result.Errors() {
            errors = append(errors, err.String())
        }
        return fmt.Errorf("validation failed: %v", errors)
    }
    
    return nil
}
```

**Effort**: 4-6 hours  
**Priority**: High  
**Dependencies**: `jsonschema` package (already in pyproject.toml likely)

---

## Issue 2: Hardcoded Paths

### Problem
Some code still uses hardcoded paths despite `PATHS` utility.

### Recommended Solution: Strengthen Existing Hook + Ruff Rule

**Why**: Pre-commit hook exists but is non-blocking. Need to make it blocking and add ruff rule for IDE feedback.

#### Step 1: Make Pre-commit Hook Blocking

```yaml
# .pre-commit-config.yaml (modify existing hook)
- id: check-hardcoded-paths
  name: Check for hardcoded paths
  entry: bash -c 'python3 scripts/validation/check_hardcoded_paths.py "$@" || exit 1'  # Remove || true
  language: system
  types: [python]
  stages: [commit]
  pass_filenames: true
  fail_fast: true  # Stop on first error
```

#### Step 2: Add Ruff Rule (Custom)

```python
# src/ml/utils/path_linter.py
"""Custom ruff rule to detect hardcoded paths."""
import ast
from typing import Any

def check_hardcoded_paths(tree: ast.AST) -> list[tuple[int, int, str]]:
    """AST visitor to find hardcoded paths."""
    issues = []
    
    class PathVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            # Check for Path("data/...") or Path("experiments/...")
            if isinstance(node.func, ast.Name) and node.func.id == "Path":
                if node.args and isinstance(node.args[0], ast.Constant):
                    path_str = node.args[0].value
                    if isinstance(path_str, str):
                        if any(path_str.startswith(prefix) for prefix in ["data/", "experiments/", "src/"]):
                            issues.append((
                                node.lineno,
                                node.col_offset,
                                f"Hardcoded path: {path_str}. Use PATHS utility instead."
                            ))
            self.generic_visit(node)
    
    PathVisitor().visit(tree)
    return issues
```

**Alternative**: Use ruff's existing pattern matching:

```toml
# pyproject.toml
[tool.ruff.lint]
# Add custom rule (if ruff supports it) or use existing checks
select = ["E", "W", "F", "I", "N", "UP", "B", "C4", "SIM", "RUF"]

# Or use ruff's --select to catch Path("data/") patterns
```

#### Step 3: Fix Existing Instances

```python
# src/ml/scripts/evaluate_downstream_complete.py
# Change:
pairs_path = Path("src/backend/pairs.csv")
# To:
from ml.utils.paths import PATHS
pairs_path = PATHS.pairs_large  # Or PATHS.backend / "pairs.csv"
```

**Effort**: 1-2 hours  
**Priority**: High  
**Dependencies**: None (just fix code)

---

## Issue 3: Lineage Enforcement

### Problem
`validate_write_path()` exists but isn't called in data processing scripts.

### Recommended Solution: Context Manager Pattern

**Why**: Context managers are Pythonic and ensure validation happens automatically.

#### Step 1: Create Safe Write Context Manager

```python
# src/ml/utils/lineage.py (add to existing file)
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

@contextmanager
def safe_write(path: Path | str, order: int, strict: bool = True) -> Generator[Path, None, None]:
    """
    Context manager for safe data writes with lineage validation.
    
    Args:
        path: Path to write to
        order: Data lineage order (1-6)
        strict: If True, raise error on validation failure. If False, log warning.
    
    Yields:
        Path object for writing
        
    Raises:
        ValueError: If path violates lineage rules (when strict=True)
    """
    path_obj = Path(path) if isinstance(path, str) else path
    
    # Validate before opening
    is_valid, error = validate_write_path(path_obj, order)
    if not is_valid:
        if strict:
            raise ValueError(f"Lineage violation: {error}")
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Lineage warning: {error}")
    
    # Check dependencies
    deps_satisfied, missing = check_dependencies(order)
    if not deps_satisfied:
        if strict:
            raise ValueError(f"Missing dependencies for order {order}: {missing}")
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Missing dependencies: {missing}")
    
    # Yield path for writing
    yield path_obj
    
    # Post-write validation (optional)
    if not path_obj.exists():
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"File was not created: {path_obj}")
```

#### Step 2: Use in Data Processing Scripts

```python
# scripts/data_processing/unified_export_pipeline.py
from ml.utils.lineage import safe_write

# In export_decks_from_raw:
with safe_write(output_file, order=1, strict=False) as out_path:
    # Write operations
    with open(out_path, "w") as f:
        # ... write JSONL ...
        pass

# In generate_pairs_for_games.py:
with safe_write(pairs_path, order=2, strict=True) as out_path:
    # Write CSV
    df.to_csv(out_path, index=False)
```

#### Step 3: Add to Graph Update Scripts

```python
# src/ml/data/incremental_graph.py
from ml.utils.lineage import safe_write

def save_graph(self, path: Path | None = None):
    """Save graph with lineage validation."""
    if path is None:
        path = PATHS.incremental_graph_json
    
    with safe_write(path, order=3, strict=True):
        # Save graph
        with open(path, "w") as f:
            json.dump(self.to_dict(), f)
```

**Effort**: 2-3 hours  
**Priority**: High  
**Dependencies**: None (uses existing lineage.py)

---

## Issue 4: API State Management

### Problem
FastAPI `app.state` is per-worker. Need documentation and optional shared state pattern.

### Recommended Solution: Document Current Pattern + Optional Redis

**Why**: Current pattern (per-worker state) is fine for embeddings. Just needs documentation. Redis only needed if sharing state is required.

#### Step 1: Document Worker Configuration

```python
# src/ml/api/api.py (add docstring to lifespan)
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler: load resources on startup, free on shutdown.
    
    **Worker Configuration**:
    - Each worker loads embeddings independently (memory duplication)
    - Recommended: Use single worker for development/testing
    - Production: Use multiple workers only if memory allows
      - Each worker needs ~2-4GB RAM for embeddings
      - Example: 4 workers = 8-16GB RAM total
    
    **Shared State** (if needed):
    - For shared caches/counters, use Redis (see load_signals.py)
    - Embeddings are read-only, so per-worker loading is acceptable
    - Consider shared memory (mmap) for very large embeddings if needed
    """
    # ... existing code ...
```

#### Step 2: Add Worker Count Warning

```python
# src/ml/api/api.py (in lifespan)
import os

worker_count = int(os.getenv("WEB_CONCURRENCY", "1"))
if worker_count > 1:
    logger.warning(
        f"Running with {worker_count} workers. Each worker loads embeddings independently. "
        f"Total memory usage: ~{worker_count * 2}GB (estimated). "
        f"Consider single worker if memory is constrained."
    )
```

#### Step 3: Optional Redis for Shared Signals (Future)

```python
# src/ml/api/load_signals.py (optional enhancement)
try:
    import redis.asyncio as redis
    
    REDIS_CLIENT = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, db=0)
    USE_REDIS = os.getenv("USE_REDIS_FOR_SIGNALS", "false").lower() == "true"
except ImportError:
    REDIS_CLIENT = None
    USE_REDIS = False

def load_signals_to_state(...):
    """Load signals, optionally from Redis cache."""
    if USE_REDIS and REDIS_CLIENT:
        # Try Redis first
        cached = await REDIS_CLIENT.get("signals:sideboard")
        if cached:
            state.sideboard_cooccurrence = json.loads(cached)
            return
    
    # Fall back to file loading
    # ... existing code ...
```

**Effort**: 1 hour (documentation) + 3-4 hours (Redis if needed)  
**Priority**: Medium (documentation is high, Redis is low)  
**Dependencies**: None for documentation, `redis` package for shared state

---

## Issue 5: Signal Loading Logging

### Problem
Don't know which signals are actually loaded at runtime.

### Recommended Solution: Add Startup Logging

```python
# src/ml/api/load_signals.py (modify load_signals_to_state)
def load_signals_to_state(...) -> dict[str, bool]:
    """
    Load signals and return availability status.
    
    Returns:
        Dict mapping signal name -> is_loaded
    """
    status = {
        "sideboard": False,
        "temporal": False,
        "gnn": False,
        "text_embedder": False,
        "visual_embedder": False,
        "archetype": False,
        "format": False,
    }
    
    # Load each signal and update status
    if sideboard_path.exists():
        state.sideboard_cooccurrence = json.load(f)
        status["sideboard"] = True
        logger.info(f"✓ Loaded sideboard signal: {len(state.sideboard_cooccurrence)} cards")
    else:
        logger.debug(f"✗ Sideboard signal not found: {sideboard_path}")
    
    # ... repeat for each signal ...
    
    # Log summary
    loaded_count = sum(status.values())
    total_count = len(status)
    logger.info(
        f"Signal loading complete: {loaded_count}/{total_count} signals loaded. "
        f"Available: {', '.join(k for k, v in status.items() if v)}"
    )
    
    return status
```

**Effort**: 1 hour  
**Priority**: Medium  
**Dependencies**: None

---

## Implementation Priority

### Phase 1: Critical Fixes (Week 1)
1. ✅ Fix hardcoded paths (1-2h)
2. ✅ Add lineage enforcement context manager (2-3h)
3. ✅ Add schema validation for Go exports (4-6h)

**Total**: 7-11 hours

### Phase 2: Improvements (Week 2)
4. ✅ Add signal loading logging (1h)
5. ✅ Document API worker configuration (1h)
6. ✅ Make pre-commit hook blocking (30min)

**Total**: 2.5 hours

### Phase 3: Optional Enhancements (Future)
7. ⏳ Go-side schema validation (if needed)
8. ⏳ Redis shared state (if multi-worker required)
9. ⏳ Ruff custom rule for paths (if ruff supports it)

---

## Testing Strategy

### Schema Validation
```python
# tests/test_export_schema.py
def test_deck_export_schema():
    """Test deck export schema validation."""
    from ml.data.export_schema import DeckExport
    
    valid_deck = {
        "deck_id": "test-123",
        "scraped_at": "2025-01-01T00:00:00Z",
        "cards": [{"name": "Lightning Bolt", "count": 4, "partition": "mainboard"}],
        "export_version": "1.0"
    }
    
    deck = DeckExport(**valid_deck)
    assert deck.deck_id == "test-123"
    
    # Test invalid
    invalid = valid_deck.copy()
    invalid["cards"] = []  # Empty cards
    with pytest.raises(ValidationError):
        DeckExport(**invalid)
```

### Lineage Enforcement
```python
# tests/test_lineage_enforcement.py
def test_safe_write_validates_order():
    """Test safe_write validates lineage order."""
    with pytest.raises(ValueError, match="Order 0"):
        with safe_write(Path("src/backend/data-full/games/test.json"), order=0):
            pass
    
    # Valid write
    with safe_write(tmp_path / "test.json", order=1):
        Path(tmp_path / "test.json").write_text("test")
```

---

## References

- Pydantic JSON Schema: https://docs.pydantic.dev/latest/concepts/json_schema/
- jsonschema library: https://python-jsonschema.readthedocs.io/
- FastAPI state management: https://fastapi.tiangolo.com/deployment/server-workers/
- Context managers: https://docs.python.org/3/library/contextlib.html

