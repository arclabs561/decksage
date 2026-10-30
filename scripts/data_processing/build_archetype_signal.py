#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Build the archetype signal for similarity from shipped deck lists.

The fusion pipeline has an `archetype` signal (`src/ml/similarity/archetype_signal.py`)
whose inputs were never produced: `src/ml/api/load_signals.py` looks for
`experiments/signals/<game>/archetype_staples.json` and
`archetype_cooccurrence.json`, and neither the artefacts nor a producer existed.

This script writes them from deck-level `archetype` labels that the shipped
corpus already carries (`data/decks/decks_<game>*.jsonl`):

  archetype_staples.json       card -> {archetype: share of that archetype's decks}
                               only cards present in >= staple_threshold of them
  archetype_cooccurrence.json  card -> {other card: share, within archetypes}
                               capped to max_partners per card
  archetype_signal.manifest.json  parameters, source files, sha256 of both outputs

A game whose deck files carry no archetype label gets status `no_source_data`,
no artefacts, and stale artefacts removed, so the API reports it honestly as
missing instead of serving an invented index.

Usage:
  uv run scripts/data_processing/build_archetype_signal.py
  uv run scripts/data_processing/build_archetype_signal.py --games magic,yugioh
  uv run scripts/data_processing/build_archetype_signal.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DECKS_DIR = REPO_ROOT / "data" / "decks"
OUT_ROOT = REPO_ROOT / "experiments" / "signals"

DEFAULT_GAMES = ["magic", "pokemon", "yugioh"]

# Provider buckets, not archetypes. Counting them would invent a pseudo-archetype
# whose "staples" are just the most common cards in the corpus.
PLACEHOLDER_LABELS = frozenset({"unknown", "-", "none", "n/a", "other", "imported deck"})

STAPLES_FILE = "archetype_staples.json"
COOCCURRENCE_FILE = "archetype_cooccurrence.json"
MANIFEST_FILE = "archetype_signal.manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> int:
    """Write canonical JSON (sorted keys, no incidental whitespace); return byte size."""
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text + "\n", encoding="utf-8")
    return len(text) + 1


def _deck_cards(deck: dict) -> set[str]:
    cards = deck.get("cards") or []
    return {c["name"].strip() for c in cards if isinstance(c, dict) and c.get("name")}


def read_archetype_decks(game: str, decks_dir: Path) -> tuple[dict[str, list[set[str]]], dict]:
    """Group the cards of each deck by archetype label, deduplicated by deck_id across files.

    Deck exports overlap (commander vs commander_combined, masterduelmeta vs its
    pickled graph source), so the same deck_id can appear twice. First file in
    sorted order wins; the duplicates are counted and reported.
    """
    files = sorted(decks_dir.glob(f"decks_{game}*.jsonl"))
    by_archetype: defaultdict[str, list[set[str]]] = defaultdict(list)
    seen_ids: set[str] = set()
    stats: dict[str, object] = {
        "files": [],
        "labelled": 0,
        "placeholder": 0,
        "duplicate_deck_ids": 0,
        "unlabelled": 0,
        "without_cards": 0,
    }
    file_stats: list[dict] = []

    for path in files:
        used = 0
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    deck = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(deck, dict):
                    continue

                label = (deck.get("archetype") or "").strip()
                if not label:
                    stats["unlabelled"] += 1
                    continue
                if label.lower() in PLACEHOLDER_LABELS:
                    stats["placeholder"] += 1
                    continue
                stats["labelled"] += 1

                deck_id = deck.get("deck_id")
                if deck_id:
                    if deck_id in seen_ids:
                        stats["duplicate_deck_ids"] += 1
                        continue
                    seen_ids.add(deck_id)

                cards = _deck_cards(deck)
                if not cards:
                    stats["without_cards"] += 1
                    continue
                by_archetype[label].append(cards)
                used += 1

        if used:
            file_stats.append({"file": path.name, "bytes": path.stat().st_size, "decks_used": used})

    stats["files"] = file_stats
    stats["used"] = sum(len(d) for d in by_archetype.values())
    return dict(by_archetype), stats


