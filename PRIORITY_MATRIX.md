# Priority Matrix: Next Actions

**Context**: Post-fixes deep review of DeckSage ML system  
**Date**: October 6, 2025

---

## Visual Priority Map

```
Impact
  ↑
  │  ┌─────────────────┐
  │  │ T0.1: Test Set  │ ← START HERE
  │  │ T0.2: Deck Qual │ ← THEN THIS  
  │  ├─────────────────┤
  │  │ T1.1: Text Emb  │ ← BIGGEST WIN
  │  └─────────────────┘
  │  ┌────────┐┌────────┐
  │  │T0.3:Dash││T1.2:A/B│
  │  └────────┘└────────┘
  │  ┌────┐┌────┐┌────┐
  │  │T2.1││T2.2││T2.3│
  │  └────┘└────┘└────┘
  │  ┌────┐┌────┐
  │  │T3.1││T3.2│
  │  └────┘└────┘
  └─────────────────────→ Effort
```

---

## Decision Tree

```
START: What are you optimizing for?

├─ Production Launch (MVP)?
│  └─> Do: T0.2 (deck quality) + T0.1 (50 queries)
│      Time: 10-15 hours
│      Result: Validated core feature
│
├─ Research Performance (P@10 goal)?
│  └─> Do: T0.1 (100 queries) + T1.1 (text embeddings)
│      Time: 20-30 hours
│      Result: P@10 = 0.18-0.22 (meeting README goal)
│
├─ Production + Performance?
│  └─> Do: All T0 + T1.1 + T1.2
│      Time: 35-45 hours
│      Result: Production-ready system hitting goals
│
└─ Maintenance / Tech Debt?
   └─> Do: T2.* items
       Time: 6-9 hours
       Result: Cleaner, more maintainable code
```

---

## Quick Triage by Role

### If You're a Researcher
**Focus**: T0.1 (test set) + T1.1 (text embeddings)  
**Why**: Need rigorous evaluation and performance improvement  
**Skip**: T2.* (technical debt), T0.3 (dashboard)

### If You're Building a Product  
**Focus**: T0.2 (deck quality) + T0.3 (monitoring)  
**Why**: Need to validate UX and prevent degradation  
**Skip**: T1.1 (performance optimization can wait)

### If You're Maintaining This
**Focus**: T2.2 (paths) + T2.3 (types) + T0.3 (dashboard)  
**Why**: Reduce future maintenance burden  
**Skip**: T1.* (research improvements)

---

## Effort vs Value Matrix

```
Value
  ↑
H │ [T0.1]    [T0.2]          [T1.1]
I │ 6-10h     6-10h           13-19h
G │
H │     [T0.3]    [T1.2]
  │     4-6h      6-8h
M │                    [T1.3]
E │                    10-15h
D │ [T2.2]  [T2.1]  [T2.3]
I │ 1-2h    2-3h    3-4h
U │
M │ [T3.1]  [T3.2]
  │ 4-6h    2-3h
L │
O └────────────────────────────→ Effort
W   Low    Medium    High
```

---

## Monthly Roadmap (If Sustained Focus)

### Month 1: Foundation
**Goal**: Trustworthy evaluation + validated core feature

- Week 1: T0.1 (expand test set to 100 queries)
- Week 2: T0.2 (deck quality validation)  
- Week 3: T0.3 (quality dashboard)
- Week 4: T2.2 (fix hardcoded paths)

**Outcome**: Know definitively if system works

### Month 2: Performance
**Goal**: Break P@10 plateau

- Week 1-2: T1.1 (implement card text embeddings)
- Week 3: T1.2 (A/B testing framework)
- Week 4: Re-tune fusion, generate comparison reports

**Outcome**: P@10 = 0.18-0.22 (meeting README goal)

### Month 3: Production Readiness
**Goal**: Reliable, maintainable system

- Week 1: T2.1 + T2.3 (clean up technical debt)
- Week 2: T3.1 (dataset versioning if needed)
- Week 3: Performance optimization
- Week 4: Documentation polish

