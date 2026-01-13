# Critique: expand_all_test_sets.py

## Date: 2026-01-XX

## Executive Summary

The `expand_all_test_sets.py` script is a **good orchestration layer** that wraps the existing `expand_test_set_with_llm.py` functionality. However, it has several **critical issues** that limit its production readiness:

1. **Dependency Management**: Poor handling of missing dependencies
2. **Error Handling**: Insufficient error recovery and user feedback
3. **Integration Complexity**: Relies on complex, optional dependencies
4. **User Experience**: Lacks clear guidance when things fail
5. **Testing**: No validation of generated test sets

## Strengths ✅

### 1. Clean Interface
- Simple, intuitive CLI with sensible defaults
- Dry-run mode for planning
- Clear progress reporting
- Good separation of concerns (orchestration vs. implementation)

### 2. Flexible Configuration
- Supports individual games or all games
- Configurable target size and judge count
- Proper use of argparse

### 3. Progress Tracking
- Shows current vs. target sizes
- Provides expansion summary
- Clear status indicators (✓, ⚠, ✗)

## Critical Issues ❌

### 1. Dependency Chain Failure
**Problem**: The script imports `PATHS` which triggers a chain of imports that require `pandas`, `numpy`, etc. This causes failures even in dry-run mode when dependencies aren't installed.

**Impact**: Script fails before it can even check what needs to be done.

**Fix Applied**: Added try/except around PATHS import with fallback paths.

**Remaining Issue**: The underlying `expand_test_set_with_llm` has even more complex dependencies:
- `pydantic-ai` (required)
- `generate_queries_enhanced.py` (optional, may not exist)
- `improve_labeling_expand_test_set.py` (optional, may not exist)
- `generate_labels_multi_judge.py` (optional, may not exist)
- `parallel_multi_judge.py` (optional, may not exist)

**Recommendation**:
```python
def check_dependencies() -> tuple[bool, list[str]]:
    """Check if all required dependencies are available."""
    missing = []

    try:
        import pydantic_ai
    except ImportError:
        missing.append("pydantic-ai (pip install pydantic-ai)")

    # Check for required modules
    required_modules = [
        "ml.scripts.expand_test_set_with_llm",
        "ml.scripts.generate_labels_multi_judge",
    ]

    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing.append(f"{module} (file not found)")

    return len(missing) == 0, missing
```

### 2. No Validation of Generated Test Sets
**Problem**: After expansion, the script doesn't validate:
- Test set format correctness
- Query uniqueness
- Label quality (IAA scores)
- Coverage of card types/archetypes

**Impact**: May generate invalid or low-quality test sets.

**Recommendation**:
```python
def validate_expanded_test_set(test_set_path: Path, game: str) -> dict[str, Any]:
    """Validate expanded test set quality."""
    from ml.utils.data_loading import load_test_set

    try:
        test_set = load_test_set(game=game, path=test_set_path, validate=True)

        # Check quality metrics
        queries = test_set.get("queries", {})
        total_labels = sum(
            len(labels.get(level, []))
            for labels in queries.values()
            for level in ["highly_relevant", "relevant", "somewhat_relevant"]
        )
        avg_labels = total_labels / len(queries) if queries else 0

        # Check IAA scores
        iaa_scores = [
            labels.get("iaa", {}).get("agreement_rate", 0.0)
            for labels in queries.values()
            if "iaa" in labels
        ]
        avg_iaa = sum(iaa_scores) / len(iaa_scores) if iaa_scores else 0.0

        return {
            "valid": True,
            "num_queries": len(queries),
            "avg_labels_per_query": avg_labels,
            "avg_iaa": avg_iaa,
            "warnings": [] if avg_iaa >= 0.7 else ["Low IAA scores detected"],
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
        }
```

### 3. In-Place Updates Without Backup
**Problem**: The script updates test sets in place without creating backups.

**Impact**: If expansion fails partway through, original test set may be corrupted.

**Recommendation**:
```python
def expand_test_set_for_game(...):
    # Create backup before modification
    if test_set_path.exists():
        backup_path = test_set_path.with_suffix(f".backup_{int(time.time())}.json")
        shutil.copy2(test_set_path, backup_path)
        logger.info(f"Created backup: {backup_path}")

    # Use temporary file for expansion
    temp_path = test_set_path.with_suffix(".tmp.json")
    try:
        result = expand_test_set(
            existing_test_set_path=test_set_path,
            output_path=temp_path,  # Write to temp first
            ...
        )

        # Validate before replacing
        validation = validate_expanded_test_set(temp_path, game)
        if validation["valid"]:
            temp_path.replace(test_set_path)  # Atomic replace
        else:
            raise ValueError(f"Validation failed: {validation.get('error')}")
    except Exception:
        # Restore from backup if needed
        if backup_path.exists():
            backup_path.replace(test_set_path)
        raise
```

### 4. No Cost Estimation
**Problem**: LLM-based expansion can be expensive, but script doesn't warn users or estimate costs.

**Impact**: Users may run expensive operations without realizing it.

