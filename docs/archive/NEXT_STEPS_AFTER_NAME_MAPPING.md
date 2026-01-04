# Next Steps After Name Normalization

## Immediate Next Steps

### 1. Test Evaluation with Name Mapping ⏳
**Priority**: High
**Status**: Ready (blocked by local dependencies)

**Options**:
- **Option A**: Fix local environment (install pandas, numpy, gensim)
- **Option B**: Run on AWS EC2 (recommended given scipy issues)

**AWS Execution Plan**:
```python
# Create script: src/ml/scripts/evaluate_on_aws.py
# - Upload evaluation script to S3
# - Launch EC2 instance
# - Install dependencies
# - Run evaluation
# - Download results
```

### 2. Verify Name Mapping Effectiveness
- Run evaluation with and without mapping
- Compare P@10 and MRR metrics
- Confirm 0 hits issue is resolved
- Identify any remaining gaps

### 3. Expand Name Mapping if Needed
- Check coverage for all test set queries
- Add mappings for missing cards
- Handle edge cases (special characters, variants)

## Medium-Term Tasks

### 4. Compute All Signals ⏳
**Status**: Blocked by scipy build issue

**Signals to Compute**:
- Sideboard co-occurrence
- Temporal trends (monthly co-occurrence)
- Archetype staples
- Archetype co-occurrence
- Format co-occurrence
- Cross-format patterns

**AWS Execution**:
- Use `train_on_aws_instance.py` pattern
- Run `compute_and_cache_signals.py` on EC2
- Upload results to S3

### 5. Export Decks Metadata ⏳
**Status**: Data directory may not exist locally

**Check**:
```bash
ls -la src/backend/data-full/games/magic/
```

**If missing**:
- Download from S3 if available
- Or generate using Go export command on AWS

### 6. Train GNN Models ⏳
**Status**: Blocked by scipy/PyTorch dependencies

**AWS Execution**:
- Use EC2 with GPU instance (if needed)
- Install PyTorch Geometric
- Run `train_gnn.py`
- Upload embeddings to S3

## Long-Term Tasks

### 7. Expand Test Sets
- Use LLM-as-Judge to generate more test queries
- Expand to 50-100 queries per game
- Include diverse card types and formats

### 8. Multi-Judge LLM System
- Implement consensus computation
- Use multiple LLM judges with different personas
- Improve annotation quality

### 9. Temporal Evaluation Implementation
- Capture temporal context (timestamps, ban lists, meta state)
- Evaluate recommendations with time awareness
- Track format rotations and ban timeline

## Recommended Execution Order

1. **Test evaluation with mapping** (verify fix works)
2. **Compute signals on AWS** (if decks metadata available)
3. **Train GNN on AWS** (if needed for better embeddings)
4. **Expand test sets** (improve evaluation coverage)
5. **Implement temporal evaluation** (first-class concern)

## Blockers

1. **Local Environment**: Missing pandas, numpy, gensim, scipy
   - **Solution**: Use AWS EC2 for all computation

2. **Decks Metadata**: May not exist locally
   - **Solution**: Check S3, download if available, or generate on AWS

3. **Data Directory**: `src/backend/data-full/games/magic/` may not exist
   - **Solution**: Use S3 as source of truth, download as needed

## AWS-First Strategy

Given the local environment issues, recommend:
- **All computation on AWS EC2**
- **S3 as data source and destination**
- **Local machine for orchestration only**

This approach:
- ✅ Avoids dependency hell
- ✅ Faster computation (better hardware)
- ✅ Consistent environment
- ✅ Easy to scale
