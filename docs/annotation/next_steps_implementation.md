# Next Steps Implementation Guide

## Completed ✅

1. **Updated to Latest Models (January 2026)**
   - Gemini 3 Flash (primary) - Fast, high-quality
   - Claude Opus 4.5 - Best reasoning
   - Gemini 3 Pro - Best context (1M token window)

2. **Human Annotation Queue System**
   - Automatic queuing for low IAA, high uncertainty, edge cases
   - Priority-based task management
   - Integration with annotation services

3. **Programmatic Human Annotation Services**
   - Amazon Mechanical Turk ($0.10/annotation)
   - Scale AI ($0.50/annotation)
   - Custom annotation interface (free, internal)

## Implementation Status

### Ready to Use

1. **Queue Human Annotations**
   ```bash
   # Generate LLM annotations and queue low-quality ones
   python scripts/annotation/queue_human_annotations.py \
       --game magic \
       --num-pairs 50 \
       --use-multi-annotator \
       --use-uncertainty
   ```

2. **Submit to Annotation Service**
   ```bash
   # Submit pending tasks to MTurk
   python scripts/annotation/submit_human_annotations.py submit \
       --service mturk \
       --priority high \
       --limit 10
   
   # Or use custom interface (saves to files)
   python scripts/annotation/submit_human_annotations.py submit \
       --service custom \
       --limit 20
   ```

3. **Retrieve Results**
   ```bash
   # Retrieve completed annotations
   python scripts/annotation/submit_human_annotations.py retrieve \
       --service mturk \
       --limit 50
   ```

4. **Large-Scale Validation**
   ```bash
   # Compare methods at scale (50+ annotations each)
   python scripts/annotation/run_large_scale_validation.py \
       --game magic \
       --num-pairs 50
   ```

## Next Steps (In Progress)

### 1. Test Human Annotation Queue ⏳

**Action:** Test with small batch (10-20 tasks)

```bash
# Queue a small batch
python scripts/annotation/queue_human_annotations.py \
    --game magic \
    --num-pairs 20 \
    --use-uncertainty

# List queued tasks
python scripts/annotation/queue_human_annotations.py --list-queue

# Submit to custom interface (for testing)
python scripts/annotation/submit_human_annotations.py submit \
    --service custom \
    --limit 10 \
    --dry-run  # Test without actually submitting
```

### 2. Integrate Human Annotations ⏳

**Action:** Merge human annotations into unified pipeline

- Load human annotations from queue
- Convert to unified format
- Integrate with LLM annotations
- Resolve conflicts (human > LLM)
- Use in training/evaluation

### 3. Active Learning Loop ⏳

**Action:** Retrain model after each annotation batch

- After each batch of annotations:
  1. Retrain model with new annotations
  2. Update uncertainty estimates
  3. Select next batch based on updated uncertainty
  4. Repeat

### 4. Annotator Reliability Tracking ⏳

**Action:** Track IAA over time per annotator

- Monitor annotator performance
- Auto-adjust weights based on agreement
- Identify annotator drift
- Handle annotator failure gracefully

## Human Annotation Service Setup

### Amazon Mechanical Turk

**Setup:**
1. Create AWS account
2. Enable MTurk API
3. Set credentials:
   ```bash
   export AWS_ACCESS_KEY_ID=your_key
   export AWS_SECRET_ACCESS_KEY=your_secret
   ```
4. Install boto3: `pip install boto3`

**Cost:** ~$0.10 per annotation
**Quality:** Good with qualifications (approval rate > 95%)

### Scale AI

**Setup:**
1. Create Scale AI account
2. Get API key
3. Set environment variable:
   ```bash
   export SCALE_API_KEY=your_key
   ```
4. Install requests: `pip install requests`

**Cost:** ~$0.50 per annotation
**Quality:** High (specialized annotators)

### Custom Interface (Internal)

**Setup:**
- No setup required
- Tasks saved to `annotations/human_tasks/`
- Manual annotation via custom UI
- Results saved back to task files

**Cost:** Free (internal annotators)
**Quality:** Depends on annotators

## Cost Estimation

### For 100 Annotations

- **MTurk**: $10.00
- **Scale AI**: $50.00
- **Custom**: $0.00 (internal)

### For 1000 Annotations

- **MTurk**: $100.00
- **Scale AI**: $500.00
- **Custom**: $0.00 (internal)

## Quality Assurance

### MTurk Qualifications
- US locale requirement
- Approval rate > 95%
- Minimum approved HITs

### Best Practices
1. Start small (10-20 annotations)
2. Review first batch manually
3. Adjust instructions based on results
4. Monitor cost and quality
5. Compare human vs LLM annotations

## Integration Workflow

```
1. Generate LLM Annotations
   ↓
2. Queue Low-Quality for Human Review
   ↓
3. Submit to Annotation Service
   ↓
4. Retrieve Human Annotations
   ↓
5. Integrate with LLM Annotations
   ↓
6. Resolve Conflicts (Human > LLM)
   ↓
7. Use in Training/Evaluation
```

## Research Findings

- **Active learning**: 30-50% annotation budget reduction
- **Multi-annotator consensus**: 8-32% accuracy improvement
- **Human annotation**: Highest quality, but 5-10x cost of LLM
- **Hybrid approach**: LLM + human review for critical cases = best balance

## Recommendations

1. **For Training Data**: Use uncertainty-based selection (LLM)
2. **For Evaluation Data**: Use multi-annotator IAA (LLM consensus)
3. **For Critical Cases**: Queue for human annotation
4. **For Cost Optimization**: Use MTurk for large-scale, Scale AI for high-quality

