# Multi-Task Embedding Deployment

## Quick Deploy

```bash
./scripts/deploy_multitask_embeddings.sh
```

Or:

```bash
just deploy-multitask
```

## What Gets Deployed

- **Model**: `data/embeddings/multitask_sub5.wv` → `data/embeddings/production.wv`
- **Performance**: +155.6% overall improvement
- **Key Feature**: Substitution task now works (0.0 → 0.22 P@10)

## Documentation

- **Full Guide**: `docs/MULTITASK_EMBEDDINGS.md`
- **Deployment**: `docs/DEPLOYMENT_GUIDE.md`
- **Reports**: `experiments/FINAL_MULTITASK_REPORT.json`

## Performance

| Task | Baseline | Multi-Task | Improvement |
|------|----------|------------|-------------|
| Co-occurrence | 0.1960 | 0.2100 | +7.1% |
| Functional | 0.0114 | 0.0934 | +717% |
| Substitution | 0.0000 | 0.2200 | ∞% |
| **Overall** | **0.0685** | **0.1749** | **+155.6%** |

## Post-Deployment

1. Monitor performance metrics
2. Collect user feedback
3. Track substitution success rates
4. Review logs for issues

See `docs/DEPLOYMENT_GUIDE.md` for detailed monitoring checklist.
