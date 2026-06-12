#!/usr/bin/env python3
"""Evaluate Jaccard on ground truth labels"""

import json
from collections import defaultdict

import pandas as pd


# Load graph
df = pd.read_csv("../backend/pairs_500decks.csv")
adj = defaultdict(set)
for _, row in df.iterrows():
    adj[row["NAME_1"]].add(row["NAME_2"])
    adj[row["NAME_2"]].add(row["NAME_1"])

# Load ground truth
with open("ground_truth_v1.json") as f:
    test_set = json.load(f)

# Evaluate Jaccard


class JaccardModel:
    def __init__(self, adj_list):
        self.adj = adj_list

    def most_similar(self, card, topn=10):
        if card not in self.adj:
            return []

        query_neighbors = self.adj[card]
        similarities = []

        for other in self.adj:
            if other == card:
                continue
            other_neighbors = self.adj[other]
            intersection = len(query_neighbors & other_neighbors)
            union = len(query_neighbors | other_neighbors)
            if union > 0:
                similarities.append((other, intersection / union))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:topn]


# Evaluate manually
jaccard_model = JaccardModel(adj)

# Load test set
relevance_weights = {
    "highly_relevant": 1.0,
    "relevant": 0.75,
    "somewhat_relevant": 0.5,
    "marginally_relevant": 0.25,
    "irrelevant": 0.0,
}

results = {"P@5": [], "P@10": [], "P@20": [], "MRR": []}

for query, ground_truth in test_set.items():
    preds = jaccard_model.most_similar(query, topn=20)

    # P@K
    for k in [5, 10, 20]:
        score = 0.0
        for card, _ in preds[:k]:
            for level, weight in relevance_weights.items():
                if card in ground_truth.get(level, []):
                    score += weight
                    break
        results[f"P@{k}"].append(score / k if k > 0 else 0)

    # MRR
    for rank, (card, _) in enumerate(preds, 1):
        is_relevant = False
        for level in ["highly_relevant", "relevant"]:
            if card in ground_truth.get(level, []):
                is_relevant = True
                break
        if is_relevant:
            results["MRR"].append(1.0 / rank)
            break
    else:
        results["MRR"].append(0.0)

# Average
avg_results = {k: sum(v) / len(v) if v else 0 for k, v in results.items()}

print("Jaccard on Ground Truth:")
for metric, value in avg_results.items():
    print(f"  {metric}: {value:.4f}")
