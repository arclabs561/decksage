#!/usr/bin/env python3
"""
Progressive Annotation System with Temporal Weighting

Key principles:
1. Start small (5 queries), validate, expand (geometric growth)
2. Multiple methods generate candidates (diversity)
3. Temporal weighting: recent > old (exponential decay)
4. Bias detection: flag when all methods agree (groupthink)
5. JSON output only (no text parsing)
6. Track provenance (who/when/how)
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors


class ProgressiveAnnotationEngine:
    """Manages growing annotation dataset with quality controls"""

    def __init__(self, annotation_dir="../../annotations"):
        self.annotation_dir = Path(annotation_dir)
        self.judgments_dir = self.annotation_dir / "llm_judgments"
        self.judgments_dir.mkdir(parents=True, exist_ok=True)

        self.all_judgments = []
        self.load_existing_judgments()

    def load_existing_judgments(self):
        """Load all existing judgment files"""
        for json_file in sorted(self.judgments_dir.glob("judgment_*.json")):
            with open(json_file) as f:
                self.all_judgments.append(json.load(f))

        print(f"Loaded {len(self.all_judgments)} existing judgment batches")

    def add_programmatic_judgment(
        self,
        query: str,
        model_predictions: dict[str, list],  # {method_name: [(card, score)]}
        annotator_id: str = "system",
    ):
        """
        Create structured judgment from model predictions.

        Uses ensemble of methods to reduce bias:
        - If all methods agree → high confidence
        - If methods disagree → flag for human review
        """

        # Collect all unique candidates
        all_candidates = set()
        for preds in model_predictions.values():
            all_candidates.update(card for card, _ in preds[:10])

        # Score each candidate
        evaluations = []

        for card in all_candidates:
            # Get scores from each method
            method_scores = {}
            method_ranks = {}

            for method, preds in model_predictions.items():
                for rank, (pred_card, score) in enumerate(preds, 1):
                    if pred_card == card:
                        method_scores[method] = score
                        method_ranks[method] = rank
                        break

            # Compute consensus
            num_methods_voted = len(method_scores)
            avg_rank = np.mean(list(method_ranks.values())) if method_ranks else 100

            # Heuristic relevance (would be replaced by real labels)
            if num_methods_voted >= 2 and avg_rank <= 3:
                relevance = 4  # High consensus, top-ranked
            elif num_methods_voted >= 2 and avg_rank <= 5:
                relevance = 3
            elif num_methods_voted >= 1 and avg_rank <= 10:
                relevance = 2
            elif num_methods_voted == 1:
                relevance = 1
            else:
                relevance = 0

            # Confidence based on agreement
            confidence = min(1.0, num_methods_voted / len(model_predictions))

            # Bias detection: flag if ALL methods give same rank (groupthink)
            if method_ranks and len(set(method_ranks.values())) == 1:
                bias_flag = "groupthink_possible"
            else:
                bias_flag = None

            evaluations.append(
                {
                    "card": card,
                    "relevance": relevance,
                    "confidence": confidence,
                    "method_votes": list(method_scores.keys()),
                    "avg_rank": avg_rank,
                    "bias_flag": bias_flag,
                }
            )

        # Sort by confidence * relevance
        evaluations.sort(key=lambda x: x["confidence"] * x["relevance"], reverse=True)

        # Create judgment structure
        judgment = {
            "query_card": query,
            "annotator": annotator_id,
            "annotation_type": "programmatic_ensemble",
            "timestamp": datetime.now().isoformat(),
            "evaluations": evaluations,
            "methods_used": list(model_predictions.keys()),
            "bias_checks": {
                "groupthink_candidates": [e["card"] for e in evaluations if e.get("bias_flag")],
                "low_confidence": [e["card"] for e in evaluations if e["confidence"] < 0.5],
            },
        }

        return judgment

    def save_judgment(self, judgment: dict):
        """Save judgment with provenance"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.judgments_dir / f"judgment_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump(judgment, f, indent=2)

        self.all_judgments.append(judgment)
        print(f"💾 Saved: {filename}")
        return filename

    def compute_temporal_weights(self, decay_days=30.0):
        """
        Compute temporal weights for all judgments.

        w(t) = exp(-days_old / decay_days)

        Recent judgments get weight ~1.0
        Month-old judgments get weight ~0.37
        """
        now = datetime.now()
        weights = []

        for judgment in self.all_judgments:
            timestamp = datetime.fromisoformat(judgment["timestamp"])
            days_old = (now - timestamp).total_seconds() / 86400
            weight = np.exp(-days_old / decay_days)
            weights.append(weight)

        return weights

    def export_weighted_test_set(
        self, output_file="../../assets/experiments/test_set_weighted.json"
    ):
        """
        Export test set with temporal weighting.

        Aggregates all judgments, applying temporal decay.
        """
        # Group by query
        by_query = defaultdict(list)

        for judgment in self.all_judgments:
            query = judgment["query_card"]
            by_query[query].append(judgment)

        # Aggregate with temporal weighting
        test_set = {}
        now = datetime.now()

        for query, judgments in by_query.items():
            # Collect weighted votes
            card_votes = defaultdict(list)

            for judgment in judgments:
                # Temporal weight
                timestamp = datetime.fromisoformat(judgment["timestamp"])
                days_old = (now - timestamp).total_seconds() / 86400
                temporal_weight = np.exp(-days_old / 30.0)

                for eval_item in judgment.get("evaluations", []):
                    card = eval_item["card"]
                    relevance = eval_item["relevance"]
                    confidence = eval_item.get("confidence", 1.0)

                    weight = temporal_weight * confidence
                    card_votes[card].append((relevance, weight))

            # Compute weighted average relevance for each card
            test_set[query] = {
                "highly_relevant": [],
                "relevant": [],
                "somewhat_relevant": [],
                "marginally_relevant": [],
                "irrelevant": [],
            }

            for card, votes in card_votes.items():
                # Weighted average
                total_weight = sum(w for _, w in votes)
                if total_weight > 0:
                    avg_relevance = sum(r * w for r, w in votes) / total_weight
                else:
                    avg_relevance = 0

                # Bin into category
                if avg_relevance >= 3.5:
                    test_set[query]["highly_relevant"].append(card)
                elif avg_relevance >= 2.5:
                    test_set[query]["relevant"].append(card)
                elif avg_relevance >= 1.5:
                    test_set[query]["somewhat_relevant"].append(card)
                elif avg_relevance >= 0.5:
                    test_set[query]["marginally_relevant"].append(card)
                else:
                    test_set[query]["irrelevant"].append(card)

        with open(output_file, "w") as f:
            json.dump(test_set, f, indent=2)

        print(f"✓ Exported weighted test set: {output_file}")
        print(f"  Queries: {len(test_set)}")
        print("  Temporal weighting applied (30-day decay)")

        return test_set

    def quality_dashboard(self):
        """Generate quality metrics"""
        weights = self.compute_temporal_weights()

        return {
            "total_judgments": len(self.all_judgments),
            "unique_queries": len({j["query_card"] for j in self.all_judgments}),
            "temporal_weights": {
                "min": min(weights) if weights else 0,
                "max": max(weights) if weights else 0,
                "mean": np.mean(weights) if weights else 0,
            },
            "bias_flags": sum(
                len(j.get("bias_checks", {}).get("groupthink_candidates", []))
                for j in self.all_judgments
            ),
        }


if __name__ == "__main__":
    engine = ProgressiveAnnotationEngine()

    # Example: Add judgment from model predictions
    from gensim.models import KeyedVectors

    wv = KeyedVectors.load("../../data/embeddings/magic_500decks_pecanpy.wv")

    # Get predictions from multiple methods
    query = "Lightning Bolt"

    model_predictions = {
        "node2vec": wv.most_similar(query, topn=10) if query in wv else [],
    }

    # Create structured judgment
    judgment = engine.add_programmatic_judgment(query, model_predictions)
    engine.save_judgment(judgment)

    # Export
    engine.export_weighted_test_set()

    # Quality report
    metrics = engine.quality_dashboard()
    print("\nQuality Metrics:")
    print(json.dumps(metrics, indent=2))
