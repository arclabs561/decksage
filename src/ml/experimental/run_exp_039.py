#!/usr/bin/env python3
"""exp_039: Community Detection for Card Clustering"""

from collections import defaultdict

import pandas as pd
from true_closed_loop import ClosedLoopExperiment


def community_based_similarity(test_set, config):
    """Use community structure to identify card groups"""

    df = pd.read_csv("../../data/processed/pairs_large.csv")

    LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}
    adj = defaultdict(set)

    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]
        if c1 not in LANDS and c2 not in LANDS:
            adj[c1].add(c2)
            adj[c2].add(c1)

    # Simple community detection: connected components
    cards = list(adj.keys())
    visited = set()
    communities = []

    def dfs(node, community):
        if node in visited:
            return
        visited.add(node)
        community.add(node)
        for neighbor in list(adj[node])[:10]:  # Limit depth
            if neighbor not in visited:
                dfs(neighbor, community)

    # Find communities (sample)
    for card in cards[:100]:
        if card not in visited:
            community = set()
            dfs(card, community)
            if len(community) > 3:
                communities.append(community)

    print(f"  Found {len(communities)} communities")

    # Evaluate
    scores = []
    for query, labels in test_set.items():
        if query not in adj:
            continue

        # Find query's community
        query_comm = None
        for comm in communities:
            if query in comm:
                query_comm = comm
                break

        if not query_comm:
            continue

        # Prefer cards in same community
        neighbors = adj[query]
        sims = []

        for other in list(adj.keys())[:2000]:
            if other == query or other in LANDS:
                continue

            # Jaccard
            other_n = adj[other]
            i = len(neighbors & other_n)
            u = len(neighbors | other_n)
            jaccard = i / u if u > 0 else 0

            # Community boost
            same_comm = other in query_comm
            boost = 1.3 if same_comm else 1.0

            sims.append((other, jaccard * boost))

        sims.sort(key=lambda x: x[1], reverse=True)

        score = 0.0
        for card, _ in sims[:10]:
            if card in labels.get("highly_relevant", []):
                score += 1.0
            elif card in labels.get("relevant", []):
                score += 0.75
            elif card in labels.get("somewhat_relevant", []):
                score += 0.5

        scores.append(score / 10.0)

    p10 = sum(scores) / len(scores) if scores else 0.0
    print(f"  P@10: {p10:.4f} on {len(scores)} queries")

    return {"p10": p10, "num_queries": len(scores)}


loop = ClosedLoopExperiment(game="magic")

results = loop.run_with_context(
    community_based_similarity,
    {
        "experiment_id": "exp_039",
        "date": "2025-10-01",
        "game": "magic",
        "phase": "graph_structure",
        "hypothesis": "Community detection identifies card groups",
        "method": "Jaccard + Community boost",
    },
)

print(f"\nResult: P@10 = {results['p10']:.4f}")
print(f"vs Baseline: {results['p10'] - 0.12:+.4f}")
