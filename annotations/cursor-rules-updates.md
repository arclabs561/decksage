# Cursor Rules Updates Needed

## Summary
The cursor rules in `.cursor/rules/annotations.mdc` should be updated with learnings from the annotations/judgments unification work.

## Key Updates Needed

### 1. Conversion Consistency (CRITICAL)

**Add to annotations.mdc:**

```markdown
## Conversion Consistency (CRITICAL)

**Always use annotation_utils conversion functions for core processing:**

- `convert_relevance_to_similarity_score(relevance, scale="0-4")` 
  - Uses non-linear mapping: `{4:0.95, 3:0.75, 2:0.55, 1:0.35, 0:0.1}`
- `convert_similarity_score_to_relevance(similarity_score, scale="0-4")`
  - Reverse mapping with thresholds: >=0.9→4, >=0.7→3, >=0.5→2, >=0.3→1, else→0

**DO NOT use linear conversions (`relevance / 4.0` or `int(score * 4)`) in:**
- Core annotation processing (`progressive_annotation.py`, `multi_perspective_judge.py`)
- Integration scripts (`integrate_all_annotations.py`)
- Any code that processes annotations for training/evaluation

**Linear conversions are acceptable in:**
- Evaluation/analysis scripts for display purposes
- Quick approximations in non-critical paths
```

### 2. Atomic File Writes (CRITICAL)

**Add to annotations.mdc:**

```markdown
## File Operations

**Always use atomic writes for annotation files:**

```python
temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
try:
    with open(temp_path, "w") as f:
        json.dump(data, f, indent=2)
    temp_path.replace(output_path)  # Atomic rename
except Exception as e:
    if temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            pass
    raise
```

This prevents partial writes on failure and ensures data integrity.
```

### 3. Unified Format

**Update existing section:**

```markdown
## Unified Format

- All LLM judgments now use annotation JSONL format (`judgment_*.jsonl`)
- Old JSON format (`annotations/llm_judgments/judgment_*.json`) still supported for backward compatibility
- New judgments should be saved directly as JSONL annotations
```

### 4. Error Handling

**Add to annotations.mdc:**

```markdown
## Error Handling

- Validate and clamp relevance to [0, 4] range
- Validate and clamp confidence to [0.0, 1.0] range
- Handle missing timestamps gracefully (default to recent weight)
- Skip invalid entries rather than failing entire batch
```

### 5. Deduplication

**Update existing section:**

```markdown
## Deduplication

- Deduplicate by (card1, card2) pair when merging from multiple sources
- When converting to test sets, keep highest similarity_score per candidate
- Use `seen_pairs = set()` with `tuple(sorted([card1, card2]))` for normalization
```

## Files That Need Updates

1. `.cursor/rules/annotations.mdc` - Add all sections above
2. Consider adding to `.cursor/rules/data-lineage.mdc` - Update judgment format location

## Verification

After updating, verify:
- [ ] Conversion consistency section added
- [ ] Atomic writes pattern documented
- [ ] Error handling patterns documented
- [ ] Unified format section updated
- [ ] Deduplication section updated
