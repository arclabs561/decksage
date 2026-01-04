# Development Rules & Themes

**Note for AI Agents**: This document outlines common rules and themes that should be enforced during code review and development. Read this alongside `.cursor/rules/*.mdc` files for complete context.

## Core Principles

### 1. Code Duplication Prevention
- **Before creating new variants**: Check if existing script can be extended with parameters/flags
- **Naming convention**: Use descriptive suffixes only when necessary:
  - `_refined` = improved version (keep both temporarily during migration)
  - `_enhanced` = adds metadata/advanced features
  - `_simple` = simplified version for specific use case
- **Unification process**: When consolidating duplicates:
  1. Search for all references: `rg -l "script_name" --type py`
  2. Update all imports/references first
  3. Merge functionality into canonical version
  4. Run type checker: `uvx ty check <files>`
  5. Run e2e tests to verify functionality
  6. Remove obsolete files only after all references updated

### 2. Path Handling
- **Always use PATHS utility**: Never hardcode paths like `"data/"`, `"experiments/"`, `"src/ml/"`
- **Use**: `from ml.utils.paths import PATHS` then `PATHS.processed`, `PATHS.experiments`, etc.
- **Exception**: Only `src/ml/utils/paths.py` itself can have hardcoded paths (it defines PATHS)

### 3. Data Lineage
- **Strict hierarchy**: Order 0 (Primary) → Order 1 (Exported) → Order 2 (Pairs) → Order 3+ (Derived)
- **Validation**: All data processing scripts MUST include lineage comments
- **Traceability**: Every derived dataset must be traceable to its source
- **See**: `.cursor/rules/data-lineage.mdc` for full details

### 4. Code Style
- **Type hints**: Use Python 3.11+ type hints (e.g., `dict[str, Any]`, `Path | None`)
- **Tooling**: Prefer `uv`/`uvx` over `pip`, `fd` not `find`, `rg` not `grep`, `bat` not `cat`
- **Scripts**: Use PEP 723 scripts for standalone tools (`# /// script`)
- **Error handling**: Use try/except with specific exception types, provide clear error messages

### 5. Abstraction & Complexity
- **No premature abstraction**: Wait until pattern appears 3+ times before abstracting
- **Chesterton's fence**: Understand existing design before suggesting changes
- **Complexity budget**: Limit each work session to ≤3 new files, ≤200 new lines
- **Wrong abstraction**: Duplication is cheaper than wrong abstraction

### 6. Testing & Quality
- **Property-based testing**: Use Hypothesis for invariants (confidence scores in [0,1], valid UTF-8, etc.)
- **Test pyramid**: Many fast unit tests, fewer integration tests, minimal e2e tests
- **Mark slow tests**: Use `@pytest.mark.slow` and create separate commands
- **LLM applications**: Track correctness, consistency, safety, performance

### 7. Documentation
- **Code as documentation**: Improve code and comments as primary documentation
- **Lineage comments**: All data processing scripts MUST include lineage comments
- **Why not what**: Use comments to explain "why", not "what"
- **No excessive MD files**: Don't create excessive markdown files for progress

## Common Patterns to Avoid

### ❌ Anti-Patterns
- Hardcoded paths: `Path("data/processed/file.csv")` → Use `PATHS.processed / "file.csv"`
- Code duplication: Creating `_v2`, `_new`, `_updated` variants → Extend existing
- Premature abstraction: Creating framework after 1 occurrence → Wait for 3+
- Missing type hints: `def func(x):` → `def func(x: str) -> int:`
- Broad except: `except Exception:` → `except SpecificError:`
- Magic numbers: `if count > 100:` → `if count > MAX_ITEMS:`

### ✅ Preferred Patterns
- Use PATHS utility for all file paths
- Extend existing scripts with parameters/flags
- Wait for pattern to prove itself (3+ occurrences)
- Explicit type annotations
- Specific exception handling
- Named constants for magic numbers

## Review Checklist

When reviewing code (human or AI), check:
- [ ] Uses PATHS utility (no hardcoded paths)
- [ ] No unnecessary code duplication
- [ ] Type hints present (Python 3.11+)
- [ ] Data lineage comments included (if data processing)
- [ ] Error handling is specific (not bare `except:`)
- [ ] Tests included for new functionality
- [ ] Follows existing patterns in codebase
- [ ] No premature abstraction

## For AI Agents

When generating or reviewing code:
1. **Check existing code first**: Search for similar functionality before creating new
2. **Read `.cursor/rules/*.mdc`**: These contain detailed rules and context
3. **Enforce PATHS utility**: Always suggest using `PATHS` instead of hardcoded paths
4. **Prevent duplication**: Suggest extending existing code rather than duplicating
5. **Respect Chesterton's fence**: Understand why code exists before changing it
6. **Type hints required**: Always include type hints for new functions
7. **Data lineage**: Include lineage comments in data processing scripts

## Quick Reference

```python
# ✅ Good: Uses PATHS utility
from ml.utils.paths import PATHS
data_path = PATHS.processed / "decks_magic.jsonl"

# ❌ Bad: Hardcoded path
data_path = Path("data/processed/decks_magic.jsonl")

# ✅ Good: Type hints
def process_decks(decks: list[dict[str, Any]]) -> int:
    return len(decks)

# ❌ Bad: No type hints
def process_decks(decks):
    return len(decks)

# ✅ Good: Specific exception
try:
    load_data()
except FileNotFoundError as e:
    logger.error(f"Data file not found: {e}")

# ❌ Bad: Broad exception
try:
    load_data()
except Exception:
    pass
```

## Related Documentation

- `.cursor/rules/code-duplication-prevention.mdc` - Detailed duplication rules
- `.cursor/rules/data-lineage.mdc` - Data lineage architecture
- `.cursor/rules/code-style.mdc` - Code style guidelines
- `.cursor/rules/testing.mdc` - Testing best practices
