# DeckSage - Roadmap to Production
## From B (7/10) to A (9/10) in 2-3 Weeks

**Current State**: Solid foundation with 2 critical bugs + data gaps
**Target State**: Production-ready multi-game similarity platform
**Timeline**: 2-3 weeks of focused work
**Confidence**: Very high (we know all issues)

---

## Week 1: Bug Fixes + Testing (B → B+)

### Critical Bug Fixes (Days 1-2)

#### Fix #1: Race Condition in IterItemsBlobPrefix

**File**: `games/dataset.go:227-297`

**Current issue**:
```go
// Can deadlock, lose errors
errs := make(chan error, parallel)
errs <- err  // Blocking
```

**Fix**:
```go
// Non-blocking error handling
select {
case errs <- err:
default:
    // Error already captured
}

// Wait before checking errors
wg.Wait()
if err := it.Err(); err != nil {
    return err
}
```

**Test**:
```go
func TestIterItems_ConcurrentErrors(t *testing.T) {
    // Create scenario where all goroutines error
    // Verify no deadlock, first error returned
}
```

**Time**: 4-6 hours

---

#### Fix #2: Regex Performance in Section()

**File**: `games/dataset.go:90-98`

**Current issue**:
```go
// Recompiles regex every call
re := regexp.Compile(fmt.Sprintf("(?i)%s", pat))
```

**Fix Option A** (Simple):
```go
type ResolvedUpdateOptions struct {
    ...
    compiledSectionRegexes map[string]*regexp.Regexp
}

// Compile once during ResolveUpdateOptions
for _, section := range sectionOnly {
    re, err := regexp.Compile(fmt.Sprintf("(?i)%s", section))
    if err != nil {
        return ResolvedUpdateOptions{}, err
    }
    compiledSectionRegexes[section] = re
}
```

**Test**:
```go
func BenchmarkSection(b *testing.B) {
    // Measure performance improvement
}
```

**Time**: 3-4 hours

---

### Add Missing Tests (Days 3-4)

**YGO Monster Type Parsing**:
```go
func TestParseMonsterType(t *testing.T) {
    tests := []struct{
        typeStr string
        want game.MonsterType
    }{
        {"Synchro Tuner Effect Monster", MonsterType{
            IsEffect: true, IsSynchro: true, // Tuner in subtypes
        }},
        {"XYZ Effect Monster", MonsterType{IsEffect: true, IsXyz: true}},
        {"Link Effect Monster", MonsterType{IsEffect: true, IsLink: true}},
    }
    // ...
}
```

**Concurrent Iteration**:
```go
func TestIterItems_Concurrent(t *testing.T) {
    // Test parallel iteration
    // Test context cancellation
    // Test error propagation
}
```

**Time**: 1 day

---

### Pokemon Audit (Day 5)

**Tasks**:
1. Review Pokemon implementation
2. Complete dataset.go or mark as WIP
3. Add to documentation
4. Test or deprecate

**Time**: 4-6 hours

---

**Week 1 Outcome**: B+ (8/10)
- All critical bugs fixed ✅
- Concurrent tests added ✅
- Pokemon status clear ✅

---

## Week 2: Data Diversity (B+ → A-)

### Extract Balanced MTG Data (Days 1-3)

**Target**: 200+ more decks

**Format Balance**:
```bash
# Modern: 16 → 60 decks
go run ./cmd/dataset extract mtgtop8 \
  --section="modern" --limit=100 --bucket=file://./data-full

# Pioneer: 15 → 40 decks
go run ./cmd/dataset extract mtgtop8 \
  --section="pioneer" --limit=50

# Pauper: Balance archetypes (avoid Faeries clustering)
```

**Validation After Each Batch**:
```bash
go run ./cmd/analyze-decks data-full/games/magic
```

**Success Criteria**:
- [ ] Modern: 60+ decks, 15+ archetypes
- [ ] All formats: 30+ decks minimum
- [ ] Tarmogoyf, Ragavan in vocabulary
- [ ] No archetype >20% per format

**Time**: 2-3 days (extraction + validation)

---

### Extract YGO Decks (Days 4-5)

**Implement YGO Deck Scraper**:

**Option 1**: YGOPRODeck deck database
**Option 2**: DuelingBook popular decks
**Option 3**: YGOScope tournament results

**Target**: 100+ YGO decks

**Format Balance**:
- TCG: 50 decks
- OCG: 30 decks
- Speed Duel: 20 decks

**Time**: 1-2 days

---

### Re-train & Validate (Day 5)

