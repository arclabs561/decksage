#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Improve canonical test set by adding labels from unified test set.

Merges labels from unified test set (940 queries, 94.98% quality) into
canonical test set (38 queries) to improve quality.
"""

import json
import sys
from pathlib import Path
from typing import Any


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def improve_test_set(
    canonical_path: Path,
    unified_path: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Improve canonical test set using unified test set."""
    # Load both test sets
    with open(canonical_path) as f:
        canonical_data = json.load(f)

    with open(unified_path) as f:
        unified_data = json.load(f)

    canonical_queries = canonical_data.get("queries", canonical_data)
    unified_queries = unified_data.get("queries", unified_data)

    if not isinstance(canonical_queries, dict) or not isinstance(unified_queries, dict):
        return {
            "success": False,
            "error": "Invalid test set format",
        }

    improvements = []
    stats = {
        "total_queries": len(canonical_queries),
        "queries_improved": 0,
        "labels_added": 0,
        "queries_with_few_labels_before": 0,
        "queries_with_few_labels_after": 0,
    }

    # Count queries with few labels before
    for query, labels in canonical_queries.items():
        if isinstance(labels, dict):
            total_labels = sum(
                len(labels.get(level, []))
                for level in [
                    "highly_relevant",
                    "relevant",
                    "somewhat_relevant",
                    "marginally_relevant",
                ]
            )
            if total_labels < 3:
                stats["queries_with_few_labels_before"] += 1

    # Improve each query
    for query, canonical_labels in canonical_queries.items():
        if query not in unified_queries:
            continue

        unified_labels = unified_queries[query]
        if not isinstance(canonical_labels, dict) or not isinstance(unified_labels, dict):
            continue

        # Count labels before
        total_before = sum(
            len(canonical_labels.get(level, []))
            for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]
        )

        # Merge labels (unified takes precedence for missing levels, canonical keeps existing)
        improved_labels = canonical_labels.copy()
        labels_added = 0

        for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
            canonical_list = set(canonical_labels.get(level, []))
            unified_list = set(unified_labels.get(level, []))

            # Add unified labels that aren't in canonical
            new_labels = unified_list - canonical_list
            if new_labels:
                improved_labels[level] = list(canonical_list | unified_list)
                labels_added += len(new_labels)

        # Count labels after
        total_after = sum(
            len(improved_labels.get(level, []))
            for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]
        )

        if labels_added > 0:
            improvements.append(
                {
                    "query": query,
                    "labels_before": total_before,
                    "labels_after": total_after,
                    "labels_added": labels_added,
                }
            )
            canonical_queries[query] = improved_labels
            stats["queries_improved"] += 1
            stats["labels_added"] += labels_added

    # Count queries with few labels after
    for query, labels in canonical_queries.items():
        if isinstance(labels, dict):
            total_labels = sum(
                len(labels.get(level, []))
                for level in [
                    "highly_relevant",
                    "relevant",
                    "somewhat_relevant",
                    "marginally_relevant",
                ]
            )
            if total_labels < 3:
                stats["queries_with_few_labels_after"] += 1

    # Create improved test set
    improved_data = {
        "version": canonical_data.get("version", "improved"),
        "description": canonical_data.get("description", "") + " (improved with unified labels)",
        "queries": canonical_queries,
    }

    # Save if output path provided
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(improved_data, f, indent=2)

    return {
        "success": True,
        "stats": stats,
        "improvements": improvements,
        "output_path": str(output_path) if output_path else None,
    }


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Improve canonical test set")
    parser.add_argument(
        "--canonical",
        type=Path,
        default=Path("experiments/test_set_canonical_magic.json"),
        help="Canonical test set JSON",
    )
    parser.add_argument(
        "--unified",
        type=Path,
        default=Path("experiments/test_set_unified_magic.json"),
        help="Unified test set JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/test_set_canonical_magic_improved.json"),
        help="Output improved test set",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Backup original canonical test set",
    )

    args = parser.parse_args()

    if not args.canonical.exists():
        print(f"Error: Canonical test set not found: {args.canonical}")
        return 1

    if not args.unified.exists():
        print(f"Error: Unified test set not found: {args.unified}")
        return 1

    print("Improving canonical test set...")
    print(f"  Canonical: {args.canonical}")
    print(f"  Unified: {args.unified}")
    print(f"  Output: {args.output}")
    print()

    # Backup if requested
    if args.backup:
        backup_path = args.canonical.parent / f"{args.canonical.stem}_backup.json"
        import shutil

        shutil.copy2(args.canonical, backup_path)
        print(f"Backed up original to: {backup_path}")
        print()

    result = improve_test_set(args.canonical, args.unified, args.output)

    if not result["success"]:
        print(f"Error: {result.get('error', 'Unknown error')}")
        return 1

    stats = result["stats"]
    print("Improvement Summary")
    print("=" * 70)
    print(f"Total queries: {stats['total_queries']}")
    print(f"Queries improved: {stats['queries_improved']}")
    print(f"Labels added: {stats['labels_added']}")
    print(f"Queries with <3 labels before: {stats['queries_with_few_labels_before']}")
    print(f"Queries with <3 labels after: {stats['queries_with_few_labels_after']}")
    print()

    if result["improvements"]:
        print("Top improvements:")
        for imp in sorted(result["improvements"], key=lambda x: x["labels_added"], reverse=True)[
            :10
        ]:
            print(
                f"  {imp['query']}: {imp['labels_before']} → {imp['labels_after']} labels (+{imp['labels_added']})"
            )

    if args.output:
        print(f"\nImproved test set saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
