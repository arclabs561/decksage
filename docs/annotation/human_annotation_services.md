# Human Annotation Services Integration

## Overview

Programmatic integration with human annotation services for high-quality ground truth data when LLM annotations are uncertain or disagree.

## Supported Services

### 1. Amazon Mechanical Turk (MTurk)

**Best for:** Large-scale, cost-effective annotation

**Features:**
- Large worker pool (millions of workers)
- Low cost: ~$0.10 per annotation
- Qualification system for quality assurance
- API for programmatic access

**Requirements:**
- AWS account
- boto3 library: `pip install boto3`
- AWS credentials (access key + secret key)

**Setup:**
```bash
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
```

**Cost:** ~$0.10 per annotation

**Quality:** Good with proper qualifications (approval rate > 95%, US locale)

### 2. Scale AI

**Best for:** High-quality, specialized annotations

**Features:**
- Specialized annotators
- Quality assurance mechanisms
- API access
- Higher cost but better quality

**Requirements:**
- Scale AI account
- API key
- requests library: `pip install requests`

**Setup:**
```bash
export SCALE_API_KEY=your_key
```

**Cost:** ~$0.50 per annotation

**Quality:** High (specialized annotators)

### 3. Labelbox

**Best for:** Human-in-the-loop workflows

**Features:**
- Model-assisted labeling
- Quality workflows
- API integration
- Custom annotation interfaces

**Requirements:**
- Labelbox account
- API key
- Labelbox Python SDK: `pip install labelbox`

**Cost:** Custom pricing (contact Labelbox)

**Quality:** High (with quality workflows)

### 4. Appen/Figure Eight

**Best for:** Enterprise-scale annotation

**Features:**
- Over 1 million skilled contributors
- Quality assurance
- Custom workflows
- API access

**Requirements:**
- Appen account
- API credentials
- Custom integration

**Cost:** Custom pricing (contact Appen)

**Quality:** High (enterprise-grade)

### 5. Custom Annotation Interface

**Best for:** Internal annotation, expert review

**Features:**
- No external dependencies
- Full control
- Free (internal)
- Custom workflows

**Setup:**
- Tasks saved to `annotations/human_tasks/`
- Manual annotation via custom UI
- Results saved back to task files

**Cost:** Free (internal)

**Quality:** Depends on annotators

## When to Queue for Human Annotation

### Automatic Queuing

1. **Low IAA (< 0.4)**: Multi-annotator systems disagree significantly
2. **High Uncertainty (> 0.7)**: Uncertainty-based selection identifies ambiguous cases
3. **Edge Cases**: Very low (< 0.1) or very high (> 0.9) similarity scores
4. **Low Confidence**: Short reasoning, missing data

### Manual Queuing

- User explicitly requests human review
- Quality control checks
- Validation of critical annotations

## Usage

### Queue Annotations

```bash
# Generate LLM annotations and queue low-quality ones
python scripts/annotation/queue_human_annotations.py \
    --game magic \
    --num-pairs 50 \
    --use-multi-annotator \
    --use-uncertainty

# List pending tasks
python scripts/annotation/queue_human_annotations.py --list-queue

# Show statistics
python scripts/annotation/queue_human_annotations.py --stats
```

### Submit to Annotation Service

```python
from src.ml.annotation.human_annotation_queue import HumanAnnotationQueue
from src.ml.annotation.human_annotation_services import get_annotation_service

queue = HumanAnnotationQueue()
service = get_annotation_service("mturk")  # or "scale", "custom"

# Get pending tasks
pending = queue.get_pending_tasks(priority=AnnotationPriority.HIGH, limit=10)

# Submit to service
for task in pending:
    external_id = service.submit_task(task)
    queue.update_task_status(
        task.task_id,
        AnnotationStatus.SUBMITTED,
        external_task_id=external_id,
    )
```

### Retrieve Results

```python
# Poll for results
for task in queue.get_pending_tasks(status=AnnotationStatus.SUBMITTED):
    result = service.get_result(task.external_task_id)
    if result:
        queue.update_task_status(
            task.task_id,
            AnnotationStatus.COMPLETED,
            human_annotation=result.__dict__,
            cost=result.cost,
            annotator_id=result.annotator_id,
        )
```

## Cost Estimation

### MTurk
- **Per annotation**: $0.10
- **100 annotations**: $10.00
- **1000 annotations**: $100.00

### Scale AI
- **Per annotation**: $0.50
- **100 annotations**: $50.00
- **1000 annotations**: $500.00

### Custom (Internal)
- **Per annotation**: $0.00
- **Cost**: Time of internal annotators

## Quality Assurance

### MTurk Qualifications
- US locale requirement
- Approval rate > 95%
- Minimum number of approved HITs

### Scale AI
- Specialized annotators
- Quality checks
- Review process

### Best Practices
1. **Start Small**: Test with 10-20 annotations
2. **Quality Checks**: Review first batch manually
3. **Iterate**: Adjust instructions based on results
4. **Monitor**: Track cost and quality metrics
5. **Compare**: Compare human vs LLM annotations

## Integration with Annotation Pipeline

Human annotations are integrated into the unified annotation system:

1. **Queue**: Tasks queued automatically or manually
2. **Submit**: Submitted to annotation service
3. **Retrieve**: Results retrieved via API
4. **Integrate**: Merged with LLM annotations
5. **Validate**: Quality checks and validation
6. **Use**: Converted to training/evaluation data

## Next Steps

1. ✅ Queue system implemented
2. ✅ Service integrations (MTurk, Scale AI, Custom)
3. ⏳ Test with small batch (10-20 annotations)
4. ⏳ Compare human vs LLM annotations
5. ⏳ Integrate results into annotation pipeline
6. ⏳ Set up automated submission/retrieval

## References

- MTurk: https://docs.aws.amazon.com/AWSMechTurk/latest/AWSMturkAPI/Welcome.html
- Scale AI: https://docs.scale.com/
- Labelbox: https://docs.labelbox.com/
- Appen: https://appen.com/