**Tasks**:
```bash
# Export clean graphs
go run ./cmd/export-decks-only data-full/games/magic mtg_v2.csv
go run ./cmd/export-decks-only data-full/games/yugioh ygo_v1.csv

# Train embeddings
cd ../ml
.venv/bin/python card_similarity_pecan.py \
  --input ../backend/mtg_v2.csv --output magic_v2

.venv/bin/python card_similarity_pecan.py \
  --input ../backend/ygo_v1.csv --output yugioh_v1

# Validate
.venv/bin/python analyze_embeddings.py \
  --embeddings ../backend/magic_v2_pecanpy.wv \
  --pairs ../backend/mtg_v2.csv \
  --visualize

# Expert validation
.venv/bin/python card_similarity_pecan.py \
  --input ../backend/mtg_v2.csv \
  --query "Tarmogoyf" "Ragavan" "Lava Spike"
```

**Success Criteria**:
- [ ] Tarmogoyf found ✅
- [ ] Format coverage >80% all formats
- [ ] YGO embeddings semantically valid
- [ ] Cross-game comparison complete

**Time**: 1 day

---

**Week 2 Outcome**: A- (9/10)
- Diverse data extracted ✅
- All formats balanced ✅
- 2 games with quality embeddings ✅

---

## Week 3: Production Features (A- → A)

### Build REST API (Days 1-2)

**Framework**: Go with Fiber or Gin

**Endpoints**:
```go
GET  /api/{game}/similar/{cardName}?top_k=10
GET  /api/{game}/recommend?cards=A,B,C
GET  /api/{game}/search?q=lightning
GET  /api/health
```

**Features**:
- Rate limiting
- Caching (embeddings in memory)
- Error handling
- CORS support

**Time**: 1-2 days

---

### Build Web UI (Days 3-4)

**Framework**: React or Svelte

**Features**:
- Card search with autocomplete
- Similarity results display
- Visual embedding space (t-SNE)
- Format/game selector
- Responsive design

**Time**: 1-2 days

---

### Deploy & Monitor (Day 5)

**Infrastructure**:
- Docker containers
- Docker Compose for local
- Cloud deployment (Fly.io / Railway / AWS)

**Monitoring**:
- Request logs
- Error rates
- Query latency
- Embedding cache hit rate

**Time**: 1 day

---

**Week 3 Outcome**: A (9/10)
- Production API ✅
- Web UI ✅
- Deployed ✅
- Monitored ✅

---

## Acceptance Criteria for A Grade

### Code Quality

- [ ] All critical bugs fixed
- [ ] Concurrent tests added
- [ ] Edge case tests added
- [ ] Code review completed
- [ ] Linting clean

### Data Quality

- [ ] 60+ Modern decks
- [ ] Format balance (30+ each)
- [ ] Temporal span >30 days
- [ ] Archetype diversity (entropy >2.0)
- [ ] Format coverage >80%

### Embedding Quality

- [ ] MTG: Tarmogoyf, Ragavan, all staples present
- [ ] YGO: 100+ decks, semantically valid
- [ ] Expert validation passed
- [ ] Precision@10 >80%

### Production Readiness

- [ ] REST API tested
- [ ] Web UI functional
- [ ] Deployed to cloud
- [ ] Monitoring in place
- [ ] Load tested (1000 req/min)

### Documentation

- [ ] All games documented
- [ ] API documented
- [ ] Deployment guide
- [ ] Known issues list

---

## Risk Assessment

### Low Risk (Likely to Succeed)

- Bug fixes (know exactly what to fix)
- Data extraction (infrastructure works)
- API build (straightforward)

### Medium Risk (Might Hit Issues)

- YGO deck scraper (API might be tricky)
- Pokemon completion (unknown scope)
- Performance at scale (untested)

### High Risk (Unknown)

- User adoption (market validation)
- Long-term maintenance
- Cross-game quality consistency

**Mitigation**: Ship iteratively, gather feedback, adapt

---

## Success Metrics

### Technical Metrics

| Metric | Current | Week 1 | Week 2 | Week 3 |
|--------|---------|--------|--------|--------|
| Critical bugs | 2 | 0 | 0 | 0 |
| Test coverage | 40% | 60% | 60% | 70% |
| MTG decks | 150 | 150 | 300+ | 300+ |
| YGO decks | 0 | 0 | 100+ | 100+ |
| Format coverage | 60-100% | 60-100% | 80-100% | 80-100% |
| Embedding quality | 8.5/10 | 8.5/10 | 9/10 | 9/10 |
| Production ready | No | No | Yes | Yes |

### Quality Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Overall grade | B (7/10) | A (9/10) |
| Architecture | A+ (9.5/10) | A+ (9.5/10) |
| Data quality | C+ (6.5/10) | A- (9/10) |
| Test coverage | C+ (6.5/10) | B+ (8/10) |
| Documentation | A (9/10) | A (9/10) |

---

## Estimated Effort

### Week 1 (Bug Fixes)
- Fix race condition: 4-6 hours
- Fix regex performance: 3-4 hours
- Add tests: 8 hours
- Pokemon audit: 4-6 hours
- **Total**: 20-24 hours (3-4 days)

### Week 2 (Data)
- Extract MTG: 8-12 hours
- Implement YGO scraper: 8-12 hours
- Extract YGO: 4-6 hours
- Validate: 4-6 hours
- **Total**: 24-36 hours (3-5 days)

