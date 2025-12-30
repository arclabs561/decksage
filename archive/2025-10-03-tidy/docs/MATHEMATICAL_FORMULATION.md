# Mathematical Formulation of Deck Improvement

## Problem Statement

**Input:** Deck $D = \{c_1, c_2, ..., c_n\}$, Card pool $C$

**Output:** Recommendations $R = \{(c_{remove}, c_{add}, score)\}$

**Objective:** Maximize deck quality $Q(D)$

## What is Deck Quality?

### Option 1: Win Rate (Simulation-Based)
$$Q(D) = \mathbb{E}_{D' \sim \text{MetaDecks}}[\text{WinRate}(D, D')]$$

Requires: Game simulator (expensive, 300 games per eval in Q-DeckRec paper)

### Option 2: Similarity to Tournament Decks (Supervised)
$$Q(D) = \max_{D_{tournament} \in \mathcal{T}} \text{Similarity}(D, D_{tournament})$$

Requires: Tournament decklists with results

### Option 3: Expert Rating (Annotation-Based)
$$Q(D) = \text{Expert}(D)$$

Requires: Human evaluation of decks

### Option 4: Meta Statistics (Data-Driven)
$$Q(D) = \sum_{c \in D} \text{PickRate}(c) \cdot \text{WinRate}(c)$$

Requires: Card statistics from actual play data

## Current Approach vs Correct Formulation

### What We're Doing
$$\text{arg min}_{c'} \text{Distance}(c_{query}, c')$$

Finds: Similar cards (co-occurrence, embeddings)

### What We Should Do
$$\text{arg max}_{c_{add}, c_{remove}} Q(D \setminus \{c_{remove}\} \cup \{c_{add}\}) - Q(D)$$

Finds: Cards that improve deck quality

## Learning to Rank Formulation

Given deck $D$, rank candidates $\{c_1, ..., c_m\}$ by improvement potential:

$$f(D, c_i) = \text{Predicted improvement if adding } c_i$$

Training data: $(D, c_i, y_i)$ where $y_i$ is actual improvement

Loss (LambdaRank):
$$L = \sum_{i,j: y_i > y_j} \log(1 + \exp(-(f(D, c_i) - f(D, c_j))))$$

Features for $f(D, c_i)$:
- Jaccard similarity with cards in $D$
- Card frequency (meta)
- Color/type match with $D$
- Mana curve fit
- Synergy signals
- Win rate (if available)

## Why Our Current Metrics Are Wrong

**P@10 measures:**
"Of top 10 cards, how many are relevant to the query card?"

**But we need:**
"Of top 10 cards, how many would actually improve this deck?"

These are DIFFERENT!

Example:
- Lightning Bolt in Burn deck
- Similar: Chain Lightning (P@10 counts this ✓)
- But Burn already has 4x Bolt
- Adding Chain Lightning: Marginal improvement (should rank lower)
- Adding Orcish Bowmasters: Different function, high improvement (should rank higher)

## Correct Loss Function

For deck improvement, we should optimize:

$$L = \sum_{decks} \sum_{swaps} (y_{improve} - \hat{y}_{improve})^2$$

Where:
- $y_{improve}$ = actual improvement (from tournament results, win rate, or expert)
- $\hat{y}_{improve}$ = predicted improvement from our model

This is regression, not similarity!

## API Design for Deck Improvement

```python
@app.post("/improve_deck")
def improve_deck(request: DeckImprovementRequest):
    """
    Input:
      current_deck: List[str] (cards in deck)
      format: str (Modern, Legacy, etc.)
      budget: float (optional)
      
    Output:
      suggestions: List[{
        remove: str,
        add: str,
        improvement_score: float,
        reason: str
      }]
    """
    
    # 1. Analyze deck
    deck_vector = embed_deck(current_deck)
    
    # 2. For each possible swap:
    for card_in_deck in current_deck:
        for candidate in card_pool:
            # Predict improvement
            improvement = model.predict([
                jaccard_sim(candidate, deck),
                card_win_rate(candidate),
                color_match(candidate, deck),
                mana_curve_improvement(candidate, deck),
                ...
            ])
            
    # 3. Rank by improvement
    # 4. Return top-k
```

This is FUNDAMENTALLY different from what we're doing!

## What We Need to Change

1. **Annotations:** Not "is X similar to Y?" but "does adding X improve deck D?"

2. **Loss:** Not P@10 (similarity) but MSE on improvement prediction

3. **Features:** Not just co-occurrence but deck context:
   - Current deck composition
   - Mana curve
   - Color distribution
   - Archetype coherence
   - Missing functions

4. **Evaluation:** Not canonical test set of isolated cards, but:
   - Sample decks from tournaments
   - For each deck, try suggestions
   - Measure actual improvement

## Next Steps

1. Reformulate problem as deck improvement, not similarity
2. Collect deck improvement labels (expert ratings or win rate changes)
3. Build LTR model with proper features
4. Evaluate on deck improvement task

Current experiments are solving wrong problem!


