#!/usr/bin/env python3
"""
Consolidated Similarity Methods (User Principle: Best code is no code)

Instead of re-implementing Jaccard in every experiment,
centralize all similarity methods here.
"""

from collections import defaultdict

import numpy as np
import pandas as pd


# Reusable land filter (mentioned in 3+ experiments)
LANDS = {
    "Plains",
    "Island",
    "Swamp",
    "Mountain",
    "Forest",
    "Flooded Strand",
    "Polluted Delta",
    "Scalding Tarn",
    "Misty Rainforest",
    "Verdant Catacombs",
    "Marsh Flats",
    "Bloodstained Mire",
    "Wooded Foothills",
    "Windswept Heath",
    "Arid Mesa",
    "Command Tower",
    "City of Brass",
}


def load_graph(csv_path=None, graph_db=None, game=None, filter_lands=True):
    """
    Load co-occurrence graph from graph database (preferred) or CSV (fallback).

    Returns: adjacency dict, edge weights dict

    Caching: parsed CSV results are cached as .pkl next to the source file.
    The cache is invalidated when the CSV is newer than the pickle.

    Args:
        csv_path: Path to pairs CSV (legacy option)
        graph_db: Path to incremental graph database (SQLite .db) - preferred
        game: Filter by game ("MTG", "PKM", "YGO")
        filter_lands: Filter out basic lands (Magic only)
    """
    import logging
    import os
    from pathlib import Path

    from ..utils.paths import PATHS

    _logger = logging.getLogger(__name__)

    # Try graph database first (preferred), but only if csv_path not explicitly provided
    use_graph_db = csv_path is None

    if use_graph_db:
        if graph_db is None:
            graph_db = PATHS.incremental_graph_db

        if graph_db and Path(graph_db).exists():
            try:
                from ..utils.shared_operations import load_graph_for_jaccard

                adj = load_graph_for_jaccard(graph_db=Path(graph_db), game=game)
                weights = {}
                for c1 in adj:
                    for c2 in adj[c1]:
                        if filter_lands and game == "MTG" and (c1 in LANDS or c2 in LANDS):
                            continue
                        key = tuple(sorted([c1, c2]))
                        weights[key] = weights.get(key, 0) + 1
                        weights[(c1, c2)] = weights.get((c1, c2), 0) + 1
                        weights[(c2, c1)] = weights.get((c2, c1), 0) + 1
                return adj, weights
            except Exception as e:
                import warnings

                warnings.warn(
                    f"Could not load from graph database: {e}, falling back to CSV",
                    stacklevel=2,
                )

    # Resolve CSV path
    if csv_path is None:
        csv_path = str(PATHS.pairs_large)

    if not os.path.exists(csv_path):
        if PATHS.pairs_large.exists():
            csv_path = str(PATHS.pairs_large)
        else:
            alternatives = [
                str(PATHS.pairs_500),
                "data/processed/pairs_large.csv",
            ]
            for alt in alternatives:
                if os.path.exists(alt):
                    csv_path = alt
                    break
            else:
                raise FileNotFoundError(
                    f"Could not find pairs CSV. Tried: {[csv_path, *alternatives]}"
                )

    csv_p = Path(csv_path)
    cache_suffix = f".{game}.pkl" if game else ".pkl"
    cache_path = csv_p.with_suffix(csv_p.suffix + cache_suffix)

    # Use pickle cache if it exists and is newer than the CSV.
    # Pickle is used over msgpack because the graph has 14M weight entries with
    # repeated card name strings -- pickle's object reference sharing makes the
    # cache 3x smaller and 3x faster to load (281MB/3s vs 714MB/12s for Magic).
    if cache_path.exists() and cache_path.stat().st_mtime >= csv_p.stat().st_mtime:
        _logger.debug("Loading graph from cache: %s", cache_path)
        try:
            import pickle

            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            return cached["adj"], cached["weights"]
        except Exception as exc:
            _logger.warning(
                "Corrupt graph cache %s (%s); deleting and rebuilding from CSV",
                cache_path, exc,
            )
            try:
                cache_path.unlink()
            except OSError:
                pass

    # Parse CSV (slow path)
    df = pd.read_csv(csv_path)

    adj = defaultdict(set)
    weights = {}

    for _, row in df.iterrows():
        c1, c2 = str(row["NAME_1"]).strip(), str(row["NAME_2"]).strip()

        if filter_lands and (c1 in LANDS or c2 in LANDS):
            continue

        adj[c1].add(c2)
        adj[c2].add(c1)

        weights[(c1, c2)] = row.get("COUNT_MULTISET", 1)
        weights[(c2, c1)] = row.get("COUNT_MULTISET", 1)

    adj = dict(adj)

    # Write pickle cache for next startup
    try:
        import pickle

        with open(cache_path, "wb") as f:
            pickle.dump({"adj": adj, "weights": weights}, f, protocol=5)
        _logger.info("Wrote graph cache: %s (%.1f MB)", cache_path, cache_path.stat().st_size / 1e6)
    except OSError:
        _logger.debug("Could not write graph cache: %s", cache_path, exc_info=True)

    return adj, weights


