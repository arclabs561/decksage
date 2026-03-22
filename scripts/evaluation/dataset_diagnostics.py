#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Dataset diagnostics: transparency metrics for data, annotations, and graphs.

Run before training to catch issues like:
- Duplicate edge types (deck == enriched)
- Edge type imbalance (Commander 40M vs enriched 1.5M)
- Missing metadata coverage
- Annotation quality distribution
- Prompt variant divergence
- Deck duplication rate

Usage:
    uv run scripts/evaluation/dataset_diagnostics.py --game magic
    uv run scripts/evaluation/dataset_diagnostics.py --all-games
    uv run scripts/evaluation/dataset_diagnostics.py --all-games --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def diagnose_edges(game: str) -> dict:
    """Analyze edge types for balance, duplication, and coverage."""
    graph_dir = DATA_DIR / "graphs"
    edge_files = {
        "deck": graph_dir / f"{game}_merged_all.edg",
        "enriched": graph_dir / f"{game}_merged_enriched.edg",
        "set": graph_dir / f"{game}_set_cooccurrence.edg",
        "precon": graph_dir / f"{game}_precon_cooccurrence.edg",
        "keyword": graph_dir / f"{game}_keyword_sharing.edg",
        "archetype": graph_dir / f"{game}_archetype_cooccurrence.edg",
        "commander": graph_dir / f"{game}_archidekt_commander.edg",
    }

    results = {"edge_types": {}, "warnings": []}
    all_cards: set[str] = set()
    edge_sets: dict[str, set[tuple[str, str]]] = {}

    for etype, path in edge_files.items():
        if not path.exists():
            continue
        edges = set()
        cards = set()
        with open(path) as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    pair = (min(parts[0], parts[1]), max(parts[0], parts[1]))
                    edges.add(pair)
                    cards.update(parts[:2])

        edge_sets[etype] = edges
        all_cards.update(cards)
        results["edge_types"][etype] = {
            "edges": len(edges),
            "cards": len(cards),
            "file": str(path),
        }

    results["total_cards"] = len(all_cards)

    # Check for duplicate edge types (Jaccard similarity > 0.95)
    etypes = list(edge_sets.keys())
    for i in range(len(etypes)):
        for j in range(i + 1, len(etypes)):
            a, b = etypes[i], etypes[j]
            overlap = len(edge_sets[a] & edge_sets[b])
            union = len(edge_sets[a] | edge_sets[b])
            if union > 0:
                jaccard = overlap / union
                if jaccard > 0.95:
                    results["warnings"].append(
                        f"DUPLICATE: {a} and {b} are {jaccard:.1%} identical ({overlap}/{union} edges)"
                    )
                elif jaccard > 0.80:
                    results["warnings"].append(
                        f"HIGH OVERLAP: {a} and {b} share {jaccard:.1%} of edges"
                    )

    # Check for edge type imbalance
    if len(results["edge_types"]) >= 2:
        sizes = [(k, v["edges"]) for k, v in results["edge_types"].items()]
        sizes.sort(key=lambda x: -x[1])
        largest_name, largest_count = sizes[0]
        smallest_name, smallest_count = sizes[-1]
        if largest_count > 10 * smallest_count and smallest_count > 0:
            ratio = largest_count / smallest_count
            results["warnings"].append(
                f"IMBALANCE: {largest_name} ({largest_count:,}) is {ratio:.0f}x larger than "
                f"{smallest_name} ({smallest_count:,}). MetaPath2Vec walks will be dominated by {largest_name}."
            )

    # Check MetaPath2Vec viability
    distinct_types = len([k for k, v in results["edge_types"].items() if v["edges"] > 0])
    if distinct_types < 2:
        results["warnings"].append(
            f"METAPATH2VEC NOT VIABLE: only {distinct_types} edge type(s). Need >= 2 distinct types."
        )

    return results


