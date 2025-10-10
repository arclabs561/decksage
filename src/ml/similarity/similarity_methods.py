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


def load_graph(csv_path="../backend/pairs_large.csv", filter_lands=True):
    """
    Load co-occurrence graph from CSV.

    Returns: adjacency dict, edge weights dict

    Principle: Don't reload graph in every experiment.
    Default path: ../backend/pairs_large.csv (from src/ml/)
    """
    import os

    # Handle different working directories
    if not os.path.exists(csv_path):
        # Try alternative paths
        alternatives = [
            "../../data/processed/pairs_large.csv",
            "../data/processed/pairs_large.csv",
            "data/processed/pairs_large.csv",
            "../backend/pairs_large.csv",
            "../../src/backend/pairs_large.csv",
        ]
        for alt in alternatives:
            if os.path.exists(alt):
                csv_path = alt
                break
        else:
            raise FileNotFoundError(f"Could not find pairs CSV. Tried: {alternatives}")

    df = pd.read_csv(csv_path)

    adj = defaultdict(set)
    weights = {}

    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]

        if filter_lands and (c1 in LANDS or c2 in LANDS):
            continue

        adj[c1].add(c2)
        adj[c2].add(c1)

        weights[(c1, c2)] = row.get("COUNT_MULTISET", 1)
        weights[(c2, c1)] = row.get("COUNT_MULTISET", 1)

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
        types = set([t.strip() for t in type_line.split() if t.strip()])
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
