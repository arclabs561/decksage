# Strategy Shift: PyG + LLM Judge for Rapid Validation

**Date:** October 1, 2025  
**Current:** Stuck on gensim/pecanpy dependency hell  
**Solution:** PyTorch Geometric + LLM-assisted annotation

## 🚨 Current Blocker

```
gensim/models/word2vec_inner.c:9364:41: error: no member named
```

**Root cause:** Gensim/PecanPy compilation issues with Python 3.13

**Time wasted:** 30+ minutes on pip/uv dependency resolution

## 💡 Better Approach: PyTorch Geometric

Per [PyG documentation](https://pytorch-geometric.readthedocs.io/en/latest/cheatsheet/gnn_cheatsheet.html), we can use modern GNN architectures instead of Node2Vec:

### Why PyG > PecanPy?

| Feature | PecanPy (current) | PyTorch Geometric |
|---------|------------------|-------------------|
| **Install** | ❌ Compilation hell | ✅ `pip install torch-geometric` |
| **Architecture** | Random walks only | GCN, GAT, GraphSAGE, Transformer |
| **Edge features** | No | Yes (edge attributes) |
| **Batching** | Manual | Built-in |
| **GPU** | Limited | Full support |
| **Maintenance** | Small project | 15K+ stars, active |

### Recommended Models

From [PyG cheatsheet](https://pytorch-geometric.readthedocs.io/en/latest/cheatsheet/gnn_cheatsheet.html):

1. **GraphSAGE** ([Hamilton+ 2017](https://arxiv.org/abs/1706.02216))
   - Aggregates neighbor features
   - Scales to large graphs
   - ✅ Supports edge weights

2. **GAT** (Graph Attention) ([Veličković+ 2017](https://arxiv.org/abs/1710.10903))
   - Learns attention weights
   - Better for heterogeneous graphs
   - ✅ Supports edge attributes

3. **GCN** (Graph Convolutional) ([Kipf+ 2016](https://arxiv.org/abs/1609.02907))
   - Simple, fast
   - Good baseline
   - ✅ Proven effective

### Implementation

```python
import torch
from torch_geometric.nn import SAGEConv, GATConv
from torch_geometric.data import Data

# Convert our CSV to PyG format
edge_index = torch.tensor([[src_ids], [dst_ids]], dtype=torch.long)
edge_weight = torch.tensor(weights, dtype=torch.float)

# Build model
class CardGNN(torch.nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, out_channels)
    
    def forward(self, x, edge_index, edge_weight):
        x = self.conv1(x, edge_index, edge_weight).relu()
        x = self.conv2(x, edge_index, edge_weight)
        return x

# Train end-to-end (no walks needed!)
```

**Time to implement:** 2-3 hours (vs days debugging pecanpy)

## 📊 Annotation Strategy: LLM Judge

**We already have `llm_judge.py`!** ✅

### Current Annotation Status

```bash
$ fd -e yaml -e json -d 3 --base-directory experiments
llm_judge_report.json  # ← Already exists!
```

**No manual annotations yet** - perfect opportunity to use LLM judge.

### LLM-Accelerated Annotation Workflow

#### 1. **Generate Candidates** (PyG model)
```bash
python card_similarity_pyg.py --input ../../data/processed/pairs.csv
# → Produces embeddings
```

#### 2. **LLM Batch Evaluation** (Already implemented!)
```python
from llm_judge import LLMJudge

judge = LLMJudge()  # Uses Claude/GPT via OpenRouter

# Evaluate 100 cards in parallel
for query_card in sample_cards:
    similar = model.get_similar(query_card, k=10)
    
    # LLM provides expert analysis
    result = judge.evaluate_similarity(
        query_card=query_card,
        similar_cards=similar,
        context="Magic: The Gathering"
    )
    
    # Returns:
    # - overall_quality: 0-10
    # - card_ratings: [relevance 0-4 for each]
    # - issues: ["Format bias", "Missing Modern staples"]
    # - suggestions: ["Add deck context", "Filter by color"]
```

**Speed:** 100 annotations in ~10 minutes (vs hours manually)

**Quality:** Expert-level reasoning + bias detection

#### 3. **Human Validation** (Sample only)
- LLM evaluates 100% of results
- You review 10% to calibrate
- Fix systematic issues in data/model

### Advantages

✅ **Speed:** 10-100x faster than manual  
✅ **Consistency:** No annotator fatigue  
✅ **Insight:** Detects biases/patterns  
✅ **Scale:** Can process full dataset  
✅ **Cost:** ~$0.50 for 100 cards @ Claude Sonnet  

## 🎯 Revised Action Plan

### Today (2 hours)

1. **Switch to PyG** (30 min)
   ```bash
   uv pip install torch torch-geometric
   # Create card_similarity_pyg.py (copy structure from pecanpy version)
   ```

2. **Train first model** (20 min)
   ```bash
   python card_similarity_pyg.py --model graphsage --dim 128
   # Should work immediately (no compilation issues)
   ```

3. **LLM evaluation** (30 min)
   ```bash
   python llm_judge.py \
     --embeddings ../../data/embeddings/magic_pyg.pt \
     --num-queries 50 \
     --output ../../experiments/llm_eval_v1.json
   ```

4. **Review HTML dashboard** (30 min)
   - Open `debug/index.html`
   - Check LLM-flagged issues
   - Identify data problems

5. **Iterate based on LLM feedback** (10 min)
   - If "Format bias toward Legacy" → Extract more Modern
   - If "Missing burn spells" → Check data coverage
   - If "Color confusion" → Add node features

### This Week (5-10 hours)

6. **Compare PyG models**
   - GraphSAGE vs GAT vs GCN
   - Let LLM judge which is best
   - Pick winner

7. **Refine data based on LLM insights**
   - Address systematic biases
   - Balance formats
   - Add missing archetypes

8. **Human spot-check**
   - Review 20 LLM evaluations
   - Validate LLM is accurate
   - Adjust prompts if needed

9. **Production model**
   - Train on cleaned data
   - Deploy via FastAPI
   - Monitor with LLM judge

## 📈 Expected Improvements

| Metric | PecanPy (blocked) | PyG + LLM |
|--------|------------------|-----------|
| **Setup time** | ∞ (broken) | 30 min |
| **Training time** | Unknown | 5-10 min |
| **Annotation** | Days (manual) | Hours (LLM) |
| **Model quality** | Random walks | Learned aggregation |
| **Iteration speed** | Slow | Fast (GPU) |

## 🔬 Research Angles

Per [PyG tutorials](https://github.com/AntonioLonga/PytorchGeometricTutorial) and [CERN presentation](https://indico.cern.ch/event/1025220/contributions/4304559/attachments/2220154/3759466/PYG.pdf):

1. **Node features:** Card attributes (color, CMC, type)
2. **Edge features:** Co-occurrence strength, deck format
3. **Heterogeneous graphs:** Cards + Decks as different node types
4. **Temporal:** Track meta changes over time

**All impossible with simple Node2Vec, easy with PyG**

## ✅ Decision Matrix

### Keep PecanPy if:
- ❌ Can't install PyTorch
- ❌ Need pure NumPy/Gensim stack
- ❌ Random walks are theoretically required

### Switch to PyG if:
- ✅ Want modern GNN architectures
- ✅ Need to iterate quickly
- ✅ Want node/edge features
- ✅ Care about research credibility

**Verdict:** Switch to PyG + LLM judge

## 🚀 Immediate Next Command

```bash
cd /Users/henry/Documents/dev/decksage/src/ml

# Install PyG (works on any Python 3.8+)
source .venv/bin/activate
uv pip install torch torch-geometric

# Create PyG version
cp card_similarity_pecan.py card_similarity_pyg.py
# (We'll modify it to use PyG instead of PecanPy)

# Run LLM judge on existing data to get baseline
python llm_judge.py \
  --mode batch_evaluate \
  --queries "Lightning Bolt,Counterspell,Brainstorm" \
  --output ../../experiments/llm_baseline.json
```

**Expected time to first results:** 1 hour  
**Expected quality improvement:** Significant (modern GNNs + LLM feedback)

---

## 💭 Why This Works

**Problem:** Can't get Node2Vec dependencies working  
**Solution:** Use better tools (PyG) + LLM to accelerate validation

**Key insight:** We don't need 100% manual annotation. LLM can:
1. Spot obvious errors (Blue card similar to Red card?)
2. Detect patterns (All results are Legacy staples)
3. Suggest improvements (Need more Modern data)
4. Provide expert reasoning (These are both rituals in Storm)

**We validate LLM with spot checks, not the other way around.**

This is **faster, cheaper, and likely better** than pure manual annotation.





