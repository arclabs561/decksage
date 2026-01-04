#!/usr/bin/env python3
"""
Create model cards for all ML artifacts in S3.

Model cards follow modern best practices:
- Model details (type, version, date)
- Training data and methodology
- Performance metrics
- Intended use and limitations
- Ethical considerations
- Usage instructions
"""

# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.34.0",
# ]
# ///

import json
from datetime import UTC, datetime
from typing import Any

import boto3


S3_BUCKET = "games-collections"
S3_PREFIX = "model-cards/"


def create_embedding_model_card(
    name: str,
    method: str,
    dimensions: int,
    training_data: str,
    performance: dict[str, Any] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Create a model card for an embedding model."""
    return {
        "model_details": {
            "name": name,
            "type": "graph_embedding",
            "method": method,
            "dimensions": dimensions,
            "version": "1.0.0",
            "date": datetime.now(UTC).isoformat(),
        },
        "training": {
            "data_source": training_data,
            "data_size": "See training_data field",
            "methodology": f"{method} algorithm for learning node embeddings from co-occurrence graphs",
            "hyperparameters": {
                "dimensions": dimensions,
                "method_specific": "See training script for full hyperparameters",
            },
        },
        "performance": performance
        or {
            "metrics": "P@10, MRR (see evaluation results)",
            "baseline_comparison": "Compared against Jaccard similarity",
        },
        "intended_use": {
            "primary_use": "Card similarity search and recommendation",
            "use_cases": [
                "Finding similar cards based on deck co-occurrence",
                "Deck completion suggestions",
                "Contextual card discovery",
            ],
            "out_of_scope": [
                "Price prediction",
                "Tournament outcome prediction",
                "Card legality checking (use format rules)",
            ],
        },
        "limitations": [
            "Embeddings reflect historical deck co-occurrence patterns",
            "May not capture recent meta shifts without retraining",
            "Quality depends on training data coverage",
        ],
        "usage": {
            "load_command": f"from gensim.models import KeyedVectors; model = KeyedVectors.load('{name}.wv')",
            "similarity_example": "model.most_similar('CardName', topn=10)",
            "s3_location": f"s3://{S3_BUCKET}/embeddings/{name}.wv",
        },
        "notes": notes,
    }


def create_signal_model_card(
    name: str,
    signal_type: str,
    description: str,
    computation_method: str,
    data_source: str,
    performance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a model card for a similarity signal."""
    return {
        "model_details": {
            "name": name,
            "type": "similarity_signal",
            "signal_type": signal_type,
            "version": "1.0.0",
            "date": datetime.now(UTC).isoformat(),
        },
        "description": description,
        "computation": {
            "method": computation_method,
            "data_source": data_source,
            "frequency": "Pre-computed and cached",
        },
        "performance": performance
        or {
            "metrics": "Integrated into fusion similarity (see fusion weights)",
        },
        "intended_use": {
            "primary_use": "Component of multi-modal similarity fusion",
            "use_cases": [
                "Card similarity search",
                "Deck completion",
                "Contextual discovery",
            ],
        },
        "limitations": [
            "Signal quality depends on data coverage",
            "May require periodic recomputation as new data arrives",
        ],
        "usage": {
            "s3_location": f"s3://{S3_BUCKET}/signals/{name}.json",
            "load_example": "See src/ml/api/load_signals.py",
        },
    }


def upload_model_card(s3_client: Any, card: dict[str, Any], filename: str) -> None:
    """Upload a model card to S3."""
    key = f"{S3_PREFIX}{filename}"
    content = json.dumps(card, indent=2, ensure_ascii=False)
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="application/json",
    )
    print(f"✓ Uploaded {key}")