**Outcome**: Production deployment ready

---

## Critical Path Analysis

**To Ship MVP (Deck Completion Tool)**:
```
T0.2 (deck quality) → Validate use case works
      ↓
    Launch
```
**Time**: 6-10 hours

**To Meet README Goals (P@10 = 0.20)**:
```
T0.1 (test set) → T1.1 (text embeddings) → Recompute metrics
    ↓                  ↓                         ↓
  Rigor            Performance                Success
```
**Time**: 19-29 hours

**To Production Deploy**:
```
T0.1 → T0.2 → T0.3 → T1.1 → T1.2 → Launch
```
**Time**: 35-45 hours

---

## Risk Assessment

| Action | Technical Risk | Business Risk | Mitigation |
|--------|----------------|---------------|------------|
| T0.1 | Low | None | Annotation is safe |
| T0.2 | Medium | Low | Quality def needs alignment |
| T0.3 | Low | None | Monitoring is pure upside |
| T1.1 | Medium | Medium | Might not reach 0.20 goal |
| T1.2 | Low | None | Infrastructure improvement |
| T1.3 | High | Medium | Might not beat greedy |
| T2.* | Low | None | Pure cleanup |

**Highest ROI**: T0.1 + T0.2 (foundation)  
**Biggest Leap**: T1.1 (text embeddings)  
**Safest Bets**: T0.3 + T2.2 (monitoring + paths)

---

## Resources Needed

### For T0 (Foundation)
- **Human time**: 16-26 hours annotation + coding
- **Compute**: Minimal (local dev)
- **Cost**: $0 (no API calls)

### For T1 (Performance)
- **Human time**: 19-27 hours coding + tuning
- **Compute**: GPU helpful for text embeddings (but CPU works)
- **Cost**: ~$5-10 for sentence-transformer inference (or $0 with local models)

### For Full System
- **Human time**: 35-45 hours
- **Compute**: Local development machine
- **Cost**: <$20 total (mostly LLM caching reduces this)

---

## Success Criteria

### T0 (Foundation) Success =
- [ ] 100+ annotated queries across 3 games
- [ ] Confidence intervals on all metrics
- [ ] Deck quality score defined and measured
- [ ] Quality dashboard shows green (>95% validation)

### T1 (Performance) Success =
- [ ] P@10 = 0.18-0.22 with text embeddings
- [ ] Statistical significance vs baseline (p < 0.05)
- [ ] A/B framework validates improvements
- [ ] Updated fusion weights saved to `experiments/`

### Production Success =
- [ ] All T0 + T1 complete
- [ ] API serves fusion with text signal
- [ ] Quality monitoring active
- [ ] Documentation reflects reality

---

## Quick Decision Guide

**Question**: Should I do this next action?

**Decision rubric**:
1. Does it validate core assumptions? → **T0** (do first)
2. Does it achieve README goals? → **T1** (do next)
3. Does it reduce tech debt? → **T2** (do when stable)
4. Is it nice-to-have? → **T3** (do if time permits)

**When in doubt**: Do T0.1 first. Evaluation rigor unlocks everything else.

---

## Anti-Patterns to Avoid

Based on `experimental/REALITY_FINDINGS.md`:

❌ **Don't**: Optimize graph algorithms further  
✅ **Do**: Add new signals (text, type, CMC)

❌ **Don't**: Add format-specific filtering  
✅ **Do**: Accept co-occurrence serves specific use cases

❌ **Don't**: Scrape more decks without quality checks  
✅ **Do**: Improve signal quality over quantity

❌ **Don't**: Declare "production ready" prematurely  
✅ **Do**: Validate core features work first (T0.2)

---

## This Document vs Others

- **README.md**: What the system is, how to use it
- **REVIEW_SUMMARY.md**: What was fixed today
- **DEEP_REVIEW_TRIAGED_ACTIONS.md**: Why + detailed analysis
- **QUICK_REFERENCE.md**: Daily workflow reference (current file)
- **This file**: Decision-making tool for next actions

Use this file when asking: "What should I work on next?"
