# DeckSage Failure Mode Taxonomy

Based on qualitative analysis of 60 queries (20 per game) across embedding,
fusion, and jaccard methods. 2026-03-31.

## Overall Accuracy

| Game | Correct top-1 | Acceptable top-3 | Primary failure mode |
|------|--------------|-------------------|---------------------|
| Magic | 60% | 78% | Text token overlap (name matching) |
| Pokemon | 72% | 85% | Type/tribe matching |
| YuGiOh | 70% | 83% | Archetype name overlap |

## Failure Categories

### 1. Text Token Overlap (40% of failures)

The reranker's text_e5 signal matches on shared words in card names or
oracle text, even when the cards serve completely different functions.

Examples:
- "Sacred Ground" returned for "Wrath of God" (shares no function,
  but "ground" appears in board-wipe contexts)
- "Goblin Guide" returned for "Goblin Chainwhirler" (goblin tribe match,
  different roles: aggro 1-drop vs midrange sweeper)

### 2. Type/Tribe Matching (25% of failures)

Cards of the same creature type or card type cluster together regardless
of function. Particularly bad for Pokemon (type-heavy game).

Examples:
- Fire-type Pokemon returned for other Fire-types despite completely
  different attack patterns and deck roles
- YuGiOh archetype members returned for each other even when they
  serve different combo roles (starter vs extender vs payoff)

### 3. Co-occurrence Dominance (20% of failures)

When use_case=substitute, co-occurrence signals still leak through the
reranker and push deck partners (complements) above functional
substitutes. The text-boost dampening (0.3x on co-occur sources)
helps but doesn't fully solve this.

Examples:
- Synergy partners ranked above true substitutes for narrow-use cards
- Commander staples (Sol Ring, Command Tower) appear in results for
  unrelated queries because they co-occur with everything

### 4. Stat/Cost Mismatch (10% of failures)

Cards with similar text but wildly different mana costs or power levels
are returned as substitutes. A 2-mana counterspell is not a substitute
for a 5-mana counterspell in competitive play.

### 5. Format Blindness (5% of failures)

Results include cards from different formats or eras that wouldn't
actually be legal replacements. Less of a similarity failure and more
of a missing filter.

## Implications for Training

1. The cross-encoder should learn to distinguish functional similarity
   from surface text overlap. Including card name + type + cost in the
   training text helps (v3 does this).

2. Co-occurrence signal should be more aggressively dampened for
   substitute queries, or excluded entirely (use text_e5 + cross-encoder
   only).

3. Stat/cost matching could be a hard filter (not a soft signal) --
   reject candidates with >2 mana cost difference for substitute mode.

4. Format legality filtering is already available via the `format`
   parameter but isn't applied by default in the UI.
