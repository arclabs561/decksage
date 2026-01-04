# Deck Modification System Design

**Date**: 2025-01-27
**Status**: Design phase - ready for implementation

---

## Executive Summary

Design a comprehensive deck modification system that supports multiple interaction modes:
1. **Incremental refinement** - "What should I add/remove/replace?"
2. **Strategic optimization** - "How do I improve this deck?"
3. **Contextual discovery** - "What works with this card?"
4. **Archetype guidance** - "What am I missing for this archetype?"

**Key Insight**: Users want **constrained choice** (5-10 options) with **clear reasoning**, not overwhelming lists.

---

## Real User Needs (From Research)

### What Users Actually Want

1. **Quick Iteration** - Add/remove cards without friction
2. **Clear Reasoning** - "Why is this card recommended?"
3. **Context Awareness** - Format, archetype, budget constraints
4. **Visual Feedback** - See deck stats change in real-time
5. **Package Reuse** - Save common card combinations
6. **Strategic Guidance** - "You're missing removal" not just "add these cards"

### What Doesn't Work

- ❌ Overwhelming lists (20+ suggestions)
- ❌ Generic recommendations without context
- ❌ No explanation of why cards are suggested
- ❌ Ignoring format legality and budget
- ❌ Treating all cards equally (no role awareness)

---

## System Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────┐
│              Deck Modification API                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Incremental │  │  Strategic    │  │  Contextual   │ │
│  │  Refinement  │  │  Optimization │  │  Discovery    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Recommendation Engine                    │  │
│  │  - Similarity signals (embedding, jaccard, etc.) │  │
│  │  - Archetype analysis                             │  │
│  │  - Functional role coverage                      │  │
│  │  - Budget/format constraints                     │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Explanation Generator                     │  │
│  │  - Why this card?                                │  │
│  │  - What role does it fill?                       │  │
│  │  - How does it improve the deck?                 │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## API Design

### 1. Incremental Refinement: `POST /v1/deck/refine`

**Use Case**: "I have a partial deck, what should I add/remove/replace?"

```python
class RefineRequest(BaseModel):
    game: Literal["magic", "yugioh", "pokemon"]
    deck: dict  # Current deck state
    mode: Literal["add", "remove", "replace", "suggest"] = "suggest"
    constraints: Optional[RefineConstraints] = None
    top_k: int = 10  # Constrained choice - max 10 suggestions

class RefineConstraints(BaseModel):
    budget_max: Optional[float] = None
    format: Optional[str] = None  # "Modern", "Legacy", etc.
    archetype: Optional[str] = None  # "Burn", "Control", etc.
    preserve_roles: bool = True  # Don't remove cards that fill unique roles

class RefineResponse(BaseModel):
    suggestions: list[CardSuggestion]
    deck_stats: DeckStats  # Before/after comparison
    reasoning: list[str]  # Why these suggestions?

class CardSuggestion(BaseModel):
    card: str
    action: Literal["add", "remove", "replace_with", "move_to_sideboard"]
    target: Optional[str] = None  # For replace/move actions
    score: float
    reasoning: str  # "Fills removal gap", "Budget alternative to X", etc.
    impact: dict[str, Any]  # How this changes deck stats
```

**Example Request**:
```json
{
  "game": "magic",
  "deck": {
    "main": {"Lightning Bolt": 4, "Monastery Swiftspear": 4},
    "sideboard": {}
  },
  "mode": "suggest",
  "constraints": {
    "budget_max": 5.0,
    "format": "Modern",
    "archetype": "Burn"
  },
  "top_k": 8
}
```

**Example Response**:
```json
{
  "suggestions": [
    {
      "card": "Lava Spike",
      "action": "add",
      "score": 0.92,
      "reasoning": "Archetype staple - appears in 87% of Modern Burn decks. Fills direct damage role.",
      "impact": {
        "direct_damage_count": "+4",
        "archetype_coverage": "+12%"
      }
    },
    {
      "card": "Rift Bolt",
      "action": "add",
      "score": 0.88,
      "reasoning": "Budget alternative to Skewer the Critics. Similar effect, lower price.",
      "impact": {
        "direct_damage_count": "+4",
        "budget_remaining": "-$2.40"
      }
    }
  ],
  "deck_stats": {
    "before": {"size": 8, "archetype_coverage": 0.15},
    "after": {"size": 16, "archetype_coverage": 0.27}
  },
  "reasoning": [
    "Deck is missing key Burn staples (Lava Spike, Rift Bolt)",
    "Low removal count - consider adding Searing Blaze",
    "Budget allows for 8 more cards under $5"
  ]
}
```

---

### 2. Strategic Optimization: `POST /v1/deck/optimize`

**Use Case**: "How do I improve this complete deck?"

