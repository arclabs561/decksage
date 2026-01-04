# Complete Embedding Pipeline Review

## Current Pipeline (Node2Vec)

```
Decks → Co-occurrence Graph → Node2Vec → Embeddings → Similarity
```

### Step-by-Step Analysis

**1. Data Extraction**
```go
// Go scraper extracts decks from tournament sites
dataset.Extract(ctx, scraper, options...)
→ Saves Collections as JSON (cards + metadata)
```

**Issues:**
- ✓ Multi-source (MTGTop8, Goldfish, Scryfall, Deckbox)
- ✗ No deck metadata used (format, archetype, date → discarded!)
- ✗ Single snapshot (no temporal info)
- ✗ Many parsing errors (Goldfish: empty decks)

**2. Graph Construction**
```go
// Transform: Collections → Card co-occurrence graph
export-decks-only: pairs.csv (NAME_1, NAME_2, COUNT_MULTISET)
```

**Issues:**
- ✓ Clean deck-only edges (removed contamination)
- ✗ Unattributed graph (just counts, no context)
- ✗ No node features (card color, type, CMC → lost!)
- ✗ No edge features (format, archetype → lost!)

**3. Embedding Training**
```python
# PecanPy: Random walks → Word2Vec
graph → Node2Vec(p=1, q=1, dim=128) → embeddings.wv
```

