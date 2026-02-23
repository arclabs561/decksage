# DeckSage Docker Setup

Complete Docker Compose setup for running DeckSage as a service.

## ML Assets (Required Bind Mounts)

The following ML assets **must** be mounted as volumes:

### Required Assets

1. **Embeddings** (`EMBEDDINGS_PATH`)
   - **Volume**: `./data/embeddings:/app/data/embeddings:ro`
   - **Format**: Gensim KeyedVectors (`.wv` file)
   - **Contains**: Card embeddings for similarity search
   - **Example**: `magic_128d_test_pecanpy.wv`

2. **Graph Data** (`PAIRS_PATH`)
   - **Volume**: `./data/graphs:/app/data/graphs:ro`
   - **Format**: CSV with card pairs and weights
   - **Contains**: Jaccard similarity graph
   - **Example**: `pairs_large.csv`

3. **Card Attributes** (`ATTRIBUTES_PATH`)
   - **Volume**: `./data/attributes:/app/data/attributes:ro`
   - **Format**: CSV with card metadata
   - **Contains**: Type, mana cost, oracle text, functional tags
   - **Example**: `card_attrs.csv`

### Optional Assets

4. **Signals** (various paths)
   - **Volume**: `./data/signals:/app/data/signals:ro`
   - **Files**: `sideboard.json`, `temporal.json`, `gnn_graphsage.json`

## Quick Start

```bash
# 1. Prepare data structure
mkdir -p data/{embeddings,graphs,attributes,signals}

# 2. Place your ML assets in the directories above

# 3. Create .env file
cat > .env << EOL
EMBEDDINGS_PATH=/app/data/embeddings/model.wv
PAIRS_PATH=/app/data/graphs/pairs.csv
ATTRIBUTES_PATH=/app/data/attributes/card_attrs.csv
EOL

# 4. Start services
docker-compose up -d

# 5. Check health
curl http://localhost:8000/live
curl http://localhost:8000/ready
```

## Services

- **decksage-api**: Main API service (port 8000)
- **meilisearch**: Text search service (port 7700)
- **qdrant**: Vector search service (port 6333)

All services are on the `decksage-network` bridge network.

## Asset Version Tracking

### Creating Asset Metadata

Before deploying, create a metadata file that tracks which training/eval run produced each asset:

```bash
# Create asset metadata
python scripts/docker/create_asset_metadata.py \
    --embeddings data/embeddings/magic_128d_test_pecanpy.wv \
    --pairs data/graphs/pairs_large.csv \
    --attributes data/attributes/card_attrs.csv \
    --version v2026-W01 \
    --training-run experiments/training_run_v2026-W01.json \
    --eval-results experiments/evaluation_results/test_model_evaluation_v2026-W01.json \
    --output data/ASSET_METADATA.json
```

This creates `data/ASSET_METADATA.json` with:
- Version tag (e.g., `v2026-W01`)
- File hashes (SHA256) for integrity checking
- File sizes and modification dates
- Links to training run metadata
- Links to evaluation results (P@10, MRR, etc.)

### Version Format

Versions follow the format: `vYYYY-WWW` (e.g., `v2026-W01` for week 1 of 2026)

The API automatically:
- Extracts version from file paths (e.g., `model_v2026-W01.wv`)
- Loads asset metadata if `ASSET_METADATA_PATH` is set
- Includes version info in `/v1/diagnostics` and `/v1/similar` responses

### Viewing Asset Versions

```bash
# Check API diagnostics (includes asset version)
curl http://localhost:8000/v1/diagnostics | jq '.model_info.asset_version'

# Check specific asset metadata
cat data/ASSET_METADATA.json | jq '.version, .evaluation.p_at_10'
```

### Linking Training to Assets

The metadata file links assets to:
- **Training runs**: Training parameters, timestamps, model configs
- **Evaluation results**: P@10, MRR, test set used, evaluation date

This makes it clear which training run produced which assets and how they performed.
