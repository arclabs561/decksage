# DeckSage Demo Script

Setup time: ~10 min. Demo time: ~30 min.

---

## 0. Setup (on demo machine)

```bash
# Clone and install
git clone https://github.com/arclabs561/decksage.git && cd decksage
uv sync --extra embeddings

# Download and extract data assets (presigned URL, ask for current link)
curl -Lo /tmp/decksage-demo-data.tar.gz "<PRESIGNED_URL>"
tar xzf /tmp/decksage-demo-data.tar.gz

# Configure
cp .env.example .env

# Start search backends
docker compose up -d meilisearch qdrant

# Start API (~40s to load 3 games + index cards)
uv run uvicorn src.ml.api.api:app --host 127.0.0.1 --port 8001
```

Verify: `curl http://localhost:8001/live` returns `{"status":"ok"}`.

---

## 1. Problem Statement (2 min, talk)

"Given a trading card game card, find functionally similar cards -- substitutes, synergies, upgrades. Three games: Magic (26K cards), Pokemon (4.4K), Yu-Gi-Oh (13K)."

The hard part: **co-occurrence (cards in the same deck) measures complement, not substitute.** Lightning Bolt and Monastery Swiftspear appear together but do completely different things. We need cards that do the same thing as Lightning Bolt -- Lava Spike, Searing Blaze, Chain Lightning.

---

## 2. Web UI -- Live Search (5 min, show)

Open `http://localhost:8001` in a browser.

### Demo queries (Magic):

| Query | Mode | What to point out |
|-------|------|-------------------|
| Lightning Bolt | substitute | Results are burn spells, not creatures that go with burn |
| Counterspell | substitute | Gets Negate, Mana Leak, Force of Will -- functional replacements |
| Counterspell | synergy | Gets blue staples that go in the same deck -- Islands, Brainstorm, Snapcaster |
| Wrath of God | fusion | Shows all 6 signal bars -- which signals agree/disagree |
| Sol Ring | substitute vs synergy | Swap modes to show the difference clearly |

### Demo queries (cross-game):

| Query | Game | What to point out |
|-------|------|-------------------|
| Ultra Ball | Pokemon | Substitute: Nest Ball, Quick Ball (search-for-Pokemon effects) |
| Ash Blossom & Joyous Spring | Yu-Gi-Oh | Substitute: other hand traps (Effect Veiler, Infinite Impermanence) |

### What to highlight in the UI:

- **Score breakdown bars**: each result shows per-signal strength (embed, jaccard, functional, text, visual, archetype)
- **Method dropdown**: switch between substitute/synergy/fusion/embedding/jaccard/meta
- **Typeahead**: card name autocomplete (MeiliSearch-backed, fast)
- **Card images**: loaded from Scryfall/official APIs

---

## 3. Signal Architecture (5 min, talk + show)

Switch to fusion mode on a query and point at the breakdown bars.

Six signals fused via Reciprocal Rank Fusion:

1. **Embedding cosine** (co-occurrence): PecanPy Word2Vec on 184K decks. Good at complement, mediocre at substitute.
2. **Jaccard co-occurrence**: direct deck overlap ratio. Pure complement signal.
3. **Functional tags**: type line, keywords, mana cost similarity. Rules-based, no learning.
4. **Text embeddings** (E5-base-v2): card text similarity. 14-25% better than co-occurrence at substitute.
5. **Visual embeddings** (SigLIP2): card art similarity. Catches visual archetypes.
6. **Archetype similarity**: deck archetype template matching (25 Magic archetypes, etc.).

Key insight: **substitute mode text-boosts** -- reranker upweights text_e5 and dampens co-occurrence for substitute use_case.

---

## 4. Side-by-Side Comparison (3 min, show)

Use the Compare tab in the UI. Set query to "Lightning Bolt", left=substitute, right=synergy. Shows how the same card gets different results depending on the question.

---

## 5. Training Pipeline (5 min, talk, show code)