def diagnose_annotations(game: str) -> dict:
    """Analyze annotation quality and coverage."""
    results = {"warnings": []}

    # Test set
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if test_path.exists():
        with open(test_path) as f:
            data = json.load(f)
        queries = data.get("queries", {})
        n_with_ann = sum(1 for q in queries.values() if q.get("annotations"))
        results["test_set"] = {
            "queries": len(queries),
            "with_annotations": n_with_ann,
            "bucket_only": len(queries) - n_with_ann,
        }

    # Card annotations
    ann_path = DATA_DIR / "test_sets" / f"card_annotations_{game}.json"
    if ann_path.exists():
        with open(ann_path) as f:
            data = json.load(f)
        cards = data.get("cards", {})
        errored = sum(1 for c in cards.values() if "error" in c)
        results["card_annotations"] = {
            "total": len(cards),
            "errored": errored,
            "success": len(cards) - errored,
        }

    # Diverse IAA
    ckpt_path = DATA_DIR / "annotations" / f"diverse_checkpoint_{game}.jsonl"
    if ckpt_path.exists():
        model_counts: dict[str, int] = defaultdict(int)
        variant_counts: dict[str, int] = defaultdict(int)
        scores = []
        pairs = set()
        with open(ckpt_path) as f:
            for line in f:
                if not line.strip():
                    continue
                ann = json.loads(line)
                model_counts[ann.get("llm_model", "unknown")] += 1
                variant_counts[ann.get("prompt_variant", "default")] += 1
                score = ann.get("similarity_score")
                if score is not None:
                    scores.append(float(score))
                pairs.add((ann.get("query", ""), ann.get("candidate", "")))

        results["diverse_iaa"] = {
            "total_judgments": sum(model_counts.values()),
            "unique_pairs": len(pairs),
            "models": dict(model_counts),
            "variants": dict(variant_counts),
            "score_mean": float(np.mean(scores)) if scores else 0,
            "score_std": float(np.std(scores)) if scores else 0,
            "annotators_per_pair": round(sum(model_counts.values()) / max(len(pairs), 1), 1),
        }

        # Check variant divergence
        variant_means: dict[str, float] = {}
        variant_scores: dict[str, list] = defaultdict(list)
        with open(ckpt_path) as f:
            for line in f:
                if not line.strip():
                    continue
                ann = json.loads(line)
                v = ann.get("prompt_variant", "default")
                s = ann.get("similarity_score")
                if s is not None:
                    variant_scores[v].append(float(s))
        for v, ss in variant_scores.items():
            variant_means[v] = float(np.mean(ss))

        if len(variant_means) > 1:
            values = list(variant_means.values())
            spread = max(values) - min(values)
            if spread < 0.02:
                results["warnings"].append(
                    f"LOW VARIANT DIVERGENCE: prompt variants differ by only {spread:.3f} "
                    f"in mean score. Variants add IAA coverage but not different perspectives."
                )
            results["diverse_iaa"]["variant_means"] = variant_means

    return results


def diagnose_metadata(game: str) -> dict:
    """Check card metadata coverage."""
    import pandas as pd

    results = {"warnings": []}
    csv_path = DATA_DIR / "processed" / f"card_attributes_{game}_enriched.csv"
    if not csv_path.exists() and game == "magic":
        csv_path = DATA_DIR / "processed" / "card_attributes_enriched.csv"
    if not csv_path.exists():
        return {"error": "no card attributes CSV"}

    df = pd.read_csv(csv_path, low_memory=False)
    total = len(df)
    coverage = {}
    for col in ["name", "oracle_text", "type", "type_line", "mana_cost", "colors", "rarity", "image_url"]:
        if col in df.columns:
            filled = (df[col].notna() & (df[col].astype(str) != "") & (df[col].astype(str) != "nan")).sum()
            coverage[col] = {"filled": int(filled), "total": total, "pct": round(filled / total * 100)}
            if filled / total < 0.5:
                results["warnings"].append(f"LOW COVERAGE: {col} only {filled/total:.0%} filled")

    results["total_cards"] = total
    results["coverage"] = coverage
    return results