```python
class OptimizeRequest(BaseModel):
    game: Literal["magic", "yugioh", "pokemon"]
    deck: dict
    objective: Literal["archetype_coverage", "budget_efficiency", "meta_positioning", "role_balance"]
    constraints: Optional[RefineConstraints] = None
    max_changes: int = 5  # Limit changes to avoid overwhelming

class OptimizeResponse(BaseModel):
    current_analysis: DeckAnalysis
    recommendations: list[OptimizationRecommendation]
    projected_improvement: dict[str, float]

class DeckAnalysis(BaseModel):
    archetype_match: float  # How well does this match archetype?
    role_coverage: dict[str, float]  # Removal, threats, etc.
    budget_efficiency: float
    meta_relevance: float
    weaknesses: list[str]  # "Low removal count", "Missing sideboard tech"

class OptimizationRecommendation(BaseModel):
    changes: list[CardChange]  # Atomic changes
    reasoning: str
    expected_improvement: dict[str, float]
    confidence: float

class CardChange(BaseModel):
    action: Literal["add", "remove", "replace"]
    card: str
    target: Optional[str] = None
    count: int = 1
```

**Example**:
```json
{
  "game": "magic",
  "deck": { /* complete 75-card deck */ },
  "objective": "archetype_coverage",
  "max_changes": 3
}
```

**Response**:
```json
{
  "current_analysis": {
    "archetype_match": 0.72,
    "role_coverage": {"removal": 0.6, "threats": 0.9, "card_draw": 0.4},
    "weaknesses": ["Low card draw", "Missing graveyard hate in sideboard"]
  },
  "recommendations": [
    {
      "changes": [
        {"action": "add", "card": "Expressive Iteration", "count": 2},
        {"action": "remove", "card": "Opt", "count": 2}
      ],
      "reasoning": "Expressive Iteration is the current meta standard for card draw in this archetype. Replaces Opt for better card advantage.",
      "expected_improvement": {
        "archetype_match": "+0.08",
        "card_draw_quality": "+0.15"
      },
      "confidence": 0.89
    }
  ]
}
```

---

### 3. Contextual Discovery: `POST /v1/cards/{card}/contextual`

**Use Case**: "What works well with Lightning Bolt?"

```python
class ContextualRequest(BaseModel):
    card: str
    game: Literal["magic", "yugioh", "pokemon"]
    context: Optional[ContextualContext] = None

class ContextualContext(BaseModel):
    format: Optional[str] = None
    archetype: Optional[str] = None
    current_deck: Optional[dict] = None  # Filter to cards that work with current deck
    role: Optional[str] = None  # "removal", "threat", etc.

class ContextualResponse(BaseModel):
    synergies: list[CardSynergy]  # Cards that work well together
    alternatives: list[CardAlternative]  # Functional alternatives
    upgrades: list[CardUpgrade]  # Better versions (if budget allows)
    downgrades: list[CardDowngrade]  # Budget alternatives

class CardSynergy(BaseModel):
    card: str
    score: float
    co_occurrence_rate: float  # % of decks with both cards
    reasoning: str  # "Commonly played together in Burn decks"
```

**Example**:
```json
GET /v1/cards/Lightning Bolt/contextual?game=magic&format=Modern&archetype=Burn
```

**Response**:
```json
{
  "synergies": [
    {
      "card": "Lava Spike",
      "score": 0.94,
      "co_occurrence_rate": 0.89,
      "reasoning": "Both are direct damage spells. Appear together in 89% of Modern Burn decks."
    },
    {
      "card": "Monastery Swiftspear",
      "score": 0.87,
      "co_occurrence_rate": 0.82,
      "reasoning": "Swiftspear benefits from instant-speed spells. Synergistic in aggressive strategies."
    }
  ],
  "alternatives": [
    {
      "card": "Chain Lightning",
      "score": 0.91,
      "reasoning": "Functional equivalent - 3 damage instant. Slightly more expensive mana cost."
    }
  ],
  "upgrades": [
    {
      "card": "Skewer the Critics",
      "score": 0.88,
      "reasoning": "Similar effect with spectacle cost. More flexible in late game."
    }
  ],
  "downgrades": [
    {
      "card": "Shock",
      "score": 0.72,
      "reasoning": "Budget alternative - 2 damage instead of 3. Much cheaper price."
    }
  ]
}
```

---

### 4. Archetype Guidance: `POST /v1/deck/archetype_guidance`

**Use Case**: "What am I missing for a proper Burn deck?"

