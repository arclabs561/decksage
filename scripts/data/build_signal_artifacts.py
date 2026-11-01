#!/usr/bin/env python3
"""Materialize tag and reprint lookups for the API, for every game.

The serving layer should not parse Scryfall's 40 MB tag bulk or re-normalize
oracle text per request. This writes compact card->tags and card->reprint-group
JSON under data/processed; the API loads them at startup.

Magic tags come from the curated tag index. Pokemon and Yu-Gi-Oh! have no
curated tag artifact, so their tags are *derived* from structured columns
(subtypes, keywords, race, attribute, archetype). That is weaker evidence and
is labelled as derived, but it makes the tag relation available and honest
rather than absent.

Idempotent: writes the same bytes for the same inputs; safe to rerun in refresh.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))
sys.path.insert(0, str(ROOT / "src"))

from heuristic_scorers import build_tag

from ml.utils.paths import PATHS


CARDS = PATHS.data / "raw" / "scryfall" / "oracle-cards.json"
TAGS = ROOT / "data-local" / "label-anchor-20261030" / "oracle-tags.jsonl.gz"
PROCESSED = PATHS.processed

# Columns that carry real categorical labels, per game.
DERIVED_FIELDS = {
    # "type" repeats supertype+subtypes ("Pokémon Basic"), so it adds tokens
    # without adding information.
    "pokemon": ("supertype", "subtypes", "keywords"),
    "yugioh": ("keywords", "race_enriched", "attribute_enriched", "monster_type", "archetype"),
}


def norm(text: str) -> str:
    text = re.sub(r"\([^)]*\)", "", text or "")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _split(value: str) -> list[str]:
    return [part.strip().lower() for part in (value or "").split(",") if part.strip()]


def derived_tags(game: str) -> dict[str, list[str]]:
    """Build card->tags from structured columns; deterministic, no model."""
    path = PROCESSED / f"card_attributes_{game}_enriched.csv"
    if not path.exists():
        raise SystemExit(f"missing card metadata for {game}: {path}")
    fields = DERIVED_FIELDS[game]
    tags: dict[str, list[str]] = {}
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            name = row.get("name", "")
            if not name:
                continue
            values: set[str] = set()
            for field in fields:
                values |= set(_split(row.get(field, "")))
            values = {value for value in values if 1 < len(value) < 40}
            if values:
                tags[name] = sorted(values)
    return tags


def magic_tags() -> dict[str, list[str]]:
    index = build_tag("magic", TAGS, CARDS)
    return {
        name: sorted(index.tag_sets[position])
        for name, position in index.positions.items()
        if index.tag_sets[position]
    }


def magic_reprints() -> tuple[dict[str, str], int]:
    """Reprints from Scryfall text+type, preserving the existing Magic basis.

    The CSV-derived path would shift group membership slightly; Magic's group
    ids are referenced by the repaired reprint labels, so keep them stable.
    """
    cards = json.loads(CARDS.read_text(encoding="utf-8"))
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
    # Sets iterate in hash order; sort so the file is byte-identical run to run.
    card_group = {name: group for group, names in members.items() for name in sorted(names)}
    multi = sum(1 for names in members.values() if len(names) > 1)
    return card_group, multi


def reprint_groups(game: str) -> tuple[dict[str, str], int]:
    """Same oracle text + type => same card, printed again."""
    path = PROCESSED / f"card_attributes_{game}_enriched.csv"
    if not path.exists():
        raise SystemExit(f"missing card metadata for {game}: {path}")
    groups: dict[str, str] = {}
    members: dict[str, set[str]] = {}
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            name = row.get("name")
            text = norm(row.get("oracle_text") or "")
            if not name or not text or len(text) < 10:
                continue
            key = f"{text}|{norm(row.get('type') or '')}"
            group = groups.setdefault(key, f"g{len(groups)}")
            members.setdefault(group, set()).add(name)
    # Sets iterate in hash order; sort so the file is byte-identical run to run.
    card_group = {name: group for group, names in members.items() for name in sorted(names)}
    multi = sum(1 for names in members.values() if len(names) > 1)
    return card_group, multi


def write_if_changed(path: Path, payload: str) -> bool:
    """Write only when the bytes differ.

    Refresh runs this daily; rewriting identical JSON would bump the mtime and
    make the graph's --if-stale check rebuild three graphs for nothing.
    """
    if path.exists() and path.read_text(encoding="utf-8") == payload:
        return False
    path.write_text(payload, encoding="utf-8")
    return True


def build(game: str, out_dir: Path) -> tuple[int, int, int]:
    tags = magic_tags() if game == "magic" else derived_tags(game)
    changed = write_if_changed(
        out_dir / f"{game}_tags.json", json.dumps(tags, separators=(",", ":"))
    )
    card_group, multi = magic_reprints() if game == "magic" else reprint_groups(game)
    changed |= write_if_changed(
        out_dir / f"{game}_reprints.json", json.dumps(card_group, separators=(",", ":"))
    )
    if not changed:
        print(f"{game}: artifacts unchanged")
    return len(tags), len(card_group), multi


def ensure_artifacts(game: str, out_dir: Path | None = None) -> bool:
    """Build the artifacts only when missing; used by bootstrap and refresh."""
    directory = out_dir or PROCESSED
    tags_path = directory / f"{game}_tags.json"
    groups_path = directory / f"{game}_reprints.json"
    if tags_path.exists() and groups_path.exists():
        return False
    tags, groups, multi = build(game, directory)
    print(f"{game}: tags {tags} cards; {multi} multi-card reprint groups covering {groups} cards")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game", action="append", choices=("magic", "pokemon", "yugioh"), default=None
    )
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=PROCESSED)
    args = parser.parse_args()
    games = ["magic", "pokemon", "yugioh"] if args.all else (args.game or ["magic"])
    for game in games:
        tags, groups, multi = build(game, args.out_dir)
        print(
            f"{game}: tags {tags} cards; {multi} multi-card reprint groups covering {groups} cards"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
