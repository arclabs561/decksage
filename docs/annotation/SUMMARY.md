# Annotation Services Summary

## Quick Answers

### Did we submit to both services?
**No** - Only dry runs so far. Need to add MTurk balance ($0.12 per task) and fix Scale AI API endpoint.

### Are tasks well-defined?
**Improved** - Added:
- Score range examples (0.0-1.0 with card examples)
- Clear substitution criteria
- Detailed similarity type definitions
- Reasoning requirements
- Consistency guidelines

### What is "Custom" service?
**NOT our LLMs** - It's for internal/expert human annotation:
- Saves tasks to files: `experiments/annotations/human_tasks/`
- Human annotator fills in JSON file
- System retrieves completed annotations
- Cost: $0.00 (but time cost)

### Where are annotations stored?
1. **Queue**: `experiments/annotations/human_annotation_queue.jsonl`
2. **Custom tasks**: `experiments/annotations/human_tasks/*.json`
3. **Final annotations**: `experiments/annotations/human_annotations_*.jsonl`
4. **Main directory**: `annotations/` (all sources)

## Service Comparison

| Service | Cost | Quality | Speed | Best For |
|---------|------|---------|-------|----------|
| MTurk | $0.12 | Medium | Medium | Training data |
| Scale AI | $0.50 | High | Fast | Evaluation data |
| Custom | $0.00 | Variable | Slow | Expert validation |

## Next Steps

1. Fix Scale AI API endpoint (404 error)
2. Add MTurk balance ($0.12+)
3. Submit test tasks (1-2 per service)
4. Compare quality
5. Integrate into pipeline