### Week 3 (Production)
- Build API: 8-12 hours
- Build UI: 12-16 hours
- Deploy: 4-6 hours
- Test: 4-6 hours
- **Total**: 28-40 hours (4-5 days)

**Grand Total**: 72-100 hours (10-14 days of focused work)

**Calendar time**: 2-3 weeks

---

## Decision Points

### After Week 1

**If bugs fixed + tests added**: Proceed to Week 2
**If bugs remain**: Extend Week 1
**Decision criteria**: All critical bugs resolved

### After Week 2

**If data quality achieved**: Proceed to Week 3
**If coverage still poor**: Extract more data
**Decision criteria**: Format coverage >80%, embeddings quality >8.5/10

### After Week 3

**If production deploy successful**: Ship!
**If issues found**: Iterate
**Decision criteria**: API stable, UI functional, monitoring active

---

## Fallback Plans

### If YGO Scraper Too Hard

**Plan B**: Use YGOPRODeck deck API (if exists)
**Plan C**: Manual curated deck list
**Plan D**: Ship with MTG only, add YGO later

### If Data Quality Insufficient

**Plan B**: Lower coverage threshold to 70%
**Plan C**: Format-specific models (don't mix)
**Plan D**: Ship as "beta" with known limitations

### If Timeline Slips

**Plan B**: Ship API without UI
**Plan C**: Ship with known bugs documented
**Plan D**: Extend timeline, don't compromise quality

---

## Commitment to Quality

### Non-Negotiables

- ✅ Fix ALL critical bugs before ship
- ✅ Expert validation must pass
- ✅ Documentation stays honest
- ✅ Known issues documented

### Flexible

- ⚠️ Exact number of decks
- ⚠️ UI polish level
- ⚠️ Format coverage threshold
- ⚠️ Pokemon inclusion

---

## Final Checklist

### Before Declaring "Production Ready"

- [ ] All critical bugs fixed
- [ ] Concurrent tests passing
- [ ] Expert validation passed (all games)
- [ ] Data diversity validated
- [ ] API load tested
- [ ] UI user tested
- [ ] Monitoring in place
- [ ] Known issues documented
- [ ] Grade ≥ A- (9/10)

**Don't skip checklist items!**

---

## Success Criteria

### Minimum Viable Production

- MTG: 200+ decks, >80% coverage, embeddings validated
- YGO: 100+ decks, embeddings semantically valid
- API: Working, tested, documented
- UI: Functional, responsive
- Grade: A- (8.5/10) minimum

### Ideal Production

- MTG: 500+ decks, >95% coverage, temporal diversity
- YGO: 200+ decks, archetype balanced
- Pokemon: 100+ decks or removed
- API: Robust, monitored, cached
- UI: Polished, delightful
- Grade: A (9.5/10)

---

## How to Maintain B→A Trajectory

### Keep Doing

1. ✅ Scrutinize continuously
2. ✅ Grade honestly
3. ✅ Fix bugs immediately
4. ✅ Test rigorously
5. ✅ Document comprehensively

### Stop Doing

1. ❌ Inflating grades
2. ❌ Skipping validation steps
3. ❌ Trusting tests alone
4. ❌ Shipping known bugs

### Start Doing

1. 🆕 Automated quality checks
2. 🆕 Continuous integration
3. 🆕 User feedback loops
4. 🆕 Performance monitoring

---

## Expected Final State (Week 3)

```
DeckSage - Multi-Game Card Similarity Platform
Status: ✅ PRODUCTION
Grade: A (9/10)

Games:
- MTG: 300+ decks, embeddings validated ✅
- YGO: 100+ decks, embeddings validated ✅
- Pokemon: Working or deprecated (clear status) ✅

Quality:
- Critical bugs: 0 ✅
- Test coverage: 60-70% ✅
- Expert validation: Passed ✅
- User validation: Initial feedback positive ✅

Features:
- REST API: Working, documented ✅
- Web UI: Functional, responsive ✅
- Monitoring: Active ✅

Documentation:
- 40+ files, comprehensive ✅
- Known limitations documented ✅
```

---

## The Honest Promise

**We will not declare "production ready" until**:

1. All critical bugs are fixed
2. Tests cover concurrent paths
3. Data diversity is validated
4. Expert review passes for all games
5. API is load tested
6. Users validate the product

**No shortcuts. No inflated grades. No premature celebration.**

**Just rigorous engineering until it's truly ready.**

---

**Current**: B (7/10) - Bugs + data gaps documented
**Week 1**: B+ (8/10) - Bugs fixed, tests added
**Week 2**: A- (9/10) - Data diversity achieved
**Week 3**: A (9/10) - Production deployed

**Timeline**: Realistic, based on actual experience
**Commitment**: Fix it right, then ship it

🎯 **From B to A through rigorous engineering, not wishful thinking**
