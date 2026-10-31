#!/usr/bin/env python3
"""Materialize tag and reprint lookups for the API.

The serving layer should not parse Scryfall's 40 MB tag bulk or re-normalize
oracle text per request. This writes compact card->tags and card->reprint-group
JSON under data/processed; the API loads them at startup.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))

from heuristic_scorers import build_tag


CARDS = ROOT / "data/raw/scryfall/oracle-cards.json"
TAGS = ROOT / "data-local/label-anchor-20261030/oracle-tags.jsonl.gz"


def norm(text: str) -> str:
    text = re.sub(r"\([^)]*\)", "", text or "")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data/processed")
    args = parser.parse_args()
    cards = json.loads(CARDS.read_text(encoding="utf-8"))
    index = build_tag("magic", TAGS, CARDS)
    tags = {
        name: sorted(index.tag_sets[position])
        for name, position in index.positions.items()
        if index.tag_sets[position]
    }
    (args.out_dir / "magic_tags.json").write_text(json.dumps(tags, separators=(",", ":")))

    groups: dict[str, str] = {}
    members: dict[str, set[str]] = {}
    for card in cards:
        name = card.get("name")
        text = norm(card.get("oracle_text") or "")
        if not name or not text or len(text) < 10:
            continue
        key = f"{text}|{norm(card.get('type_line') or '')}"
        group = groups.setdefault(key, f"g{len(groups)}")
        members.setdefault(group, set()).add(name)
    card_group = {name: group for group, names in members.items() for name in names}
    (args.out_dir / "magic_reprints.json").write_text(json.dumps(card_group, separators=(",", ":")))
    print(f"tags {len(tags)} cards; reprint groups {len(members)} covering {len(card_group)} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
