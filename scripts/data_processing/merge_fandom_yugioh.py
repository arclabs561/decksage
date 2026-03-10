# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas"]
# ///
"""Merge Fandom Wiki scrape data into card_attributes_yugioh_enriched.csv.

Adds columns: name_jp, fandom_categories, fusion_material, synchro_material,
ritual_spell, fandom_statuses, fandom_description.

Usage:
    uv run scripts/data_processing/merge_fandom_yugioh.py \
        --fandom data/processed/yugioh_fandom_cards.json \
        --enriched data/processed/card_attributes_yugioh_enriched.csv
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


def load_fandom_cards(path: str) -> dict[str, dict]:
    """Load Fandom JSON and build a lookup by English name."""
    with open(path) as f:
        raw = json.load(f)

    by_name: dict[str, dict] = {}
    by_passcode: dict[int, dict] = {}

    for entry in raw:
        card = entry.get("card", entry)
        name = card.get("name_en", "").strip()
        if not name:
            continue
        by_name[name] = card
        passcode = card.get("passcode", 0)
        if passcode and passcode > 0:
            by_passcode[passcode] = card

    return by_name, by_passcode


def _extract_field(card: dict, field: str) -> str:
    """Extract a field from a Fandom card dict, serializing lists/dicts."""
    val = card.get(field)
    if val is None:
        return ""
    if isinstance(val, (list, dict)):
        if not val:
            return ""
        return json.dumps(val, ensure_ascii=False)
    return str(val) if val else ""


def merge(enriched_path: str, fandom_path: str, out_path: str | None = None):
    df = pd.read_csv(enriched_path)
    by_name, _ = load_fandom_cards(fandom_path)

    # Build a fandom dataframe indexed by name for fast merge
    fandom_rows = []
    for name, card in by_name.items():
        cats = card.get("categories")
        cats_str = json.dumps(cats, ensure_ascii=False) if cats and any(cats.values()) else ""

        fandom_rows.append(
            {
                "name": name,
                "name_jp": card.get("name_jp", "") or "",
                "fandom_categories": cats_str,
                "fusion_material": _extract_field(card, "fusion_material"),
                "synchro_material": _extract_field(card, "synchro_material"),
                "ritual_spell": card.get("ritual_spell", "") or "",
                "fandom_statuses": _extract_field(card, "statuses"),
                "fandom_description": (card.get("description", "") or "")[:500],
            }
        )

    fandom_df = pd.DataFrame(fandom_rows)

    # Merge on name
    merged = df.merge(fandom_df, on="name", how="left", suffixes=("", "_fandom"))

    # Only backfill description where oracle_text is empty
    has_oracle = (
        merged["oracle_text"].notna()
        & (merged["oracle_text"].astype(str).str.strip() != "")
        & (merged["oracle_text"].astype(str) != "nan")
    )
    merged.loc[has_oracle, "fandom_description"] = ""

    # Fill NaN with empty string for new columns
    new_cols = [
        "name_jp",
        "fandom_categories",
        "fusion_material",
        "synchro_material",
        "ritual_spell",
        "fandom_statuses",
        "fandom_description",
    ]
    for col in new_cols:
        if col in merged.columns:
            merged[col] = merged[col].fillna("")

    out = out_path or enriched_path
    merged.to_csv(out, index=False)

    # Stats
    matched = merged["name_jp"].astype(bool).sum()
    unmatched_local = len(merged) - matched
    fandom_only = len(by_name) - matched
    print(f"Matched: {matched}")
    print(f"Unmatched (local only): {unmatched_local}")
    print(f"Unmatched (Fandom only): {fandom_only}")
    print(f"Total enriched rows: {len(merged)}")
    print(f"New columns: {new_cols}")
    print(f"Wrote: {out}")


def main():
    parser = argparse.ArgumentParser(description="Merge Fandom data into enriched CSV")
    parser.add_argument(
        "--fandom",
        default="data/processed/yugioh_fandom_cards.json",
        help="Path to Fandom scrape JSON",
    )
    parser.add_argument(
        "--enriched",
        default="data/processed/card_attributes_yugioh_enriched.csv",
        help="Path to enriched CSV (will be overwritten)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output path (defaults to overwriting --enriched)",
    )
    args = parser.parse_args()

    if not Path(args.fandom).exists():
        print(f"Fandom file not found: {args.fandom}", file=sys.stderr)
        sys.exit(1)
    if not Path(args.enriched).exists():
        print(f"Enriched CSV not found: {args.enriched}", file=sys.stderr)
        sys.exit(1)

    merge(args.enriched, args.fandom, args.out)


if __name__ == "__main__":
    main()
