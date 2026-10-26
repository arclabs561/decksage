#!/usr/bin/env python3
"""Build functional-reprint families from Scryfall oracle cards.

Cards with identical normalized oracle text, type line and mana cost are
perfect substitutes by construction. That gives objective substitute labels
with no judge, no human, and no licence question: same effect, same cost, same
card type, different name.

Usage:
    uv run scripts/data/reprint_families.py --game magic
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.utils.paths import PATHS


REMINDER = re.compile(r"\([^()]*\)")
NON_WORD = re.compile(r"[^a-z0-9 ]+")
SKIP_TYPES = ("token", "emblem", "basic land", "card //", "vanguard", "scheme", "plane")


def normalize_text(text: str, name: str) -> str:
    """Normalize oracle text so reprints collide and variants do not.

    The card's own name is replaced with a placeholder, because oracle text
    refers to the card by name and otherwise no two reprints would ever match.
    Reminder text is stripped: it is printing-dependent rules help, not effect.
    """
    lowered = text.lower().replace(name.lower(), "~")
    without_reminders = REMINDER.sub(" ", lowered)
    cleaned = NON_WORD.sub(" ", without_reminders)
    return " ".join(cleaned.split())


def family_key(card: dict) -> tuple[str, str, str, str]:
    text = card.get("oracle_text") or ""
    name = card.get("name") or ""
    return (
        normalize_text(text, name),
        (card.get("type_line") or "").lower().strip(),
        (card.get("mana_cost") or "").lower().strip(),
        f"{card.get('power', '')}/{card.get('toughness', '')}".lower().strip("/"),
    )


def is_eligible(card: dict) -> bool:
    if card.get("object") != "card":
        return False
    if not card.get("oracle_text") or len(card["oracle_text"]) < 15:
        return False
    type_line = (card.get("type_line") or "").lower().strip()
    if not type_line or type_line in {"card", "token", "emblem"}:
        return False
    if any(skip in type_line for skip in SKIP_TYPES):
        return False
    # Cards whose text is only reminder or theme text normalize to nothing and
    # would otherwise collapse into one giant fake family.
    return len(normalize_text(card["oracle_text"], card["name"])) >= 15


def build_families(cards: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for card in cards:
        if is_eligible(card):
            groups[family_key(card)].add(card["name"])

    families = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        text, type_line, mana_cost, stats = key
        families.append(
            {
                "members": sorted(members),
                "size": len(members),
                "type_line": type_line,
                "mana_cost": mana_cost,
                "stats": stats,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
        )
    families.sort(key=lambda f: (-f["size"], f["members"]))
    return families


def main() -> int:
    parser = argparse.ArgumentParser(description="Build functional-reprint families")
    parser.add_argument("--game", default="magic", choices=["magic"])
    parser.add_argument(
        "--cards", default=str(PATHS.data / "raw" / "scryfall" / "oracle-cards.json")
    )
    parser.add_argument(
        "--out", default=str(PATHS.data / "derived" / "reprint_families_magic.json")
    )
    args = parser.parse_args()

    cards_path = Path(args.cards)
    if not cards_path.exists():
        print(f"missing {cards_path}; this script does not download data", file=sys.stderr)
        return 2

    with open(cards_path) as handle:
        payload = json.load(handle)
    cards = payload.get("data", payload) if isinstance(payload, dict) else payload
    families = build_families(cards)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "game": args.game,
                "source": str(cards_path),
                "families": len(families),
                "cards_covered": sum(f["size"] for f in families),
                "records": families,
            },
            indent=1,
        )
    )

    covered = sum(f["size"] for f in families)
    print(f"cards scanned: {len(cards):,}")
    print(f"families: {len(families):,} covering {covered:,} cards")
    if families:
        print(f"largest family: {families[0]['size']} cards, e.g. {families[0]['members'][:4]}")
    print(f"written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
