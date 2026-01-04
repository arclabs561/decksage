# GNN and AWS Status

**Date**: 2025-01-27
**Library**: **PyTorch Geometric** (torch_geometric)

---

## What We're Using

### GNN Library: PyTorch Geometric

**Implementation**: `src/ml/similarity/gnn_embeddings.py`

**Models**:
1. **GraphSAGE** (default, recommended)
2. **GCN** (Graph Convolutional Network)
3. **GAT** (Graph Attention Network)

**Status**: ✅ Code complete, ready for training

---

## Current Blockers

### 1. Scipy Build Failure
- **Issue**: Python 3.13 compatibility (Cython/numpy API changes)
- **Error**: `cimported module has no attribute 'NPY_F_CONTIGUOUS'`
- **Impact**: Blocks all training (scipy is a dependency)

### 2. PyTorch Geometric Not Installed
- **Status**: Added to `pyproject.toml` but blocked by scipy
- **Needs**: `torch` and `torch-geometric`

---

## Solutions

### Option 1: Use AWS for Training (Recommended)

**Train on AWS EC2/SageMaker** with Python 3.11:
```bash
# On AWS instance with Python 3.11
uv sync
uv run python -m src.ml.scripts.train_gnn
```

**Or use AWS SageMaker**:
- Pre-configured environments
- No local build issues
- Can upload/download models via S3

### Option 2: Make Scipy Optional

**For GNN training**, scipy is not directly needed:
- PyTorch Geometric only needs `torch`
- Scipy is only needed for some evaluation metrics
- Can train GNN without scipy

**Action**: Make scipy optional in dependencies, train GNN separately

### Option 3: Use Pre-built Wheels

**Download pre-built scipy**:
```bash
# Try conda or pre-built wheels
pip install --only-binary=scipy scipy
```

---

## AWS Integration

### S3 Operations
- ✅ Scripts created: `aws_data_ops.py`, `train_with_aws.py`
- ✅ Can download/upload embeddings
- ✅ Can check S3 for existing models

### Available Buckets
- `games-collections` - Has raw data
- Can create `decksage-data` for models/embeddings

---

## Immediate Actions

### 1. Train GNN on AWS (Bypass Scipy Issue)
```bash
# On AWS EC2 with Python 3.11
aws s3 cp s3://games-collections/processed/pairs_large.csv ./
uv sync
uv run python -m src.ml.scripts.train_gnn --pairs-csv pairs_large.csv
aws s3 cp experiments/signals/gnn_embeddings.json s3://games-collections/embeddings/
```

### 2. Make Scipy Optional (Local Training)
- Remove scipy from core dependencies
- Add to optional-dependencies
- Train GNN without scipy

### 3. Use Docker/Container
- Pre-built Python 3.11 environment
- All dependencies included
- No build issues

---

## What Works Now

✅ **Code**:
- GNN implementation complete
- Training script ready
- Fusion integration ready
- AWS scripts ready

❌ **Environment**:
- Scipy build failing (Python 3.13)
- PyTorch Geometric not installed (blocked by scipy)

---

## Recommendation

**Use AWS for training**:
1. Launch EC2 instance (Python 3.11)
2. Train GNN there
3. Upload results to S3
4. Download locally for use

**Or make scipy optional** and train GNN locally without it.

---

**Status**: ✅ **PyTorch Geometric** - Code ready, environment issue blocking
