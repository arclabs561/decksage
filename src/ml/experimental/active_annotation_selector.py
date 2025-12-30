#!/usr/bin/env python3
"""
Active Annotation Selector

Self-sustaining annotation system:
1. Models make predictions
2. System identifies uncertain/disagreeing cases
3. Prioritizes what to annotate next
4. Human annotates
5. Feed back into training
6. Loop continues

Principles:
- Annotate where we're uncertain (max info gain)
- Annotate where methods disagree (resolve conflicts)
- Annotate unlabeled predictions from good models (expand coverage)
- Don't waste time on easy cases
"""

import builtins
import contextlib
import json
from collections import defaultdict

import pandas as pd
from gensim.models import KeyedVectors


class ActiveAnnotationSelector:
    """Intelligently selects next annotations based on model uncertainty"""

    def __init__(self, game="magic"):
        self.game = game

        # Load current labels
        with open(f"../../experiments/test_set_canonical_{game}.json") as f:
            data = json.load(f)
            self.labeled_queries = data["queries"]

        # Load experiment log and learn from failures
        self.experiments = []
        self.failed_queries = set()

        with open("../../experiments/EXPERIMENT_LOG.jsonl") as f:
            for line in f:
                if line.strip():
                    try:
                        exp = json.loads(line)
                        self.experiments.append(exp)

                        # Track failures
                        if exp.get("results", {}).get("p10", 1) == 0:
                            # This experiment failed, don't suggest similar
                            method = exp.get("method", "")
                            if "archetype" in method.lower():
                                self.failed_queries.add("archetype_based")
                    except:
                        pass

        print("Loaded:")
        print(f"  Current labels: {len(self.labeled_queries)} queries")
        print(f"  Past experiments: {len(self.experiments)}")
        print(f"  Known failures: {self.failed_queries}")

    def find_model_disagreements(self, models, query, k=10):
        """
        Find where models disagree most.
        High disagreement = uncertain = worth annotating.
        """

        all_preds = {}

        for model_name, model in models.items():
            if query in model:
                preds = model.most_similar(query, topn=k)
                all_preds[model_name] = [card for card, _ in preds]

        if not all_preds:
            return []

        # Cards that appear in some but not all predictions
        all_cards = set()
        for preds in all_preds.values():
            all_cards.update(preds)

        disagreement_scores = []
        for card in all_cards:
            # Count how many models predicted this
            count = sum(1 for preds in all_preds.values() if card in preds)

            # Max disagreement when ~half predict it
            disagreement = count * (len(all_preds) - count)
            disagreement_scores.append((card, disagreement, count))

        # Sort by disagreement
        disagreement_scores.sort(key=lambda x: x[1], reverse=True)

        return disagreement_scores

    def find_unlabeled_from_good_predictions(self, model, labeled_query):
        """
        Model predicts cards not in our labels.
        If model is generally good, these might be relevant but unlabeled.
        """

        if labeled_query not in model:
            return []

        preds = model.most_similar(labeled_query, topn=20)
        labels = self.labeled_queries[labeled_query]

        # All labeled cards
        all_labeled = set()
        for category in [
            "highly_relevant",
            "relevant",
            "somewhat_relevant",
            "marginally_relevant",
            "irrelevant",
        ]:
            all_labeled.update(labels.get(category, []))

        # Find unlabeled predictions
        unlabeled = []
        for rank, (card, score) in enumerate(preds, 1):
            if card not in all_labeled:
                unlabeled.append((card, score, rank))

        return unlabeled

    def suggest_next_annotations(self, max_suggestions=20):
        """
        Prioritize what to annotate next.

        Strategy:
        1. High disagreement cases (models conflict)
        2. Unlabeled predictions from best model
        3. New query cards (expand coverage)
        """

        suggestions = []

        # Load models
        models = {}
        for name in ["node2vec_default", "deepwalk"]:
            with contextlib.suppress(builtins.BaseException):
                models[name] = KeyedVectors.load(f"../../data/embeddings/{name}.wv")

        print(f"\nAnalyzing {len(models)} models...")

        # Strategy 1: Find disagreements on labeled queries
        for query in self.labeled_queries:
            disagreements = self.find_model_disagreements(models, query, k=20)

            for card, disagreement_score, num_votes in disagreements[:5]:
                # Check if already labeled
                labels = self.labeled_queries[query]
                all_labeled = set()
                for cat in labels.values():
                    if isinstance(cat, list):
                        all_labeled.update(cat)

                if card not in all_labeled:
                    suggestions.append(
                        {
                            "type": "disagreement",
                            "priority": disagreement_score,
                            "query": query,
                            "candidate": card,
                            "num_models_voted": num_votes,
                            "total_models": len(models),
                            "reason": f"Models disagree ({num_votes}/{len(models)} voted)",
                        }
                    )

        # Strategy 2: Unlabeled predictions from best model
        if models:
            best_model = next(iter(models.values()))  # Would pick actual best

            for query in self.labeled_queries:
                unlabeled = self.find_unlabeled_from_good_predictions(best_model, query)

                for card, score, rank in unlabeled[:3]:
                    suggestions.append(
                        {
                            "type": "coverage_expansion",
                            "priority": score * 100,  # High score = likely relevant
                            "query": query,
                            "candidate": card,
                            "model_score": score,
                            "rank": rank,
                            "reason": f"Top-{rank} prediction but unlabeled (score: {score:.3f})",
                        }
                    )

        # Strategy 3: Suggest new query cards
        # Cards that appear frequently but aren't queries yet
        # FILTER: Don't suggest lands (learned from exp_005)
        LANDS = {
            "Plains",
            "Island",
            "Swamp",
            "Mountain",
            "Forest",
            "Command Tower",
            "Arid Mesa",
            "Scalding Tarn",
            "Polluted Delta",
            "Verdant Catacombs",
            "Bloodstained Mire",
            "Wooded Foothills",
            "Misty Rainforest",
            "Flooded Strand",
            "Windswept Heath",
            "Marsh Flats",
            "Gemstone Caverns",
            "City of Brass",
            "Mana Confluence",
        }

        df = pd.read_csv("../backend/pairs_large.csv")
        card_freq = defaultdict(int)
        for _, row in df.iterrows():
            card_freq[row["NAME_1"]] += 1
            card_freq[row["NAME_2"]] += 1

        for card, freq in sorted(card_freq.items(), key=lambda x: x[1], reverse=True)[:200]:
            # Skip if land or already a query
            if card in LANDS or card in self.labeled_queries:
                continue

            suggestions.append(
                {
                    "type": "new_query",
                    "priority": freq / 10,  # Lower priority than disagreements
                    "query": card,
                    "candidate": None,
                    "frequency": freq,
                    "reason": f"High frequency ({freq}) non-land card",
                }
            )

        # Sort by priority
        suggestions.sort(key=lambda x: x["priority"], reverse=True)

        return suggestions[:max_suggestions]

    def generate_annotation_batch(
        self, suggestions, output_file="../../annotations/batch_auto_generated.yaml"
    ):
        """Generate YAML annotation batch from suggestions"""
        import yaml

        # Group by query
        by_query = defaultdict(list)
        new_queries = []

        for sug in suggestions:
            if sug["type"] == "new_query":
                new_queries.append(sug["query"])
            else:
                by_query[sug["query"]].append(sug)

        # Create annotation structure
        tasks = []

        # Existing queries with new candidates
        for query, candidates in by_query.items():
            task = {
                "query": query,
                "candidates": [
                    {
                        "card": c["candidate"],
                        "suggested_by": c["type"],
                        "reason": c["reason"],
                        "relevance": None,  # To be filled
                    }
                    for c in candidates
                ],
            }
            tasks.append(task)

        # New queries
        for query in new_queries[:5]:  # Limit new queries
            tasks.append(
                {
                    "query": query,
                    "candidates": [],
                    "note": "New query - need to define ground truth",
                }
            )

        # Save
        with open(output_file, "w") as f:
            yaml.dump(
                {
                    "generated_by": "active_annotation_selector",
                    "generation_method": "model_uncertainty + disagreement + coverage",
                    "tasks": tasks,
                },
                f,
            )

        print(f"\n✓ Generated annotation batch: {output_file}")
        print(f"  Existing queries with new candidates: {len(by_query)}")
        print(f"  New queries: {len(new_queries[:5])}")


def main():
    selector = ActiveAnnotationSelector()

    print(f"\n{'=' * 60}")
    print("Active Annotation Selection")
    print("=" * 60)

    # Get suggestions
    suggestions = selector.suggest_next_annotations(max_suggestions=30)

    # Display
    print("\nTop 15 annotations to do next:")
    print("=" * 60)

    for i, sug in enumerate(suggestions[:15], 1):
        if sug["type"] == "new_query":
            print(f"{i:2d}. NEW QUERY: {sug['query']} (freq: {sug['frequency']})")
        else:
            print(f"{i:2d}. {sug['query']} → {sug['candidate']}")
            print(f"     [{sug['type']}] {sug['reason']}")

    # Generate batch
    selector.generate_annotation_batch(suggestions)

    print(f"\n{'=' * 60}")
    print("Self-Sustaining Cycle:")
    print("=" * 60)
    print("1. Models make predictions")
    print("2. System finds disagreements/unlabeled")
    print("3. Auto-generates annotation batch")
    print("4. Human annotates")
    print("5. Expand test_set_canonical_magic.json")
    print("6. Re-run experiments")
    print("7. Better labels → better models → better suggestions")
    print("\nSystem feeds off itself!")


if __name__ == "__main__":
    main()
