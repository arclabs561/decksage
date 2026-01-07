# Amazon Mechanical Turk Setup Guide

## Current Status

✅ **AWS CLI**: Installed and configured
✅ **AWS Credentials**: Configured in `~/.aws/credentials`
✅ **MTurk Account**: Linked and ready to use

## Setup Steps

### 1. Link AWS Account to MTurk

Visit: https://requester.mturk.com/developer

1. Sign in with your AWS account
2. Link your AWS account to MTurk
3. Complete requester registration
4. Verify email address

### 2. Add Prepaid Balance

1. Go to: https://requester.mturk.com/account
2. Add prepaid balance (minimum: $10)
3. Balance is used to pay workers

### 3. Test Connection

```bash
# Test account balance (after linking)
aws mturk get-account-balance

# Should return your account balance
```

### 4. Test HIT Creation (Sandbox)

```bash
# Use sandbox for testing (no real money)
aws mturk create-hit \
    --endpoint-url https://mturk-requester-sandbox.us-east-1.amazonaws.com \
    --title "Test HIT" \
    --description "Testing MTurk integration" \
    --reward "0.01" \
    --assignment-duration-in-seconds 300 \
    --lifetime-in-seconds 3600
```

## Pricing Details

### Commission Structure

- **Base commission**: 20% of reward
- **High-volume commission**: 40% (if 10+ assignments per HIT)
- **Minimum fee**: $0.01 per assignment

### Cost Calculation

For single-assignment HITs at $0.10 reward:
- Worker reward: $0.10
- MTurk commission (20%): $0.02
- **Total cost: $0.12 per HIT**

For 100 HITs:
- Total: $12.00

### Best Practices for Pricing

1. **Minimum viable reward**: $0.10 (attracts quality workers)
2. **Competitive rates**: $0.15-$0.25 for complex tasks
3. **Time estimate**: 5-10 minutes per task = $0.10-$0.20
4. **Quality incentives**: Bonus payments for high-quality work

## Qualification Requirements

Our implementation uses:

1. **US Locale** (QualificationTypeId: `00000000000000000071`)
   - Ensures English proficiency
   - Better quality for text tasks

2. **Approval Rate > 95%** (QualificationTypeId: `000000000000000000L0`)
   - Filters out low-quality workers
   - Ensures reliable annotations

### Additional Qualifications (Optional)

- **Masters Qualification**: Highest quality (extra fee)
- **Number of Approved HITs**: Minimum experience
- **Custom Qualifications**: Domain-specific skills

## Testing Workflow

### 1. Test in Sandbox

```bash
# Submit test task (sandbox)
python scripts/annotation/submit_human_annotations.py submit \
    --service mturk \
    --limit 1 \
    --dry-run  # Test without submitting
```

### 2. Submit Real Tasks

```bash
# Submit to production MTurk
python scripts/annotation/submit_human_annotations.py submit \
    --service mturk \
    --priority high \
    --limit 10
```

### 3. Monitor Results

```bash
# Retrieve completed annotations
python scripts/annotation/submit_human_annotations.py retrieve \
    --service mturk \
    --limit 50
```

## Quality Assurance

### Pre-Submission

1. **Test HITs**: Submit 1-2 test HITs first
2. **Review format**: Ensure HTML renders correctly
3. **Check instructions**: Clear and unambiguous

### Post-Submission

1. **Review first batch**: Manually review 5-10 annotations
2. **Reject low quality**: Reject assignments that don't meet standards
3. **Adjust instructions**: Refine based on feedback

### Quality Metrics

- **Approval rate**: Target > 90%
- **Completion time**: 5-15 minutes per task
- **Consistency**: Compare multiple workers on same task

## Cost Optimization

1. **Batch HITs**: Combine multiple tasks into single HIT (reduces commission)
2. **Bulk pricing**: 10+ assignments = 40% commission (but can be cheaper overall)
3. **Bonus payments**: Reward high-quality work (incentivizes quality)

## Troubleshooting

### "RequestError: To use the MTurk API..."

**Solution**: Link AWS account to MTurk at https://requester.mturk.com/developer

### "InsufficientFunds"

**Solution**: Add prepaid balance at https://requester.mturk.com/account

### "InvalidParameterValue"

**Solution**: Check HIT parameters (reward, duration, qualifications)

## References

- MTurk Pricing: https://www.mturk.com/pricing
- MTurk Developer Guide: https://docs.aws.amazon.com/AWSMechTurk/latest/AWSMturkAPI/Welcome.html
- Requester Sandbox: https://requestersandbox.mturk.com

