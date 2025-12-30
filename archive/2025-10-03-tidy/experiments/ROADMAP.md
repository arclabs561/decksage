# Scientific Roadmap to Attributed Graph Embeddings

## Current State (Oct 1, 2025)

**What works:**
- Jaccard similarity: 83% accuracy (with land filtering)

**What doesn't:**
- Node2Vec: 25% accuracy (format mixing, no attributes)

**Data:**
- 500 MTG decks, mixed formats
- No card attributes
- No edge attributes

## Systematic Build-Up Plan

### Phase 1: Establish Baselines ✅ COMPLETE

**Experiments:**
- exp_001: Random baseline (P@10: 0.012)
- exp_002: Degree centrality (P@10: 0.012)
- exp_003: Jaccard similarity (P@10: 0.145)

**Learning:** Simple methods establish floor. Jaccard is strong baseline.

**Next:** Unattributed graph embeddings

---

### Phase 2: Unattributed Embeddings ✅ COMPLETE

**Experiments:**
- exp_004: Node2Vec basic (P@10: 0.136 on 150 decks)
- exp_005: Node2Vec with more data (P@10: 0.070 on 500 decks, degraded!)

**Learning:** Unattributed Node2Vec doesn't work for this task.

**Why it fails:**
- Learns co-occurrence patterns (archetype) not function (card role)
- Format mixing: Sol Ring in Commander ≠ Sol Ring in Legacy
- No way to distinguish spell types

**Next:** Add node attributes

---

### Phase 3: Node-Attributed Embeddings (CURRENT)

**Plan:**
1. Fetch Scryfall metadata for all cards
2. Create node feature matrix: [color, type, CMC, text_embedding]
3. Use PyTorch Geometric GNN

**Hypothesis:** Adding card attributes will help model distinguish:
- Burn spells from creatures (both in red aggro)
- Card type matters more than co-occurrence

**Experiment Design:**
```python
# Node features
features = {
    'Lightning Bolt': {
        'color': [1,0,0,0,0],  # R
        'is_instant': 1,
        'is_sorcery': 0,
        'is_creature': 0,
        'cmc': 1,
        'text_emb': bert_encode("deals 3 damage")
    }
}

# PyTorch Geometric
from torch_geometric.nn import GATConv

model = GATConv(in_channels=feature_dim, out_channels=128)
embeddings = model(node_features, edge_index)
```

**Expected Result:** P@10 > 0.50 (better than unattributed)

**Success Criteria:**
- Beats Jaccard (P@10 > 0.83)
- No more Hedron Crab for Sol Ring
- Type-coherent predictions

**Timeline:** 1 week

---

### Phase 4: Edge-Attributed Embeddings

**Plan:**
1. Add format to each edge
2. Add partition context (maindeck vs sideboard)
3. Use edge features in GNN

**Hypothesis:** Edge attributes help distinguish:
- Lightning Bolt in Burn (maindeck, offensive)
- Lightning Bolt in Control (sideboard, removal)

**Experiment Design:**
```python
# Edge features
edge_features = {
    ('Lightning Bolt', 'Monastery Swiftspear'): {
        'format': 'Modern',
        'archetype': 'Prowess',
        'partition': 'maindeck',
        'weight': 42
    }
}

# GAT with edge attributes
model = GATConv(edge_dim=edge_feature_dim)
embeddings = model(node_features, edge_index, edge_features)
```

**Expected Result:** P@10 > 0.60

**Success Criteria:**
- Format-specific predictions
- Context-aware (Bolt in Burn vs Bolt in Control)
- Beats node-attributed

**Timeline:** 2 weeks

---

### Phase 5: Heterogeneous Graphs

**Plan:**
1. Multiple node types: Cards, Formats, Archetypes
2. Multiple edge types: co-occurs, played_in, belongs_to
3. Use metapath2vec or HeteroGNN

**Hypothesis:** Explicit structure helps model understand relationships

**Experiment Design:**
```python
# Heterogeneous graph
nodes = {
    'card': ['Lightning Bolt', ...],
    'format': ['Modern', 'Legacy'],
    'archetype': ['Burn', 'Prowess']
}

edges = {
    ('card', 'cooccurs', 'card'): edge_index_card_card,
    ('card', 'played_in', 'format'): edge_index_card_format,
    ('card', 'belongs_to', 'archetype'): edge_index_card_archetype
}

from torch_geometric.nn import HeteroConv
# Train heterogeneous GNN
```

**Expected Result:** P@10 > 0.70

**Timeline:** 3-4 weeks

---

### Phase 6: Multi-Game Comparison

**Plan:**
1. Apply best method to YGO and Pokemon
2. Cross-game evaluation
3. Transfer learning experiments

**Hypothesis:** Method that works for MTG should work for other TCGs

**Experiments:**
- Same architecture on YGO/Pokemon graphs
- Transfer MTG embeddings to YGO (if similar mechanics)
- Cross-game similarity

**Timeline:** 4-6 weeks

---

## Experiment Log Protocol

### For Each Experiment:

**Before:**
```json
{
  "experiment_id": "exp_XXX",
  "date": "YYYY-MM-DD",
  "hypothesis": "Clear testable hypothesis",
  "method": "Algorithm + hyperparameters",
  "data": "Dataset description",
  "evaluation": "Metrics and test set",
  "expected_result": "What we think will happen"
}
```

**After:**
```json
{
  ...
  "results": {"metric": value},
  "conclusion": "Accept/reject hypothesis",
  "learnings": ["Key insight 1", "Key insight 2"],
  "issues_found": ["Problem discovered"],
  "next_steps": ["What to try next"]
}
```

### Append to Log:
```bash
# Append new experiment
echo '{...}' >> experiments/EXPERIMENT_LOG.jsonl

# View all experiments
cat experiments/EXPERIMENT_LOG.jsonl | jq .

# Analyze trends
python analyze_experiments.py
```

## Success Criteria Progression

| Phase | Method | Target P@10 | Actual | Status |
|-------|--------|-------------|--------|--------|
| 1 | Jaccard | > 0.10 | 0.145 | ✅ Exceeded |
| 2 | Node2Vec | > 0.15 | 0.136 | ⚠️ Close but below |
| 3 | Node-attributed | > 0.50 | TBD | 🔄 In progress |
| 4 | Edge-attributed | > 0.60 | TBD | Planned |
| 5 | Heterogeneous | > 0.70 | TBD | Planned |
| 6 | Production | > 0.80 | TBD | Goal |

## Current Focus: Phase 3

**This Week:**
1. Fetch Scryfall card metadata (35K cards available)
2. Build node feature matrix
3. Implement simple GNN (GCN or GAT)
4. Compare to Jaccard baseline

**Don't:**
- Skip to complex methods
- Ignore baselines
- Forget to log experiments

**Do:**
- One step at a time
- Compare to previous best
- Document everything
- Test on diverse queries (not cherry-picked!)