**Issues:**
- ✓ Fast implementation (PecanPy)
- ✗ No hyperparameter tuning
- ✗ Fixed p=q=1 (doesn't explore BFS/DFS)
- ✗ No node attributes used
- ✗ No edge weights beyond count

**4. Evaluation**
```python
# Test on held-out edges
evaluate.py: P@K, MRR, NDCG vs baselines
```

**Issues:**
- ✓ Proper metrics
- ✓ Baseline comparisons
- ✗ Random split (not temporal)
- ✗ No cross-format evaluation
- ✗ No archetype-specific metrics

**Result:** Jaccard (0.141) > Node2Vec (0.136)

## Root Causes of Failure

### 1. Information Loss

**We throw away 90% of available information:**

| Available | Used | Lost |
|-----------|------|------|
| Format (Modern/Legacy) | ✗ | ✓ Format-specific similarity |
| Archetype (Burn/Control) | ✗ | ✓ Strategic context |
| Card attributes (color, type) | ✗ | ✓ Functional similarity |
| Deck metadata (date, player) | ✗ | ✓ Temporal patterns |
| Edge context (maindeck vs sideboard) | ✗ | ✓ Role specificity |

**Example:**
- Lightning Bolt + Fireblast in Burn deck (maindeck, offensive)
- Lightning Bolt + Ancient Grudge in Control (sideboard, different role)

Currently: Both treated identically. Should: Different embeddings based on context.

### 2. Unattributed Graphs

**Current:** Just co-occurrence counts
**Missing:**
- Node attributes: card_color, card_type, cmc, rarity
- Edge attributes: format, archetype, partition (main/side)

**Impact:** Model can't distinguish:
- Burn spell vs creature (both in aggro)
- Removal in control vs removal in aggro
- Format-specific substitutes

### 3. No Semantic Features

**We have Scryfall API** with full card data:
```json
{
  "name": "Lightning Bolt",
  "mana_cost": "{R}",
  "type_line": "Instant",
  "oracle_text": "Lightning Bolt deals 3 damage...",
  "colors": ["R"],
  "cmc": 1
}
```

**But we ignore it all!** Just use card names.

## Solution: Attributed Graph Embeddings

### Approach 1: PyTorch Geometric (GNN)

**Idea:** Use card attributes as node features

```python
from torch_geometric.data import Data
from torch_geometric.nn import GCNConv, GAT

# Node features: [color_vec, type_vec, cmc, power, toughness]
x = encode_card_features(cards)  # Shape: [num_cards, feature_dim]

# Edge index + edge attributes
edge_index = torch.tensor([[src], [dst]])
edge_attr = encode_edge_features(format, archetype, partition)

# GNN model
data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr)
model = GAT(in_channels=feature_dim, hidden_channels=128, out_channels=64)
embeddings = model(data.x, data.edge_index, data.edge_attr)
```

**Advantages:**
- Uses all available information
- Learns feature interactions
- Can handle new cards (zero-shot via attributes)
- Edge-aware (format-specific embeddings)

**Disadvantages:**
- More complex
- Needs labeled data for supervised training
- Slower than Node2Vec

### Approach 2: Attributed Node2Vec

**Idea:** Concatenate features with learned embeddings

```python
# Learn structural embeddings
structural_emb = node2vec(graph)  # [num_cards, 128]

# Encode card attributes
feature_emb = encode_features(cards)  # [num_cards, 64]

# Concatenate
final_emb = concat([structural_emb, feature_emb])  # [num_cards, 192]
```

**Advantages:**
- Simpler than full GNN
- Still unsupervised
- Adds semantic info

**Disadvantages:**
- Naive concatenation (no learned interaction)
- Features may dominate or be ignored

### Approach 3: Heterogeneous Graphs

**Idea:** Different node types (cards, formats, archetypes)

```
Card nodes: Lightning Bolt, Fireblast
Format nodes: Modern, Legacy, Pauper
Archetype nodes: Burn, Control, Aggro

Edges:
- Card-Card: co-occurrence
- Card-Format: played_in
- Card-Archetype: belongs_to
```

Use metapath2vec or heterogeneous GNN (HeteroConv)

**Advantages:**
- Captures multi-level structure
- Format-aware, archetype-aware
- Can query: "Similar cards in Modern Burn"

**Disadvantages:**
- Complex graph construction
- Need archetype labels (manual or clustering)

## Recommended Next Steps

### Immediate (This Week)

**1. Wait for current extractions to finish**
```bash
# Monitor
watch -n 5 'ls data-full/games/magic/*/*.json | wc -l'

# When complete (300+ decks):
cd src/ml
./pipeline.sh  # Re-train and re-evaluate
```

**2. If Node2Vec still loses to Jaccard:**
- Accept it: Ship Jaccard-based API
- Move to attributed methods

### Short-term (1-2 Weeks)

**3. Add card attributes to graph**
```python
# Fetch from Scryfall API
card_features = {
    'Lightning Bolt': {
        'colors': ['R'],
        'type': 'Instant',
        'cmc': 1,
        'text_embedding': bert_encode(oracle_text)
    }
}

# PyTorch Geometric with features
data = Data(
    x=encode_features(cards),  # Node features
    edge_index=edge_index,
    edge_attr=encode_edges(format, archetype)  # Edge features
)
```

**4. Try GNN approaches**
- GraphSAGE (inductive, handles new cards)
- GAT (attention on edges)
- GIN (good for graph classification)

### Medium-term (2-4 Weeks)

**5. Heterogeneous graph**
```python
from torch_geometric.nn import HeteroConv

# Define schema
metadata = (
    ['card', 'format', 'archetype'],  # Node types
    [
        ('card', 'cooccurs', 'card'),
        ('card', 'played_in', 'format'),
        ('card', 'belongs_to', 'archetype')
    ]
)
```

**6. Cross-game transfer**
- Train on MTG
- Test on YGO/Pokemon
- See if learned relationships transfer

## Critical Assessment of Current Approach

### What We're Doing Wrong

**1. Treating cards as atomic units**
- Reality: Cards have structure (color, type, text)
- We: Ignore everything except name
- Loss: Can't reason about why cards are similar

**2. Ignoring graph context**
- Reality: Same cards play different roles in different decks
- We: All Lightning Bolts are identical
- Loss: Can't distinguish Burn vs Control usage

**3. No semantic grounding**
- Reality: Card text explains function ("deals 3 damage")
- We: Just co-occurrence statistics
- Loss: Can't generalize to unseen cards

### What Jaccard Does Right

**Jaccard:** $\frac{|N(u) \cap N(v)|}{|N(u) \cup N(v)|}$

- Simple, interpretable
- Uses actual observed co-occurrence
- No assumptions about walks or embeddings
- Works on sparse data

**Why it wins:** Our data is too sparse for Node2Vec to beat direct neighborhood comparison.

## Proposed Enhanced Pipeline

### V2: Attributed Node Embeddings

```python
# 1. Extract with metadata
{
  "deck": {
    "cards": ["Lightning Bolt", ...],
    "format": "Modern",
    "archetype": "Burn",  # From deck name or clustering
    "date": "2025-09-30"
  }
}

# 2. Build attributed graph
nodes = {
    'Lightning Bolt': {
        'color': [1,0,0,0,0],  # R
        'type': [0,0,1,0,0],   # Instant
        'cmc': 1,
        'text_emb': bert(['deals 3 damage'])
    }
}

edges = {
    ('Lightning Bolt', 'Fireblast'): {
        'count': 42,
        'formats': ['Modern', 'Pauper'],
        'archetypes': ['Burn'],
        'contexts': ['maindeck']
    }
}

# 3. PyTorch Geometric GNN
from torch_geometric.nn import GATConv

class CardGNN(nn.Module):
    def __init__(self):
        self.conv1 = GATConv(in_channels, 128, edge_dim=edge_features)
        self.conv2 = GATConv(128, 64, edge_dim=edge_features)

    def forward(self, x, edge_index, edge_attr):
        x = F.relu(self.conv1(x, edge_index, edge_attr))
        x = self.conv2(x, edge_index, edge_attr)
        return x

# 4. Evaluate
embeddings = model(node_features, edge_index, edge_attr)
# Should beat Jaccard because it uses MORE information
```

### V3: Hybrid Approach

**Combine multiple signals:**

1. **Structural:** Node2Vec on co-occurrence
2. **Semantic:** BERT on card text
3. **Attributional:** GNN on card features
4. **Direct:** Jaccard on neighbors

```python
final_similarity = (
    0.3 * node2vec_sim(c1, c2) +
    0.3 * bert_sim(text1, text2) +
    0.2 * gnn_sim(c1, c2) +
    0.2 * jaccard_sim(c1, c2)
)
```

Learn weights from annotated data.

## Experiments to Run

### Experiment 1: More Data (Running Now)
- Extract 300-500 decks
- Re-train Node2Vec
- **Hypothesis:** Beats Jaccard with more data
- **If fails:** Data quality not the issue

### Experiment 2: Hyperparameter Sweep
```bash
for p in 0.5 1.0 2.0; do
  for q in 0.5 1.0 2.0; do
    for dim in 64 128 256; do
      python card_similarity_pecan.py --p $p --q $q --dim $dim
    done
  done
done
```
- **Hypothesis:** Better p,q,dim exists
- **If fails:** Node2Vec not suitable for this graph

### Experiment 3: Add Node Features
```python
# Use Scryfall data
node_features = encode_card_attributes(cards)

# PyTorch Geometric
model = GATConv(...)
embeddings = model(node_features, edge_index)
```
- **Hypothesis:** Features help distinguish function
- **Expected:** Beats plain Node2Vec

### Experiment 4: Edge Attribution
```python
# Add format/archetype to edges
edge_features = encode_context(format, archetype, partition)

model = GATConv(edge_dim=edge_features_dim)
embeddings = model(x, edge_index, edge_features)
```
- **Hypothesis:** Context-aware edges improve accuracy
- **Expected:** Significant improvement

## Timeline Estimate

**Week 1:** More data + hyperparameter sweep
- If Node2Vec wins: Ship it
- If Jaccard wins: Move to attributed graphs

**Week 2-3:** Attributed Node2Vec (add features)
- Fetch Scryfall metadata for all cards
- Encode features (color, type, CMC, text)
- Re-train with concatenated features

**Week 4:** PyTorch Geometric GNN
- Implement GAT with node + edge features
- Compare to all previous methods
- Ship winner

**Week 5-6:** Multi-game + Paper
- YGO + Pokemon extractions
- Cross-game evaluation
- Write/submit arXiv paper

## Honest Assessment

**What we have:**
- Working evaluation framework
- Proof that current approach is suboptimal
- Multiple paths forward

**What we need:**
- More data (in progress)
- Better use of available information
- Willingness to abandon Node2Vec if it doesn't work

**Most likely outcome:**
- Attributed GNN beats everything (uses most info)
- But requires most engineering effort
- Jaccard is "good enough" for MVP

**Recommendation:**
1. Wait for data extraction (2-3 hours)
2. Re-run pipeline with new data
3. If Node2Vec still loses → implement attributed version
4. Don't waste time on unattributed Node2Vec if data doesn't help