def load_card_attributes_csv(csv_path: str):
    """Load card attributes CSV with columns: NAME, CMC, TYPE_LINE.

    Returns: dict[name] -> {"cmc": float, "type_line": str, "types": set[str]}
    """
    df = pd.read_csv(csv_path)
    attrs = {}
    for _, row in df.iterrows():
        name = row["NAME"]
        cmc = float(row.get("CMC", 0) or 0)
        type_line = str(row.get("TYPE_LINE", "") or "")
        types = {t.strip() for t in type_line.split() if t.strip()}
        attrs[name] = {"cmc": cmc, "type_line": type_line, "types": types}
    return attrs


def jaccard_similarity_faceted(query, adj, attrs: dict, facet: str = "type", top_k: int = 10):
    """Facet-aware Jaccard: restrict candidate set to same facet as query.

    facet: "type" (overlap in TYPE_LINE tokens) or "cmc" (same integer CMC)
    """
    if query not in adj:
        return []

    qattr = attrs.get(query)
    if not qattr:
        # Fall back to standard Jaccard
        return jaccard_similarity(query, adj, top_k=top_k, filter_lands=True)

    # Build candidate set respecting facet
    candidates = []
    if facet == "type":
        qtypes = qattr.get("types", set())
        if not qtypes:
            return jaccard_similarity(query, adj, top_k=top_k, filter_lands=True)
        for other in adj:
            if other == query:
                continue
            otypes = attrs.get(other, {}).get("types", set())
            if qtypes & otypes:
                candidates.append(other)
    elif facet == "cmc":
        qcmc = int(qattr.get("cmc", 0) or 0)
        for other in adj:
            if other == query:
                continue
            ocmc = int(attrs.get(other, {}).get("cmc", 0) or 0)
            if ocmc == qcmc:
                candidates.append(other)
    else:
        return jaccard_similarity(query, adj, top_k=top_k, filter_lands=True)

    if not candidates:
        return []

    neighbors = adj[query]
    sims = []
    for other in candidates:
        other_n = adj[other]
        inter = len(neighbors & other_n)
        union = len(neighbors | other_n)
        if union > 0:
            sims.append((other, inter / union))
    sims.sort(key=lambda x: x[1], reverse=True)
    return sims[:top_k]


def jaccard_similarity(query, adj, top_k=10, filter_lands=True):
    """
    Standard Jaccard similarity.

    User principle: This is simple, works, keep it.
    """
    if query not in adj:
        return []

    neighbors = adj[query]
    sims = []

    for other in adj:
        if other == query:
            continue

        other_n = adj[other]
        intersection = len(neighbors & other_n)
        union = len(neighbors | other_n)

        if union > 0:
            sims.append((other, intersection / union))

    sims.sort(key=lambda x: x[1], reverse=True)
    return sims[:top_k]


def weighted_jaccard(query, adj, weights, top_k=10):
    """
    Jaccard weighted by edge strength.

    From exp_035: Uses co-occurrence count as signal.
    """
    if query not in adj:
        return []

    neighbors = adj[query]
    sims = []

    for other in adj:
        if other == query or other in LANDS:
            continue

        other_n = adj[other]

        # Weighted intersection/union
        intersection_weight = sum(
            weights.get((query, n), 0) + weights.get((other, n), 0) for n in neighbors & other_n
        )
        union_weight = sum(
            weights.get((query, n), 0) + weights.get((other, n), 0) for n in neighbors | other_n
        )

        if union_weight > 0:
            sims.append((other, intersection_weight / union_weight))

    sims.sort(key=lambda x: x[1], reverse=True)
    return sims[:top_k]


def evaluate_on_test_set(similarity_fn, test_set, **kwargs):
    """
    Standard evaluation function (DRY principle).

    Returns: P@10, num_queries evaluated
    """
    relevance_weights = {
        "highly_relevant": 1.0,
        "relevant": 0.75,
        "somewhat_relevant": 0.5,
        "marginally_relevant": 0.25,
        "irrelevant": 0.0,
    }

    scores = []

    for query, labels in test_set.items():
        preds = similarity_fn(query, **kwargs)

        if not preds:
            continue

        score = 0.0
        for card, _ in preds[:10]:
            for level, weight in relevance_weights.items():
                if card in labels.get(level, []):
                    score += weight
                    break

        scores.append(score / 10.0)

    p10 = sum(scores) / len(scores) if scores else 0.0

    return {
        "p10": p10,
        "num_queries": len(scores),
        "scores_distribution": {
            "min": min(scores) if scores else 0,
            "max": max(scores) if scores else 0,
            "mean": p10,
            "std": np.std(scores) if scores else 0,
        },
    }


# Principle: Simplify. This file replaces ~200 lines of duplication across experiments.
