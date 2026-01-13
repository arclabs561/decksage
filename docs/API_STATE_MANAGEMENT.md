# API State Management

## Overview

The FastAPI application uses `app.state` to manage in-memory resources (embeddings, signals, graph data) that are loaded at startup and available to all request handlers.

## Architecture

### State Loading

State is loaded during the `lifespan` context manager in `src/ml/api/api.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load embeddings, signals, graph data
    load_embeddings_to_state(emb_path, pairs_path)
    signal_status = load_signals_to_state(...)
    yield
    # Cleanup on shutdown
```

### State Access

State is accessed via `get_state()`:

```python
from src.ml.api.api import get_state

state = get_state()
embeddings = state.embeddings
graph_data = state.graph_data
```

## Worker Configuration

### Single Worker (Recommended for Development)

Each worker loads embeddings independently, causing memory duplication.

**Recommended for development/testing:**
```bash
uvicorn src.ml.api.api:app --workers 1
```

**Memory usage:** ~2-4GB per worker

### Multiple Workers (Production)

For production with multiple workers:

```bash
uvicorn src.ml.api.api:app --workers 4
```

**Memory usage:** 4 workers = 8-16GB RAM total

**Considerations:**
- Each worker loads embeddings independently
- No shared state between workers
- Use Redis for shared caches/counters if needed
- Consider shared memory (mmap) for very large embeddings

## Signal Availability

Signals are loaded with status tracking. Check availability:

```python
state = get_state()
signal_status = state.signal_status

# Check which signals are loaded
if signal_status.get("text_embedder"):
    # Use text embeddings
    pass
```

Available signals:
- `sideboard`: Sideboard co-occurrence data
- `temporal`: Temporal co-occurrence data
- `gnn`: GNN embeddings
- `text_embedder`: Text embedding model
- `visual_embedder`: Visual embedding model
- `archetype`: Archetype signals
- `format`: Format signals

## Testing

### Inject Test State

For testing with different state configurations:

```python
from src.ml.api.api import app, get_state

# Override state in tests
state = get_state()
state.embeddings = mock_embeddings
state.graph_data = mock_graph_data
```

### Test Fixtures

Create test fixtures for common state configurations:

```python
@pytest.fixture
def api_state_with_embeddings():
    state = get_state()
    state.embeddings = load_test_embeddings()
    return state
```

## Deployment

### Environment Variables

- `EMBEDDINGS_PATH`: Path to embeddings file (.wv)
- `PAIRS_PATH`: Path to pairs CSV (optional)
- `TEXT_EMBEDDER_MODEL`: Text embedding model name
- `VISUAL_EMBEDDER_MODEL`: Visual embedding model name

### Health Checks

The `/ready` endpoint checks state availability:

```python
@router.get("/ready")
def ready() -> dict:
    state = get_state()
    if state.embeddings is None:
        raise HTTPException(status_code=503, detail="Embeddings not loaded")
    return {"status": "ready", "signals": state.signal_status}
```

## Troubleshooting

### Signals Not Loading

1. Check logs for signal loading status
2. Verify file paths exist
3. Check environment variables
4. Review `signal_status` in `/ready` endpoint

### Memory Issues

1. Reduce number of workers
2. Use shared memory for embeddings
3. Consider lazy loading for optional signals
4. Monitor memory usage per worker

## Best Practices

1. **Single worker for development**: Faster startup, easier debugging
2. **Multiple workers for production**: Better concurrency, but higher memory
3. **Check signal availability**: Always verify signals are loaded before use
4. **Graceful degradation**: Handle missing signals gracefully (return 0.0 similarity)
5. **Log signal status**: Log which signals are available at startup