Walk through the pipeline (point at files, don't run them):

```
Deck scraping (Go backend, src/backend/)
    -> Co-occurrence pairs (data/processed/pairs_*.csv)
    -> Enriched graph (scripts/training/build_unified_graph.py)
    -> PecanPy random walks + Word2Vec (scripts/training/train_metapath2vec.py)
    -> Card attribute fusion (scripts/training/fuse_embeddings.py, alpha=0.7)
    -> Text embedding index (scripts/training/build_text_embedding_index.py)
    -> Visual embedding index (scripts/training/build_visual_embedding_index.py)
```

Key decisions:
- **ns_exponent=-0.5**: down-weights staple cards in negative sampling (Caselles-Dupre 2018)
- **Spectral propagation**: smooths embeddings over graph Laplacian
- **Card attribute fusion at alpha=0.7**: without it, nDCG drops 30-50%

---

## 6. Annotation Pipeline (5 min, talk + show prompt)

How we generated 100K annotations for $25.

### The prompt (show `scripts/annotation/multi_model_annotate.py` lines 101-125)

```
Rate these {GAME} cards on similarity (0.0-1.0).

Card A: {full card text, type, cost, oracle text}
Card B: {full card text, type, cost, oracle text}

SCORING SCALE (use the FULL range):
- 0.00: Unrelated. Different functions, different archetypes.
- 0.15: Tangential. Same broad category but different targets/timing/cost.
- 0.40: Moderate. Same function AND similar cost, or strong co-occurrence.
- 0.65: Strong similarity. Competitive alternatives, similar efficiency.
- 0.80: Near-substitute. Functionally interchangeable, minor differences.
- 1.00: Functional reprint or strictly-better/worse pair.

CALIBRATION ANCHORS:
- Lightning Bolt vs Shock = 0.70
- Path to Exile vs Swords to Plowshares = 0.80
- Counterspell vs Mana Leak = 0.50
- Lightning Bolt vs Counterspell = 0.10
- Sol Ring vs Wrath of God = 0.05
```

### Key design decisions:

1. **Card context is mandatory** (exp 0009). Without oracle text, LLMs hallucinate card effects from names. Error rate: 16% without context, 1% with.
2. **Calibration anchors** in the prompt. Without them, models cluster scores around 0.5. Anchors spread the distribution.
3. **Multi-model cascade**: Groq Llama 70B + Cerebras Llama 235B. Two independent models, consensus-averaged. Cost: $0.40/1K pairs.
4. **4-dimensional scores**: similarity, functional, synergy, meta_relevance. Only `similarity_score` used for nDCG; others are diagnostic.
5. **Provenance tracking**: every annotation records backend, model, prompt version, temperature.

### What went wrong (and how we fixed it):

- **Dedup crisis** (exp 0052): multi-model IAA produced duplicate annotations per pair. All nDCG numbers inflated 50-101%. Fix: consensus-average by (query, candidate) before eval.
- **8B models don't work** (exp 0057): Ollama llama3.2 produced 54% zero scores, correlation -0.076 vs IAA. Minimum viable: 70B.
- **IAA disagreement**: Krippendorff alpha 0.43 across 4 judges. Models disagree on fine-grained scores. We accept this and average.

### The eval-annotation feedback loop:

```
Train embedding -> Retrieve top-K -> Find unjudged cards (holes)
    -> Annotate holes -> Recompute nDCG -> (repeat)
```

"Filling holes" (annotating the top-K candidates the embedding actually retrieves) had 5-10x the impact of annotating random pairs. nDCG jumped from 0.10 to 0.52 in two rounds ($23 total).

---

## 7. Experiment History (5 min, talk)

Open `docs/experimental_narrative.md` -- 12 phases, 63 experiments.

Show `docs/figures/experiment_progression.png` for the visual arc.

### The story in 5 beats:

1. **Baseline** (exp 0001-0002): Co-occurrence embeddings work for synergy but not substitute. Functional AUC 0.317 -- barely better than random for substitution.

2. **GNNs fail** (exp 0004, 0054-0055): LightGCN, HGT. Link prediction AUC 0.80 but similarity nDCG 0.003-0.014. The objective function matters more than the architecture. Reconstruction/link-prediction loss doesn't produce similarity-preserving embeddings.

3. **Evaluation is harder than training** (exp 0052, 0057-0059): annotation dedup crisis invalidated a week of results. Then: filling evaluation holes (annotating what the model actually retrieves) moved nDCG from 0.10 to 0.52. We spent more time on evaluation methodology than on model architecture.

4. **Text wins** (exp 0061-0062): E5-base-v2 text similarity (zero-shot, no training) beats 60 experiments of co-occurrence engineering by 14-25%. Co-occurrence captures what goes together; text captures what does the same thing.

5. **Methodology > architecture** (exp 0063): Cross-encoder training. v2 showed Pearson 0.695; v3 with honest query-level split showed 0.56. The convenient number is always higher than the honest one.

### Key failures worth mentioning:

| What | Why it failed | What we learned |
|------|--------------|-----------------|
| LightGCN | Sweep eval inflated 0.095->0.545 | Never trust sweep-internal eval |
| Data scaling | 10x Pokemon pairs barely moved nDCG | Tournament decks are homogeneous |
| MetaPath2Vec | Deployed v7 was 4-sigma above mean | Multi-seed validation mandatory |
| E5 fine-tuning | Catastrophic forgetting (0.44->0.29) | Frozen encoder + fusion > fine-tuning |
| Commander data | 51K decks, no improvement | Commander != cross-format substitute |

---

## 8. Deck Completion (3 min, show)

In the API docs (`/docs`), POST to `/v1/deck/complete`:

```json
{
  "game": "magic",
  "cards": ["Lightning Bolt", "Monastery Swiftspear", "Goblin Guide", "Eidolon of the Great Revel"],
  "target_size": 20,
  "method": "beam"
}
```

Shows beam search filling a burn deck with appropriate cards, respecting archetype curve targets (25 Magic archetypes, 15 YGO, 10 Pokemon).

---

## 9. Q&A Prep

**"Why not fine-tune E5/BERT end-to-end?"**
Tried (exp 0005, 0064). E5 fine-tuning caused catastrophic forgetting (Pearson 0.44->0.29). LoRA + multi-task was better but still below the fusion approach. The frozen encoder + late fusion architecture is more robust.

**"Why not GNNs?"**
Tried LightGCN and HGT (exp 0004, 0054-0055). Link prediction AUC 0.80 but embedding similarity near-random. The objective function (reconstruction/link-prediction) doesn't produce similarity-preserving embeddings.

**"How do you know the annotations are good?"**
Multi-model IAA (Krippendorff alpha 0.43). Calibration anchors in the prompt. Card context mandatory (error rate 16% -> 1%). Minimum 70B model. Isotonic calibration on the cascade. We accept inter-judge disagreement and consensus-average.

**"Why condensed nDCG?"**
Standard nDCG is biased downward with sparse annotations -- it penalizes unjudged cards as irrelevant. Condensed nDCG (Sakai 2007) only ranks judged items, measuring ranking quality not annotation coverage. When the gap between standard and condensed closes (<0.005), annotations are saturated for that embedding.

**"What's the cost?"**
~$25 for 100K annotations via Groq/Cerebras. Infrastructure: MeiliSearch + Qdrant in Docker, CPU-only inference. No GPU needed for serving. Total cloud spend: ~$30 (annotations + one A10G session for HGT experiments).
