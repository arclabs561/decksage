# DeckSage: Experimental Narrative

A chronological account of what was tried, what worked, what failed, and how failures motivated subsequent steps. Intended as a presentation reference for ML audiences.

---

## Phase 1: Baseline and the Fundamental Signal Problem (exp 0001-0002)

**Starting point**: PecanPy random walks on co-occurrence graphs (cards that appear in the same tournament deck), trained via Word2Vec. Three games: Magic (83K decks), Pokemon (24K), Yu-Gi-Oh (77K).

**v4 baseline** (raw co-occurrence): Magic nDCG 0.151, Pokemon 0.049, YuGiOh 0.554.

**v5 fused** (enriched edges + ns_exponent=-0.5 + card attribute fusion): Magic 0.156, Pokemon 0.247, YuGiOh 0.554.

The key architectural decision: **card attribute fusion**. PCA-projecting card attributes (type, mana cost, colors, rarity) into the same 128D space and blending at alpha=0.7. This was essential -- without it, nDCG drops 30-50% across games.

**Negative sampling exponent -0.5** (Caselles-Dupre 2018): by down-weighting frequent cards in negative sampling, we reduce the "staple card" dominance (Lightning Bolt, Sol Ring appear in thousands of decks and dominate the embedding space).

**First insight**: co-occurrence captures *complement* signal (cards that go together in decks), NOT *substitute* signal (cards that replace each other). Functional AUC for substitution: 0.317. This is the central tension of the project -- the training data fundamentally measures a different thing than what users want when they ask "what card is similar to X?"

---

## Phase 2: GNN Approaches -- Three Failures (exp 0004, 0024, 0054-0055)

### LightGCN (exp 0004): Inflated Metrics Discovery

Swept 16 configs of LightGCN (He et al., SIGIR 2020) with reconstruction loss. The sweep evaluator reported **0.545 nDCG** -- a 3.5x improvement over v5 fused.

**The catch**: the sweep evaluator ranked within the annotation candidate set (relative ranking), while the canonical evaluator checks whether ground-truth cards appear in the embedding's top-10 (absolute recall). Canonical eval: **0.095** -- actually *worse* than v5 fused (0.154).

**Root cause**: (1) smaller vocab (15.7K vs 21.2K -- GNN only embeds graph nodes, misses cards not in training edges), (2) annotations were created from v5 neighbors, biasing ground truth toward what v5 retrieves.

**Lesson**: never trust sweep-internal eval for absolute numbers. Always verify with the canonical evaluator on the canonical test set. This became a hard rule.

### LightGCN Collapse Diagnosis (exp 0024)

Further investigation revealed the fundamental issue: on dense co-occurrence graphs, BPR's random-negative assumption breaks down. Random negatives are mostly *connected* nodes (the graph is dense -- 331K edges for 15K nodes). The model learns trivial solutions. Reconstruction loss (weighted MSE) works mechanically but the representations aren't similarity-preserving.

### HGT on A10G GPU (exp 0054-0055)

Tried Heterogeneous Graph Transformer (HGT) with NeighborLoader mini-batching on an A10G 24GB GPU. 12M directed edges across 6 edge types, 36K nodes.

**Link prediction worked**: val AUC 0.80 with link prediction objective.

**Similarity did not**: sub nDCG 0.003 raw, 0.014 fused. Link prediction optimizes for edge existence, not for producing similarity-preserving embeddings.

**Tried contrastive loss (InfoNCE)** (exp 0055): worse -- 0.002 raw, 0.012 fused. Loss plateaued at epoch 20.

**Conclusion**: GNN approaches using link prediction or reconstruction loss produce embeddings that are near-random for card similarity. The objective function matters more than the architecture. This killed the GNN line of investigation.

---

## Phase 3: The Annotation Quality Crisis (exp 0009, 0027, 0052, 0057)

### Card Context Discovery (exp 0009)

