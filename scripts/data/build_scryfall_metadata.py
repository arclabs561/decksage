#!/usr/bin/env python3
"""Extract set, legality and price metadata from the Scryfall oracle bulk file.

The API merged legalities and prices but never set or set_name, so `set_name`
was a filterable Meilisearch attribute with no values behind it and no way to
ask "which set is this card from". This writes three flat lookups from one
169 MB read instead of parsing Scryfall per request.

Usage:
    scripts/data/build_scryfall_metadata.py            # skip when fresh
    scripts/data/build_scryfall_metadata.py --force
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ml.utils.paths import PATHS


SOURCE = PATHS.data / "raw" / "scryfall" / "oracle-cards.json"
OUT_DIR = PATHS.processed
LEGALITY = OUT_DIR / "scryfall_legality.json"
PRICES = OUT_DIR / "scryfall_prices.json"
SETS = OUT_DIR / "scryfall_sets.json"


def _is_fresh(target: Path, source: Path) -> bool:
    if not target.exists():
        return False
    return target.stat().st_mtime >= source.stat().st_mtime


def build(force: bool = False) -> dict[str, int]:
    if not SOURCE.exists():
        raise SystemExit(f"missing Scryfall bulk file: {SOURCE}")
    targets = (LEGALITY, PRICES, SETS)
    if not force and all(_is_fresh(path, SOURCE) for path in targets):
        print("scryfall metadata is up to date; pass --force to rebuild")
        return {path.name: 0 for path in targets}

    cards = json.loads(SOURCE.read_text(encoding="utf-8"))
    legality: dict[str, dict[str, str]] = {}
    prices: dict[str, dict[str, str | None]] = {}
    sets: dict[str, dict[str, object]] = {}
    counts: dict[str, int] = {}
    for card in cards:
        name = card.get("name")
        if not name:
            continue
        # Multi-face cards repeat the same name; keep the first record so the
        # lookup stays deterministic across bulk-file reorderings.
        if name in sets:
            continue
        card_legalities = card.get("legalities") or {}
        if card_legalities:
            legality[name] = card_legalities
        card_prices = card.get("prices") or {}
        if card_prices:
            prices[name] = card_prices
        set_code = card.get("set")
        if set_code:
            entry: dict[str, object] = {"set": set_code, "set_name": card.get("set_name") or ""}
            released = card.get("released_at")
            if released:
                entry["released_at"] = released
            sets[name] = entry

    for path, payload in ((LEGALITY, legality), (PRICES, prices), (SETS, sets)):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
        print(f"{path.name}: {len(payload)} cards")
        counts[path.name] = len(payload)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Rebuild even when fresh")
    args = parser.parse_args()
    build(force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
