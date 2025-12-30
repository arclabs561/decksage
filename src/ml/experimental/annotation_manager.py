#!/usr/bin/env python3
"""
Annotation Management System

Tracks:
- Multiple annotators
- Inter-annotator agreement
- Annotation quality over time
- Progressive dataset growth
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml


class AnnotationManager:
    """Manage annotation batches and quality"""

    def __init__(self, annotation_dir="../../annotations"):
        self.annotation_dir = Path(annotation_dir)
        self.batches = []
        self.load_all_batches()

    def load_all_batches(self):
        """Load all annotation batches"""
        for yaml_file in self.annotation_dir.glob("batch_*.yaml"):
            with open(yaml_file) as f:
                batch = yaml.safe_load(f)
                self.batches.append(batch)

        print(f"Loaded {len(self.batches)} annotation batches")

    def get_all_annotations(self):
        """Get all annotations across batches"""
        all_annotations = []
        for batch in self.batches:
            all_annotations.extend(batch.get("annotations", []))
        return all_annotations

    def compute_inter_annotator_agreement(self):
        """
        Compute Cohen's kappa or Fleiss' kappa for multi-annotator agreement.

        Requires: Same queries annotated by multiple annotators
        """
        # Group by query
        by_query = defaultdict(list)
        for ann in self.get_all_annotations():
            query = ann["query_card"]
            annotator = ann["annotator"]

            # Get ratings for each candidate
            ratings = {}
            for cand in ann.get("candidates", []):
                ratings[cand["card"]] = cand["relevance"]

            by_query[query].append({"annotator": annotator, "ratings": ratings})

        # Find queries with multiple annotators
        multi_annotated = {q: anns for q, anns in by_query.items() if len(anns) > 1}

        if not multi_annotated:
            return {
                "status": "insufficient_data",
                "message": "Need same queries annotated by multiple annotators",
                "multi_annotated_queries": 0,
            }

        # Compute agreement (simplified - would need proper Cohen's kappa)
        agreements = []
        for query, anns in multi_annotated.items():
            # Get common cards
            all_cards = set()
            for ann in anns:
                all_cards.update(ann["ratings"].keys())

            # For each card, check if annotators agree
            for card in all_cards:
                ratings = [ann["ratings"].get(card) for ann in anns if card in ann["ratings"]]
                if len(ratings) >= 2:
                    # Exact agreement
                    agreements.append(len(set(ratings)) == 1)

        agreement_rate = sum(agreements) / len(agreements) if agreements else 0.0

        return {
            "status": "computed",
            "multi_annotated_queries": len(multi_annotated),
            "agreement_rate": agreement_rate,
            "total_comparisons": len(agreements),
        }

    def export_consolidated_test_set(self, output_file="consolidated_test_set.json"):
        """
        Export consolidated test set, handling multiple annotations.

        Strategy:
        - If single annotator: Use their labels
        - If multiple: Take majority vote or conservative (lower score)
        """
        test_set = {}

        # Group by query
        by_query = defaultdict(list)
        for ann in self.get_all_annotations():
            query = ann["query_card"]
            by_query[query].append(ann)

        for query, anns in by_query.items():
            # Collect all candidates
            candidates_by_card = defaultdict(list)

            for ann in anns:
                for cand in ann.get("candidates", []):
                    card = cand["card"]
                    relevance = cand["relevance"]
                    candidates_by_card[card].append(relevance)

            # Consolidate (take median or mode)
            test_set[query] = {
                "highly_relevant": [],
                "relevant": [],
                "somewhat_relevant": [],
                "marginally_relevant": [],
                "irrelevant": [],
            }

            for card, relevances in candidates_by_card.items():
                # Take conservative (lower) score if disagreement
                consensus = int(np.floor(np.median(relevances)))

                if consensus == 4:
                    test_set[query]["highly_relevant"].append(card)
                elif consensus == 3:
                    test_set[query]["relevant"].append(card)
                elif consensus == 2:
                    test_set[query]["somewhat_relevant"].append(card)
                elif consensus == 1:
                    test_set[query]["marginally_relevant"].append(card)
                else:
                    test_set[query]["irrelevant"].append(card)

        with open(output_file, "w") as f:
            json.dump(test_set, f, indent=2)

        print(f"✓ Consolidated test set: {output_file}")
        print(f"  Queries: {len(test_set)}")
        return test_set

    def quality_report(self):
        """Generate quality report"""
        anns = self.get_all_annotations()

        report = {
            "total_queries": len({a["query_card"] for a in anns}),
            "total_annotations": len(anns),
            "annotators": len({a["annotator"] for a in anns}),
            "avg_candidates_per_query": np.mean([len(a.get("candidates", [])) for a in anns]),
            "date_range": (
                min(a["annotation_date"] for a in anns),
                max(a["annotation_date"] for a in anns),
            ),
            "inter_annotator_agreement": self.compute_inter_annotator_agreement(),
        }

        return report

    def next_queries_to_annotate(self, n=10, strategy="diverse"):
        """
        Suggest next queries to annotate.

        Strategies:
        - 'diverse': Mix of archetypes
        - 'uncertain': Where models disagree most
        - 'popular': High-frequency cards
        """
        # Would implement smart query selection
        # For now, return placeholder
        return {
            "strategy": strategy,
            "suggested_queries": [],
            "reason": "Not yet implemented - need card frequency data",
        }


def main():
    manager = AnnotationManager()

    # Quality report
    print("\n" + "=" * 60)
    print("ANNOTATION QUALITY REPORT")
    print("=" * 60 + "\n")

    report = manager.quality_report()

    print("Dataset Size:")
    print(f"  Total queries: {report['total_queries']}")
    print(f"  Total annotations: {report['total_annotations']}")
    print(f"  Annotators: {report['annotators']}")
    print(f"  Avg candidates/query: {report['avg_candidates_per_query']:.1f}")

    print("\nQuality Metrics:")
    agreement = report["inter_annotator_agreement"]
    print(f"  Multi-annotated queries: {agreement.get('multi_annotated_queries', 0)}")
    if agreement.get("agreement_rate"):
        print(f"  Agreement rate: {agreement['agreement_rate']:.2%}")
    else:
        print(f"  Agreement: {agreement.get('message', 'N/A')}")

    # Export consolidated
    manager.export_consolidated_test_set("../../assets/experiments/test_set_v1.json")

    print("\nNext Steps:")
    print("  1. Add second annotator for inter-annotator agreement")
    print("  2. Annotate 10 more queries (total: 15)")
    print("  3. Re-run evaluation with larger test set")
    print("  4. Track quality metrics over time")


if __name__ == "__main__":
    main()