def main() -> None:
    """Create and upload model cards for all artifacts."""
    s3_client = boto3.client("s3")

    # Embedding model cards
    embeddings = [
        {
            "name": "magic_128d_test_pecanpy",
            "method": "Node2Vec (PecanPy)",
            "dimensions": 128,
            "training_data": "pairs_large.csv (tournament deck co-occurrence)",
            "performance": {
                "p_at_10": "See evaluation results",
                "mrr": "See evaluation results",
                "training_date": "2025-12-03",
            },
            "notes": "Primary embedding model for Magic: The Gathering. Trained on AWS EC2 spot instance.",
        },
        {
            "name": "node2vec_default",
            "method": "Node2Vec (default p=1, q=1)",
            "dimensions": 128,
            "training_data": "pairs_large.csv",
            "notes": "Baseline Node2Vec with unbiased random walks.",
        },
        {
            "name": "node2vec_bfs",
            "method": "Node2Vec (BFS-biased, p=0.25, q=4)",
            "dimensions": 128,
            "training_data": "pairs_large.csv",
            "notes": "BFS-biased walks for local neighborhood exploration.",
        },
        {
            "name": "node2vec_dfs",
            "method": "Node2Vec (DFS-biased, p=4, q=0.25)",
            "dimensions": 128,
            "training_data": "pairs_large.csv",
            "notes": "DFS-biased walks for global structure exploration.",
        },
        {
            "name": "deepwalk",
            "method": "DeepWalk",
            "dimensions": 128,
            "training_data": "pairs_large.csv",
            "notes": "DeepWalk baseline (uniform random walks).",
        },
    ]

    for emb in embeddings:
        card = create_embedding_model_card(**emb)
        filename = f"embeddings/{emb['name']}.json"
        upload_model_card(s3_client, card, filename)

    # Signal model cards
    signals = [
        {
            "name": "sideboard_cooccurrence",
            "signal_type": "sideboard_pattern",
            "description": "Card co-occurrence patterns in sideboards",
            "computation_method": "Count co-occurrences in sideboards, normalize by card frequencies",
            "data_source": "decks_with_metadata.jsonl",
        },
        {
            "name": "temporal_cooccurrence",
            "signal_type": "temporal_trend",
            "description": "Monthly co-occurrence trends over time",
            "computation_method": "Time-series analysis of deck co-occurrence by month",
            "data_source": "decks_with_metadata.jsonl",
        },
        {
            "name": "archetype_staples",
            "signal_type": "archetype_analysis",
            "description": "Archetype staple cards and inclusion rates",
            "computation_method": "Aggregate card inclusion rates by archetype",
            "data_source": "decks_with_metadata.jsonl",
        },
        {
            "name": "archetype_cooccurrence",
            "signal_type": "archetype_pattern",
            "description": "Card co-occurrence within archetypes",
            "computation_method": "Count co-occurrences within same archetype",
            "data_source": "decks_with_metadata.jsonl",
        },
        {
            "name": "format_cooccurrence",
            "signal_type": "format_pattern",
            "description": "Card co-occurrence within formats",
            "computation_method": "Count co-occurrences within same format",
            "data_source": "decks_with_metadata.jsonl",
        },
        {
            "name": "cross_format_patterns",
            "signal_type": "cross_format_analysis",
            "description": "Patterns that appear across multiple formats",
            "computation_method": "Identify cards that co-occur across formats",
            "data_source": "decks_with_metadata.jsonl",
        },
    ]

    for sig in signals:
        card = create_signal_model_card(**sig)
        filename = f"signals/{sig['name']}.json"
        upload_model_card(s3_client, card, filename)

    # Create README for model-cards directory
    readme = {
        "title": "DeckSage Model Cards",
        "description": "Model cards for all ML artifacts in the DeckSage project",
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "structure": {
            "embeddings/": "Graph embedding models (Node2Vec, DeepWalk variants)",
            "signals/": "Similarity signals (sideboard, temporal, archetype, format)",
        },
        "usage": {
            "view_model_card": "Download JSON from s3://games-collections/model-cards/{category}/{name}.json",
            "list_all": "aws s3 ls s3://games-collections/model-cards/ --recursive",
        },
        "standards": {
            "format": "JSON",
            "schema": "Based on Model Cards for Model Reporting (Google Research)",
            "version": "1.0.0",
        },
    }

    readme_content = json.dumps(readme, indent=2, ensure_ascii=False)
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=f"{S3_PREFIX}README.json",
        Body=readme_content.encode("utf-8"),
        ContentType="application/json",
    )
    print(f"✓ Uploaded {S3_PREFIX}README.json")

    print("\n✓ All model cards created and uploaded")


if __name__ == "__main__":
    main()
