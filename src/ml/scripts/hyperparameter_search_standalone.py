#!/usr/bin/env python3
"""
Standalone hyperparameter search script for AWS EC2 execution.

This script downloads data from S3, runs hyperparameter search, and uploads results.
Designed to run on EC2 without complex shell escaping.
"""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "pecanpy>=2.0.0",
#     "gensim>=4.3.0",
#     "boto3>=1.34.0",
# ]
# ///

import json
import sys
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple

try:
    import boto3
    import pandas as pd
    import numpy as np
    from gensim.models import Word2Vec, KeyedVectors
    from pecanpy.pecanpy import SparseOTF
    
    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    print(f"Missing dependencies: {e}")

# Import the hyperparameter search functions
# We'll inline them here to avoid import issues
def prepare_edgelist(csv_file: Path, output_edg: Path, min_cooccurrence: int = 2) -> TupleType[int, int]:
    """Convert pairs CSV to edgelist format."""
    df = pd.read_csv(csv_file)
    df = df[df["COUNT_SET"] >= min_cooccurrence]
    
    with open(output_edg, "w") as f:
        for _, row in df.iterrows():
            f.write(f"{row['NAME_1']}\t{row['NAME_2']}\t{row['COUNT_MULTISET']}\n")
    
    num_nodes = len(set(df["NAME_1"]) | set(df["NAME_2"]))
    return num_nodes, len(df)


def train_embedding(
    edgelist_file: Path,
    dim: int,
    walk_length: int,
    num_walks: int,
    window_size: int,
    p: float,
    q: float,
    epochs: int,
    workers: int = 4,
) -> KeyedVectors:
    """Train Node2Vec embedding with given hyperparameters."""
    g = SparseOTF(p=p, q=q, workers=workers, verbose=False, extend=True)
    g.read_edg(str(edgelist_file), weighted=True, directed=False)
    
    walks = g.simulate_walks(num_walks=num_walks, walk_length=walk_length)
    
    model = Word2Vec(
        walks,
        vector_size=dim,
        window=window_size,
        min_count=0,
        sg=1,
        workers=workers,
        epochs=epochs,
    )
    
    return model.wv


def evaluate_embedding(
    wv: KeyedVectors,
    test_set: dict,
    name_mapper: Optional[DictType[str, str]] = None,
    top_k: int = 10,
) -> DictType[str, float]:
    """Evaluate embedding on test set."""
    # Simple name mapper
    class NameMapper:
        def __init__(self, mapping=None):
            self.mapping = mapping or {}
        def map_name(self, name):
            return self.mapping.get(name, name)
        def map_names(self, names):
            return [self.mapping.get(n, n) for n in names]
    
    mapper = NameMapper(name_mapper) if name_mapper else None
    
    total_p_at_k = 0.0
    total_mrr = 0.0
    num_queries = 0
    
    for query, labels in test_set.items():
        # Map query name
        if mapper:
            query = mapper.map_name(query)
        
        if query not in wv:
            continue
        
        # Get all relevant cards
        all_relevant = set()
        for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
            cards = labels.get(level, [])
            if mapper:
                cards = mapper.map_names(cards)
            all_relevant.update(cards)
        
        if not all_relevant:
            continue
        
        # Get predictions
        try:
            similar = wv.most_similar(query, topn=top_k * 2)
            predictions = [card for card, _ in similar if card in wv][:top_k]
        except KeyError:
            continue
        
        # Calculate P@K
        hits = sum(1 for pred in predictions if pred in all_relevant)
        p_at_k = hits / min(top_k, len(predictions)) if predictions else 0.0
        
        # Calculate MRR
        mrr = 0.0
        for rank, pred in enumerate(predictions, 1):
            if pred in all_relevant:
                mrr = 1.0 / rank
                break
        
        total_p_at_k += p_at_k
        total_mrr += mrr
        num_queries += 1
    
    if num_queries == 0:
        return {"p@10": 0.0, "mrr": 0.0, "num_queries": 0}
    
    return {
        "p@10": total_p_at_k / num_queries,
        "mrr": total_mrr / num_queries,
        "num_queries": num_queries,
    }


