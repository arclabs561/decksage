# Code Review: games/yugioh/

**Files Reviewed**: yugioh/game/game.go, yugioh/dataset/ygoprodeck/dataset.go

---

## 🔴 CRITICAL BUG: contains() Function is Broken

**Lines 177-181** in `ygoprodeck/dataset.go`:
```go
func contains(s, substr string) bool {
    return len(s) >= len(substr) && (s == substr ||
        (len(s) > len(substr) && (s[:len(substr)] == substr ||
         s[len(s)-len(substr):] == substr)))
}
```

**Intended**: Check if string contains substring (prefix OR suffix)

**Actually does**: Checks if substr is prefix OR suffix OR exact match

**Problem**: Doesn't check if substr appears in MIDDLE of string!

**Example**:
```go
contains("Effect Monster", "Effect")   // ✅ true (prefix)
contains("Fusion Monster", "Fusion")   // ✅ true (prefix)  
contains("Synchro Tuner Monster", "Tuner")  // ❌ FALSE! (middle)
```

**Impact**: Monster type parsing will FAIL for:
- "Synchro Tuner Monster" - Won't detect Tuner
- "Effect Pendulum Monster" - Won't detect Pendulum in middle
- "XYZ Effect Monster" - might miss Effect

**Correct Implementation**:
```go
func contains(s, substr string) bool {
    return strings.Contains(s, substr)
}
```

**Or just use `strings.Contains` directly!**

**Severity**: CRITICAL - Core parsing logic is broken

---

### 🔴 CRITICAL: Monster Type Parsing Will Fail

**Lines 166-172**: Uses broken `contains()` function

**Example card**: "Synchro Tuner Effect Monster"

**Expected**:
```go
IsEffect:  true
IsSynchro: true
// (Tuner in SubTypes)
```

**Actual** (with broken contains):
```go
IsEffect:  false  // ❌ "Effect" is in middle
IsSynchro: true   // ✅ "Synchro" is prefix
// Tuner: NOT DETECTED
```

**Impact**: Incorrect card type metadata for ALL Yu-Gi-Oh! cards

**Severity**: CRITICAL - Would require re-extraction to fix

---

### 🟡 WARNING: No Validation of API Response

**Lines 78-84**: Unmarshals API response without validation

**Missing checks**:
- Is response actually JSON?
- Is Data field present?
- Are required fields present in each card?

**Should**:
```go
if err := json.Unmarshal(page.Response.Body, &apiResp); err != nil {
    return fmt.Errorf("failed to parse API response: %w", err)
}

if len(apiResp.Data) == 0 {
    return fmt.Errorf("API returned 0 cards (unexpected)")
}
```

**Severity**: Medium (API could change)

---

### 🟢 OBSERVATION: Pointer Fields Could Be int

**Lines 45-48** in apiCard:
```go
ATK     *int   `json:"atk"`
DEF     *int   `json:"def"`
Level   *int   `json:"level"`
```

**Why pointers**: Distinguish between 0 and absent

**Issue**: ATK=0 is valid (e.g., "Kuriboh" has 0 ATK)

**Current approach**: Correct ✅

**But**: Should document that ATK=0 and ATK=nil are different

---

## Testing Gaps

**Critical**: NO TESTS for YGO implementation!

**Must add**:
- [ ] Test contains() function edge cases
- [ ] Test monster type parsing ("Synchro Tuner Effect Monster")
- [ ] Test API response parsing
- [ ] Test card type detection
- [ ] Test extraction (integration test with real API)

---

## Immediate Actions Required

1. **FIX contains() function** - Use strings.Contains
2. **Add unit tests** for YGO parsing
3. **Test with real YGOPRODeck API** before declaring working
4. **Validate monster type parsing** with known cards

---

## Grade

**Code Correctness**: D (4/10) - Core logic broken  
**Test Coverage**: F (0/10) - No tests  
**API Design**: B+ (8/10) - Good structure  

**Overall**: **D+ (5/10)** - BROKEN, needs immediate fixes before use

**Status**: 🔴 **DO NOT USE until contains() is fixed and tested**
