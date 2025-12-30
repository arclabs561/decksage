#!/usr/bin/env python3
"""
Comprehensive Fix and Measurement Script

This script:
1. Checks what data/models are available
2. Measures individual signal performance (Jaccard, Functional, Embed)
3. Reports what's missing and what can be fixed
4. Provides actionable next steps

Think calmly and mindfully - systematic approach.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    # Fallback for basic operations
    class np:
        @staticmethod
        def mean(x):
            return sum(x) / len(x) if x else 0.0
        @staticmethod
        def std(x):
            if not x:
                return 0.0
            m = sum(x) / len(x)
            return (sum((v - m) ** 2 for v in x) / len(x)) ** 0.5
        @staticmethod
        def percentile(x, p):
            if not x:
                return 0.0
            sorted_x = sorted(x)
            idx = int(len(sorted_x) * p / 100)
            return sorted_x[min(idx, len(sorted_x) - 1)]
        @staticmethod
        def random():
            import random
            return random

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Import paths
from ..utils.paths import PATHS

# Try to import dependencies
try:
    from gensim.models import KeyedVectors
    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False
    KeyedVectors = None

try:
    from ..similarity.similarity_methods import load_graph, jaccard_similarity
    HAS_SIMILARITY = True
except ImportError:
    HAS_SIMILARITY = False
    load_graph = None
    jaccard_similarity = None

try:
    from ..enrichment.card_functional_tagger import FunctionalTagger
    HAS_TAGGER = True
except ImportError:
    HAS_TAGGER = False
    FunctionalTagger = None

try:
    from ..similarity.fusion import WeightedLateFusion, FusionWeights
    HAS_FUSION = True
except ImportError:
    HAS_FUSION = False


def check_file_exists(path: Path, description: str) -> tuple[bool, Optional[str]]:
    """Check if file exists and return status."""
    if path.exists():
        size = path.stat().st_size
        return True, f"{size:,} bytes"
    return False, None


def precision_at_k(predictions: list[str], labels: dict[str, list[str]], k: int = 10) -> float:
    """Compute weighted precision at k from test set labels."""
    if not predictions:
        return 0.0
    
    top_k = predictions[:k]
    score = 0.0
    
    # Weighted relevance levels
    weights = {
        "highly_relevant": 1.0,
        "relevant": 0.8,
        "somewhat_relevant": 0.5,
        "marginally_relevant": 0.2,
        "irrelevant": 0.0,
    }
    
    for pred in top_k:
        for level, weight in weights.items():
            if pred in labels.get(level, []):
                score += weight
                break
    
    return score / k


def measure_signal(
    test_set: dict[str, Any],
    signal_name: str,
    similarity_fn: Callable[[str, int], list[tuple[str, float]]],
    top_k: int = 10,
) -> dict[str, Any]:
    """Measure P@10 for a single signal."""
    queries = test_set.get("queries", test_set)
    scores = []
    
    for query, labels in queries.items():
        try:
            predictions_with_scores = similarity_fn(query, top_k)
            predictions = [card for card, _ in predictions_with_scores]
            p_at_k = precision_at_k(predictions, labels, k=top_k)
            scores.append(p_at_k)
        except Exception as e:
            logger.warning(f"  Query '{query}' failed: {e}")
            scores.append(0.0)
    
    if not scores:
        return {
            "signal": signal_name,
            "mean_p_at_k": 0.0,
            "n_queries": 0,
            "status": "no_data",
        }
    
    mean_p = float(np.mean(scores))
    std_p = float(np.std(scores))
    
    # Bootstrap CI
    if HAS_NUMPY:
        n_bootstrap = 1000
        bootstrap_means = []
        for _ in range(n_bootstrap):
            sample = np.random.choice(scores, size=len(scores), replace=True)
            bootstrap_means.append(np.mean(sample))
        
        ci_lower = float(np.percentile(bootstrap_means, 2.5))
        ci_upper = float(np.percentile(bootstrap_means, 97.5))
    else:
        # Simple approximation without numpy
        import random
        n_bootstrap = 100
        bootstrap_means = []
        for _ in range(n_bootstrap):
            sample = [random.choice(scores) for _ in scores]
            bootstrap_means.append(sum(sample) / len(sample))
        
        sorted_means = sorted(bootstrap_means)
        ci_lower = float(sorted_means[int(len(sorted_means) * 0.025)])
        ci_upper = float(sorted_means[int(len(sorted_means) * 0.975)])
    
    return {
        "signal": signal_name,
        "mean_p_at_k": mean_p,
        "std": std_p,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "n_queries": len(scores),
        "status": "success",
    }


def create_jaccard_similarity_fn(adj: dict[str, set[str]]) -> Callable[[str, int], list[tuple[str, float]]]:
    """Create Jaccard similarity function from adjacency."""
    if not HAS_SIMILARITY:
        def jaccard_fn(query: str, k: int) -> list[tuple[str, float]]:
            return []
        return jaccard_fn
    
    def jaccard_fn(query: str, k: int) -> list[tuple[str, float]]:
        return jaccard_similarity(query, adj, top_k=k, filter_lands=True)
    
    return jaccard_fn


def create_embedding_similarity_fn(embeddings: Any) -> Callable[[str, int], list[tuple[str, float]]]:
    """Create embedding similarity function."""
    def embed_fn(query: str, k: int) -> list[tuple[str, float]]:
        if not embeddings:
            return []
        try:
            similar = embeddings.most_similar(query, topn=k)
            return [(card, float(sim)) for card, sim in similar]
        except KeyError:
            return []
        except Exception as e:
            logger.warning(f"Embedding similarity failed for '{query}': {e}")
            return []
    
    return embed_fn


def create_functional_similarity_fn(tagger: Any, adj: dict[str, set[str]]) -> Callable[[str, int], list[tuple[str, float]]]:
    """Create functional tag similarity function."""
    def functional_fn(query: str, k: int) -> list[tuple[str, float]]:
        if not tagger:
            return []
        
        try:
            query_tags = tagger.tag_card(query)
            if not query_tags:
                return []
            
            query_tag_set = set(query_tags.tags if hasattr(query_tags, 'tags') else [])
            
            # Compare with neighbors
            if query not in adj:
                return []
            
            candidates = list(adj[query])[:100]  # Limit candidates
            scored = []
            
            for candidate in candidates:
                try:
                    cand_tags = tagger.tag_card(candidate)
                    if not cand_tags:
                        continue
                    
                    cand_tag_set = set(cand_tags.tags if hasattr(cand_tags, 'tags') else [])
                    
                    # Jaccard on tags
                    intersection = len(query_tag_set & cand_tag_set)
                    union = len(query_tag_set | cand_tag_set)
                    similarity = intersection / union if union > 0 else 0.0
                    
                    scored.append((candidate, similarity))
                except Exception:
                    continue
            
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:k]
        except Exception as e:
            logger.warning(f"Functional similarity failed for '{query}': {e}")
            return []
    
    return functional_fn


def main() -> int:
    """Main execution."""
    logger.info("=" * 70)
    logger.info("Comprehensive Fix and Measurement Script")
    logger.info("=" * 70)
    logger.info("")
    
    # Step 1: Check what's available
    logger.info("Step 1: Checking available data and models...")
    logger.info("")
    
    status = {
        "test_set": False,
        "pairs_csv": False,
        "embeddings": False,
        "tagger": False,
        "decks_metadata": False,
    }
    
    # Check test set
    test_set_path = PATHS.test_magic
    test_set_exists, test_set_info = check_file_exists(test_set_path, "Test set")
    status["test_set"] = test_set_exists
    logger.info(f"  Test set: {'✅' if test_set_exists else '❌'} {test_set_path}")
    if test_set_exists:
        logger.info(f"    Size: {test_set_info}")
    
    # Check pairs CSV
    pairs_paths = [
        PATHS.pairs_large,
        Path("data/processed/pairs_large.csv"),
        Path("src/backend/pairs_large.csv"),
    ]
    pairs_csv = None
    for path in pairs_paths:
        exists, info = check_file_exists(path, "Pairs CSV")
        if exists:
            pairs_csv = path
            status["pairs_csv"] = True
            logger.info(f"  Pairs CSV: ✅ {path}")
            logger.info(f"    Size: {info}")
            break
    if not pairs_csv:
        logger.info(f"  Pairs CSV: ❌ Not found (tried: {[str(p) for p in pairs_paths]})")
    
    # Check embeddings
    embed_paths = [
        PATHS.embeddings / "magic_128d_pecanpy.wv",
        PATHS.embeddings / "magic_64d_pecanpy.wv",
        Path("data/embeddings/magic_128d_pecanpy.wv"),
    ]
    embeddings = None
    embeddings_path = None
    for path in embed_paths:
        exists, info = check_file_exists(path, "Embeddings")
        if exists and HAS_GENSIM:
            try:
                embeddings = KeyedVectors.load(str(path))
                embeddings_path = path
                status["embeddings"] = True
                logger.info(f"  Embeddings: ✅ {path}")
                logger.info(f"    Cards: {len(embeddings):,}, Dim: {embeddings.vector_size}")
                break
            except Exception as e:
                logger.warning(f"  Failed to load {path}: {e}")
    if not embeddings:
        logger.info(f"  Embeddings: ❌ Not found or not loadable")
        if not HAS_GENSIM:
            logger.info(f"    (gensim not installed)")
    
    # Check tagger
    tagger = None
    if HAS_TAGGER and FunctionalTagger:
        try:
            tagger = FunctionalTagger()
            status["tagger"] = True
            logger.info(f"  Functional Tagger: ✅ Available")
        except Exception as e:
            logger.warning(f"  Functional Tagger: ⚠️ Failed to initialize: {e}")
    else:
        logger.info(f"  Functional Tagger: ❌ Not available")
    
    # Check decks metadata
    decks_metadata_path = PATHS.decks_with_metadata
    decks_metadata_exists, decks_metadata_info = check_file_exists(decks_metadata_path, "Decks metadata")
    status["decks_metadata"] = decks_metadata_exists
    logger.info(f"  Decks metadata: {'✅' if decks_metadata_exists else '❌'} {decks_metadata_path}")
    if decks_metadata_exists:
        logger.info(f"    Size: {decks_metadata_info}")
    
    logger.info("")
    
    # Step 2: Load test set
    if not test_set_exists:
        logger.error("❌ Test set not found. Cannot proceed with measurement.")
        return 1
    
    logger.info("Step 2: Loading test set...")
    with open(test_set_path) as f:
        test_set = json.load(f)
    
    queries = test_set.get("queries", test_set)
    logger.info(f"  Loaded {len(queries)} queries")
    logger.info("")
    
    # Step 3: Load graph if available
    adj = {}
    if pairs_csv and HAS_SIMILARITY:
        logger.info("Step 3: Loading graph...")
        try:
            adj, weights = load_graph(str(pairs_csv), filter_lands=True)
            logger.info(f"  Loaded graph: {len(adj):,} cards, {len(weights):,} edges")
        except Exception as e:
            logger.warning(f"  Failed to load graph: {e}")
    else:
        logger.info("Step 3: Skipping graph (not available)")
    logger.info("")
    
    # Step 4: Measure individual signals
    logger.info("Step 4: Measuring individual signal performance...")
    logger.info("")
    
    results = {
        "test_set": str(test_set_path),
        "n_queries": len(queries),
        "signals": [],
        "status": status,
    }
    
    # Measure Jaccard
    if adj:
        logger.info("  Measuring Jaccard similarity...")
        jaccard_fn = create_jaccard_similarity_fn(adj)
        jaccard_result = measure_signal(test_set, "jaccard", jaccard_fn)
        results["signals"].append(jaccard_result)
        logger.info(f"    P@10: {jaccard_result['mean_p_at_k']:.4f} (95% CI: [{jaccard_result['ci_lower']:.4f}, {jaccard_result['ci_upper']:.4f}])")
    else:
        logger.info("  Jaccard: ❌ Skipped (no graph data)")
        results["signals"].append({"signal": "jaccard", "status": "missing_data"})
    
    # Measure Embedding
    if embeddings:
        logger.info("  Measuring Embedding similarity...")
        embed_fn = create_embedding_similarity_fn(embeddings)
        embed_result = measure_signal(test_set, "embed", embed_fn)
        results["signals"].append(embed_result)
        logger.info(f"    P@10: {embed_result['mean_p_at_k']:.4f} (95% CI: [{embed_result['ci_lower']:.4f}, {embed_result['ci_upper']:.4f}])")
    else:
        logger.info("  Embedding: ❌ Skipped (no embeddings)")
        results["signals"].append({"signal": "embed", "status": "missing_data"})
    
    # Measure Functional
    if tagger:
        logger.info("  Measuring Functional tag similarity...")
        functional_fn = create_functional_similarity_fn(tagger, adj)
        functional_result = measure_signal(test_set, "functional", functional_fn)
        results["signals"].append(functional_result)
        logger.info(f"    P@10: {functional_result['mean_p_at_k']:.4f} (95% CI: [{functional_result['ci_lower']:.4f}, {functional_result['ci_upper']:.4f}])")
    else:
        logger.info("  Functional: ❌ Skipped (no tagger)")
        results["signals"].append({"signal": "functional", "status": "missing_data"})
    
    logger.info("")
    
    # Step 5: Compare to fusion baseline
    logger.info("Step 5: Comparing to fusion baseline...")
    fusion_baseline = 0.088  # From fusion_grid_search_latest.json
    jaccard_baseline = 0.089  # From CURRENT_BEST_magic.json
    
    logger.info(f"  Fusion baseline: P@10 = {fusion_baseline:.4f}")
    logger.info(f"  Jaccard baseline: P@10 = {jaccard_baseline:.4f}")
    logger.info("")
    
    # Find best individual signal
    available_signals = [r for r in results["signals"] if r.get("status") == "success"]
    if available_signals:
        best_signal = max(available_signals, key=lambda x: x.get("mean_p_at_k", 0.0))
        logger.info(f"  Best individual signal: {best_signal['signal']} (P@10 = {best_signal['mean_p_at_k']:.4f})")
        
        if best_signal['mean_p_at_k'] > fusion_baseline:
            logger.info(f"  ✅ Individual signal beats fusion baseline!")
        else:
            logger.info(f"  ⚠️ Individual signal below fusion baseline")
    logger.info("")
    
    # Step 6: Save results
    output_path = PATHS.experiments / "signal_performance_measurement.json"
    logger.info(f"Step 6: Saving results to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"  ✅ Saved")
    logger.info("")
    
    # Step 7: Recommendations
    logger.info("Step 7: Recommendations...")
    logger.info("")
    
    if not status["embeddings"]:
        logger.info("  🔴 CRITICAL: Train embeddings")
        logger.info("     Run: uv run python -m src.ml.similarity.card_similarity_pecan \\")
        logger.info("       --input <pairs_csv> --output magic_128d --dim 128")
        logger.info("")
    
    if not status["pairs_csv"]:
        logger.info("  🔴 CRITICAL: Pairs CSV missing - cannot compute signals")
        logger.info("     Need to export graph from backend")
        logger.info("")
    
    if not status["decks_metadata"]:
        logger.info("  🟡 IMPORTANT: Decks metadata missing - cannot compute sideboard/temporal/archetype signals")
        logger.info("     Need: data/processed/decks_with_metadata.jsonl")
        logger.info("")
    
    if status["embeddings"] and status["pairs_csv"] and status["tagger"]:
        logger.info("  ✅ All core data available - can measure all signals")
        logger.info("  ✅ Can proceed with fusion weight optimization")
        logger.info("")
    
    logger.info("=" * 70)
    logger.info("Measurement complete!")
    logger.info("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

