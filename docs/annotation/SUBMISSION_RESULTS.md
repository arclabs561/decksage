# Human Annotation Submission Results

## Summary

**Status**: Code is ready, but external service setup required

## Issues Found

### 1. MTurk - Low Balance
- **Error**: Account balance $0.02, need $0.12+ per task
- **Fix**: Add prepaid balance at https://requester.mturk.com/account
- **Code Status**: ✅ Fixed indentation bug

### 2. Scale AI - API Access Not Enabled
- **Error**: 402 Payment Required - "You have not been authorized to use this API endpoint"
- **Endpoint**: `/task/textcollection` (correct endpoint)
- **Fix**: Contact sales@scale.ai to enable textcollection API endpoint
- **Alternative**: Use custom service for now

## Code Fixes Applied

1. ✅ Fixed MTurk `question_html` variable indentation bug
2. ✅ Updated Scale AI endpoint to `/task/textcollection` 
3. ✅ Improved task instructions with score examples
4. ✅ Enhanced HTML form styling for MTurk

## Next Steps

### Immediate (Can Do Now)
- Use **Custom Service** - works immediately, no setup
  ```bash
  python scripts/annotation/submit_human_annotations.py submit \
      --service custom --limit 1
  ```

### For MTurk
1. Add prepaid balance ($5-10 recommended)
2. Retry submission:
   ```bash
   python scripts/annotation/submit_comparison_tasks.py \
       --mturk-only --num-tasks 1
   ```

### For Scale AI
1. Contact sales@scale.ai to enable textcollection endpoint
2. Or use custom service as alternative

## Service Comparison

| Service | Setup | Cost/Task | Status |
|---------|-------|-----------|--------|
| **MTurk** | Add balance | $0.12 | ⏳ Ready (needs balance) |
| **Scale AI** | Enable API | $0.50 | ⏳ Ready (needs API access) |
| **Custom** | None | $0.00 | ✅ Works now |

## Recommendation

Use **Custom Service** for immediate testing while setting up MTurk/Scale AI access.