**Recommendation**:
```python
def estimate_cost(num_queries: int, num_judges: int, game: str) -> dict[str, Any]:
    """Estimate API costs for expansion."""
    # Rough estimates based on typical usage
    queries_per_dollar = 100  # Approximate
    judges_per_dollar = 50    # Approximate

    query_cost = num_queries / queries_per_dollar
    judge_cost = (num_queries * num_judges) / judges_per_dollar
    total_cost = query_cost + judge_cost

    return {
        "estimated_cost_usd": total_cost,
        "query_generation_cost": query_cost,
        "labeling_cost": judge_cost,
        "warnings": ["High cost"] if total_cost > 10.0 else [],
    }
```

### 5. Limited Error Recovery
**Problem**: If expansion fails for one game, script continues but doesn't provide clear recovery guidance.

**Impact**: Users don't know how to fix issues.

**Recommendation**:
```python
def expand_test_set_for_game(...):
    try:
        # ... expansion logic ...
    except ImportError as e:
        logger.error(f"{game}: Missing dependencies")
        logger.error(f"  Install: pip install pydantic-ai")
        logger.error(f"  Check: src/ml/scripts/expand_test_set_with_llm.py exists")
        return {"status": "error", "error": "missing_dependencies", "fix": "install_dependencies"}
    except Exception as e:
        logger.error(f"{game}: Expansion failed: {e}")
        logger.error(f"  Check logs for details")
        logger.error(f"  Try: --num-queries {needed // 2} to reduce load")
        return {"status": "error", "error": str(e), "suggestion": "reduce_batch_size"}
```

### 6. No Progress Persistence
**Problem**: If script is interrupted, all progress is lost (except checkpoints in underlying script).

**Impact**: Long-running expansions can't be resumed.

**Recommendation**: Check for existing checkpoint files and offer to resume:
```python
def find_checkpoint(test_set_path: Path) -> Path | None:
    """Find existing checkpoint file."""
    checkpoint_pattern = test_set_path.parent / f"{test_set_path.stem}_checkpoint.json"
    if checkpoint_pattern.exists():
        return checkpoint_pattern
    return None

def resume_from_checkpoint(checkpoint_path: Path) -> dict[str, Any]:
    """Resume expansion from checkpoint."""
    with open(checkpoint_path) as f:
        checkpoint_data = json.load(f)
    return checkpoint_data.get("queries", {})
```

## Design Issues ⚠️

### 1. Tight Coupling to Implementation
The script is tightly coupled to `expand_test_set_with_llm.expand_test_set()`. If that function changes signature or behavior, this script breaks.

**Better Approach**: Create an abstraction layer:
```python
class TestSetExpander:
    """Abstract interface for test set expansion."""

    def expand(
        self,
        test_set_path: Path,
        target_size: int,
        game: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

class LLMTestSetExpander(TestSetExpander):
    """LLM-based expansion implementation."""
    # ... implementation ...
```

### 2. Hardcoded Game Mapping
Game-to-path mapping is hardcoded and may not match actual PATHS structure.

**Better Approach**: Use PATHS utility consistently:
```python
game_map = {
    "pokemon": getattr(PATHS, "test_pokemon", Path("experiments/test_set_unified_pokemon.json")),
    "yugioh": getattr(PATHS, "test_yugioh", Path("experiments/test_set_unified_yugioh.json")),
    "riftbound": Path("experiments/test_set_unified_riftbound.json"),
}
```

### 3. No Integration with CI/CD
Script doesn't integrate with existing CI/CD or validation pipelines.

**Recommendation**: Add integration points:
```python
def main():
    # ... existing code ...

    # If running in CI, validate results
    if os.getenv("CI"):
        for game, result in results.items():
            if result["status"] == "success":
                validate_expanded_test_set(game_map[game], game)
```

## Recommendations for Improvement

### High Priority
1. ✅ **Add dependency checking** (partially done)
2. **Add test set validation** after expansion
3. **Add backup/restore** before in-place updates
4. **Add cost estimation** warnings
5. **Improve error messages** with actionable fixes

### Medium Priority
6. **Add progress persistence** (resume from checkpoints)
7. **Add integration tests** for the script
8. **Add cost tracking** (log actual API costs)
9. **Add quality metrics** reporting (IAA, coverage, etc.)

### Low Priority
10. **Refactor to use abstraction layer**
11. **Add CI/CD integration**
12. **Add parallel expansion** across games (currently sequential)

## Testing Recommendations

### Unit Tests Needed
```python
def test_dry_run_mode():
    """Test dry-run doesn't modify files."""
    # ...

def test_dependency_checking():
    """Test dependency detection."""
    # ...

def test_backup_creation():
    """Test backup is created before modification."""
    # ...

def test_validation_after_expansion():
    """Test expanded test sets are validated."""
    # ...
```

### Integration Tests Needed
```python
def test_full_expansion_workflow():
    """Test complete expansion workflow."""
    # Requires test environment with LLM access
    # ...

def test_resume_from_checkpoint():
    """Test resuming interrupted expansion."""
    # ...
```

## Conclusion

The script is a **good start** but needs significant improvements before production use:

**Current State**: ⚠️ **Beta Quality** - Works for basic use cases but has reliability issues

**Recommended State**: ✅ **Production Ready** - After implementing high-priority fixes

**Key Metrics**:
- **Reliability**: 6/10 (dependency issues, no validation)
- **User Experience**: 7/10 (good interface, poor error handling)
- **Maintainability**: 7/10 (clean code, tight coupling)
- **Production Readiness**: 5/10 (needs improvements)

**Verdict**: Use with caution. Implement high-priority fixes before relying on it for critical test set expansions.
