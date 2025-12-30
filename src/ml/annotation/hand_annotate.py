#!/usr/bin/env python3
"""
Hand Annotation Tool for Test Set Expansion

Creates annotation batches for manual hand annotation and grading.
Supports expanding test sets to 100+ queries with proper statistical rigor.

Usage:
    # Generate annotation batch for MTG
    python hand_annotate.py generate --game magic --target 50 --current 38
    
    # Grade completed annotations
    python hand_annotate.py grade --input annotations/hand_batch_001_magic.yaml
    
    # Merge into canonical test set
    python hand_annotate.py merge --input annotations/hand_batch_001_magic.yaml --output experiments/test_set_canonical_magic.json
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:
    from gensim.models import KeyedVectors

    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False

from ..utils.paths import PATHS


class QueryGenerator:
    """Generate diverse query cards for annotation"""

    def __init__(self, pairs_csv: str | Path, embeddings_path: str | Path | None = None):
        self.df = pd.read_csv(pairs_csv)
        self.embeddings = None
        if embeddings_path and HAS_GENSIM:
            try:
                self.embeddings = KeyedVectors.load(str(embeddings_path))
            except Exception:
                pass
        self._build_graph()

    def _build_graph(self):
        """Build adjacency list and degree stats"""
        self.adj = defaultdict(list)
        self.degree = defaultdict(int)
        self.total_weight = defaultdict(float)

        for _, row in self.df.iterrows():
            c1, c2, weight = row["NAME_1"], row["NAME_2"], row.get("COUNT_MULTISET", 1)
            self.adj[c1].append((c2, weight))
            self.adj[c2].append((c1, weight))
            self.degree[c1] += 1
            self.degree[c2] += 1
            self.total_weight[c1] += weight
            self.total_weight[c2] += weight

    def sample_queries(
        self,
        n: int,
        strategy: str = "stratified",
        exclude: set[str] | None = None,
        seed: int = 42,
    ) -> list[str]:
        """
        Sample query cards for annotation.

        Strategies:
        - stratified: Mix of high/medium/low degree cards (best for coverage)
        - random: Uniform random
        - popular: High degree only (well-known cards)
        - diverse: Maximize diversity using embeddings (if available)
        """
        random.seed(seed)
        exclude = exclude or set()
        cards = [c for c in self.degree.keys() if c not in exclude]

        if strategy == "random":
            return random.sample(cards, min(n, len(cards)))

        elif strategy == "popular":
            sorted_cards = sorted(cards, key=lambda c: self.degree[c], reverse=True)
            return sorted_cards[:n]

        elif strategy == "stratified":
            # Divide into high/medium/low degree
            sorted_cards = sorted(cards, key=lambda c: self.degree[c], reverse=True)
            n_third = max(1, n // 3)

            high = random.sample(
                sorted_cards[: len(sorted_cards) // 3], min(n_third, len(sorted_cards) // 3)
            )
            mid = random.sample(
                sorted_cards[len(sorted_cards) // 3 : 2 * len(sorted_cards) // 3],
                min(n_third, len(sorted_cards) // 3),
            )
            low = random.sample(
                sorted_cards[2 * len(sorted_cards) // 3 :],
                min(n - 2 * n_third, len(sorted_cards) // 3),
            )

            return high + mid + low

        elif strategy == "diverse" and self.embeddings:
            # Use embeddings to maximize diversity
            # Start with highest degree card, then iteratively add most diverse
            sorted_cards = sorted(cards, key=lambda c: self.degree[c], reverse=True)
            selected = [sorted_cards[0]]

            for _ in range(min(n - 1, len(sorted_cards) - 1)):
                best_card = None
                best_score = -1

                for candidate in sorted_cards:
                    if candidate in selected:
                        continue

                    # Compute minimum similarity to already selected
                    min_sim = 1.0
                    for sel in selected:
                        try:
                            sim = self.embeddings.similarity(candidate, sel)
                            min_sim = min(min_sim, abs(sim))
                        except KeyError:
                            min_sim = 0.0

                    if min_sim < best_score or best_score == -1:
                        best_score = min_sim
                        best_card = candidate

                if best_card:
                    selected.append(best_card)
                else:
                    break

            return selected

        else:
            raise ValueError(f"Unknown strategy: {strategy}")


class CandidateGenerator:
    """Generate candidate cards for annotation"""

    def __init__(
        self,
        pairs_csv: str | Path,
        embeddings_path: str | Path | None = None,
        graph_adj: dict[str, set[str]] | None = None,
    ):
        self.pairs_csv = pairs_csv
        self.embeddings = None
        if embeddings_path and HAS_GENSIM:
            try:
                self.embeddings = KeyedVectors.load(str(embeddings_path))
            except Exception:
                pass

        # Build graph adjacency if not provided
        if graph_adj:
            self.adj = graph_adj
        else:
            self.adj = self._build_adj_from_csv()

    def _build_adj_from_csv(self) -> dict[str, set[str]]:
        """Build adjacency list from pairs CSV"""
        df = pd.read_csv(self.pairs_csv)
        adj = defaultdict(set)
        for _, row in df.iterrows():
            c1, c2 = row["NAME_1"], row["NAME_2"]
            adj[c1].add(c2)
            adj[c2].add(c1)
        return dict(adj)

    def generate_candidates(self, query: str, k: int = 30) -> list[dict[str, Any]]:
        """
        Generate candidate cards from multiple sources.

        Returns list of candidates with source attribution.
        """
        candidates = {}

        # From embeddings
        if self.embeddings and query in self.embeddings:
            try:
                similar = self.embeddings.most_similar(query, topn=k)
                for card, score in similar:
                    if card not in candidates:
                        candidates[card] = {
                            "card": card,
                            "sources": [],
                            "scores": {},
                        }
                    candidates[card]["sources"].append("embedding")
                    candidates[card]["scores"]["embedding"] = float(score)
            except KeyError:
                pass

        # From graph co-occurrence
        if query in self.adj:
            neighbors = list(self.adj[query])[:k]
            for card in neighbors:
                if card not in candidates:
                    candidates[card] = {
                        "card": card,
                        "sources": [],
                        "scores": {},
                    }
                candidates[card]["sources"].append("cooccurrence")
                candidates[card]["scores"]["cooccurrence"] = 1.0

        # Sort by number of sources and scores
        candidate_list = list(candidates.values())
        candidate_list.sort(
            key=lambda x: (len(x["sources"]), max(x["scores"].values()) if x["scores"] else 0),
            reverse=True,
        )

        return candidate_list[:k]


def create_annotation_batch(
    game: str,
    target_queries: int,
    current_queries: int,
    pairs_csv: str | Path,
    embeddings_path: str | Path | None = None,
    output_path: str | Path | None = None,
    existing_test_set: dict[str, Any] | None = None,
    seed: int = 42,
) -> Path:
    """
    Create annotation batch for hand annotation.

    Args:
        game: 'magic', 'pokemon', or 'yugioh'
        target_queries: Target number of queries (e.g., 50 for MTG)
        current_queries: Current number in test set
        pairs_csv: Path to pairs CSV
        embeddings_path: Optional path to embeddings
        output_path: Output YAML path
        existing_test_set: Existing test set to exclude queries from
        seed: Random seed

    Returns:
        Path to created annotation file
    """
    # Determine how many new queries needed
    n_new = max(0, target_queries - current_queries)

    if n_new == 0:
        print(f"✓ Already have {current_queries} queries, no expansion needed")
        return Path(output_path) if output_path else Path("annotations/hand_batch_empty.yaml")

    # Load existing queries to exclude
    exclude = set()
    if existing_test_set:
        queries = existing_test_set.get("queries", existing_test_set)
        exclude = set(queries.keys())

    # Generate new queries
    print(f"📋 Generating {n_new} new queries for {game}...")
    query_gen = QueryGenerator(pairs_csv, embeddings_path)
    new_queries = query_gen.sample_queries(n_new, strategy="stratified", exclude=exclude, seed=seed)

    # Generate candidates for each query
    print(f"🔍 Generating candidates for {len(new_queries)} queries...")
    cand_gen = CandidateGenerator(pairs_csv, embeddings_path)

    tasks = []
    for query in new_queries:
        candidates = cand_gen.generate_candidates(query, k=30)
        tasks.append(
            {
                "query": query,
                "game": game,
                "candidates": [
                    {
                        "card": c["card"],
                        "sources": c["sources"],
                        "relevance": None,  # To be filled by annotator
                        "notes": "",
                    }
                    for c in candidates
                ],
            }
        )

    # Create output directory
    if output_path:
        output_file = Path(output_path)
    else:
        output_dir = Path("annotations")
        output_dir.mkdir(exist_ok=True)
        batch_num = len(list(output_dir.glob("hand_batch_*.yaml"))) + 1
        output_file = output_dir / f"hand_batch_{batch_num:03d}_{game}.yaml"

    # Write YAML
    with open(output_file, "w") as f:
        yaml.dump(
            {
                "metadata": {
                    "game": game,
                    "batch_id": output_file.stem,
                    "num_queries": len(tasks),
                    "created": pd.Timestamp.now().isoformat(),
                    "target_total": target_queries,
                    "current_total": current_queries,
                },
                "instructions": {
                    "relevance_scale": {
                        4: "Extremely similar (near substitutes, same function)",
                        3: "Very similar (often seen together, similar role)",
                        2: "Somewhat similar (related function or archetype)",
                        1: "Marginally similar (loose connection)",
                        0: "Irrelevant (different function, color, or archetype)",
                    },
                    "grading_guidelines": [
                        "Focus on functional similarity (can they replace each other?)",
                        "Consider archetype context (do they appear in same decks?)",
                        "Consider mana cost and card type",
                        "Add notes for edge cases or interesting patterns",
                    ],
                },
                "tasks": tasks,
            },
            f,
            default_flow_style=False,
            sort_keys=False,
        )

    print(f"✓ Created annotation batch: {output_file}")
    print(f"   Queries: {len(tasks)}")
    print(f"   Total candidates: {sum(len(t['candidates']) for t in tasks)}")
    print(f"\n📝 Next steps:")
    print(f"   1. Open {output_file} in text editor")
    print(f"   2. For each candidate, set relevance (0-4) and add notes")
    print(f"   3. Run: python hand_annotate.py grade --input {output_file}")

    return output_file


def grade_annotations(input_path: str | Path) -> dict[str, Any]:
    """
    Grade and validate completed annotations.

    Returns statistics and validation results.
    """
    input_path = Path(input_path)
    with open(input_path) as f:
        data = yaml.safe_load(f)

    tasks = data.get("tasks", [])
    stats = {
        "total_queries": len(tasks),
        "total_candidates": 0,
        "graded_candidates": 0,
        "ungraded_candidates": 0,
        "relevance_distribution": defaultdict(int),
        "queries_with_notes": 0,
        "validation_errors": [],
    }

    for task in tasks:
        query = task.get("query", "unknown")
        candidates = task.get("candidates", [])
        stats["total_candidates"] += len(candidates)

        query_has_notes = False
        for cand in candidates:
            relevance = cand.get("relevance")
            if relevance is None:
                stats["ungraded_candidates"] += 1
                stats["validation_errors"].append(f"{query}: Candidate '{cand.get('card')}' not graded")
            else:
                stats["graded_candidates"] += 1
                try:
                    rel_int = int(relevance)
                    if rel_int < 0 or rel_int > 4:
                        stats["validation_errors"].append(
                            f"{query}: Invalid relevance {rel_int} (must be 0-4)"
                        )
                    else:
                        stats["relevance_distribution"][rel_int] += 1
                except (ValueError, TypeError):
                    stats["validation_errors"].append(
                        f"{query}: Non-numeric relevance '{relevance}'"
                    )

            if cand.get("notes", "").strip():
                query_has_notes = True

        if query_has_notes:
            stats["queries_with_notes"] += 1

    stats["completion_rate"] = (
        stats["graded_candidates"] / stats["total_candidates"]
        if stats["total_candidates"] > 0
        else 0.0
    )

    return stats


def merge_to_test_set(
    annotation_path: str | Path,
    existing_test_set_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """
    Merge completed annotations into canonical test set.

    Converts YAML annotations to test set JSON format.
    """
    annotation_path = Path(annotation_path)
    existing_test_set_path = Path(existing_test_set_path)

    # Load existing test set
    with open(existing_test_set_path) as f:
        existing = json.load(f)

    # Load annotations
    with open(annotation_path) as f:
        annotations = yaml.safe_load(f)

    # Extract queries from existing (handle both formats)
    existing_queries = existing.get("queries", existing)

    # Convert annotations to test set format
    for task in annotations.get("tasks", []):
        query = task["query"]
        if query in existing_queries:
            print(f"⚠️  Query '{query}' already exists, skipping...")
            continue

        # Build relevance buckets
        buckets = {
            "highly_relevant": [],
            "relevant": [],
            "somewhat_relevant": [],
            "marginally_relevant": [],
            "irrelevant": [],
        }

        for cand in task.get("candidates", []):
            relevance = cand.get("relevance")
            if relevance is None:
                continue

            try:
                rel_int = int(relevance)
                card = cand["card"]

                if rel_int == 4:
                    buckets["highly_relevant"].append(card)
                elif rel_int == 3:
                    buckets["relevant"].append(card)
                elif rel_int == 2:
                    buckets["somewhat_relevant"].append(card)
                elif rel_int == 1:
                    buckets["marginally_relevant"].append(card)
                elif rel_int == 0:
                    buckets["irrelevant"].append(card)
            except (ValueError, TypeError):
                continue

        existing_queries[query] = buckets

    # Update metadata
    if "version" not in existing:
        existing["version"] = "merged"
    if "queries" not in existing:
        existing["queries"] = existing_queries
    else:
        existing["queries"] = existing_queries
    existing["num_queries"] = len(existing_queries)

    # Write output
    if output_path:
        output_file = Path(output_path)
    else:
        output_file = existing_test_set_path

    with open(output_file, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"✓ Merged annotations into: {output_file}")
    print(f"   Total queries: {existing['num_queries']}")

    return output_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Hand annotation tool for test set expansion")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Generate annotation batch
    gen = subparsers.add_parser("generate", help="Generate annotation batch")
    gen.add_argument("--game", choices=["magic", "pokemon", "yugioh"], required=True)
    gen.add_argument("--target", type=int, required=True, help="Target number of queries")
    gen.add_argument("--current", type=int, required=True, help="Current number of queries")
    gen.add_argument("--pairs", type=str, help="Path to pairs CSV (default: from PATHS)")
    gen.add_argument("--embeddings", type=str, help="Path to embeddings file")
    gen.add_argument("--output", type=str, help="Output YAML path")
    gen.add_argument("--test-set", type=str, help="Existing test set to exclude queries from")
    gen.add_argument("--seed", type=int, default=42)

    # Grade annotations
    grade = subparsers.add_parser("grade", help="Grade and validate annotations")
    grade.add_argument("--input", type=str, required=True, help="Annotation YAML file")

    # Merge to test set
    merge = subparsers.add_parser("merge", help="Merge annotations into test set")
    merge.add_argument("--input", type=str, required=True, help="Annotation YAML file")
    merge.add_argument("--test-set", type=str, required=True, help="Existing test set JSON")
    merge.add_argument("--output", type=str, help="Output test set JSON (default: overwrite input)")

    args = parser.parse_args()

    if args.command == "generate":
        # Determine pairs CSV path
        if args.pairs:
            pairs_csv = Path(args.pairs)
        else:
            pairs_csv = PATHS.pairs_large
            if not pairs_csv.exists():
                pairs_csv = PATHS.pairs_500

        if not pairs_csv.exists():
            print(f"❌ Pairs CSV not found: {pairs_csv}")
            return 1

        # Load existing test set if provided
        existing_test_set = None
        if args.test_set:
            with open(args.test_set) as f:
                existing_test_set = json.load(f)

        create_annotation_batch(
            game=args.game,
            target_queries=args.target,
            current_queries=args.current,
            pairs_csv=pairs_csv,
            embeddings_path=args.embeddings,
            output_path=args.output,
            existing_test_set=existing_test_set,
            seed=args.seed,
        )

    elif args.command == "grade":
        stats = grade_annotations(args.input)

        print("\n📊 Annotation Statistics:")
        print(f"   Total queries: {stats['total_queries']}")
        print(f"   Total candidates: {stats['total_candidates']}")
        print(f"   Graded: {stats['graded_candidates']}")
        print(f"   Ungraded: {stats['ungraded_candidates']}")
        print(f"   Completion rate: {stats['completion_rate']:.1%}")

        print("\n📈 Relevance Distribution:")
        for rel in sorted(stats["relevance_distribution"].keys()):
            count = stats["relevance_distribution"][rel]
            print(f"   {rel}: {count} candidates")

        if stats["validation_errors"]:
            print(f"\n⚠️  Validation Errors ({len(stats['validation_errors'])}):")
            for error in stats["validation_errors"][:10]:
                print(f"   - {error}")
            if len(stats["validation_errors"]) > 10:
                print(f"   ... and {len(stats['validation_errors']) - 10} more")

        if stats["ungraded_candidates"] > 0:
            print(f"\n❌ Incomplete: {stats['ungraded_candidates']} candidates still need grading")
            return 1
        elif stats["validation_errors"]:
            print(f"\n⚠️  Has validation errors, but all candidates graded")
            return 1
        else:
            print(f"\n✓ All annotations complete and valid!")
            return 0

    elif args.command == "merge":
        merge_to_test_set(args.input, args.test_set, args.output)

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

