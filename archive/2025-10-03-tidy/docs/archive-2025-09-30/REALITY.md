# Reality - October 1, 2025

## What We Actually Have

**Verified Results on Canonical Test Set (10 MTG queries):**
- exp_021: Jaccard (39K decks) = P@10: 0.14
- exp_022: Node2Vec (39K decks) = P@10: 0.06
- exp_023: Ensemble (5 methods) = P@10: 0.08

**Winner:** Jaccard at 0.14 (poor but real)

**Data:**
- 39,384 MTG decks extracted
- 13,930 YGO cards (no decks)
- 3,000 Pokemon cards (no decks)

**System:**
- Closed-loop framework exists
- Canonical test sets for 3 games
- Experiment log with 30 entries (but only 3 verified)

## What We Don't Have

**No YGO/Pokemon deck data** - can't do cross-game experiments yet

**No metadata usage** - ignoring 95% of available signals:
- Archetype labels
- Tournament placement
- Oracle text
- Card types
- Prices
- Win rates

**Poor performance** - 0.14 P@10 means only 1-2 relevant cards in top-10

## What to Actually Do

Run 5 real experiments today, measure real improvement:

**exp_026:** Actually use Scryfall types (not placeholder)
**exp_027:** Actually train Modern-only embeddings 
**exp_028:** Actually implement archetype conditioning
**exp_029:** Actually use oracle text with BERT
**exp_030:** Whichever actually works best

Each will be real code that runs and produces numbers.
No more placeholders.

