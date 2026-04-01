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

## 6. Evaluation and Experiment History (5 min, talk)

Open `docs/experimental_narrative.md` -- 12 phases, 63 experiments.

Highlight stories:
- **Phase 2**: GNN approaches (LightGCN, HGT) all failed at similarity despite good link prediction
- **Phase 3**: annotation dedup crisis invalidated a week of results
- **Phase 7**: filling evaluation holes moved nDCG from 0.10 to 0.52 ($23 in LLM annotations)
- **Phase 11**: text embeddings beat co-occurrence by 14-25% at substitute

Show `docs/figures/experiment_progression.png` for the visual arc.

Eval method: ~100K LLM-generated annotations (Groq 70B + Cerebras 235B cascade, $25 total), condensed nDCG to correct for sparse annotation coverage (Sakai 2007).

---

## 7. Deck Completion (3 min, show)

In the API docs (`/docs`), POST to `/v1/deck/complete`:

```json
{
  "game": "magic",
  "cards": ["Lightning Bolt", "Monastery Swiftspear", "Goblin Guide", "Eidolon of the Great Revel"],
  "target_size": 20,
  "method": "beam"
}
```

Shows beam search filling a burn deck with appropriate cards, respecting archetype curve targets.

---

## 8. Q&A Prep

Common questions and answers:

**"Why not fine-tune E5/BERT end-to-end?"**
Tried (exp 0005, 0064). E5 fine-tuning caused catastrophic forgetting (Pearson 0.44->0.29). LoRA + multi-task was better but still below the fusion approach.

**"Why not GNNs?"**
Tried LightGCN and HGT (exp 0004, 0054-0055). Link prediction AUC 0.80 but embedding similarity near-random (nDCG 0.003-0.014). Reconstruction/link-prediction objectives don't produce similarity-preserving embeddings.

**"How do you know the annotations are good?"**
Multi-model IAA (Krippendorff alpha 0.43 -- judges disagree on fine-grained scores). Isotonic calibration on the cascade. Card context in prompts drops error rate from 16% to 1%.

**"What's the cost?"**
~$25 for 100K annotations. Infrastructure: MeiliSearch + Qdrant in Docker, CPU-only inference. No GPU needed for serving.
