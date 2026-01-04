# Code Review: games/game.go

**Reviewer**: Systematic scrutiny
**Date**: 2025-09-30
**File**: `src/backend/games/game.go`

---

## Issues Found

### 🔴 CRITICAL: Type Registry Race Condition Risk

**Line 70**: `var TypeRegistry = make(map[string]func() CollectionType)`

**Issue**: Global mutable map

**Scenario**:
```go
// If two games register concurrently (shouldn't happen but...)
func init() {
    games.RegisterCollectionType("Deck", ...) // Game 1
}
func init() {
    games.RegisterCollectionType("Deck", ...) // Game 2
}
```

**Current behavior**: Last writer wins (silent overwrite)

**Should**: Error or panic on duplicate registration

**Fix**:
```go
func RegisterCollectionType(typeName string, constructor func() CollectionType) {
    if _, exists := TypeRegistry[typeName]; exists {
        panic(fmt.Sprintf("collection type %q already registered", typeName))
    }
    TypeRegistry[typeName] = constructor
}
```

**Severity**: Medium (unlikely but possible)

---

### 🟡 WARNING: Canonicalize Mutates in Place

**Lines 130, 155**: Sorts `Partitions` and `Cards` in place

**Issue**: Side effects not documented in function signature

**Current**:
```go
func (c *Collection) Canonicalize() error
```

**Better**:
```go
// Canonicalize validates and normalizes a collection IN PLACE.
// Mutates: Sorts partitions and cards by name.
func (c *Collection) Canonicalize() error
```

**Or** (immutable):
```go
func (c *Collection) Canonicalize() (*Collection, error) {
    canonical := *c // Copy
    // Sort canonical.Partitions
    return &canonical, nil
}
```

**Severity**: Low (current behavior is fine, just undocumented)

---

### 🟡 WARNING: UnmarshalJSON Unhelpful Error

**Line 86**: Error message doesn't list valid types

**Current**:
```go
return fmt.Errorf("unknown collection type %q (not registered)", ww.Type)
```

**Better**:
```go
validTypes := make([]string, 0, len(TypeRegistry))
for t := range TypeRegistry {
    validTypes = append(validTypes, t)
}
return fmt.Errorf(
    "unknown collection type %q (not registered); valid types: %v",
    ww.Type, validTypes,
)
```

**Severity**: Low (debugging UX)

---

### 🟢 MINOR: Card Name Validation Could Be Stricter

**Line 150-152**: Checks for empty/control characters

**Missing checks**:
- Extremely long names (>200 chars = likely corrupted)
- Invalid UTF-8 sequences
- Leading/trailing whitespace (should be trimmed)

**Suggestion**:
```go
if len(card.Name) > 200 {
    return fmt.Errorf("card name too long (%d chars): %q", len(card.Name), card.Name)
}
if card.Name != strings.TrimSpace(card.Name) {
    return fmt.Errorf("card name has leading/trailing whitespace: %q", card.Name)
}
```

**Severity**: Low (edge case)

---

### 🟢 MINOR: ReleaseDate Validation Semantic Issue

**Line 122-124**: Checks `ReleaseDate.IsZero()`

**Issue**: We discovered ReleaseDate is extraction timestamp, not tournament date

**Implications**:
- Validation passes (timestamp always set)
- But doesn't validate actual tournament date
- Temporal analysis broken

**Fix needed elsewhere**: Scraper should parse tournament date from page

**Severity**: Medium (architectural issue, not code bug)

---

### 🟢 OBSERVATION: No Partition Validation for Duplicates

**Lines 135-141**: Validates partition name not empty, has cards

**Missing**: Check for duplicate partition names

**Scenario**:
```json
{
  "partitions": [
    {"name": "Main Deck", "cards": [...]},
    {"name": "Main Deck", "cards": [...]}  // Duplicate!
  ]
}
```

**Should**: Either error or merge partitions

**Suggestion**:
```go
partitionNames := make(map[string]bool)
for i, p := range c.Partitions {
    if partitionNames[p.Name] {
        return fmt.Errorf("duplicate partition name: %q", p.Name)
    }
    partitionNames[p.Name] = true
    // ... rest of validation
}
```

**Severity**: Low (unlikely in practice)

---

### 🟢 OBSERVATION: No Total Card Count Limits

**No validation**: Could have 10,000 card "deck"

**Scenario**: Malformed data or set (not deck) gets through

**Suggestion**:
```go
// After partition validation
totalCards := 0
for _, p := range c.Partitions {
    for _, card := range p.Cards {
        totalCards += card.Count
    }
}
if totalCards > 5000 {  // Reasonable limit
    return fmt.Errorf("collection has %d cards (max 5000)", totalCards)
}
```

**Severity**: Very low (sanity check only)

---

## Positive Observations

✅ **Good error messages** - Contextual, helpful
✅ **Proper use of fmt.Errorf** with %w for wrapping
✅ **Regex compiled at package level** - Good performance
✅ **Stable sorts** - Preserves original order for equal elements
✅ **Validation is thorough** - Checks multiple invariants

---

## Recommendations

### Must Fix (Before Production)

1. **Add duplicate type registration check** - Prevents silent bugs

### Should Fix (Quality)

2. **Document mutation in Canonicalize**
3. **Improve UnmarshalJSON error message** (list valid types)

### Nice to Have (Polish)

4. **Add partition name uniqueness check**
5. **Add total card count sanity check**
6. **Stricter card name validation** (length, whitespace)

---

## Testing Gaps

**Current tests**: Validate happy path

**Missing tests**:
- [ ] Duplicate type registration
- [ ] Duplicate partition names
- [ ] Extremely long card names
- [ ] Whitespace in card names
- [ ] Very large collections (10K+ cards)
- [ ] Concurrent type registration

**Severity**: Medium (add tests for robustness)

---

## Grade

**Code Quality**: A- (8.5/10)
**Robustness**: B+ (needs duplicate checks)
**Documentation**: B (needs mutation docs)

**Overall**: **B+ (8/10)** - Very good, minor improvements needed