def grid_search(
    edgelist_file: Path,
    test_set: dict,
    name_mapper: Optional[DictType[str, str]] = None,
    max_configs: int = 50,
) -> DictType[str, Any]:
    """Grid search over hyperparameters."""
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Focused search space
    p_values = [0.5, 1.0, 2.0]
    q_values = [0.5, 1.0, 2.0]
    dim_values = [128, 256]
    walk_length_values = [80, 120]
    num_walks_values = [10, 20]
    epochs_values = [1, 5]
    
    results = []
    config_num = 0
    
    logger.info("Starting grid search...")
    total_configs = len(p_values) * len(q_values) * len(dim_values) * len(walk_length_values) * len(num_walks_values) * len(epochs_values)
    logger.info(f"Search space: {total_configs} configs (testing up to {max_configs})")
    
    # Prepare edgelist once
    work_dir = Path("/tmp/hyperparam_search")
    work_dir.mkdir(exist_ok=True)
    edg_file = work_dir / "graph.edg"
    prepare_edgelist(edgelist_file, edg_file)
    
    for p in p_values:
        for q in q_values:
            for dim in dim_values:
                for walk_length in walk_length_values:
                    for num_walks in num_walks_values:
                        for epochs in epochs_values:
                            config_num += 1
                            
                            if config_num > max_configs:
                                logger.info(f"Reached max_configs ({max_configs}), stopping search")
                                break
                            
                            logger.info(f"\n[{config_num}] Testing: p={p}, q={q}, dim={dim}, walk={walk_length}, walks={num_walks}, epochs={epochs}")
                            
                            try:
                                # Train
                                wv = train_embedding(
                                    edg_file,
                                    dim=dim,
                                    walk_length=walk_length,
                                    num_walks=num_walks,
                                    window_size=10,
                                    p=p,
                                    q=q,
                                    epochs=epochs,
                                )
                                
                                # Evaluate
                                metrics = evaluate_embedding(wv, test_set, name_mapper)
                                
                                result = {
                                    "config": {
                                        "p": p,
                                        "q": q,
                                        "dim": dim,
                                        "walk_length": walk_length,
                                        "num_walks": num_walks,
                                        "epochs": epochs,
                                    },
                                    "metrics": metrics,
                                }
                                
                                results.append(result)
                                
                                logger.info(f"  P@10: {metrics['p@10']:.4f}, MRR: {metrics['mrr']:.4f}, Queries: {metrics['num_queries']}")
                                
                            except Exception as e:
                                logger.error(f"  Error: {e}")
                                continue
                        
                        if config_num > max_configs:
                            break
                    if config_num > max_configs:
                        break
                if config_num > max_configs:
                    break
            if config_num > max_configs:
                break
        if config_num > max_configs:
            break
    
    # Find best
    if not results:
        return {"error": "No successful configurations"}
    
    best = max(results, key=lambda x: x["metrics"]["p@10"])
    
    return {
        "best_config": best["config"],
        "best_metrics": best["metrics"],
        "all_results": results,
        "summary": {
            "total_configs": len(results),
            "best_p@10": best["metrics"]["p@10"],
            "best_mrr": best["metrics"]["mrr"],
        },
    }


def main() -> int:
    """Run hyperparameter search."""
    if not HAS_DEPS:
        print("❌ Missing dependencies")
        return 1
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Hyperparameter search for Node2Vec")
    parser.add_argument("--input", type=str, required=True, help="Pairs CSV")
    parser.add_argument("--test-set", type=str, required=True, help="Test set JSON")
    parser.add_argument("--name-mapping", type=str, help="Name mapping JSON")
    parser.add_argument("--output", type=str, default="results.json", help="Output JSON")
    parser.add_argument("--max-configs", type=int, default=50, help="Max configurations")
    
    args = parser.parse_args()
    
    # Load test set
    with open(args.test_set) as f:
        test_data = json.load(f)
        test_set = test_data.get("queries", test_data)
    
    # Load name mapping
    name_mapper = None
    if args.name_mapping:
        with open(args.name_mapping) as f:
            mapping_data = json.load(f)
            name_mapper = mapping_data.get("mapping", {})
    
    # Run grid search
    results = grid_search(
        Path(args.input),
        test_set,
        name_mapper,
        max_configs=args.max_configs,
    )
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Search complete!")
    print(f"📊 Results saved to {output_path}")
    
    if "best_config" in results:
        print(f"\n🏆 Best Configuration:")
        for key, value in results["best_config"].items():
            print(f"  {key}: {value}")
        print(f"\n📈 Best Metrics:")
        print(f"  P@10: {results['best_metrics']['p@10']:.4f}")
        print(f"  MRR: {results['best_metrics']['mrr']:.4f}")
    
    # Upload to S3 if on EC2
    try:
        s3 = boto3.client("s3")
        bucket = "games-collections"
        s3_key = "experiments/hyperparameter_search_results.json"
        s3.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=json.dumps(results, indent=2),
            ContentType="application/json",
        )
        print(f"✅ Uploaded to s3://{bucket}/{s3_key}")
    except Exception as e:
        print(f"⚠️  Could not upload to S3: {e}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