def diagnose_decks(game: str) -> dict:
    """Check deck data quality."""
    results = {"warnings": []}
    deck_dir = DATA_DIR / "decks"
    total_decks = 0
    sources: dict[str, int] = {}

    for f in sorted(deck_dir.glob(f"decks_{game}_*.jsonl")):
        count = sum(1 for _ in open(f))
        source = f.stem.replace(f"decks_{game}_", "")
        sources[source] = count
        total_decks += count

    results["total_decks"] = total_decks
    results["sources"] = sources
    return results


def run_diagnostics(game: str, as_json: bool = False) -> dict:
    """Run all diagnostics for one game."""
    results = {
        "game": game,
        "edges": diagnose_edges(game),
        "annotations": diagnose_annotations(game),
        "decks": diagnose_decks(game),
    }

    # Only load pandas for metadata check
    try:
        results["metadata"] = diagnose_metadata(game)
    except Exception as e:
        results["metadata"] = {"error": str(e)}

    # Collect all warnings
    all_warnings = []
    for section in ["edges", "annotations", "metadata", "decks"]:
        all_warnings.extend(results.get(section, {}).get("warnings", []))
    results["warnings"] = all_warnings

    if not as_json:
        print(f"\n{'=' * 60}")
        print(f"DATASET DIAGNOSTICS: {game.upper()}")
        print(f"{'=' * 60}")

        # Edges
        print(f"\n--- Edge Types ---")
        for etype, info in results["edges"].get("edge_types", {}).items():
            print(f"  {etype:15s}: {info['edges']:>12,} edges, {info['cards']:>6,} cards")
        print(f"  {'TOTAL':15s}: {results['edges'].get('total_cards', 0):>12,} unique cards")

        # Annotations
        ann = results.get("annotations", {})
        if "test_set" in ann:
            ts = ann["test_set"]
            print(f"\n--- Test Set ---")
            print(f"  Queries: {ts['queries']}, with annotations: {ts['with_annotations']}")
        if "card_annotations" in ann:
            ca = ann["card_annotations"]
            print(f"\n--- Card Annotations ---")
            print(f"  Total: {ca['total']}, success: {ca['success']}, errored: {ca['errored']}")
        if "diverse_iaa" in ann:
            iaa = ann["diverse_iaa"]
            print(f"\n--- Diverse IAA ---")
            print(f"  Judgments: {iaa['total_judgments']:,}, pairs: {iaa['unique_pairs']:,}")
            print(f"  Annotators/pair: {iaa['annotators_per_pair']}")
            print(f"  Score: mean={iaa['score_mean']:.3f}, std={iaa['score_std']:.3f}")
            if "variant_means" in iaa:
                for v, m in iaa["variant_means"].items():
                    print(f"    {v}: mean={m:.3f}")

        # Metadata
        meta = results.get("metadata", {})
        if "coverage" in meta:
            print(f"\n--- Metadata Coverage ({meta.get('total_cards', 0):,} cards) ---")
            for col, info in meta["coverage"].items():
                print(f"  {col:15s}: {info['pct']:3d}%")

        # Decks
        decks = results.get("decks", {})
        if "sources" in decks:
            print(f"\n--- Deck Sources ({decks['total_decks']:,} total) ---")
            for src, count in sorted(decks["sources"].items(), key=lambda x: -x[1]):
                print(f"  {src:30s}: {count:>8,}")

        # Warnings
        if all_warnings:
            print(f"\n--- WARNINGS ({len(all_warnings)}) ---")
            for w in all_warnings:
                print(f"  [!] {w}")
        else:
            print(f"\n  No warnings.")

    return results


def main():
    parser = argparse.ArgumentParser(description="Dataset diagnostics")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    all_results = {}
    for game in games:
        r = run_diagnostics(game, as_json=args.json)
        all_results[game] = r

    if args.json:
        print(json.dumps(all_results, indent=2, default=str))


if __name__ == "__main__":
    sys.exit(main() or 0)
