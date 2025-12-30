# Advanced Methods Roadmap - Experimental Playground

## Vision

DeckSage as a testbed for graph ML techniques across 3 card games:
- Magic: The Gathering (complex rules, 20K+ cards)
- Yu-Gi-Oh! (different mechanics, 13K+ cards)
- Pokemon (simpler, energy system)

## Progression: Simple → Advanced

### ✅ Phase 1: Classical Baselines (DONE)
- Random
- Degree centrality
- Jaccard similarity

### ✅ Phase 2: Unattributed Embeddings (DONE - Found Limitations)
- Node2Vec
- DeepWalk
- Learning: Needs attributes for this task

### 🔄 Phase 3: Node-Attributed GNN (IN PROGRESS)
- GCN (Graph Convolutional Network)
- GAT (Graph Attention)
- GraphSAGE (inductive learning)

Features: card color, type, CMC, text embeddings

### Phase 4: Edge-Attributed GNN
- GAT with edge features
- GIN (Graph Isomorphism Network)
- HeteroGNN (multiple edge types)

Features: format, archetype, partition (main/side)

### Phase 5: Contrastive Learning
**Key idea:** Learn embeddings that pull similar cards together, push dissimilar apart

```python
from torch_geometric.nn import to_hetero

# Triplet loss
anchor = Lightning Bolt
positive = Chain Lightning  # Similar
negative = Counterspell    # Dissimilar

loss = max(0, d(anchor, positive) - d(anchor, negative) + margin)
```

**Advantages:**
- Supervised with pairwise labels
- No need for full ground truth
- Can use our annotation data directly

**Experiments:**
- exp_010: Contrastive on 50 annotated pairs
- exp_011: Hard negative mining (find confusing examples)
- exp_012: Cross-game contrastive (MTG embeddings → YGO)

### Phase 6: Learning-to-Rank (LTR)

**Key idea:** Combine multiple features, learn optimal weighting

```python
from lightgbm import LGBMRanker

# Features for each (query, candidate) pair
features = [
    node2vec_similarity,
    jaccard_similarity,
    color_match,
    type_match,
    cmc_diff,
    text_similarity,
    price_ratio,
    format_legality
]

# Train ranker on annotated data
ranker = LGBMRanker()
ranker.fit(X=features, y=relevance_labels, group=query_groups)
```

**Advantages:**
- Ensemble of methods
- Interpretable feature importance
- Can add new signals easily (price, win rate, etc.)

**Experiments:**
- exp_015: LightGBM ranker with 5 features
- exp_016: Add text similarity (BERT)
- exp_017: Add price/rarity features
- exp_018: Cross-game feature transfer

### Phase 7: Heterogeneous Graphs

**Key idea:** Multiple entity types

```python
# Node types
nodes = {
    'card': ['Lightning Bolt', ...],
    'format': ['Modern', 'Legacy'],
    'archetype': ['Burn', 'Control'],
    'player': ['user_123', ...]
}

# Edge types  
edges = {
    ('card', 'cooccurs', 'card'),
    ('card', 'played_in', 'format'),
    ('card', 'archetype_staple', 'archetype'),
    ('player', 'plays', 'card')
}

from torch_geometric.nn import HeteroConv, HGTConv
```

**Experiments:**
- exp_020: Heterogeneous graph construction
- exp_021: Metapath2vec
- exp_022: HGT (Heterogeneous Graph Transformer)

### Phase 8: Advanced Topics

**Temporal graphs:**
- Time-aware embeddings
- Meta evolution tracking
- Ban list impact analysis

**Multi-modal:**
- Card image + text + graph structure
- Vision transformer + GNN hybrid

**Reinforcement learning:**
- Deck building as RL task
- Card recommendations optimize win rate

## Experiment Template

For each new technique, follow scientific method:

```json
{
  "experiment_id": "exp_XXX",
  "phase": "Node-Attributed GNN",
  "date": "2025-XX-XX",
  
  "hypothesis": "Adding node features will improve over unattributed Node2Vec",
  
  "method": {
    "algorithm": "GAT",
    "hyperparameters": {"hidden_dim": 128, "num_layers": 2},
    "features": ["color", "type", "cmc"]
  },
  
  "data": {
    "graphs": ["MTG_500decks", "YGO_cards", "Pokemon_cards"],
    "node_features": "scryfall_metadata",
    "splits": {"train": 0.7, "val": 0.15, "test": 0.15}
  },
  
  "baselines": ["Jaccard", "Node2Vec_unattributed"],
  
  "evaluation": {
    "metrics": ["P@5", "P@10", "NDCG@10", "MRR"],
    "test_set": "diverse_queries_v2.json",
    "num_queries": 20
  },
  
  "results": {
    "GAT_attributed": {"P@10": null},
    "baseline_comparison": null
  },
  
  "learnings": [],
  "issues_found": [],
  "next_experiments": []
}
```

## Multi-Game Datasets

### Magic: The Gathering ✅
- 500 decks extracted
- 1,951 unique cards
- 299K co-occurrence pairs
- Status: Ready for experiments

### Yu-Gi-Oh! ⚠️
- 13,930 cards extracted (API)
- 0 decks (need deck sources)
- Status: Need deck extraction

**Action:** Find YGO deck sources
- YGOPRODeck API (has decks?)
- DuelingBook exports
- Tournament results

### Pokemon ⚠️
- Cards partially extracted
- 0 decks
- Status: Need deck sources

**Action:** Find Pokemon deck sources
- Pokemon TCG Online exports
- Tournament decklists
- Limitless TCG

## Next 3 Experiments (This Week)

**exp_006:** Fetch Scryfall features for MTG
- Extract color, type, CMC for 1,951 cards
- Build feature matrix
- Success: Complete feature database

**exp_007:** Simple GCN with node features
- Implement basic GCN
- Train on MTG graph
- Compare to Jaccard
- Success: P@10 > 0.50

**exp_008:** GAT with attention
- Add attention mechanism
- Visualize attention weights
- Compare to GCN
- Success: P@10 > GCN

## Long-term Vision

**Month 1:** Node-attributed working (Phase 3)
**Month 2:** Edge-attributed working (Phase 4)
**Month 3:** Contrastive learning (Phase 5)
**Month 4:** Learning-to-rank ensemble (Phase 6)
**Month 5:** Multi-game comparison (Phase 6)
**Month 6:** Paper submission

## Playground Features

All experiments tracked in:
- `experiments/EXPERIMENT_LOG.jsonl` (append-only)
- `experiments/results/exp_XXX/` (artifacts per experiment)
- `notebooks/` (interactive exploration)

Easy to try new ideas:
```bash
# Try new technique
python experiment_runner.py \
  --method GAT \
  --features color,type,cmc \
  --dataset mtg_500decks

# Automatically:
# - Logs to EXPERIMENT_LOG.jsonl
# - Saves artifacts to experiments/results/
# - Compares to baselines
# - Generates HTML report
```