def compute_signals(
    by_archetype: dict[str, list[set[str]]],
    *,
    min_decks: int,
    staple_threshold: float,
    max_partners: int,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]], dict[str, int]]:
    kept = {label: decks for label, decks in by_archetype.items() if len(decks) >= min_decks}

    staples: dict[str, dict[str, float]] = defaultdict(dict)
    card_decks: Counter[str] = Counter()
    pair_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)

    for label, decks in sorted(kept.items()):
        n_decks = len(decks)
        per_archetype: Counter[str] = Counter()
        for deck in decks:
            per_archetype.update(deck)
        for card, count in per_archetype.items():
            share = count / n_decks
            if share >= staple_threshold:
                staples[card][label] = round(share, 6)
        for deck in decks:
            for card in deck:
                card_decks[card] += 1
                for other in deck:
                    if card != other:
                        pair_counts[card][other] += 1

    cooccurrence: dict[str, dict[str, float]] = {}
    for card, partners in pair_counts.items():
        total = card_decks[card]
        if total < min_decks:
            continue
        scored = {
            other: count / total
            for other, count in partners.items()
            if card_decks[other] >= min_decks
        }
        if not scored:
            continue
        ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))[:max_partners]
        cooccurrence[card] = {other: round(value, 6) for other, value in ranked}

    counts = {
        "archetypes_seen": len(by_archetype),
        "archetypes_kept": len(kept),
        # Decks inside the kept archetypes: the share of labelled decks the
        # signal actually describes. The long tail is dropped, not averaged in.
        "decks_in_kept_archetypes": sum(len(decks) for decks in kept.values()),
    }
    return dict(staples), cooccurrence, counts


def build_game(
    game: str,
    *,
    decks_dir: Path = DECKS_DIR,
    out_root: Path = OUT_ROOT,
    min_decks: int = 20,
    staple_threshold: float = 0.7,
    max_partners: int = 128,
    dry_run: bool = False,
) -> dict:
    """Build one game's artefacts. Returns the manifest (also written to disk)."""
    out_dir = out_root / game
    by_archetype, deck_stats = read_archetype_decks(game, decks_dir)
    manifest: dict = {
        "game": game,
        "generated_by": "scripts/data_processing/build_archetype_signal.py",
        "params": {
            "min_decks": min_decks,
            "staple_threshold": staple_threshold,
            "max_partners": max_partners,
            "excluded_labels": sorted(PLACEHOLDER_LABELS),
            "decks_dir": str(decks_dir.name),
        },
        "decks": deck_stats,
    }

    staples_path = out_dir / STAPLES_FILE
    cooccur_path = out_dir / COOCCURRENCE_FILE

    if not by_archetype:
        manifest["status"] = "no_source_data"
        if not dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
            for stale in (staples_path, cooccur_path):
                stale.unlink(missing_ok=True)
            _write_json(out_dir / MANIFEST_FILE, manifest)
        return manifest

    staples, cooccurrence, counts = compute_signals(
        by_archetype,
        min_decks=min_decks,
        staple_threshold=staple_threshold,
        max_partners=max_partners,
    )
    manifest["status"] = "built" if counts["archetypes_kept"] else "below_min_decks"
    manifest["archetypes"] = counts
    manifest["outputs"] = {
        STAPLES_FILE: {"cards": len(staples)},
        COOCCURRENCE_FILE: {"cards": len(cooccurrence)},
    }

    if dry_run or manifest["status"] != "built":
        return manifest

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in ((STAPLES_FILE, staples), (COOCCURRENCE_FILE, cooccurrence)):
        size = _write_json(out_dir / name, payload)
        manifest["outputs"][name].update({"bytes": size, "sha256": _sha256(out_dir / name)})
    _write_json(out_dir / MANIFEST_FILE, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the archetype similarity signal")
    parser.add_argument("--games", default=",".join(DEFAULT_GAMES))
    parser.add_argument("--min-decks", type=int, default=20, help="minimum decks per archetype")
    parser.add_argument(
        "--staple-threshold", type=float, default=0.7, help="share of an archetype's decks"
    )
    parser.add_argument(
        "--max-partners", type=int, default=128, help="co-occurrence partners per card"
    )
    parser.add_argument("--decks-dir", type=Path, default=DECKS_DIR)
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--dry-run", action="store_true", help="report without writing artefacts")
    args = parser.parse_args()

    games = [g.strip().lower() for g in args.games.split(",") if g.strip()]
    exit_code = 0
    for game in games:
        print(f"\n=== {game} ===")
        manifest = build_game(
            game,
            decks_dir=args.decks_dir,
            out_root=args.out_root,
            min_decks=args.min_decks,
            staple_threshold=args.staple_threshold,
            max_partners=args.max_partners,
            dry_run=args.dry_run,
        )
        decks = manifest["decks"]
        print(
            f"  decks: labelled={decks['labelled']:,} used={decks['used']:,} "
            f"placeholder={decks['placeholder']:,} duplicate_ids={decks['duplicate_deck_ids']:,}"
        )
        if manifest["status"] != "built":
            print(f"  status={manifest['status']}: no artefact written")
            if manifest["status"] == "no_source_data":
                print(f"  {game} has no archetype-labelled decks; the signal stays missing")
            exit_code = max(exit_code, 1)
            continue
        archetypes = manifest["archetypes"]
        print(
            f"  archetypes: seen={archetypes['archetypes_seen']:,} "
            f"kept(>= {args.min_decks} decks)={archetypes['archetypes_kept']:,}"
        )
        for name, info in manifest["outputs"].items():
            print(f"  {name}: {info['cards']:,} cards, {info['bytes'] / 1e6:.1f} MB")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
