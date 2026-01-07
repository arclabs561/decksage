# Nuances We Missed & Areas Needing TLC

## Critical Issues

### 1. Score Format Inconsistency ⚠️
**Problem**: We're dividing scores by 10.0, but `ai-visual-test` might return scores in 0-1 format already.

**Location**: `test_all_pages_visual.py:159`, `test_visual_regression.py:150`

**Fix Needed**: Handle both formats:
```python
raw_score = validation_result.get("score", 0)
if raw_score > 1:
    score = raw_score / 10.0  # Convert 0-10 to 0-1
else:
    score = raw_score
```

**Status**: ⚠️ Partially fixed but needs verification

### 2. Failing Browser Tests (8/18) ⚠️
**Problem**: Tests fail because they don't wait for results properly or have selector issues.

**Failing Tests**:
- Metadata display (needs better result waiting)
- Card images (needs better result waiting)
- Rich metadata (needs better result waiting)
- Advanced options (strict mode violation - selector finds 2 elements)
- LLM-powered suggestions (timeout - element not found)
- Game detection (needs search execution)
- Feedback controls (needs results displayed)
- Feedback submission (needs results displayed)

**Root Cause**: Tests assume results are present but don't ensure they are.

**Fix Needed**: 
- Better wait conditions (wait for specific selectors)
- More robust result checking
- Fix advanced options selector (use `.first` or more specific selector)

**Status**: ❌ Needs fixing

### 3. Temp File Cleanup ⚠️
**Problem**: Temp `.mjs` files are cleaned up in `finally` blocks, but if script crashes hard, they might remain.

**Location**: All visual test files

**Fix Needed**: 
- Use `tempfile` module for automatic cleanup
- Or add cleanup on script exit
- Or use context managers

**Status**: ⚠️ Works but could be more robust

### 4. Environment Variable Fallbacks ⚠️
**Problem**: `load_env_keys.sh` doesn't handle missing parent repos gracefully.

**Location**: `load_env_keys.sh`

**Fix Needed**: 
- Check if files exist before sourcing
- Provide clear error messages
- Fallback to current directory `.env`

**Status**: ⚠️ Works but could be better

### 5. Advanced Options Selector ⚠️
**Problem**: Selector `#advancedToggle, [class*='advanced-toggle'], button:has-text('Advanced')` finds 2 elements.

**Location**: `test_browser_comprehensive.py:350+`

**Fix Needed**: Use `.first` or more specific selector

**Status**: ❌ Still failing

### 6. Accessibility Snapshot Bug ⚠️
**Problem**: `page.accessibility.snapshot()` doesn't exist in Playwright - we need `page.accessibility.snapshot()` but it's an async method.

**Location**: `invoke_mcp_tools.py:98`

**Fix Needed**: Use correct Playwright API

**Status**: ⚠️ Fixed but needs verification

## Medium Priority Issues

### 7. Error Response Handling ⚠️
**Problem**: Visual tests don't handle all error cases from API (403, 429, timeout, etc.)

**Location**: Visual test files

**Fix Needed**: 
- Handle specific error codes
- Retry logic for rate limits
- Better error messages

**Status**: ⚠️ Basic handling exists but could be better

### 8. Missing Wait Conditions ⚠️
**Problem**: Some tests race - they check for elements before they're rendered.

**Location**: Multiple test files

**Fix Needed**: 
- Use `page.wait_for_selector()` instead of `time.sleep()`
- Wait for network idle
- Wait for specific conditions

**Status**: ⚠️ Some waits exist but not comprehensive

### 9. Prompt Escaping Edge Cases ⚠️
**Problem**: We escape backticks and dollar signs, but what about other special characters?

**Location**: Visual test files

**Fix Needed**: 
- More comprehensive escaping
- Or use JSON.stringify() in Node.js

**Status**: ⚠️ Basic escaping exists

### 10. Test Isolation ⚠️
**Problem**: Tests might interfere with each other if they share state.

**Location**: All test files

**Fix Needed**: 
- Ensure each test starts fresh
- Clear browser state between tests
- Use separate browser contexts

**Status**: ⚠️ Mostly isolated but could be better

## Low Priority / Nice to Have

### 11. Documentation Accuracy ⚠️
**Problem**: Some docs might be slightly outdated or incomplete.

**Fix Needed**: Review and update all docs

### 12. Logging Consistency ⚠️
**Problem**: Different test files use different logging patterns.

**Fix Needed**: Standardize logging format

### 13. Test Data Management ⚠️
**Problem**: Test cards are hardcoded in multiple places.

**Fix Needed**: Centralize test data

### 14. Screenshot Management ⚠️
**Problem**: Screenshots accumulate in `/tmp/visual_tests/`

**Fix Needed**: 
- Cleanup old screenshots
- Organize by test run
- Option to keep screenshots for debugging

## Recommendations

### Immediate Fixes (High Priority)
1. ✅ Fix score format handling (handle both 0-10 and 0-1)
2. ✅ Fix advanced options selector (use `.first`)
3. ✅ Improve result waiting in failing tests
4. ✅ Fix accessibility snapshot API usage

### Short Term (Medium Priority)
5. ✅ Better error handling in visual tests
6. ✅ Replace `time.sleep()` with proper waits
7. ✅ Improve environment variable fallbacks
8. ✅ Use `tempfile` for temp files

### Long Term (Low Priority)
9. ✅ Standardize logging
10. ✅ Centralize test data
11. ✅ Screenshot cleanup strategy
12. ✅ Test isolation improvements

