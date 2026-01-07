# Scale AI Setup Guide

## API Key Configuration

Scale AI API key has been added to `.env`:

```bash
SCALE_API_KEY=live_105891239dc24bef949b48c8076c313c
```

## Usage

### Submit Tasks

```bash
# Submit pending tasks to Scale AI
python scripts/annotation/submit_human_annotations.py submit \
    --service scale \
    --priority high \
    --limit 10
```

### Retrieve Results

```bash
# Retrieve completed annotations
python scripts/annotation/submit_human_annotations.py retrieve \
    --service scale \
    --limit 50
```

### Queue and Submit Workflow

```bash
# 1. Generate annotations and queue low-quality ones
python scripts/annotation/queue_human_annotations.py \
    --game magic \
    --num-pairs 50 \
    --use-uncertainty

# 2. Submit queued tasks to Scale AI
python scripts/annotation/submit_human_annotations.py submit \
    --service scale \
    --priority high \
    --limit 20

# 3. Retrieve results (run periodically)
python scripts/annotation/submit_human_annotations.py retrieve \
    --service scale \
    --limit 50
```

## Cost

- **Per annotation**: ~$0.50
- **100 annotations**: ~$50.00
- **1000 annotations**: ~$500.00

## Quality

Scale AI provides:
- Specialized annotators
- Quality assurance mechanisms
- Higher quality than MTurk (but higher cost)

## API Details

- **Base URL**: `https://api.scale.com/v1`
- **Authentication**: Basic Auth (API key as username)
- **Rate Limits**: Check Scale AI documentation

## Notes

- API key is stored in `.env` (not committed to git)
- Use live API key for production
- Test API key available for development: `test_fbc28723bd4a4a1c833f224e1c18291e`

