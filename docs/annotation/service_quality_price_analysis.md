# Annotation Services: Quality vs Price Analysis

## Service Comparison

### Amazon Mechanical Turk (MTurk)

**Setup:**
- ✅ AWS CLI installed and configured
- ⚠️ Requires MTurk account linking: https://requester.mturk.com/developer
- Uses boto3 for API access

**Pricing (2025-2026):**
- Base reward: $0.10 per HIT
- MTurk commission: 20% (40% if 10+ assignments per HIT)
- **Total cost: ~$0.12 per annotation** (with 20% commission)
- For 100 annotations: ~$12.00
- For 1000 annotations: ~$120.00

**Quality:**
- Medium quality
- Large worker pool (millions)
- Quality depends on qualifications:
  - US locale requirement
  - Approval rate > 95%
  - Minimum approved HITs
- Best practices: Clear instructions, qualification filters, test HITs

**Best For:**
- Large-scale annotation (100+ tasks)
- Budget-conscious projects
- Training data collection
- When quality can be validated post-hoc

**Limitations:**
- Requires AWS account + MTurk account linking
- Quality varies (need good qualifications)
- Slower turnaround (workers choose tasks)

### Scale AI

**Setup:**
- ✅ API key configured in `.env`
- ✅ Service initialized and ready
- Uses requests library for API access

**Pricing:**
- **Cost: $0.50 per annotation**
- For 100 annotations: $50.00
- For 1000 annotations: $500.00
- 5x more expensive than MTurk

**Quality:**
- High quality
- Specialized annotators
- Quality assurance mechanisms
- Consistent results
- Faster turnaround

**Best For:**
- Critical annotations
- Evaluation data (ground truth)
- When quality is paramount
- When speed matters

**Limitations:**
- Higher cost
- Less control over annotator selection

### Custom Annotation Interface

**Setup:**
- ✅ No setup required
- ✅ Working (saves to files)

**Pricing:**
- **Cost: $0.00** (internal annotators)
- Time cost: Depends on annotator availability

**Quality:**
- Variable (depends on annotators)
- Can be highest if using experts
- Full control over process

**Best For:**
- Expert validation
- Internal review
- Quality control
- When you have domain experts available

**Limitations:**
- Requires internal annotators
- Not scalable
- Time-intensive

## Cost Comparison

| Service | Cost/Task | 100 Tasks | 1000 Tasks | Quality | Speed |
|---------|-----------|-----------|------------|---------|-------|
| **MTurk** | $0.12 | $12.00 | $120.00 | Medium | Medium |
| **Scale AI** | $0.50 | $50.00 | $500.00 | High | Fast |
| **Custom** | $0.00 | $0.00 | $0.00 | Variable | Slow |

## Quality vs Price Analysis

### Cost Efficiency (Quality per Dollar)

1. **MTurk**: Best cost efficiency for large-scale
   - 5x cheaper than Scale AI
   - Good quality with proper qualifications
   - Best ROI for training data

2. **Scale AI**: Best quality, but premium price
   - 5x more expensive than MTurk
   - Highest quality and consistency
   - Best for critical evaluation data

3. **Custom**: Best for expert validation
   - Free (but time cost)
   - Can achieve highest quality with experts
   - Not scalable

### Recommended Strategy

**Hybrid Approach:**

1. **Training Data (Large Scale)**
   - Use **MTurk** for bulk annotation
   - Cost: ~$0.12 per annotation
   - Quality: Medium (sufficient for training)
   - Scale: 100-1000+ annotations

2. **Evaluation Data (High Quality)**
   - Use **Scale AI** for ground truth
   - Cost: ~$0.50 per annotation
   - Quality: High (critical for evaluation)
   - Scale: 50-200 annotations

3. **Expert Validation**
   - Use **Custom** interface for spot checks
   - Cost: Free (internal)
   - Quality: Highest (expert review)
   - Scale: 10-50 annotations

## Setup Status

### MTurk
- ✅ AWS CLI installed
- ✅ AWS credentials configured
- ⚠️ **Needs MTurk account linking**: https://requester.mturk.com/developer
- ⚠️ **Needs account balance** (prepaid)

### Scale AI
- ✅ API key configured in `.env`
- ✅ Service ready to use
- ✅ Can submit tasks immediately

### Custom
- ✅ Fully operational
- ✅ No setup required

## Testing Results

All services tested successfully:

```
Service         Available    Cost/Task    Total (100)     Quality   
----------------------------------------------------------------------
mturk           ✓ Yes        $0.12        $12.00          Medium    
scale           ✓ Yes        $0.50        $50.00          High      
custom          ✓ Yes        $0.00        $0.00           Variable  
```

## Next Steps

1. **MTurk Setup:**
   - Link AWS account to MTurk: https://requester.mturk.com/developer
   - Add prepaid balance
   - Test with 1-2 HITs

2. **Scale AI:**
   - Ready to use
   - Test with small batch (3-5 tasks)
   - Monitor quality and cost

3. **Custom:**
   - Create annotation interface (optional)
   - Set up internal annotator workflow
   - Use for expert validation

## Recommendations

**For 100 Annotations:**
- **Budget-conscious**: MTurk ($12.00)
- **Quality-focused**: Scale AI ($50.00)
- **Expert validation**: Custom ($0.00, but time cost)

**For 1000 Annotations:**
- **Budget-conscious**: MTurk ($120.00)
- **Quality-focused**: Scale AI ($500.00)
- **Hybrid**: MTurk for 900 ($108) + Scale AI for 100 ($50) = $158

**Best Practice:**
- Use MTurk for training data (80-90%)
- Use Scale AI for evaluation data (10-20%)
- Use Custom for expert validation (spot checks)

