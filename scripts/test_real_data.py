#!/usr/bin/env python3
"""Helper script to load real data manually; not a pytest unit test."""

if __name__ == "__main__":
    from pathlib import Path
    # Support both repo and installed layouts
    try:
        from src.ml.validators.loader import load_decks_lenient
    except ModuleNotFoundError:
        from ml.validators.loader import load_decks_lenient

    decks = load_decks_lenient(
        Path("src/backend/decks_hetero.jsonl"),
        game="auto",
        max_decks=1000,
        check_legality=False,
        verbose=True,
    )

    print(f"\nLoaded {len(decks)} decks")
    print(f"   Game types: {set(type(d).__name__ for d in decks)}")
    print(f"   Formats: {len(set(d.format for d in decks))} unique")
    print(f"   Sample formats: {list(set(d.format for d in decks))[:10]}")