Early LLM annotations had a 16% error rate. Root cause: GPT-4o-mini *hallucinated card effects* from names alone (e.g., called Ebon Stronghold a "blue mana" card when it's black). Including oracle text, type line, mana cost in the prompt dropped errors to 1%.

**Lesson**: LLMs cannot judge card similarity from names -- they need the actual card data.

### IAA Reveals Judge Disagreement (exp 0027)

Multi-model IAA (4 LLM judges) produced Krippendorff alpha = 0.43. The judges disagree substantially on what constitutes similarity, especially at fine-grained continuous scores.

### The Dedup Catastrophe (exp 0052)

On 2026-03-22, diagnostic tooling revealed that multi-model IAA had produced **43-76% duplicate annotations** in the test sets (multiple judges producing separate entries for the same query-candidate pair).

**Impact**: all nDCG numbers from experiments 0031-0046 were inflated by 50-101%. True baselines after dedup:

| Embedding | Magic | Pokemon | YuGiOh |
|-----------|-------|---------|--------|
| v5_fused | 0.099 | 0.075 | 0.157 |
| MetaPath2Vec 160ep | 0.045 | 0.024 | 0.157 |

A week of experimental results were invalidated. The fix: consensus-average numeric scores by (query, candidate) before computing any ranking metric. Added as a pre-eval gate in `dataset_diagnostics.py`.

### Multi-Model Cascade Annotation (exp 0057)

Built a cascade annotation pipeline: Groq 70B + Cerebras 235B with isotonic calibration.

Key findings:
- **8B models useless for calibrated scoring** (correlation -0.076 vs IAA ground truth)
- **Ensemble dramatically beats individuals**: ensemble correlation 0.636 vs 0.102 (70B alone) and 0.309 (235B alone)
- **Removing bad annotations had the biggest single nDCG impact**: +21.6% for Magic after removing 3,349 zero-score annotations from broken Ollama/llama3.2 runs
- Cost: **$0.40/1K pairs** vs $2-15 for the full 6-model IAA

**Data quality > data quantity** -- confirmed repeatedly.

---

## Phase 4: Training Variance and Stochastic Luck (exp 0053)

Multi-seed ablation on the v7 edgelist revealed the deployed v7_fused model (nDCG 0.102) was a **2.5-sigma outlier** from its distribution mean (0.094, std 0.001).

The "improvement" from v5 to v7 was partly a lucky random walk. Strategy change: train N seeds, deploy best. Training variance is low (std ~0.001) but at the margins where we operate, a 2.5-sigma outlier is the difference between "better" and "same."

---

## Phase 5: Data Scaling -- More is Not Always Better (exp 0003, 0029, 0035, 0050)

### Pokemon pairs: 10x data, marginal gain (exp 0003)

Expanded Pokemon from 16K to 179K pairs. nDCG: 0.247 to 0.294 (+19% relative). But tournament decks are homogeneous -- more decks from the same meta provide diminishing signal.

### Commander data: coverage up, quality down (exp 0029, 0035, 0050)

Added 51K Archidekt Commander decks (25.2M edges). Coverage improved (+7,489 cards) but nDCG dropped 22%. Same with 3x Commander scaling. Root cause: Commander is a different format with different card relationships. The PecanPy random walks get diluted by casual/singleton format data when the test set measures competitive Standard/Modern similarity.

**Lesson**: heterogeneous data sources dilute signal in embedding methods that treat all edges equally. Either use edge-type-aware methods (MetaPath2Vec) or weight by source quality.

---

## Phase 6: Alternative Embedding Methods (exp 0030-0039, 0042, 0046-0047, 0056)

### MetaPath2Vec: Typed Walks (exp 0030-0039)

MetaPath2Vec uses typed random walks (deck-card-deck paths vs enriched-card-enriched paths). Initially promising: 5 epochs baseline 0.114, scaled to 0.228 at 160 epochs. But the 160ep result was **leaked** (annotation edges in training). After fixing:

- MetaPath2Vec LOST to v5_fused on Magic and Pokemon
- Tied on YuGiOh
- Adding more edge types (Commander, set, keyword) *regressed* performance -- the type-diverse walks diluted the core co-occurrence signal

MetaPath2Vec removed from production.

### Cleora: Matrix Factorization (exp 0042)

Fast, deterministic, but underperformed PecanPy across all games (Magic 0.103, Pokemon 0.103, YuGiOh 0.284).

### Spectral Propagation (ProNE): The Deterministic Winner (exp 0056)

ProNE spectral propagation applied as post-processing to PecanPy embeddings: **Magic 0.107** -- the best single-model result and fully deterministic. No random walks, no seed sensitivity. Subsumes the benefit of degree debiasing.

This became the production embedding for Magic: `v7_spectral_mu35`.

### PPMI SVD: Classical Baseline (exp 0056)

Full replacement with degree-corrected PPMI + SVD: 0.084 -- worse than PecanPy. Random walks capture more nuance than matrix factorization for this graph structure.

---

## Phase 7: The Evaluation Saturation Discovery (exp 0058-0059)

The most important methodological insight of the project.

### Standard nDCG was measuring annotation coverage, not embedding quality

After filling 5K eval holes per game ($6 total via the multi-model cascade), standard nDCG **doubled** across all games:

| Game | Before | After 5K | After full fill | Condensed |
|------|--------|----------|-----------------|-----------|
| Magic | 0.104 | 0.233 | **0.525** | 0.527 |
| Pokemon | 0.088 | 0.190 | **0.437** | 0.438 |
| YuGiOh | 0.160 | 0.240 | **0.478** | 0.482 |

When standard nDCG converges to condensed nDCG (gap < 0.005), annotation coverage is **saturated** and the metric reflects true ranking quality.

**Phase transition**: before saturation, nDCG measures how many of the embedding's top-10 items have been annotated. After saturation, it measures whether the annotated items are ranked correctly. Total cost: ~$23 for 89K annotations across 3 games.

**Saturation is embedding-specific AND retrieval-method-specific** (exp 0060): switching from cosine to fusion retrieval surfaced entirely different candidates, creating 24K new annotation holes.

### The Outer Loop

Fill holes -> get true quality -> train better embedding -> fill new holes from reshuffled top-K -> repeat. Convergence of this outer loop is when new-embedding holes don't change the ranking.

---

## Phase 8: Box and Cone Embeddings for Upgrade Ordering (exp 0040, 0043-0045, 0049)

### Box Embeddings: Degenerate on TCG Data (exp 0040, 0049)

Trained subsumer's BoxEmbeddingTrainer on (deck, contains, card) triples. AUC 0.504 -- random. Root cause: TCG decks share many staple cards, so the optimal box solution is "expand all boxes to contain everything." The same degenerate behavior appeared with card-card containment (168-365 training triples too sparse).

### Cone Embeddings: Partial Order Works (exp 0043-0045)

Switched to ConeEmbeddingTrainer for card upgrade partial orders (A upgrades B). Progression:

| Method | Magic AUC |
|--------|-----------|
| Baseline (no augmentation) | 0.700 |
| + Transitive closure | 0.762 |
| + Hard negatives | **0.857** |

Cones naturally model DAG/partial-order relationships. The cone geometry is a better inductive bias than boxes for "A is a strict upgrade of B" relationships. With only 146 training pairs and hard negatives, Magic reached production-viable AUC.

Pokemon (0.603) and YuGiOh (0.553) lagged -- likely lower-quality upgrade annotations or a different upgrade concept across games.

---

## Phase 9: The Fusion Routing Dilemma (exp 0060)

The system routes similarity queries by use case:
- **Substitute** (functional replacement): should use text + functional signals, NOT co-occurrence
- **Synergy** (cards that go together): should use co-occurrence + Jaccard
- **Meta** (competitive pairings): co-occurrence weighted by tournament performance

Experiment 0060 tested routing substitutes through the fusion engine (zeroing co-occurrence, boosting text + functional). Result: nDCG collapsed from 0.525 to 0.031.

**Not because fusion is worse** -- because the test set only covers cosine-ranked candidates. Fusion retrieves fundamentally different cards that haven't been annotated yet (convergence gap 0.256 vs 0.002 for cosine).

**Decision**: revert to cosine routing until fusion-specific annotations exist. The routing change was correct in principle but cannot be validated with the current evaluation infrastructure. Filling 24K fusion-specific holes is the next step.

---

## Cross-Cutting Themes

### 1. Evaluation methodology is harder than model development
- Inflated sweep eval (exp 0004): 3.5x overestimate
- Test set duplication (exp 0052): 50-100% inflation
- Training variance masking real differences (exp 0053)
- Annotation coverage masking true quality (exp 0058-0059)
- Method-specific saturation (exp 0060)

Each of these individually could lead to wrong conclusions. Together, they argue for extreme rigor in evaluation.

### 2. Data quality > data quantity
- 10x Pokemon pairs: +19% (exp 0003)
- 51K Commander decks: -22% (exp 0029)
- Removing 3,349 bad annotations: +21.6% (exp 0057)
- Card context in LLM prompts: error rate 16% to 1% (exp 0009)

### 3. The objective function matters more than the architecture
- LightGCN with reconstruction loss: near-random for similarity (exp 0004)
- HGT with link prediction: good AUC, useless embeddings (exp 0054)
- HGT with InfoNCE: worse than link prediction (exp 0055)
- PecanPy with ns=-0.5 + spectral post-processing: best result (exp 0056)

### 4. Co-occurrence is complement, not substitute
The fundamental signal problem. Embedding cosine on co-occurrence data measures "how likely are these cards to appear in the same deck" -- which anti-correlates with substitutability. A burn deck runs Lightning Bolt AND Eidolon, but a user looking for a Lightning Bolt substitute wants Searing Blaze, not Eidolon.

### 5. Cheap inference-time annotation at scale changes the game
The multi-model cascade ($0.40/1K pairs, correlation 0.639) enabled 89K annotations for $23. This saturation-filling approach transformed nDCG from an unreliable coverage metric into a true quality metric.

---

## Current State (2026-03-30)

| Metric | Magic | Pokemon | YuGiOh |
|--------|-------|---------|--------|
| Sub nDCG (saturated) | 0.525 | 0.437 | 0.478 |
| Condensed nDCG | 0.527 | 0.438 | 0.482 |
| Convergence gap | 0.002 | 0.001 | 0.004 |
| Total annotations | 36K | 25K | 27K |
| Embedding | v7_spectral_mu35 | v7_fused | v7_spectral_mu3 |

Production pipeline: PecanPy (ns=-0.5) -> spectral propagation (ProNE, mu=0.3-0.35) -> card attribute fusion (alpha=0.7, PCA 128D).

**Open questions**:
1. Can fusion routing improve substitution quality once fusion-specific annotations exist?
2. What is the ceiling for co-occurrence-based embeddings? (Ceiling analysis in exp 0025 suggests 95.6% of annotated ground truth IS in the top-K -- retrieval is good, ranking is the problem.)
3. Can contrastive fine-tuning on the annotation data close the gap between complement and substitute signal?
