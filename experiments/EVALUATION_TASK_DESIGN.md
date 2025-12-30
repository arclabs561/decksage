# Evaluation Task Design and Annotation Quality Framework

## Executive Summary

This document synthesizes research on what makes high-quality labeled tasks, results, and annotations for card similarity systems. It identifies all evaluation tasks we should support, provides detailed annotation guidelines, and outlines a comprehensive evaluation framework.

## Part 1: What Makes Good Labeled Tasks/Results/Annotations

### 1.1 Core Principles of High-Quality Annotations

**Clear, Unambiguous Guidelines**
- Every annotation task must have explicit definitions with concrete examples
- Guidelines should address edge cases and ambiguous scenarios proactively
- Use anchoring examples (canonical pairs) to calibrate annotator standards
- Guidelines should evolve iteratively based on annotator feedback

**Multi-Annotator Consensus**
- Use multiple annotators (3-5) per item to measure inter-annotator agreement
- Employ weighted consensus (Dawid-Skene) rather than simple majority voting
- Track individual annotator reliability and weight accordingly
- Accept disagreement as data when it reflects genuine subjectivity

**Quality Assurance Mechanisms**
- Gold standard datasets (10-20% of items) verified by expert judges
- Regular sampling and review (10-20% of work) by senior annotators
- Real-time feedback to annotators on potential inconsistencies
- Systematic error detection and correction workflows

**Inter-Annotator Agreement Targets**
- Cohen's Kappa or Krippendorff's Alpha ≥ 0.65-0.75 for recommendation systems
- Higher thresholds (≥0.8) for high-stakes applications
- Lower thresholds acceptable for genuinely subjective tasks
- Track agreement over time to detect annotator drift

### 1.2 Annotation Schema Design

**Graded Relevance Scales**
- Use 0-4 scale (not binary) to capture nuanced relationships:
  - 4: Perfect/ideal match (functional substitute, can replace)
  - 3: Strong/very appropriate (similar role, minor differences)
  - 2: Moderate/generally appropriate (related but not substitutable)
  - 1: Weak/partially appropriate (loose connection)
  - 0: Completely wrong/inappropriate (no meaningful relationship)

**Multi-Dimensional Annotation**
- Don't collapse all relationships into single similarity score
- Annotate separately: functional similarity, synergy strength, substitutability, archetype fit
- Capture reasoning/explanation for each judgment
- Include context metadata (format, archetype, use case)

**Temporal and Contextual Awareness**
- Annotations must account for temporal context (meta shifts, ban lists, price changes)
- Format legality is a hard constraint (banned = relevance 0)
- Budget constraints affect relevance (exceeds budget = relevance 0)
- Power level matching matters (casual vs competitive)

## Part 2: Complete Task Taxonomy (19+ Tasks)

### Core Similarity Tasks (3)
1. **Card Similarity** (Primary) - Measure functional similarity
2. **Functional Substitution** - Find replaceable cards
3. **Synergy Discovery** - Find cards that work together

### Downstream Application Tasks (3)
4. **Deck Completion** - Suggest cards to complete partial decks
5. **Contextual Discovery** - Find synergies/alternatives/upgrades/downgrades
6. **Archetype Classification** - Identify deck archetypes

### Advanced Relationship Tasks (3)
7. **Upgrade/Downgrade Paths** - Find better/cheaper versions
8. **Combo Piece Identification** - Identify combo enablers/protectors
9. **Meta Positioning** - Assess meta relevance

### Multi-Game Tasks (1)
10. **Cross-Game Similarity** - Similar cards across MTG/YGO/PKM

### Additional Useful Tasks (9+)
11. Format-Specific Similarity
12. Archetype-Specific Similarity
13. Budget-Aware Similarity
14. Meta Shift Detection
15. Ban Risk Assessment
16. Visual Similarity
17. Flavor Similarity
18. Intent Classification
19. Query Expansion

## Part 3: Key Research Findings

### What Makes Good Annotations
- **Clear guidelines** with examples and edge cases
- **Multi-annotator consensus** (3-5 annotators, weighted by reliability)
- **Quality assurance** (gold standards, expert review, real-time feedback)
- **Graded scales** (0-4, not binary) for nuanced relationships
- **Multi-dimensional** annotation (separate scores for different aspects)
- **Temporal awareness** (meta shifts, ban lists, price changes)

### Evaluation Metrics by Task
- **Similarity**: P@K, MRR, NDCG, confidence intervals
- **Substitution**: P@1/5/10, average rank, coverage
- **Deck Completion**: completion rate, quality, balance impact
- **Contextual Discovery**: precision@K per category, diversity

### Annotation Quality Targets
- Inter-annotator agreement ≥ 0.65-0.75 (Cohen's Kappa/Krippendorff's Alpha)
- Agreement with gold standards ≥ 0.80
- Systematic disagreement patterns identified and addressed

## Part 4: Implementation Priorities

### Immediate (Primary Tasks 1-6)
1. Expand test sets: 200 queries Magic, 100 Pokemon/YGO
2. Improve annotation quality: multi-judge with IAA tracking
3. Task coverage: ensure all primary tasks have test sets
4. Unified evaluation framework across all tasks

### Medium-Term (Advanced Tasks 7-10)
1. Upgrade/downgrade paths test sets
2. Combo piece identification
3. Meta positioning assessment
4. Cross-game similarity expansion

### Long-Term (Comprehensive Coverage)
1. All 19+ tasks with test sets
2. Continuous evaluation pipeline
3. Quality monitoring over time
4. Research publication of framework

## Conclusion

High-quality annotations require clear guidelines, multi-annotator consensus, quality assurance, and appropriate agreement metrics. Our task taxonomy covers 19+ evaluation tasks. Implementation should prioritize primary tasks while building toward comprehensive coverage.

The key is treating annotation as a first-class concern, not an afterthought. Invest in guidelines, tools, and processes that ensure annotation quality.
