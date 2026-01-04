# Theoretical Critique of LLM Validators

## Applying Structured Reasoning Theory to Current Implementation

### The Theoretical Framework

From the research context:
1. **Locality of experience**: Reasoning emerges from chaining local dependencies
2. **Dependency gaps**: P(C|A) requires marginalization through B
3. **Mantras**: Keys that induce currents/attractors in generation field F
4. **D-separation**: Intermediate variables reduce bias when direct data sparse
5. **Kolmogorov complexity**: K(prompt) must match K(function) for alignment

### Current Implementation Analysis

#### Our Pydantic Schemas

**SimilarityEvaluation:**
```python
class SimilarityEvaluation(BaseModel):
    overall_quality: int = Field(ge=0, le=10)
    analysis: str
    card_ratings: list[CardRating]
    issues: list[str]
    missing_cards: list[str]
    biases_detected: list[str]
    suggestions: list[str]
```

**Theoretical issue:** This is **output structure**, not **reasoning structure**.

### The Dependency Problem

**What we have:**
```
P(all_fields | query, cards, context)
```

Model generates all fields somewhat independently from same context.

**What theory suggests:**
```
P(card_ratings | query, cards)
→ P(issues | card_ratings, context)
→ P(missing | card_ratings, issues, domain_knowledge)
→ P(biases | issues, missing, card_ratings)
→ P(overall_quality | card_ratings, issues, biases)
→ P(suggestions | all_above)
```

Each field should condition on previous fields, creating local dependency chain.

### Why This Matters

From the "locality of experience" paper:
- **Reasoning reduces bias** when it marginalizes through intermediate variables
- **Local dependencies** in training data make reasoning effective
- **Direct prediction** (our current approach) has higher bias

Our schema asks model to produce:
```
{overall_quality: 7, analysis: "...", card_ratings: [...], ...}
```

All at once. No explicit chaining of local dependencies.

### Concrete Example

**Query:** "Is Chain Lightning similar to Lightning Bolt?"

**Current approach (one-shot):**
- Model sees: query + candidates + full schema
- Generates: all fields somewhat simultaneously
- Result: Fields may be inconsistent (quality=8 but issues list is long)

**Theory-aligned approach (chained):**
1. Generate card_ratings first:
   ```json
   {"card": "Chain Lightning", "relevance": 4, "reasoning": "Nearly identical"}
   ```
2. Then generate issues conditioned on card_ratings:
   ```json
   {"issues": ["Missing: Lava Spike, Shock"]}
   ```
3. Then quality conditioned on both:
   ```json
   {"overall_quality": 6}  // Lower due to missing cards
   ```

### Actual Behavior Check

Let me check if Pydantic AI actually enforces order...

**Hypothesis:** Pydantic AI with structured outputs generates fields in order, creating implicit chain.

**Test needed:** Does model see card_ratings when generating overall_quality?

### Implications

If fields are generated independently:
- ❌ Not leveraging locality of experience
- ❌ Higher bias (direct prediction)
- ❌ Inconsistencies between fields possible
- ❌ Not true "structured reasoning"

If fields are generated sequentially:
- ✅ Chains local dependencies
- ✅ Reduces bias per theory
- ✅ Better consistency
- ✅ True structured reasoning

### The "Mantras" Question

**Are our field names actually mantras?**

Current names:
- `overall_quality` - numeric, not much semantic pull
- `analysis` - generic, weak attractor
- `card_ratings` - specific, stronger attractor
- `issues` - specific, good attractor
- `missing_cards` - very specific, strong attractor

**Theory suggests:**
- Stronger semantic keys create stronger currents in F
- Generic keys (`analysis`) provide weak guidance
- Specific keys (`missing_cards`) create focused sub-problems

### Recommended Changes (Theory-Driven)

#### Option A: Sequential Multi-Step Agents

Instead of one schema, chain multiple agents:
```python
# Step 1: Rate each card
ratings = await agent_rate_cards.run(query, cards)

# Step 2: Identify issues (conditioned on ratings)
issues = await agent_find_issues.run(query, ratings)

# Step 3: Overall quality (conditioned on ratings + issues)
quality = await agent_assess_quality.run(ratings, issues)
```

**Pros:** Explicit dependency chain, aligns with theory
**Cons:** Multiple API calls, slower, more expensive

#### Option B: Enhanced Prompt Structure

Make dependencies explicit in prompt:
```python
prompt = f"""
STEP 1: Rate each card individually
[For each card, provide: relevance 0-4, reasoning]

STEP 2: Based on your ratings, identify issues
[List problems you see in the predictions]

STEP 3: Based on ratings and issues, what's missing?
[Cards that should be here but aren't]

STEP 4: Based on ALL above, assign overall quality 0-10
[Consider: ratings, issues, missing cards]
"""
```

**Pros:** Explicit reasoning chain in single call
**Cons:** Relies on model following steps (not enforced)

#### Option C: Nested Pydantic Models with Clear Dependencies

```python
class Step1_CardRatings(BaseModel):
    ratings: list[CardRating]
    reasoning_for_ratings: str

class Step2_IssueAnalysis(BaseModel):
    card_ratings_summary: str  # Force model to reference step 1
    issues_found: list[str]
    reasoning_for_issues: str

class Step3_OverallAssessment(BaseModel):
    ratings_summary: str  # Reference step 1
    issues_summary: str  # Reference step 2
    overall_quality: int
    final_reasoning: str
```

**Pros:** Forces model to reference prior steps
**Cons:** Verbose, more complex schema

### Current Schema Limitations

1. **No explicit dependency chain**
   - Fields don't reference each other
   - Model could generate inconsistent outputs

2. **Weak semantic keys**
   - `analysis` is too generic
   - Doesn't create strong attractor in F

3. **No intermediate marginalization**
   - Jumps directly from input to output
   - Misses opportunity to leverage locality

4. **Mixing levels of abstraction**
   - `card_ratings` (detailed) and `analysis` (summary) at same level
   - Should be hierarchical: details → summary

### Evidence in Current Tests

Looking at actual output from our tests:
```
Quality Score: 6/10
Analysis: "predictions capture some legitimate burn spells..."
Issues: "Model confuses creatures with burn spells"
```

**Inconsistency check:** Quality 6/10 but analysis sounds negative?

This supports the theory that fields are generated somewhat independently, leading to potential inconsistencies.

### Measurement Proposal

To validate theoretical concerns:
1. Generate same evaluation 10 times
2. Check consistency:
   - Does high quality correlate with few issues?
   - Does low quality correlate with many missing_cards?
3. If correlations weak → fields generated independently (bad)
4. If correlations strong → fields have implicit dependencies (better)

### Conclusion

**Current implementation:**
- Uses structured outputs (Pydantic) ✓
- But doesn't leverage locality of experience ✗
- Fields may be generated with weak dependencies ✗
- Not true "structured reasoning" from theory ✗

**Grade:** B for implementation, C for theoretical alignment

**Recommendation:**
Either accept current approach as "good enough" or redesign to explicitly chain local dependencies per theory.

Given 4 hours already spent and diminishing returns, documenting this theoretical limitation is probably correct choice.

---

**Key insight from theory:**
Structured *output* ≠ Structured *reasoning*

We have the former, not necessarily the latter.
