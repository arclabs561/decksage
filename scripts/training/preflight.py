"""Pre-flight diagnostics for training scripts.

Import and call `preflight_check(game, edge_types)` before training.
Prints warnings and returns True if safe to proceed, False if critical issues found.

Usage in training scripts:
    from preflight import preflight_check
    if not preflight_check(args.game, edge_types):
        print("Pre-flight check failed. Use --skip-preflight to override.")
        return 1
"""

from __future__ import annotations

from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def preflight_check(
    game: str,
    edge_types: dict[str, list] | None = None,
    skip: bool = False,
) -> bool:
    """Run pre-flight diagnostics. Returns True if safe to proceed."""
    if skip:
        return True

    warnings = []
    critical = []

    print(f"\n  [preflight] Checking {game}...")

    # 1. Check edge type duplication
    if edge_types and len(edge_types) >= 2:
        type_names = list(edge_types.keys())
        type_sizes = {k: len(v) for k, v in edge_types.items()}

        # Check for duplicate edge sets
        for i in range(len(type_names)):
            for j in range(i + 1, len(type_names)):
                a, b = type_names[i], type_names[j]
                sa, sb = (
                    {(e[0], e[1]) for e in edge_types[a]},
                    {(e[0], e[1]) for e in edge_types[b]},
                )
                if len(sa) > 0 and len(sb) > 0:
                    overlap = len(sa & sb) / len(sa | sb)
                    if overlap > 0.95:
                        critical.append(
                            f"DUPLICATE EDGES: {a} and {b} are {overlap:.0%} identical. "
                            f"MetaPath2Vec will degenerate to Node2Vec."
                        )

        # Check for imbalance
        if type_sizes:
            largest = max(type_sizes.values())
            smallest = min(v for v in type_sizes.values() if v > 0)
            if largest > 50 * smallest:
                largest_name = max(type_sizes, key=type_sizes.get)
                smallest_name = min((k for k, v in type_sizes.items() if v > 0), key=type_sizes.get)
                warnings.append(
                    f"EDGE IMBALANCE: {largest_name} ({largest:,}) is {largest // smallest}x "
                    f"larger than {smallest_name} ({smallest:,}). Walks will be dominated."
                )

    # 2. Check minimum edge types
    if edge_types and len(edge_types) < 2:
        critical.append(
            f"INSUFFICIENT EDGE TYPES: {len(edge_types)} type(s). "
            f"MetaPath2Vec needs >= 2 distinct edge types."
        )

    # 3. Check test set exists for evaluation
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not test_path.exists():
        warnings.append(f"NO TEST SET: {test_path} not found. Cannot evaluate.")

    # Print results
    for w in critical:
        print(f"  [preflight] CRITICAL: {w}")
    for w in warnings:
        print(f"  [preflight] WARNING: {w}")

    if not critical and not warnings:
        print("  [preflight] OK -- no issues found")

    if critical:
        print(
            f"\n  [preflight] {len(critical)} critical issue(s). Training will likely produce degenerate results."
        )
        return False

    return True
