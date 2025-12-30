# Repository Harmonization Plan

## Assessment

After harmonizing LLM validators, checking rest of repo reveals:

### 1. Documentation (21 → keep ~10)

**Archive (status/completion docs):**
- AUDIT_SUMMARY.md
- COMPLETE_*.md
- *_SUMMARY.md  
- *_FINAL.md
- SESSION_COMPLETE*.md
- VALIDATORS_EXECUTIVE_SUMMARY.md

**Keep (reference docs):**
- README.md
- DATA_VALIDATION.md
- DATA_QUALITY_VALIDATION.md
- MIGRATION_GUIDE.md (if needed)
- ENRICHMENT_GUIDE.md (if active)
- COMMANDS.md
- USE_CASES.md

### 2. LLM Code Patterns

**Files using raw requests (old pattern):**
- llm_semantic_enricher.py
- vision_card_enricher.py
- multi_perspective_judge.py

**Decision:** 
- If actively used → harmonize with Pydantic AI
- If experimental → leave as-is or archive
- Check: Are they imported anywhere?

### 3. Experimental Folder

33 experimental scripts, many with:
- Bare except clauses
- No tests
- Unknown if active

**Decision:** Leave experimental/ as-is (it's experimental)

### 4. Print Statements

Many files have 20-100 print statements.

**Decision:** 
- CLI scripts: OK (print is fine)
- Library code: Should use logging
- But: Diminishing returns on converting all

**Pragmatic:** Leave as-is unless touching file for other reasons

---

## Harmonization Actions

### High Priority (30 min)

1. ✅ Archive remaining status docs (10 files)
2. Check if enrichers are used
   - If yes: Consider harmonizing
   - If no: Document or archive
3. Update main README with validator usage
4. Final test run

### Low Priority (Skip)

- Converting prints to logging (100+ changes)
- Harmonizing experimental scripts
- Fixing bare excepts in unused code

---

## Result

**After harmonization:**
- Root docs: ~10 essential files
- Dead code: Removed
- Active code: Clean and tested
- Experimental: Left as-is (it's experimental)

**Principle:** Clean what's used, document what's not, archive what's obsolete.
