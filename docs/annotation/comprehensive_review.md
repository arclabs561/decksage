# Comprehensive Annotation System Review

## Overview

Complete review of the annotation system including:
1. Task definitions and guidelines
2. Service comparison (MTurk, Scale AI, Custom)
3. Storage locations
4. Quality vs price analysis

## Task Definition Review

### Current Instructions (Issues Found)

**Problems:**
- ❌ Missing score examples (annotators may not know what 0.5 means)
- ❌ No clear substitution criteria
- ❌ Vague similarity type definitions
- ❌ No consistency guidelines

### Improved Instructions (Implemented)

**Improvements:**
- ✅ Added score range examples (0.0-1.0 with card examples)
- ✅ Added clear substitution criteria
- ✅ Added detailed similarity type definitions
- ✅ Added reasoning requirements (2-3 sentences)
- ✅ Added consistency guidelines
- ✅ Added full range usage instructions

**Score Guidelines with Examples:**
- 0.9-1.0: Nearly identical (e.g., "Lightning Bolt" vs "Shock")
- 0.7-0.8: Very similar (e.g., "Counterspell" vs "Mana Leak")
- 0.5-0.6: Moderately similar (e.g., "Lightning Bolt" vs "Lava Spike")
- 0.3-0.4: Somewhat similar (e.g., "Lightning Bolt" vs "Bolt of Keranos")
- 0.1-0.2: Marginally similar
- 0.0-0.1: Unrelated

## Service Comparison

### Amazon Mechanical Turk (MTurk)

**Status:** ✅ Ready (needs account balance)

**Setup:**
- AWS CLI configured
- MTurk account linked
- Current balance: $0.02 (needs more for testing)

**Pricing:**
- Cost per task: $0.12 (includes 20% commission)
- 100 tasks: $12.00
- 1000 tasks: $120.00

**Quality:**
- Medium quality
- Large worker pool
- Quality depends on qualifications (US locale, >95% approval)

**Best For:**
- Large-scale training data
- Budget-conscious projects
- When quality can be validated post-hoc

### Scale AI

**Status:** ✅ Ready

**Setup:**
- API key configured in `.env`
- Service initialized and tested

**Pricing:**
- Cost per task: $0.50
- 100 tasks: $50.00
- 1000 tasks: $500.00

**Quality:**
- High quality
- Specialized annotators
- Quality assurance mechanisms
- Faster turnaround

**Best For:**
- Critical evaluation data
- When quality is paramount
- When speed matters

### Custom Annotation Service

**What it is:**
- ❌ NOT our own LLMs (those are separate)
- ✅ Internal/expert human annotation interface

**How it works:**
1. Tasks saved to files: `experiments/annotations/human_tasks/`
2. Human annotator opens file and fills in annotation
3. File updated with annotation result
4. System retrieves completed annotations

**Storage:**
- Directory: `experiments/annotations/human_tasks/`
- Format: JSON files (one per task)
- Example: `experiments/annotations/human_tasks/task_001.json`

**Use cases:**
- Expert validation (you or team members)
- Quality control (spot checks)
- When you want full control
- No budget for external services

**Pricing:**
- Cost: $0.00 (but time cost of internal annotators)

## Annotation Storage

### 1. Human Annotation Queue

**Location:** `experiments/annotations/human_annotation_queue.jsonl`

**Format:** JSONL (one task per line)

**Contains:**
- All queued tasks (pending, submitted, completed)
- Task metadata (priority, reason, LLM annotations, IAA metrics)
- External task IDs (MTurk HIT IDs, Scale AI task IDs)
- Human annotation results (when completed)
- Cost tracking

**Status:** ✅ Exists and working

### 2. Custom Annotation Tasks

**Location:** `experiments/annotations/human_tasks/`

**Format:** JSON files (one per task)

**Contains:**
- Tasks for internal annotation
- Task instructions and context
- Annotation results (when completed)

**Status:** ✅ Directory exists (0 files currently)

### 3. Final Human Annotations

**Location:** `experiments/annotations/human_annotations_*.jsonl`

**Format:** JSONL (one annotation per line)

**Contains:**
- Completed human annotations from all services
- Unified format matching LLM annotations
- Ready for integration into training/evaluation

**Status:** Created when annotations are retrieved

### 4. Main Annotation Directory

**Location:** `annotations/`

**Contains:**
- All annotation sources (LLM, human, hand, etc.)
- Integrated annotations
- Training data (substitution pairs)
- Evaluation data (test sets)

**Status:** ✅ Exists

## Submission Status

### Have We Submitted Tasks?

**Answer:** No, only dry runs so far.

**To submit:**
```bash
# Submit comparison tasks to both services
python scripts/annotation/submit_comparison_tasks.py \
    --num-tasks 2

# Or submit separately
python scripts/annotation/submit_human_annotations.py submit \
    --service mturk --limit 1

python scripts/annotation/submit_human_annotations.py submit \
    --service scale --limit 1
```

## Quality vs Price Analysis

### Cost Comparison

| Service | Cost/Task | 100 Tasks | Quality | Speed | Best For |
|---------|-----------|-----------|---------|-------|----------|
| **MTurk** | $0.12 | $12.00 | Medium | Medium | Training data |
| **Scale AI** | $0.50 | $50.00 | High | Fast | Evaluation data |
| **Custom** | $0.00 | $0.00 | Variable | Slow | Expert validation |

### Recommendations

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

## Next Steps

1. ✅ Task definitions improved
2. ✅ All services configured
3. ⏳ Submit test tasks to both services (1-2 tasks each)
4. ⏳ Retrieve and compare results
5. ⏳ Analyze quality differences
6. ⏳ Integrate into annotation pipeline

## Commands

### Review System
```bash
python scripts/annotation/review_and_test_services.py --all
```

### Submit Comparison Tasks
```bash
python scripts/annotation/submit_comparison_tasks.py --num-tasks 2
```

### Retrieve Results
```bash
python scripts/annotation/submit_human_annotations.py retrieve \
    --service mturk --limit 10

python scripts/annotation/submit_human_annotations.py retrieve \
    --service scale --limit 10
```

### Check Queue
```bash
python scripts/annotation/queue_human_annotations.py --stats
python scripts/annotation/queue_human_annotations.py --list-queue
```