```python
class ArchetypeGuidanceRequest(BaseModel):
    game: Literal["magic", "yugioh", "pokemon"]
    deck: dict
    archetype: str
    format: Optional[str] = None

class ArchetypeGuidanceResponse(BaseModel):
    staples: list[ArchetypeStaple]  # Cards in 70%+ of archetype decks
    missing_staples: list[str]  # Staples not in current deck
    role_gaps: list[RoleGap]  # Functional roles not covered
    meta_positioning: dict[str, Any]  # How this compares to meta

class ArchetypeStaple(BaseModel):
    card: str
    inclusion_rate: float  # % of archetype decks
    typical_count: int  # How many copies usually run
    role: str  # "removal", "threat", "card_draw", etc.

class RoleGap(BaseModel):
    role: str
    current_count: int
    recommended_count: int
    suggestions: list[str]
```

---

## Implementation Strategy

### Phase 1: Core Refinement (Week 1)

1. **Enhance `suggest_additions`** with:
   - Role-aware filtering (don't suggest 10 removal spells)
   - Archetype context (filter to archetype staples)
   - Budget constraints (already exists)
   - Explanation generation

2. **Add `suggest_removals`**:
   - Identify weak cards (low similarity to archetype)
   - Identify redundant cards (multiple cards filling same role)
   - Consider format legality

3. **Add `suggest_replacements`**:
   - Find better alternatives for specific cards
   - Consider budget (upgrade/downgrade)
   - Maintain role coverage

### Phase 2: Strategic Analysis (Week 2)

1. **Deck Analysis Module**:
   - Archetype matching score
   - Role coverage analysis
   - Budget efficiency
   - Meta relevance

2. **Optimization Engine**:
   - Multi-objective optimization (archetype + budget + role balance)
   - Constrained changes (max 5 changes)
   - Confidence scoring

### Phase 3: Contextual Discovery (Week 3)

1. **Card Context API**:
   - Synergy detection (co-occurrence + archetype)
   - Alternative finding (functional similarity)
   - Upgrade/downgrade paths (price + power)

2. **Integration with similarity**:
   - Use existing embedding/jaccard signals
   - Add archetype co-occurrence
   - Add format-specific patterns

### Phase 4: UX Polish (Week 4)

1. **Explanation Generation**:
   - Template-based reasoning
   - Statistical backing ("87% of decks include this")
   - Role-based explanations

2. **Visual Feedback**:
   - Deck stats before/after
   - Impact visualization
   - Confidence indicators

---

## Key Design Decisions

### 1. Constrained Choice (5-10 suggestions max)

**Rationale**: Research shows users prefer 5 choices over 20. Too many options cause analysis paralysis.

**Implementation**: Always limit `top_k` to 10, prioritize by:
1. Archetype relevance
2. Role coverage
3. Budget fit
4. Similarity score

### 2. Explanation-First Design

**Rationale**: Users need to understand *why* a card is suggested, not just *what*.

**Implementation**: Every suggestion includes:
- Primary reason ("Archetype staple")
- Statistical backing ("87% inclusion rate")
- Role impact ("Fills removal gap")

### 3. Role-Aware Recommendations

**Rationale**: Decks need balance - suggesting 10 removal spells is useless.

**Implementation**:
- Track functional roles in deck
- Identify gaps (missing removal, threats, etc.)
- Prioritize suggestions that fill gaps
- Avoid redundant suggestions

### 4. Context-Aware Filtering

**Rationale**: Modern Burn suggestions don't help Legacy players.

**Implementation**:
- Always filter by format (if provided)
- Filter by archetype (if provided)
- Use format-specific co-occurrence patterns
- Respect budget constraints

### 5. Incremental vs Batch

**Rationale**: Users want to iterate, not get overwhelmed.

**Implementation**:
- Default to incremental (1-3 suggestions)
- Support batch mode for power users
- Show impact of each change
- Allow "apply all" with confirmation

---

## Integration with Existing Code

### Leverage Existing

1. **`suggest_additions`** - Enhance with role awareness
2. **Similarity signals** - Use embedding/jaccard/fusion
3. **Functional tagger** - For role detection
4. **Beam search** - For multi-step optimization

### New Components Needed

1. **`DeckAnalyzer`** - Analyze deck composition
2. **`RoleCoverageTracker`** - Track functional roles
3. **`ArchetypeMatcher`** - Match deck to archetype
4. **`ExplanationGenerator`** - Generate human-readable reasons
5. **`OptimizationEngine`** - Multi-objective optimization

---

## Success Metrics

1. **User Satisfaction**: Do suggestions feel relevant?
2. **Action Rate**: Do users actually add suggested cards?
3. **Deck Quality**: Do optimized decks perform better?
4. **Explanation Quality**: Do users understand why cards are suggested?

---

## Next Steps

1. ✅ Design complete
2. ⏳ Implement Phase 1 (core refinement)
3. ⏳ Test with real decks
4. ⏳ Iterate based on feedback
5. ⏳ Expand to Phase 2-4

---

**Status**: Ready for implementation. Start with Phase 1 enhancements to `suggest_additions`.
